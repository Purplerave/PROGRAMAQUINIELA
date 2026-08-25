@echo off
title PANEL QUINIELA - Programa Oficial
cd /d "%~dp0"
echo ============================================
echo   PANEL QUINIELA :: http://localhost:8787
echo   Deja esta ventana ABIERTA mientras usas
echo   el panel en el navegador. Ctrl+C para salir.
echo ============================================
python scripts\PANEL_QUINIELA.py
echo.
echo El panel se cerro. Pulsa una tecla para salir.
pause >nul
