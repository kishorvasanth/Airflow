from airflow import DAG
# from airflow.operators.bash import BashOperator
from airflow.providers.standard.operators.bash import BashOperator

from datetime import datetime,timedelta


with DAG(
    dag_id='etl_dag',
    start_date=datetime(2025, 8, 1),
    schedule='@daily', 
    catchup=False,
) as dag:

    mysql_connection = BashOperator(
        task_id='mysql_connection',
        bash_command='python /opt/airflow/dags/etl_langgraph/nodes/process_config.py ',
        
)
    postgres_connection = BashOperator(
        task_id='postgres_connection',
        bash_command='python /opt/airflow/dags/etl_langgraph/db/postgres.py ',
)
    mysql_connection>>postgres_connection
    # master_pipeline