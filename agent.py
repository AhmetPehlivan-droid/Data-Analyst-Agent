import os
import time
from typing import Dict, Any, List
from dotenv import load_dotenv
from database import get_database_schema, run_sql_query
from validator import validate_and_format_sql
from groq import Groq, RateLimitError, InternalServerError
from database import get_database_schema, get_table_schemas_dict, run_sql_query
from pruner import SchemaPruner

load_dotenv()

class SQLAnalystAgent:
    def __init__(self, model_name: str = "openai/gpt-oss-120b", max_retries: int = 3):
        self.table_schemas_dict = get_table_schemas_dict()
        self.pruner = SchemaPruner(self.table_schemas_dict)
        self.top_k_tables = 7  # DVD rental için 4-5 tablo yeterlidir
        self.model_name = model_name
        self.max_retries = max_retries
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found! Please check your .env configuration.")
        
        self.client = Groq(api_key=api_key)
        self.schema = get_database_schema()

    def _call_llm(self, prompt: str, retry_count: int = 3) -> str:
        """
        Executes model inference via Groq API.
        Handles transient rate limits and internal server glitches with retry.
        """
        for attempt in range(retry_count):
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=self.model_name,
                    temperature=0.0,  # Deterministic output for SQL precision
                )
                content = chat_completion.choices[0].message.content
                if content:
                    return content.strip()
                raise ValueError("Model returned an empty response.")

            except RateLimitError:
                wait_time = 5 * (attempt + 1)
                print(f"[Rate Limit] Cooldown: waiting {wait_time}s...")
                time.sleep(wait_time)

            except InternalServerError:
                wait_time = 2 * (attempt + 1)
                print(f"[Groq Server Busy] Retrying in {wait_time}s...")
                time.sleep(wait_time)

            except Exception as e:
                if attempt == retry_count - 1:
                    raise e
                time.sleep(1)

    def _generate_sql_prompt(self, user_query: str) -> str:
        return f"""You are an expert PostgreSQL database analyst.
Generate a valid, optimized PostgreSQL SELECT query corresponding to the user question.

DATABASE SCHEMA:
{self.schema}

RULES:
1. Return ONLY the raw executable SQL query.
2. DO NOT include markdown tags (```sql or ```), quotes, or explanation.
3. Use ONLY table and column names explicitly defined in the schema.
4. Only SELECT queries are permitted.

User Question: {user_query}
SQL:"""

    def _generate_correction_prompt(self, user_query: str, failed_sql: str, error_message: str) -> str:
        return f"""The previous PostgreSQL query failed execution or AST validation. Analyze the error and correct the SQL.

DATABASE SCHEMA:
{self.schema}

USER QUESTION: {user_query}
FAILED SQL: {failed_sql}
ERROR ENCOUNTERED: {error_message}

RULES:
1. Return ONLY the raw corrected PostgreSQL query.
2. DO NOT include markdown tags, comments, or explanations.
3. Fix table/column mismatches based on the provided schema.

Corrected SQL:"""

    def _generate_summary_prompt(self, user_query: str, sql: str, data: List[Dict[str, Any]]) -> str:
        return f"""Review the user's question and the raw PostgreSQL query results below.
Transform the data into a clear, professional, one-paragraph English business summary.

User Question: {user_query}
Executed SQL: {sql}
Raw Data: {data}

Executive Summary:"""

    def run(self, user_query: str) -> Dict[str, Any]:
        active_schema = self.pruner.prune_schema(user_query, top_k=self.top_k_tables)
# LLM promptuna active_schema değişkenini gönder
        """
        Orchestrates the Text-to-SQL Agentic Workflow:
        1. SQL Generation
        2. AST Validation & Security Guardrail
        3. Database Execution
        4. Self-Correction Loop on failure
        5. Natural language executive summarization
        """
        history = []
        current_sql = self._call_llm(self._generate_sql_prompt(user_query))

        for attempt in range(1, self.max_retries + 1):
            # Step 1: AST and Security Validation
            validation = validate_and_format_sql(current_sql)
            if not validation["is_valid"]:
                error_msg = f"Validation Error: {validation['error']}"
                history.append({"attempt": attempt, "sql": current_sql, "error": error_msg})
                current_sql = self._call_llm(
                    self._generate_correction_prompt(user_query, current_sql, error_msg)
                )
                continue

            clean_sql = validation["sql"]

            # Step 2: PostgreSQL Execution
            db_result = run_sql_query(clean_sql)

            if db_result["success"]:
                data = db_result["data"]
                summary = self._call_llm(self._generate_summary_prompt(user_query, clean_sql, data))
                return {
                    "success": True,
                    "final_sql": clean_sql,
                    "data": data,
                    "summary": summary,
                    "attempts": attempt,
                    "history": history
                }

            # Step 3: Runtime Error Self-Correction
            pg_error = db_result["error"]
            history.append({"attempt": attempt, "sql": clean_sql, "error": pg_error})

            if attempt < self.max_retries:
                current_sql = self._call_llm(
                    self._generate_correction_prompt(user_query, clean_sql, pg_error)
                )

        return {
            "success": False,
            "final_sql": current_sql,
            "data": None,
            "summary": "Query could not be resolved within the maximum retry limit.",
            "attempts": self.max_retries,
            "history": history
        }

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print(" SQL ANALYST AGENT INITIALIZED (Cloud LLM / DVD Rental)")
    print("=" * 55)

    agent = SQLAnalystAgent()
    print("✓ Agent is ready! Type 'q' or 'exit' to quit.\n")

    while True:
        try:
            user_query = input("\n[Ask a Question] > ").strip()

            if not user_query:
                continue

            if user_query.lower() in ["q", "exit", "quit"]:
                print("\nShutting down agent. Goodbye!\n")
                break

            print("\nAnalyzing...")
            res = agent.run(user_query)

            if not isinstance(res, dict):
                print("\n" + "-" * 40)
                print(f"Agent Output:\n{res}")
                print("-" * 40)
                continue

            if res.get("success"):
                sql_val = res.get("final_sql", "Not specified")
                summary_val = res.get("summary", "Not specified")
                attempts = res.get("attempts", 1)

                print("\n" + "-" * 40)
                print(f"Executed SQL (Attempts: {attempts}):\n{sql_val}")
                print("-" * 40)
                print(f"Executive Summary:\n{summary_val}")
                print("-" * 40)
            else:
                err_val = res.get("error", "An unknown error occurred.")
                print(f"\nERROR: {err_val}")

        except KeyboardInterrupt:
            print("\n\nOperation interrupted by user. Exiting...")
            break
        except Exception as e:
            print(f"\nUnexpected error: {e}")