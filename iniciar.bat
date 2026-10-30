@echo off
rem Prepara o ambiente e inicia o app. Uso: dois cliques ou "iniciar.bat" no terminal.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
for %%V in (3.13 3.12 3.11 3.14) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python 3.11 ou mais novo nao foi encontrado.
    echo Instale em https://www.python.org/downloads/ marcando a opcao "Add python.exe to PATH" e rode este arquivo de novo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando o ambiente, so na primeira vez...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Nao foi possivel criar o ambiente. Veja a secao de erros comuns no README.md.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import fastapi, sqlalchemy, uvicorn, jinja2, multipart, tzdata" >nul 2>&1
if errorlevel 1 (
    echo Instalando as dependencias, so na primeira vez...
    ".venv\Scripts\python.exe" -m pip install -q --no-index --no-deps --find-links vendor\wheels -r requirements.txt >nul 2>&1
    if errorlevel 1 (
        ".venv\Scripts\python.exe" -m pip install -q --no-deps -r requirements.txt
        if errorlevel 1 (
            echo Nao foi possivel instalar as dependencias. Veja a secao de erros comuns no README.md.
            pause
            exit /b 1
        )
    )
)

".venv\Scripts\python.exe" -m app %*
if errorlevel 1 pause
