@echo off
title VPS Manager Pro
color 0A

echo.
echo ========================================
echo    VPS Manager Pro - Inicializador
echo ========================================
echo.

cd /d "%~dp0"

python start_vps_manager.py

pause