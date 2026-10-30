"""Motor de alertas. As regras entram na Fase 5."""


def salvar_e_reavaliar(db) -> None:
    """Grava as alterações pendentes. Use no lugar de db.commit() ao salvar registros relevantes."""
    db.commit()
