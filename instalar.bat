@echo off
title Discord Username Checker - Instalacao
cd /d "%~dp0"

echo.
echo  === Discord Username Checker - Instalacao ===
echo.

set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo Baixe em https://www.python.org/downloads/ e, na instalacao,
    echo marque a caixinha "Add Python to PATH". Depois rode este arquivo de novo.
    echo.
    pause
    exit /b 1
)

echo [1/3] Atualizando o pip...
%PY% -m pip install --upgrade pip

echo.
echo [2/3] Instalando as dependencias...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Nao consegui instalar as dependencias. Leia a mensagem acima.
    pause
    exit /b 1
)

echo.
echo [3/3] Preparando o proxies.txt...
if not exist proxies.txt (
    copy proxies.example.txt proxies.txt >nul
    echo proxies.txt criado. Abra ele e cole seus proxies antes de iniciar.
) else (
    echo proxies.txt ja existe, mantido como esta.
)

echo.
echo Instalacao concluida!
echo Agora cole seus proxies no proxies.txt e de dois cliques em iniciar.bat
echo.
pause
