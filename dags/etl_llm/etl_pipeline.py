import pandas as pd
from sqlalchemy import create_engine,text
from sqlalchemy import engine
from sqlalchemy import MetaData
# from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv
import logging
from langchain_groq import ChatGroq

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

user=os.getenv("MYSQL_USER")
password=os.getenv("MYSQL_PASSWORD")
host=os.getenv("MYSQL_HOST")
port=os.getenv("MYSQL_PORT")
database=os.getenv("MYSQL_DATABASE")
process_name=os.getenv("PROCESS_NAME")
process_control_table=os.getenv("PROCESS_CONTROL_TABLE")

YOUR_GROQ_KEY=os.getenv("YOUR_GROQ_KEY")
pg_user=os.getenv("PG_USER")
pg_password=os.getenv("PG_PASSWORD")
pg_host=os.getenv("PG_HOST")
pg_port=os.getenv("PG_PORT")
pg_database=os.getenv("PG_DATABASE")
pg_schema=os.getenv("PG_SCHEMA")

print("PG_PORT : ",os.getenv("PG_PORT"))

mysql_url="mysql://{user}:{password}@{host}:{port}/{database}".format(user=user,password=password,host=host,port=port,database=database)
pg_url="postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}".format(pg_user=pg_user,pg_password=pg_password,pg_host=pg_host,pg_port=pg_port,pg_database=pg_database)

# ---- MySQL---
def _make_engine(mysql_url: str, label: str) :
    engine = create_engine(mysql_url)
    logger.info("Engine created: %s (%s)", label, engine.dialect.name)
    logger.info(engine)
    return engine
 
 
def get_mysql_engine() :
    """Source MySQL engine."""
    return _make_engine(mysql_url, "MySQL source")

# ---- Postgresql---
def get_postgres_engine():
    """Source Postgres engine."""
    return _make_engine(pg_url,"Postgresql source")

def fetch_process_config(process_name: str, database: str, process_control_table: str) -> dict:
    logger.info("*" * 15 + " connecting to MySQL to fetch process config " + "*" * 15)
    logger.info("Fetching process config for '%s' from %s.%s", process_name, database, process_control_table)
    engine = get_mysql_engine()
    query = text(f"""
        SELECT * FROM {database}.{process_control_table}
        WHERE process_name = :pname AND active_flag = 'Y'
        ORDER BY run_seq ASC
    """)
    with engine.connect() as conn:
        row = conn.execute(query, {"pname": process_name}).mappings().fetchone()
    if row is None:
        raise ValueError(f"No active config found for process '{process_name}'")
    return dict(row)

