from datetime import date

from app.ui import MENU, brl, data_br, numero, pct


def test_todas_as_telas_do_menu_respondem(client):
    for url, _, _ in MENU:
        assert client.get(url).status_code == 200, url


def test_formatacao_ptbr():
    assert brl(1234.56) == "R$ 1.234,56"
    assert brl(-1234.5) == "-R$ 1.234,50"
    assert numero(1234.5, 1) == "1.234,5"
    assert pct(12.34) == "12,3%"
    assert data_br(date(2026, 1, 9)) == "09/01/2026"
