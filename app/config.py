"""Constantes do produto e limiares padrão (editáveis na tela Configurações)."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NOME_PRODUTO = "FreteLucro"

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", RAIZ / "data"))
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

HOST = "127.0.0.1"
PORTA = 8000

FUSO = ZoneInfo("America/Sao_Paulo")

UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_EXTENSOES = {".png", ".jpg", ".jpeg", ".pdf"}


def agora() -> datetime:
    """Data/hora atual em America/Sao_Paulo, sem fuso (é assim que gravamos no banco)."""
    return datetime.now(FUSO).replace(tzinfo=None)


# chave: (valor padrão, rótulo, unidade, grupo)
LIMIARES = {
    "margem_meta_pct": (12.0, "Meta de margem", "%", "Margem"),
    "margem_semanas": (4, "Janela da margem média de rota/cliente", "semanas", "Margem"),
    "margem_min_viagens": (3, "Mínimo de viagens na janela", "viagens", "Margem"),
    "custo_pneu_por_km": (0.35, "Custo de pneu por km", "R$/km", "Custos"),
    "preco_diesel_padrao": (6.20, "Preço do diesel sem histórico recente", "R$/l", "Custos"),
    "manut_janela_dias": (180, "Janela do custo de manutenção por km", "dias", "Custos"),
    "consumo_atencao_pct": (15.0, "Consumo pior que a média: atenção acima de", "%", "Combustível"),
    "consumo_critico_pct": (25.0, "Consumo pior que a média: crítico acima de", "%", "Combustível"),
    "consumo_janela": (5, "Intervalos usados na média", "intervalos", "Combustível"),
    "tanque_fator": (1.05, "Litros acima do tanque: fator de tolerância", "× tanque", "Combustível"),
    "abast_intervalo_h": (6.0, "Dois abastecimentos em menos de", "horas", "Combustível"),
    "preco_acima_pct": (20.0, "Preço/litro acima da mediana", "%", "Combustível"),
    "preco_janela_dias": (7, "Janela da mediana de preço", "dias", "Combustível"),
    "km_vazio_pct": (30.0, "Viagem com km vazio acima de", "%", "Retorno vazio"),
    "canhoto_atencao_dias": (5, "Canhoto pendente: atenção após", "dias", "Canhotos"),
    "canhoto_critico_dias": (15, "Canhoto pendente: crítico após", "dias", "Canhotos"),
    "manut_avencer_pct": (10.0, "Plano a vencer: restando até", "% do intervalo", "Manutenção"),
    "manut_avencer_dias": (15, "Plano a vencer: restando até", "dias", "Manutenção"),
    "corretivas_qtd": (3, "Corretivas reincidentes: a partir de", "OS", "Manutenção"),
    "corretivas_dias": (90, "Corretivas reincidentes: janela", "dias", "Manutenção"),
    "doc_avencer_dias": (30, "Documento vencendo em até", "dias", "Documentos"),
    "mdfe_encerrar_dias": (1, "MDF-e não encerrado após a entrega", "dias", "Fiscal"),
    "jornada_direcao_h": (5.5, "Direção contínua acima de", "horas", "Jornada"),
    "jornada_descanso_h": (11.0, "Descanso entre jornadas abaixo de", "horas", "Jornada"),
    "jornada_diaria_h": (10.0, "Jornada diária acima de", "horas", "Jornada"),
}
