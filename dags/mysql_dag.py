from airflow import DAG
# from airflow.operators.bash import BashOperator
from airflow.providers.standard.operators.bash import BashOperator

from datetime import datetime,timedelta


with DAG(
    dag_id='mysql_airflow_dag',
    start_date=datetime(2025, 8, 1),
    schedule='@daily', 
    catchup=False,
) as dag:

    master_pipeline = BashOperator(
        task_id='master_pipeline',
        bash_command='python /opt/airflow/dags/etl_llm/etl_pipeline.py ',
        
)
#     main_task = BashOperator(
#         task_id='main_task',
#         bash_command='python /opt/airflow/dags/etl/mysql_to_pssql_etl.py ',
# )
    # master_pipeline>>main_task
    master_pipeline