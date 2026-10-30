"""Ponto de entrada de iniciar.bat/iniciar.sh: `python -m app`."""
import socket
import sys
import threading
import webbrowser

import uvicorn

from app.config import HOST, PORTA
from app.db import SessionLocal, init_db
from app.services.seed import popular_se_vazio


def _porta_em_uso() -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, PORTA)) == 0


def main() -> None:
    url = f"http://localhost:{PORTA}"
    if _porta_em_uso():
        print(f"A porta {PORTA} já está em uso. O app talvez já esteja aberto em {url}.")
        print("Se não estiver, feche o outro programa que usa essa porta e tente de novo.")
        sys.exit(1)
    init_db()
    with SessionLocal() as sessao:
        popular_se_vazio(sessao)
    if "--sem-navegador" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    print(f"App rodando em {url}  (feche esta janela ou aperte Ctrl+C para parar)")
    uvicorn.run("app.main:app", host=HOST, port=PORTA, log_level="warning")


if __name__ == "__main__":
    main()
