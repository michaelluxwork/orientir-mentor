@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe manage.py migrate --noinput
if errorlevel 1 exit /b 1
echo Create your local account in another terminal with:
echo .venv\Scripts\python.exe manage.py create_mentor YOUR_LOGIN
echo For invented examples: .venv\Scripts\python.exe manage.py seed_demo
echo Open http://127.0.0.1:4365/ in your browser. Stop with Ctrl+C.
.venv\Scripts\python.exe serve.py
