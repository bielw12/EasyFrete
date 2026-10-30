#!/bin/sh
# Prepara o ambiente e inicia o app. Uso: ./iniciar.sh
cd "$(dirname "$0")" || exit 1

PY=""
for candidato in python3.13 python3.12 python3.11 python3.14 python3 python; do
    if command -v "$candidato" >/dev/null 2>&1 &&
       "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        PY="$candidato"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python 3.11 ou mais novo não foi encontrado."
    echo "Instale pelo site https://www.python.org/downloads/ ou pelo gerenciador do seu sistema e rode este script de novo."
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Criando o ambiente (só na primeira vez)..."
    "$PY" -m venv .venv || {
        echo "Não foi possível criar o ambiente. No Ubuntu/Debian, instale com: sudo apt install python3-venv"
        exit 1
    }
fi

if ! .venv/bin/python -c "import fastapi, sqlalchemy, uvicorn, jinja2, multipart, tzdata" >/dev/null 2>&1; then
    echo "Instalando as dependências (só na primeira vez)..."
    .venv/bin/python -m pip install -q --no-index --no-deps --find-links vendor/wheels -r requirements.txt >/dev/null 2>&1 ||
    .venv/bin/python -m pip install -q --no-deps -r requirements.txt || {
        echo "Não foi possível instalar as dependências. Veja a seção de erros comuns no README.md."
        exit 1
    }
fi

exec .venv/bin/python -m app "$@"
