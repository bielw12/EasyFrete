"""Cada teste roda com um banco vazio em pasta temporária."""
import os
import tempfile

os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="app-testes-")

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, recriar_db
from app.main import app


@pytest.fixture(autouse=True)
def _banco_limpo():
    recriar_db()


@pytest.fixture
def db():
    with SessionLocal() as sessao:
        yield sessao


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as cliente:
        yield cliente
