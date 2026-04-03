import pandas as pd
from sqlalchemy import create_engine,text
from sqlalchemy import engine
from sqlalchemy import MetaData
# from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv
import logging
from langchain_groq import ChatGroq
from langchain_text_splitters import CharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings


load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

user=os.getenv("MYSQL_USER")
password=os.getenv("MYSQL_PASSWORD")
host=os.getenv("MYSQL_HOST")
port=os.getenv("MYSQL_PORT")
database=os.getenv("MYSQL_DATABASE")
process_name=os.getenv("PROCESS_NAME")
# process_control_table=os.getenv("PROCESS_CONTROL_TABLE")

mysql_url="mysql+pymysql://{user}:{password}@{host}:{port}/{database}".format(user=user,password=password,host=host,port=port,database=database)
print("mysql_url : ",mysql_url)

# ---- MySQL---
def _make_engine(mysql_url: str, label: str) :
    engine = create_engine(mysql_url)
    logger.info("Engine created: %s (%s)", label, engine.dialect.name)
    logger.info(engine)
    return engine
def get_mysql_engine() :
    """Source MySQL engine."""
    # url = mysql_url
    return _make_engine(mysql_url, "MySQL source")

def mysql_data():
# Convert rows to text
    engine = get_mysql_engine()
    query = f"""SELECT distinct table_name, table_type,table_schema,create_time FROM information_schema.tables
     where table_schema= 'its' limit 100"""
    
    with engine.connect() as conn:
        row = conn.execute(text(query),{"database":database}).mappings().fetchall()
        print("Query Result : " ,row)
    documents=[]
    for r in row: 
        parts = []
        
        for key, value in r.items():
            if hasattr(value, "strftime"):
                value = value.strftime("%Y-%m-%d %H:%M:%S")

            parts.append(f"{key}: {value}")

        txt = " | ".join(parts)
        documents.append(txt)
    print("documents :" ,documents)
    return documents
    

    

if __name__ == "__main__":
    mysql_engine = _make_engine(mysql_url, "Mysql Source")
    documents = mysql_data()
    print(type(documents))
    print(f"Loaded {len(documents)} documents")
    splitter = CharacterTextSplitter(chunk_size=300,chunk_overlap=50)
    docs = splitter.create_documents(documents)
    embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2")
    doc_embeddings = embedding.embed_documents(documents)
    print("doc_embeddings : ",doc_embeddings)

