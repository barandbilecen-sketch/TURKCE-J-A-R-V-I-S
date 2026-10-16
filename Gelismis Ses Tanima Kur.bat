@echo off
chcp 65001 >nul
title Jarvis - Gelismis Ses Tanima Kurulumu
cd /d "%~dp0"
if not exist .venv (echo Once Kurulum.bat dosyasini calistir. & pause & exit /b 1)
call .venv\Scripts\activate.bat
echo.
echo [1/2] Whisper ses tanima paketi yukleniyor...
pip install -U faster-whisper
if errorlevel 1 (echo Paket yuklenemedi. Internet baglantini kontrol et. & pause & exit /b 1)
echo.
echo [2/2] Turkce ses tanima modeli indiriliyor (yaklasik 480 MB, birkac dakika surebilir)...
set PYTHONIOENCODING=utf-8
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root=r'%~dp0sesler\whisper'); print('Model hazir.')"
if errorlevel 1 (echo Model indirilemedi. & pause & exit /b 1)
echo.
echo  Tamam! Jarvis'i yeniden baslat; artik seni bilgisayarda calisan Whisper ile anlayacak.
pause
