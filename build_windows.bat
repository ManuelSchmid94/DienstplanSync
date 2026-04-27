@echo off
setlocal EnableDelayedExpansion
title DienstplanSync – Windows Build

echo =====================================================
echo  Dienstplan Sync – Windows Build-Script
echo =====================================================
echo.

:: Ordner des Scripts als Arbeitsverzeichnis
cd /d "%~dp0"

:: ── 1. Python prüfen ────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden.
    echo Bitte von https://python.org installieren ^(3.11 oder neuer^).
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER%

:: ── 2. Tesseract prüfen ─────────────────────────────────────────────────────
set TESS_DIR=C:\Program Files\Tesseract-OCR
if not exist "%TESS_DIR%\tesseract.exe" (
    echo.
    echo Tesseract nicht gefunden. Jetzt installieren?
    echo  -> https://github.com/UB-Mannheim/tesseract/wiki
    echo Beim Setup unbedingt "German language data" auswaehlen!
    echo.
    set /p INSTALL_TESS="Installer jetzt herunterladen und starten? [j/n]: "
    if /i "!INSTALL_TESS!"=="j" (
        echo Lade Tesseract-Installer herunter...
        curl -L -o tesseract_installer.exe ^
            "https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0.20241111/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
        echo Starte Installer – bitte "German" als Sprache auswaehlen!
        start /wait tesseract_installer.exe
        del tesseract_installer.exe 2>nul
    ) else (
        echo Bitte Tesseract manuell installieren und Script erneut starten.
        pause & exit /b 1
    )
)
if not exist "%TESS_DIR%\tesseract.exe" (
    echo FEHLER: Tesseract immer noch nicht gefunden nach Installation.
    pause & exit /b 1
)
echo [OK] Tesseract gefunden: %TESS_DIR%

:: Deutsch-Sprachdaten prüfen
if not exist "%TESS_DIR%\tessdata\deu.traineddata" (
    echo FEHLER: Deutsche Sprachdaten fehlen.
    echo Tesseract erneut installieren und "German" auswaehlen.
    pause & exit /b 1
)
echo [OK] Deutsch-Sprachdaten vorhanden

:: ── 3. Poppler herunterladen ────────────────────────────────────────────────
set POPPLER_DIR=tools\poppler
if not exist "%POPPLER_DIR%\Library\bin\pdftoppm.exe" (
    echo.
    echo Lade Poppler fuer Windows herunter...
    if not exist tools mkdir tools
    curl -L -o tools\poppler.zip ^
        "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.08.0-0/Release-24.08.0-0.zip"
    echo Entpacke Poppler...
    tar -xf tools\poppler.zip -C tools\
    :: Ordner umbenennen (Release-24.08.0-0 → poppler)
    for /d %%d in (tools\Release-*) do (
        if exist "%%d" ren "%%d" poppler
    )
    del tools\poppler.zip 2>nul
)
if not exist "%POPPLER_DIR%\Library\bin\pdftoppm.exe" (
    echo FEHLER: Poppler konnte nicht entpackt werden.
    pause & exit /b 1
)
echo [OK] Poppler: %POPPLER_DIR%

:: ── 4. Virtuelle Umgebung ───────────────────────────────────────────────────
if not exist .venv (
    echo.
    echo Erstelle virtuelle Python-Umgebung...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo.
echo Installiere Python-Pakete...
pip install --quiet --upgrade pip
pip install --quiet ^
    PySide6>=6.6.0 ^
    playwright>=1.42.0 ^
    pytesseract ^
    pdf2image ^
    Pillow ^
    keyring>=25.1.0 ^
    pyinstaller>=6.5.0

:: Playwright-Browser installieren
echo.
echo Pruefe Playwright-Browser (Chromium)...
playwright install chromium
echo [OK] Playwright Chromium bereit

:: ── 5. Build ────────────────────────────────────────────────────────────────
echo.
echo Starte PyInstaller...
if exist dist\DienstplanSync rmdir /s /q dist\DienstplanSync
if exist build rmdir /s /q build

pyinstaller DienstplanSync_windows.spec --clean --noconfirm
if errorlevel 1 (
    echo FEHLER: PyInstaller ist fehlgeschlagen.
    pause & exit /b 1
)

if not exist "dist\DienstplanSync\DienstplanSync.exe" (
    echo FEHLER: .exe wurde nicht erstellt.
    pause & exit /b 1
)
echo [OK] .exe erstellt: dist\DienstplanSync\DienstplanSync.exe

:: ── 6. ZIP-Archiv erstellen ─────────────────────────────────────────────────
echo.
echo Erstelle ZIP-Archiv...
if exist dist\DienstplanSync.zip del dist\DienstplanSync.zip
powershell -NoProfile -Command ^
    "Compress-Archive -Path 'dist\DienstplanSync' -DestinationPath 'dist\DienstplanSync_Windows.zip' -Force"

echo.
echo =====================================================
echo  Build abgeschlossen!
echo.
echo  Programm:  dist\DienstplanSync\DienstplanSync.exe
echo  ZIP:       dist\DienstplanSync_Windows.zip
echo.
echo  Installation auf einem anderen PC:
echo    ZIP entpacken und DienstplanSync.exe starten.
echo    Kein Setup noetig – laeuft direkt aus dem Ordner.
echo =====================================================
pause
