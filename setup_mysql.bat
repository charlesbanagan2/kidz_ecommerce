@echo off
echo Setting up MySQL database for Kids E-commerce...
echo.

REM Check if MySQL is running
net start mysql >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting MySQL service...
    net start mysql
    if %errorlevel% neq 0 (
        echo ERROR: Could not start MySQL service
        echo Please make sure MySQL is installed and try again
        pause
        exit /b 1
    )
)

echo MySQL service is running!

REM Create database if it doesn't exist
echo Creating database 'kids_ecommerce'...
mysql -u root -e "CREATE DATABASE IF NOT EXISTS kids_ecommerce CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

if %errorlevel% equ 0 (
    echo Database created successfully!
) else (
    echo ERROR: Could not create database
    pause
    exit /b 1
)

REM Migrate data from SQLite to MySQL
echo.
echo Migrating data from SQLite to MySQL...
python scripts/migrate_sqlite_to_mysql.py

if %errorlevel% equ 0 (
    echo Migration completed successfully!
) else (
    echo ERROR: Migration failed
    pause
    exit /b 1
)

echo.
echo All done! Your MySQL database is ready.
echo You can now start your Flask application.
pause
