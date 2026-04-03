# Apache Airflow Setup with Docker

## 1) Make sure Docker is installed

Make sure to create folder in `C:\airflow`

## 2) Create a folder for Airflow
    mkdir airflow
    cd airflow

## 3) Download the official Compose file
    curl -LfO https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml

Apache publishes this file directly in the docs, and the default image in that file is apache/airflow:3.1.8.

## 4) Create the required folders
    mkdir dags logs plugins config

## 5) Create an .env file

On Windows, just create a file named .env with:

    AIRFLOW_UID=50000

The official compose file supports AIRFLOW_UID and defaults it to 50000 if you do not set it.

## 6) Initialize Airflow
    docker compose up airflow-init

## 7) Start Airflow
    docker compose up -d

## 8) Open the UI
Go to: http://localhost:8080

    username: airflow
    password: airflow

## 9) Stop it later
    docker compose down

## 10) To see containers:
    docker compose ps

## 11) To view logs:
    docker compose logs -f