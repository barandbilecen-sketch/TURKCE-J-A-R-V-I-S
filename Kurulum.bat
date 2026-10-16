@echo off
chcp 65001 >nul
title Jarvis Kurulum
cd /d "%~dp0"
echo.
echo  ==== JARVIS KURULUMU ====
echo.
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 bulunamadi, yukleniyor...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo.
    echo Python otomatik yuklenemedi. https://www.python.org/downloads/release/python-3128/ adresinden
    echo "Windows installer 64-bit" indirip kur, kurarken "Add python.exe to PATH" kutusunu isaretle.
    echo Sonra bu dosyayi tekrar calistir.
    pause
    exit /b 1
  )
)
echo.
echo [1/3] Sanal ortam hazirlaniyor...
if not exist .venv py -3.12 -m venv .venv
if errorlevel 1 (echo Sanal ortam olusturulamadi. Bilgisayari yeniden baslatip tekrar dene. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
echo [2/3] Gerekli paketler yukleniyor (birkac dakika surebilir)...
pip install -r requirements.txt
if errorlevel 1 (echo Paketler yuklenemedi. Internet baglantini kontrol et. & pause & exit /b 1)
echo [3/3] "Hey Jarvis" uyanma modeli yukleniyor...
pip install openwakeword
if errorlevel 1 echo Uyanma modeli yuklenemedi; Jarvis kelime dinleme moduyla calisacak.
echo Masaustune Jarvis kisayolu ekleniyor...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Jarvis.lnk');$s.TargetPath='wscript.exe';$s.Arguments=[char]34+'%~dp0Jarvis.vbs'+[char]34;$s.WorkingDirectory='%~dp0';$s.IconLocation='%SystemRoot%\System32\shell32.dll,43';$s.Save()"
echo.
echo  Kurulum tamam! Masaustundeki "Jarvis" kisayoluna cift tikla.
echo.
pause
