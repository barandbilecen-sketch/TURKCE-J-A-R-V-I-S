@echo off
chcp 65001 >nul
title Jarvis - Yazi Modu
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe jarvis.py --yazi
pause
