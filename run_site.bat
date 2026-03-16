@echo off
TITLE Lycee Al-Mansour Failsafe Launcher
echo.
echo ============================================
echo      PROMPT FIX AND LAUNCH SYSTEM
echo ============================================
echo.
echo [1/2] Checking Python and dependencies...
python -m pip install waitress flask flask_sqlalchemy flask_cors flask_login python-dotenv fpdf2 qrcode > nul 2>&1

echo [2/2] Running Launcher...
echo.
python launcher.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] ERREUR CRITIQUE : Le serveur ne peut pas demarrer.
    echo [!] Veuillez verifier si une autre instance de Python est ouverte.
    pause
)
echo.
pause
