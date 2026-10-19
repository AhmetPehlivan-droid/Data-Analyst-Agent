from typing import Dict, Any, Optional
import sqlglot
from sqlglot import exp

# İzin verilmeyen, veri tabanını değiştiren veya tehlikeli olan AST düğümleri
FORBIDDEN_EXPRESSIONS = (
    exp.Drop,
    exp.Delete,
    exp.Update,
    exp.Insert,
    exp.Alter,
    exp.Command,
    exp.TruncateTable,
    exp.Create,
)

def clean_markdown_sql(raw_sql: str) -> str:
    """
    LLM'in dönebileceği markdown etiketlerini (```sql ... ```) temizler.
    """
    sql = raw_sql.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        # İlk satır ```sql veya ``` ise at, son satır ``` ise at
        start_idx = 1
        end_idx = len(lines) - 1 if lines[-1].strip().startswith("```") else len(lines)
        sql = "\n".join(lines[start_idx:end_idx])
    return sql.strip().rstrip(";")

def validate_and_format_sql(raw_sql: str, default_limit: int = 100) -> Dict[str, Any]:
    """
    SQL sorgusunu AST (Soyut Sözdizim Ağacı) düzeyinde doğrular ve biçimlendirir.
    
    Kontroller:
    1. Sözdizimi geçerli mi?
    2. Birden fazla sorgu (batch injection) var mı?
    3. DROP, DELETE, UPDATE gibi yasaklı komutlar içeriyor mu?
    4. Kök ifade SELECT mi?
    5. LIMIT yoksa sunucu güvenliği için otomatik limit ekler.
    """
    clean_sql = clean_markdown_sql(raw_sql)

    if not clean_sql:
        return {
            "is_valid": False,
            "sql": None,
            "error": "Sorgu boş olamaz."
        }

    # 1. PostgreSQL lehçesine göre AST olarak parse et
    try:
        parsed_statements = sqlglot.parse(clean_sql, read="postgres")
    except Exception as e:
        return {
            "is_valid": False,
            "sql": None,
            "error": f"PostgreSQL sözdizimi (syntax) hatası: {str(e)}"
        }

    if not parsed_statements:
        return {
            "is_valid": False,
            "sql": None,
            "error": "Ayrıştırılabilir bir SQL ifadesi bulunamadı."
        }

    # 2. Çoklu sorgu engeli (Örn: SELECT ...; DROP TABLE ...)
    if len(parsed_statements) > 1:
        return {
            "is_valid": False,
            "sql": None,
            "error": "Güvenlik kuralı: Tek seferde birden fazla sorgu çalıştırılamaz."
        }

    expression = parsed_statements[0]

    # 3. Kök ifadenin SELECT olup olmadığını denetle
    if not isinstance(expression, exp.Select):
        return {
            "is_valid": False,
            "sql": None,
            "error": "Güvenlik kuralı: Yalnızca SELECT sorgularına izin verilir."
        }

    # 4. AST içinde derinlemesine yasaklı komut taraması (Subquery içinde DELETE vs. varsa)
    for forbidden in FORBIDDEN_EXPRESSIONS:
        if expression.find(forbidden):
            return {
                "is_valid": False,
                "sql": None,
                "error": f"Güvenlik ihlali: '{forbidden.__name__}' komutu tespit edildi. Veri tabanı salt-okunurdur."
            }

    # 5. Otomatik LIMIT ekleme (Milyonluk tablolarda RAM taşmasını önler)
    if not expression.find(exp.Limit):
        expression = expression.limit(default_limit)

    return {
        "is_valid": True,
        "sql": expression.sql(dialect="postgres"),
        "error": None
    }

if __name__ == "__main__":
    # Test Senaryoları
    test_cases = [
        "SELECT * FROM products WHERE price > 1000",
        "```sql\nSELECT name, stock FROM products;\n```",
        "SELECT * FROM products; DROP TABLE orders;",
        "DELETE FROM products WHERE id = 1",
        "SELECT * FROM orders LIMIT 10",
        "INVALID SQL SYNTAX HERE"
    ]

    print("--- VALIDATOR TESTLERİ BAŞLIYOR ---\n")
    for test in test_cases:
        res = validate_and_format_sql(test)
        print(f"Girdi: {test.replace(chr(10), ' ')}")
        print(f"Geçerli mi?: {res['is_valid']}")
        if res["is_valid"]:
            print(f"Üretilen Güvenli SQL: {res['sql']}")
        else:
            print(f"Hata Mesajı: {res['error']}")
        print("-" * 50) 