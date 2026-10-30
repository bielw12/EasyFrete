"""Conexão com o SQLite e sessão por requisição."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, DB_PATH, UPLOADS_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@event.listens_for(engine, "connect")
def _ligar_chaves_estrangeiras(conexao, _):
    conexao.execute("PRAGMA foreign_keys=ON")


def init_db():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    from app import models  # noqa: F401  (registra as tabelas)

    Base.metadata.create_all(engine)


def recriar_db():
    from app import models  # noqa: F401

    Base.metadata.drop_all(engine)
    init_db()


def get_db():
    with SessionLocal() as sessao:
        yield sessao
