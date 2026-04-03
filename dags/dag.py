from airflow import DAG
# from airflow.operators.bash import BashOperator
from airflow.providers.standard.operators.bash import BashOperator

from datetime import datetime,timedelta


# default_args = {
#     'owner': 'airflow',
#     'depends_on_past': False,
#     'email_on_failure': False,
#     'email_on_retry': False,
#     'retries': 1,
#     'retry_delay': timedelta(minutes=1),
# }

# dag = DAG(
#     'Sample_airflow_dag',  # DAG name
#     default_args=default_args,
#     description='A sample ETL DAG',
#     schedule_interval=timedelta(minutes=5),
#     start_date=datetime(2026, 3, 16),
#     catchup=False,
# )
with DAG(
    dag_id='Sample_airflow_dag',
    start_date=datetime(2025, 8, 1),
    schedule='@daily', 
    catchup=False,
) as dag:

    start_task = BashOperator(
        task_id='start_task',
        bash_command='echo "Starting the workflow!"',
)

    main_task = BashOperator(
        task_id='main_task',
        # bash_command='echo "Welcome, This is your first Airflow DAG."',
        bash_command='python /opt/airflow/dags/etl/s3_to_snowflake.py '
)

    end_task = BashOperator(
        task_id='end_task',
        bash_command='echo "Workflow completed!"',
)

    # task dependencies
    start_task >> main_task >> end_task