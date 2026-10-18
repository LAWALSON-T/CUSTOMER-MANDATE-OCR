@echo off
echo ================================================
echo Customer Mandate ETL Pipeline - Quick Start
echo ================================================
echo.

REM Secrets live in .env, which is never committed. Stop early if it is missing.
if not exist .env (
    echo ERROR: .env not found.
    echo Copy .env.example to .env and fill in the values, then run this again.
    pause
    exit /b 1
)

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo [1/5] Docker is running...
echo.

echo [2/5] Starting all services (first run builds the Airflow image, a few minutes)...
docker compose up -d
if errorlevel 1 (
    echo ERROR: services did not start. Read the message above.
    echo A common cause: another program is already using port 3307, 27017, 8081 or 8082.
    pause
    exit /b 1
)
echo.

echo [3/5] Waiting for services to initialize (this may take 2-3 minutes)...
timeout /t 60 /nobreak >nul
echo.

echo [4/5] Checking service status...
docker compose ps
echo.

echo [5/5] Setup complete!
echo.
echo ================================================
echo Access Points (all passwords are in .env)
echo ================================================
echo Airflow UI:    http://localhost:8081
echo   Username: admin
echo   Password: see AIRFLOW_ADMIN_PASSWORD in .env
echo             (on an existing install, the password set when it was first created)
echo.
echo Mongo Express: http://localhost:8082
echo.
echo MySQL:         localhost:3307
echo   Username: etl_user
echo   Password: see MYSQL_PASSWORD in .env
echo   Database: customer_db
echo.
echo MongoDB:       localhost:27017
echo   Username: admin
echo   Password: see MONGO_ROOT_PASSWORD in .env
echo   Database: customer_mandates
echo.
echo ================================================
echo Next Steps:
echo ================================================
echo 1. Open http://localhost:8081 in your browser
echo 2. Log in as admin
echo 3. Enable the 'customer_mandate_etl' DAG
echo 4. Click the play button to run the pipeline
echo.
echo First time only, after the services are up:
echo   docker exec airflow_scheduler python /opt/airflow/scripts/migrate_upgrade.py --apply
echo   docker exec -w /opt/airflow/scripts airflow_scheduler python generate_mandate_forms.py
echo.
echo To view logs: docker compose logs -f
echo To stop:      docker compose down
echo ================================================
echo.
pause
