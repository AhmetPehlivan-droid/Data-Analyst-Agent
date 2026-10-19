import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        database=os.getenv("DB_NAME", "dvdrental"),
        user=os.getenv("DB_USER", "ai_analyst"),
        password=os.getenv("DB_PASSWORD")
    )

def run_sql_query(query: str):
    """
    Sorguyu çalıştırır ve hem ajanın hem hata yönetiminin
    beklediği sözlük (dict) formatında döner.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            if cur.description:
                rows = cur.fetchall()
                # RealDictRow objelerini düz Python dict'ine çeviriyoruz
                data = [dict(row) for row in rows]
            else:
                conn.commit()
                data = []
            return {"success": True, "data": data, "error": None}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"success": False, "data": None, "error": str(e)}
    finally:
        if conn:
            conn.close()
 
def get_database_schema() -> str:
    """
    Tüm public şemasındaki tabloları ve kolon bilgilerini tek bir metin olarak döner.
    """
    query = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
    """
    res = run_sql_query(query)
    
    # run_sql_query artık {"success": ..., "data": ...} dönüyor
    if not res.get("success"):
        raise RuntimeError(f"Şema bilgisi alınamadı: {res.get('error')}")

    rows = res["data"]
    
    schema_map = {}
    for row in rows:
        t_name = row['table_name']
        c_name = row['column_name']
        d_type = row['data_type']
        
        if t_name not in schema_map:
            schema_map[t_name] = []
        schema_map[t_name].append(f"  - {c_name} ({d_type})")
        
    formatted = []
    for t_name, cols in schema_map.items():
        formatted.append(f"Tablo: {t_name}\n" + "\n".join(cols))
        
    return "\n\n".join(formatted)
def get_table_schemas_dict() -> dict[str, str]:
    """
    SchemaPruner için her tabloyu sözlük (dict) formatında ayrı ayrı döner.
    """
    raw_schema_text = get_database_schema()
    tables = {}
    current_table = None
    buffer = []

    for line in raw_schema_text.splitlines():
        if line.startswith("Tablo: "):
            if current_table and buffer:
                tables[current_table] = "\n".join(buffer)
                buffer = []
            current_table = line.replace("Tablo: ", "").strip()
            buffer.append(line)
        elif current_table:
            buffer.append(line)

    if current_table and buffer:
        tables[current_table] = "\n".join(buffer)

    return tables