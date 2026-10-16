@echo off
chcp 65001 >nul
title Jarvis - Turkce Ses Kurulumu
cd /d "%~dp0"
if not exist .venv (echo Once Kurulum.bat dosyasini calistir. & pause & exit /b 1)
call .venv\Scripts\activate.bat
echo.
echo [1/3] Cevrimdisi Turkce ses paketi yukleniyor...
pip install -U piper-tts psutil pywebview
if errorlevel 1 (echo Paket yuklenemedi. Internet baglantini kontrol et. & pause & exit /b 1)
echo.
echo [2/3] Turkce erkek ses modeli indiriliyor (yaklasik 63 MB)...
set PYTHONIOENCODING=utf-8
python -c "import jarvis; jarvis.piper_modeli_indir()"
if errorlevel 1 (echo Ses modeli indirilemedi. & pause & exit /b 1)
echo.
echo [3/3] Deneme...
python -c "import jarvis; jarvis._konus_ses('Merhaba efendim. Türkçe sesim hazır. Emrinizdeyim.')"
echo.
echo  Sesi duyduysan tamam! Jarvis'i yeniden baslatabilirsin.
pause
