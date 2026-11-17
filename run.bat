@echo off
setlocal
chcp 65001 >nul
title AIGenProject
cd /d "%~dp0"

echo === AIGenProject ===
echo.

rem 1. Python
where python >nul 2>nul
if errorlevel 1 (
    echo [LOI] Chua cai Python. Tai tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) roi chay lai.
    pause
    exit /b 1
)

rem 2. Moi truong ao
if not exist ".venv\Scripts\python.exe" (
    echo Dang tao moi truong ao .venv ...
    python -m venv .venv || (echo [LOI] Khong tao duoc .venv & pause & exit /b 1)
    set FIRST_RUN=1
)

rem 3. Thu vien (cai khi chua co hoac khi requirements.txt moi hon dau cai lan truoc)
set NEED_INSTALL=
if defined FIRST_RUN set NEED_INSTALL=1
if not exist ".venv\.installed" set NEED_INSTALL=1
if exist ".venv\.installed" (
    for /f %%i in ('powershell -NoProfile -Command "if ((Get-Item requirements.txt).LastWriteTime -gt (Get-Item .venv\.installed).LastWriteTime) { 'yes' } else { 'no' }"') do if "%%i"=="yes" set NEED_INSTALL=1
)
if defined NEED_INSTALL (
    echo Dang cai thu vien tu requirements.txt ...
    ".venv\Scripts\python.exe" -m pip install -q --upgrade pip >nul 2>nul
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (echo [LOI] Cai thu vien that bai & pause & exit /b 1)
    type nul > ".venv\.installed"
)

rem 4. File .env
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo Da tao .env tu .env.example ^(sua PORT, MAX_DAILY_RUNS, MAX_TURNS neu can^).
)

rem 5. Kiem tra moi truong va dang nhap Claude
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" backend\cli.py --check
if errorlevel 1 (
    echo.
    echo Moi truong chua san sang. Neu bao chua dang nhap, chay:  claude login
    pause
    exit /b 1
)

rem 6. Cong tu .env (mac dinh 8000)
set PORT=8000
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /i "PORT=" .env 2^>nul`) do if not "%%b"=="" set PORT=%%b

echo.
echo Dang chay app tai http://127.0.0.1:%PORT%  ^(dong cua so nay hoac bam Ctrl+C de tat^)
echo Lich tu dong chi chay khi cua so nay con mo.
echo.
start "" "http://127.0.0.1:%PORT%"
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%

echo.
echo App da dung.
pause
