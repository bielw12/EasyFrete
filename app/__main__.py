"""Ponto de entrada de iniciar.bat/iniciar.sh: `python -m app`."""
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app.config import HOST, PORTA
from app.db import SessionLocal, init_db
from app.services.seed import popular_se_vazio

ESPERA_MAXIMA_S = 120


def _porta_em_uso() -> bool:
    with socket.socket() as s:
        return s.connect_ex((HOST, PORTA)) == 0


def _abrir_navegador_quando_pronto(url: str) -> None:
    """Na primeira execução o servidor pode levar vários segundos para subir."""
    limite = time.monotonic() + ESPERA_MAXIMA_S
    while time.monotonic() < limite:
        if _porta_em_uso():
            webbrowser.open(url)
            return
        time.sleep(0.25)


def main() -> None:
    url = f"http://localhost:{PORTA}"
    abrir_navegador = "--sem-navegador" not in sys.argv
    if _porta_em_uso():
        print(f"A porta {PORTA} já está em uso: o app provavelmente já está aberto em outra janela.")
        print(f"Abrindo {url} no navegador. Se a página não for o app, feche o programa que usa essa porta e tente de novo.")
        if abrir_navegador:
            webbrowser.open(url)
        sys.exit(1)
    print("Iniciando o servidor...")
    init_db()
    with SessionLocal() as sessao:
        popular_se_vazio(sessao)
    if abrir_navegador:
        threading.Thread(target=_abrir_navegador_quando_pronto, args=[url], daemon=True).start()
    print(f"App rodando em {url}")
    print("Mantenha esta janela aberta enquanto usa o sistema. Para encerrar, feche a janela ou aperte Ctrl+C.")
    uvicorn.run("app.main:app", host=HOST, port=PORTA, log_level="warning")


if __name__ == "__main__":
    main()