def fetch_source_schema(config: dict) -> list[dict]:
    logger.info("Connecting to MySQL to fetch source schema for %s.%s", config["SOURCE_DATABASE"], config["SOURCE_TABLE_NAME"])
    """Returns a list of column dicts: name, data_type, is_nullable, column_key"""
    engine = get_mysql_engine()
    query = text("""
        SELECT column_name, data_type, is_nullable, column_key, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {
            "schema": config["SOURCE_DATABASE"],
            "table": config["SOURCE_TABLE_NAME"]
        }).mappings().fetchall()
    
    if not rows:
        raise ValueError(f"No schema found for {config['SOURCE_DATABASE']}.{config['SOURCE_TABLE_NAME']}")
    
    columns = [{k.lower(): v for k, v in dict(r).items()} for r in rows]

    logger.info("Fetched %d columns from source schema", len(columns))
    return columns


def generate_create_statement(columns: list[dict], target_schema: str, target_table: str) -> str:
    logger.info("Generating CREATE TABLE statement for %s.%s using LLM", target_schema, target_table)
    """Ask the LLM to convert MySQL schema → Postgres CREATE TABLE SQL."""
    llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    api_key=YOUR_GROQ_KEY)
    prompt = f"""
You are a database migration expert.

Convert the following MySQL column schema into a valid PostgreSQL statement:

Target table: {target_schema}.{target_table}

Requirements:

* Generate: CREATE TABLE IF NOT EXISTS {target_schema}.{target_table}
* Only include column definitions (no indexes, no constraints, no primary key, no unique)
* Map MySQL types to PostgreSQL equivalents:

  * INT → INTEGER
  * BIGINT → BIGINT
  * TINYINT → SMALLINT
  * DATETIME → TIMESTAMP
  * VARCHAR(n) → TEXT
  * TEXT → TEXT
  * DECIMAL → NUMERIC
  * DOUBLE → DOUBLE PRECISION
* Remove MySQL-specific attributes:

  * AUTO_INCREMENT
  * ENGINE
  * CHARSET
  * COLLATE
  * UNSIGNED
* Convert DEFAULT values correctly for PostgreSQL
* Handle NULL / NOT NULL properly
* Quote column names only if necessary
* Ensure valid PostgreSQL syntax

Output Rules:

* Return ONLY the SQL statement
* No explanations
* No markdown formatting

MySQL columns:
{columns}
"""

    response = llm.invoke(prompt)
    raw = response.content.strip()
    logger.debug("LLM raw output:\n%s", raw)
    logger.info("LLM raw output:\n%s", raw)

    # sql = message.content[0].text.strip()
    return raw

def ensure_tables_exist(columns: list[dict], target_schema: str, target_table: str):
    logger.info("Ensuring tables exist in Postgres: %s.%s", target_schema, target_table)
    """Create MAIN and STG tables in Postgres if they don't already exist."""
    pg = get_postgres_engine()
    
    # STG table is a copy of main, just different name
    stg_table = f"{target_table}_stg"

    check_sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table_name
        )
    """)

    with pg.begin() as conn:
        main_exists = conn.execute(
            check_sql,
            {"schema": target_schema, "table_name": target_table}
        ).scalar()

        stg_exists = conn.execute(
            check_sql,
            {"schema": target_schema, "table_name": stg_table}
        ).scalar()

        if main_exists and stg_exists:
            logger.info("Both tables already exist. Skipping create step.")
            return

        # Only now generate create SQL
        create_sql = generate_create_statement(columns, target_schema, target_table)
        logger.info("Generated create SQL for %s.%s", target_schema, target_table)
        print("create_sql : ",create_sql)

        if not main_exists:
            logger.info("Creating main table: %s.%s", target_schema, target_table)
            conn.execute(text(create_sql))
        else:
            logger.info("Main table already exists: %s.%s", target_schema, target_table)

        if not stg_exists:
            stg_sql = create_sql.replace(
                f"{target_schema}.{target_table}",
                f"{target_schema}.{stg_table}"
            )
            logger.info("Creating staging table: %s.%s", target_schema, stg_table)
            conn.execute(text(stg_sql))
        else:
            logger.info("Staging table already exists: %s.%s", target_schema, stg_table)


def load_incremental(config: dict, columns: list[dict]):
    logger.info("Starting incremental load for %s.%s", config["SOURCE_DATABASE"], config["SOURCE_TABLE_NAME"]) 
    """Extract rows from source where trip_date > last enddate, then MERGE into target."""
    mysql_eng = get_mysql_engine()
    pg_eng = get_postgres_engine()

    src_db    = config["SOURCE_DATABASE"]
    src_table = config["SOURCE_TABLE_NAME"]
    tgt_schema = config["TARGET_SCHEMA"].lower()
    tgt_table  = config["TARGET_TABLE_NAME"].lower()
    stg_table  = f"{tgt_table}_stg"
    end_date   = config.get("ENDDATE")  # last processed datetime
    date_col   = config.get("DATE_COLUMN", "date")  # column to filter on
    primary_key   = config.get("PRIMARY_KEY", "trip_id") 
    # 1. Extract from source
    src_query = f"SELECT * FROM {src_db}.{src_table}"
    if end_date:
        src_query += f" WHERE {date_col} > '{end_date}'"
        
    print("src_query : ",src_query)
    
    with mysql_eng.connect() as conn:
        df = pd.read_sql(src_query, conn)
    
    logger.info("Extracted %d rows from source", len(df))
    if df.empty:
        logger.info("No new data. Skipping load.")
        return

    # 2. Load into STG
    with pg_eng.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tgt_schema}.{stg_table}"))
    df.to_sql(stg_table, pg_eng, schema=tgt_schema, if_exists="append", index=False)
    logger.info("Loaded %d rows into staging table", len(df))

    # 3. MERGE from STG into MAIN
    pk_col= primary_key
    if not pk_col:
        raise ValueError("No primary key found — cannot perform MERGE")

    merge_sql = f"""
        INSERT INTO {tgt_schema}.{tgt_table}
        SELECT *
        FROM {tgt_schema}.{stg_table} s
        WHERE NOT EXISTS (
            SELECT 1
            FROM {tgt_schema}.{tgt_table} t
            WHERE t.{pk_col} = s.{pk_col})
    """
    print("merge_sql : ",merge_sql)
    
    with pg_eng.begin() as conn:
        conn.execute(text(merge_sql))
    logger.info("MERGE complete into %s.%s", tgt_schema, tgt_table)

def update_process_control(config: dict, process_name: str, database: str, process_control_table: str):
    logger.info("Updating process control for process : %s (in %s.%s)", process_name, database, process_control_table)
    """Update control table with latest enddate and success status."""
    engine = get_mysql_engine()
    pengine = get_postgres_engine()

    target_schema = config["TARGET_SCHEMA"].lower()
    target_table = config["TARGET_TABLE_NAME"].lower()
    date_column = config.get("DATE_COLUMN", "date")

    with pengine.connect() as conn:
        new_end_date = conn.execute(
            text(f"SELECT MAX({date_column}) FROM {target_schema}.{target_table}")
        ).scalar()
    
    if new_end_date is None:
        logger.info("No max date found in %s.%s, skipping process control update", target_schema, target_table)
        return

    update_sql = text(f"""
        UPDATE {database}.{process_control_table}
        SET enddate = :end_date
        WHERE process_name = :pname and target_table_name = :target_table
    """)    

    with engine.begin() as conn:
        conn.execute(update_sql, {"end_date": new_end_date, "pname": process_name, "target_table": target_table})

    logger.info(
        "Updated process control table for %s with new enddate %s",
        process_name,
        new_end_date
    )
    logger.info("Updated Query : %s", update_sql)

def run_etl():
    logger.info("*" * 15 + " ETL Pipeline START 15 " + "*" * 15)
    try:
        # Step 1: Read config
        config = fetch_process_config(process_name, database, process_control_table)
        action_type = config.get("ACTION_TYPE", "").upper().strip()
        # print(config)

        # Step 2: Get source schema
        columns = fetch_source_schema(config)
        logger.info("Columns from Source Schema: %s", columns)

        # Step 3: Target table names
        tgt_schema = config["TARGET_SCHEMA"].lower()
        tgt_table  = config["TARGET_TABLE_NAME"].lower()

        # Step 4: Create tables if not exist
        ensure_tables_exist(columns, tgt_schema, tgt_table)

        # Step 5: Load data based on action type
        if action_type in ("INSERT", "UPDATE"):
            load_incremental(config, columns)

        # Step 6: Update control table
        update_process_control(config, process_name, database, process_control_table)

        logger.info("*" * 15 + " ETL Pipeline COMPLETE " + "*" * 15)

    except Exception as e:
        logger.error("ETL Pipeline FAILED: %s", e, exc_info=True)
        raise

if __name__ == "__main__":
    run_etl()