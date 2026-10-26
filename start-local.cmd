@echo off
REM Levanta Hotel Tickets en local: http://127.0.0.1:8001 (base local db.sqlite3, no toca produccion)
cd /d %~dp0
start "Hotel Tickets" cmd /k "venv\Scripts\python manage.py runserver 8001"
timeout /t 4 >nul
start http://127.0.0.1:8001/admin/
