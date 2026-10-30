import asyncio
import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import agora
from app.forms import Form
from app.main import app
from app.models import Cliente, Config, Motorista, Rota, Veiculo, Viagem
from app.routers.clientes import normalizar_cnpj
from app.routers.motoristas import normalizar_cpf
from app.routers.veiculos import normalizar_placa
from app.ui import numero_exato, selo_vencimento

VEICULO = {
    "placa": "abc1d23",
    "tipo": "truck",
    "modelo": "Volvo VM 270",
    "ano": "2021",
    "capacidade_kg": "14000",
    "tanque_l": "300",
    "consumo_ref_kmpl": "3,5",
    "odometro_km": "120000",
    "custo_fixo_mensal": "1.234,56",
    "venc_crlv": "2027-03-01",
    "venc_seguro": "2027-05-01",
    "cidade_base": "Campinas",
    "uf_base": "SP",
    "status": "ativo",
}
MOTORISTA = {
    "nome": "João da Silva",
    "cpf": "12345678900",
    "cnh_categoria": "E",
    "venc_cnh": "2027-01-10",
    "venc_mopp": "",
    "comissao_pct": "8",
    "diaria_valor": "120",
    "status": "ativo",
}
CLIENTE = {"nome": "Comercial Alfa Ltda", "cnpj": "12345678000190"}
ROTA = {
    "nome": "São Paulo – Curitiba",
    "origem_cidade": "São Paulo",
    "origem_uf": "SP",
    "destino_cidade": "Curitiba",
    "destino_uf": "PR",
    "ufs_passagem": "",
    "distancia_km": "410",
    "pedagio_estimado": "95,50",
    "tempo_estimado_h": "7",
    "frete_tabela": "3200",
}

# tela, modelo, dados válidos, campo de texto a editar
ENTIDADES = [
    ("veiculos", Veiculo, VEICULO, "modelo"),
    ("motoristas", Motorista, MOTORISTA, "nome"),
    ("clientes", Cliente, CLIENTE, "nome"),
    ("rotas", Rota, ROTA, "nome"),
]
IDS = [e[0] for e in ENTIDADES]


def _unico(db, modelo):
    db.expire_all()
    return db.scalars(select(modelo)).one()


def _total(db, modelo):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(modelo))


def _viagem(db) -> Viagem:
    veiculo = Veiculo(
        placa="AAA1A11", tipo="truck", modelo="M", ano=2020, capacidade_kg=1, tanque_l=1, consumo_ref_kmpl=1,
        odometro_km=0, custo_fixo_mensal=0, venc_crlv=date(2027, 1, 1), venc_seguro=date(2027, 1, 1),
        cidade_base="Campinas", uf_base="SP",
    )
    motorista = Motorista(nome="M", cpf="111.111.111-11", cnh_categoria="E", venc_cnh=date(2027, 1, 1), comissao_pct=0, diaria_valor=0)
    cliente = Cliente(nome="C", cnpj="11.111.111/0001-11")
    rota = Rota(
        nome="R", origem_cidade="A", origem_uf="SP", destino_cidade="B", destino_uf="RJ",
        distancia_km=1, pedagio_estimado=0, tempo_estimado_h=1, frete_tabela=0,
    )
    viagem = Viagem(veiculo=veiculo, motorista=motorista, cliente=cliente, rota=rota, saida_em=datetime(2026, 10, 1), frete_valor=100)
    db.add(viagem)
    db.commit()
    return viagem


@pytest.mark.parametrize("tela,modelo,dados,campo", ENTIDADES, ids=IDS)
def test_crud_completo(client, db, tela, modelo, dados, campo):
    # lista vazia, com estado vazio amigável
    resposta = client.get(f"/{tela}")
    assert resposta.status_code == 200
    assert 'class="vazio"' in resposta.text

    assert client.get(f"/{tela}/novo").status_code == 200

    # criar
    resposta = client.post(f"/{tela}/novo", data=dados)
    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith(f"/{tela}?msg=")
    registro = _unico(db, modelo)

    # aparece na lista e na ficha
    lista = client.get(f"/{tela}")
    assert f"/{tela}/{registro.id}" in lista.text
    assert 'class="vazio"' not in lista.text
    assert client.get(f"/{tela}/{registro.id}").status_code == 200

    # editar: formulário preenchido e alteração gravada
    edicao = client.get(f"/{tela}/{registro.id}/editar")
    assert edicao.status_code == 200
    assert f'value="{getattr(registro, campo)}"' in edicao.text
    resposta = client.post(f"/{tela}/{registro.id}/editar", data={**dados, campo: "Nome alterado"})
    assert resposta.status_code == 303
    assert getattr(_unico(db, modelo), campo) == "Nome alterado"

    # excluir
    registro_id = registro.id
    resposta = client.post(f"/{tela}/{registro_id}/excluir")
    assert resposta.status_code == 303
    assert "msg=" in resposta.headers["location"]
    assert _total(db, modelo) == 0
    assert client.get(f"/{tela}/{registro_id}").status_code == 404


@pytest.mark.parametrize("tela,modelo,dados,campo", ENTIDADES, ids=IDS)
def test_id_inexistente_da_404_amigavel(client, tela, modelo, dados, campo):
    resposta = client.get(f"/{tela}/999")
    assert resposta.status_code == 404
    assert "não existe mais" in resposta.text
    assert client.post(f"/{tela}/999/editar", data=dados).status_code == 404
    assert client.post(f"/{tela}/999/excluir").status_code == 404


@pytest.mark.parametrize("tela,modelo,dados,campo", ENTIDADES, ids=IDS)
def test_campo_obrigatorio(client, db, tela, modelo, dados, campo):
    resposta = client.post(f"/{tela}/novo", data={**dados, campo: "  "})
    assert resposta.status_code == 422
    assert "Campo obrigatório." in resposta.text
    assert 'class="erro-campo"' in resposta.text
    assert f'id="erro-{campo}"' in resposta.text
    assert _total(db, modelo) == 0


@pytest.mark.parametrize(
    "tela,modelo,dados,campo",
    [
        ("veiculos", Veiculo, VEICULO, "capacidade_kg"),
        ("veiculos", Veiculo, VEICULO, "tanque_l"),
        ("veiculos", Veiculo, VEICULO, "consumo_ref_kmpl"),
        ("veiculos", Veiculo, VEICULO, "odometro_km"),
        ("veiculos", Veiculo, VEICULO, "custo_fixo_mensal"),
        ("motoristas", Motorista, MOTORISTA, "comissao_pct"),
        ("motoristas", Motorista, MOTORISTA, "diaria_valor"),
        ("rotas", Rota, ROTA, "distancia_km"),
        ("rotas", Rota, ROTA, "pedagio_estimado"),
        ("rotas", Rota, ROTA, "tempo_estimado_h"),
        ("rotas", Rota, ROTA, "frete_tabela"),
    ],
)
def test_negativo_bloqueado(client, db, tela, modelo, dados, campo):
    resposta = client.post(f"/{tela}/novo", data={**dados, campo: "-1"})
    assert resposta.status_code == 422
    assert "O valor não pode ser negativo." in resposta.text
    assert f'id="erro-{campo}"' in resposta.text
    assert _total(db, modelo) == 0


def test_formulario_com_erro_preserva_o_que_foi_digitado(client):
    resposta = client.post("/veiculos/novo", data={**VEICULO, "modelo": "Modelo digitado", "tanque_l": "-1"})
    assert 'value="Modelo digitado"' in resposta.text
    assert 'value="-1"' in resposta.text


@pytest.mark.parametrize(
    "campo,valor,mensagem",
    [
        ("consumo_ref_kmpl", "0", "maior que zero"),
        ("tanque_l", "abc", "número válido"),
        ("ano", "1950", "mínimo é 1980"),
        ("ano", str(agora().year + 2), "O valor máximo"),
        ("ano", "2020,5", "número inteiro"),
        ("uf_base", "XX", "UF inválida"),
        ("uf_base", "S", "UF inválida"),
        ("venc_crlv", "31/12/2026", "data válida"),
        ("placa", "ABC12", "Placa inválida"),
        ("placa", "1BC1D23", "Placa inválida"),
        ("tipo", "bitrem", "Opção inválida"),
    ],
)
def test_validacoes_de_veiculo(client, db, campo, valor, mensagem):
    resposta = client.post("/veiculos/novo", data={**VEICULO, campo: valor})
    assert resposta.status_code == 422
    assert mensagem in resposta.text
    assert _total(db, Veiculo) == 0


def test_placa_normalizada():
    assert normalizar_placa("abc1d23") == "ABC1D23"
    assert normalizar_placa("ABC-1D23") == "ABC1D23"
    assert normalizar_placa("abc-1234") == "ABC-1234"
    assert normalizar_placa("ABC1234") == "ABC-1234"
    assert normalizar_placa("ABCD123") is None
    assert normalizar_placa("AB-12345") is None


@pytest.mark.parametrize("repetida", ["ABC1D23", "abc1d23", "abc-1d23"])
def test_placa_duplicada_mercosul(client, db, repetida):
    assert client.post("/veiculos/novo", data=VEICULO).status_code == 303
    resposta = client.post("/veiculos/novo", data={**VEICULO, "placa": repetida})
    assert resposta.status_code == 422
    assert "Já existe um veículo com a placa ABC1D23." in resposta.text
    assert 'id="erro-placa"' in resposta.text
    assert _total(db, Veiculo) == 1


def test_placa_antiga_com_e_sem_hifen_e_a_mesma(client, db):
    assert client.post("/veiculos/novo", data={**VEICULO, "placa": "abc-1234"}).status_code == 303
    assert _unico(db, Veiculo).placa == "ABC-1234"
    assert client.post("/veiculos/novo", data={**VEICULO, "placa": "ABC1234"}).status_code == 422


def test_editar_mantendo_a_propria_placa_e_permitido(client, db):
    client.post("/veiculos/novo", data=VEICULO)
    veiculo = _unico(db, Veiculo)
    assert client.post(f"/veiculos/{veiculo.id}/editar", data={**VEICULO, "modelo": "Outro"}).status_code == 303


def test_editar_para_placa_de_outro_veiculo_e_bloqueado(client, db):
    client.post("/veiculos/novo", data=VEICULO)
    client.post("/veiculos/novo", data={**VEICULO, "placa": "XYZ9K88"})
    db.expire_all()
    segundo = db.scalar(select(Veiculo).where(Veiculo.placa == "XYZ9K88"))
    resposta = client.post(f"/veiculos/{segundo.id}/editar", data=VEICULO)
    assert resposta.status_code == 422
    assert "Já existe um veículo" in resposta.text
    db.expire_all()
    assert db.get(Veiculo, segundo.id).placa == "XYZ9K88"


def test_valores_gravados_normalizados_e_exibidos_em_ptbr(client, db):
    client.post("/veiculos/novo", data={**VEICULO, "uf_base": "sp"})
    veiculo = _unico(db, Veiculo)
    assert veiculo.placa == "ABC1D23"
    assert veiculo.uf_base == "SP"
    assert veiculo.custo_fixo_mensal == 1234.56
    assert veiculo.venc_crlv == date(2027, 3, 1)
    ficha = client.get(f"/veiculos/{veiculo.id}").text
    assert "R$ 1.234,56" in ficha
    assert "01/03/2027" in ficha


def test_validacoes_de_motorista(client, db):
    for valor in ("123", "1234567890a", "123456789012"):
        resposta = client.post("/motoristas/novo", data={**MOTORISTA, "cpf": valor})
        assert resposta.status_code == 422 and "CPF inválido" in resposta.text
    resposta = client.post("/motoristas/novo", data={**MOTORISTA, "comissao_pct": "101"})
    assert resposta.status_code == 422 and "O valor máximo é 100." in resposta.text
    assert _total(db, Motorista) == 0

    assert client.post("/motoristas/novo", data={**MOTORISTA, "cpf": "123.456.789-00"}).status_code == 303
    motorista = _unico(db, Motorista)
    assert motorista.cpf == "123.456.789-00"
    assert motorista.venc_mopp is None
    assert "Não possui" in client.get(f"/motoristas/{motorista.id}").text


def test_cpf_e_cnpj_normalizados():
    assert normalizar_cpf("12345678900") == "123.456.789-00"
    assert normalizar_cnpj("12345678000190") == "12.345.678/0001-90"
    assert normalizar_cnpj("12.345.678/0001-90") == "12.345.678/0001-90"
    assert normalizar_cnpj("1234567800019") is None


def test_validacao_de_cnpj(client, db):
    resposta = client.post("/clientes/novo", data={**CLIENTE, "cnpj": "12.345"})
    assert resposta.status_code == 422 and "CNPJ inválido" in resposta.text
    assert _total(db, Cliente) == 0


def test_validacoes_de_rota(client, db):
    assert client.post("/rotas/novo", data={**ROTA, "origem_uf": "ZZ"}).status_code == 422
    resposta = client.post("/rotas/novo", data={**ROTA, "ufs_passagem": "MG,QQ"})
    assert resposta.status_code == 422 and "UF inválida: QQ" in resposta.text
    assert _total(db, Rota) == 0

    assert client.post("/rotas/novo", data={**ROTA, "ufs_passagem": "mg, pr pr"}).status_code == 303
    assert _unico(db, Rota).ufs_passagem == "MG,PR"


@pytest.mark.parametrize(
    "tela,modelo,atributo,mensagem",
    [
        ("veiculos", Veiculo, "veiculo_id", "marque como Inativo"),
        ("motoristas", Motorista, "motorista_id", "marque como Inativo"),
        ("clientes", Cliente, "cliente_id", "não pode ser excluído"),
        ("rotas", Rota, "rota_id", "não pode ser excluída"),
    ],
    ids=IDS,
)
def test_exclusao_com_historico_bloqueada(client, db, tela, modelo, atributo, mensagem):
    registro_id = getattr(_viagem(db), atributo)
    resposta = client.post(f"/{tela}/{registro_id}/excluir")
    assert resposta.status_code == 303
    assert "erro=" in resposta.headers["location"]
    assert db.get(modelo, registro_id) is not None
    # o aviso aparece na tela para a qual o usuário é levado
    pagina = client.get(resposta.headers["location"])
    assert 'class="aviso aviso-erro"' in pagina.text
    assert mensagem in pagina.text
    assert _total(db, modelo) == 1


def test_busca_ignora_maiusculas_e_acentos(client):
    client.post("/rotas/novo", data=ROTA)
    client.post("/rotas/novo", data={**ROTA, "nome": "Santos – Campinas", "origem_cidade": "Santos", "destino_cidade": "Campinas", "destino_uf": "SP"})
    pagina = client.get("/rotas", params={"q": "SAO paulo"}).text
    assert "Curitiba" in pagina and "Santos – Campinas" not in pagina
    vazio = client.get("/rotas", params={"q": "Manaus"})
    assert "Nenhuma rota encontrada" in vazio.text and "Manaus" in vazio.text


def test_busca_de_placa_antiga_sem_hifen(client):
    client.post("/veiculos/novo", data={**VEICULO, "placa": "ABC-1234"})
    assert "ABC-1234" in client.get("/veiculos", params={"q": "abc1234"}).text


@pytest.mark.parametrize(
    "dias,esperado",
    [
        (-5, '<span class="selo selo-critico">Vencido há 5 dias</span>'),
        (-1, '<span class="selo selo-critico">Vencido há 1 dia</span>'),
        (0, '<span class="selo selo-atencao">Vence hoje</span>'),
        (1, '<span class="selo selo-atencao">Vence em 1 dia</span>'),
        (30, '<span class="selo selo-atencao">Vence em 30 dias</span>'),
        (31, '<span class="selo selo-ok">Em dia</span>'),
    ],
)
def test_selo_de_vencimento(dias, esperado):
    assert selo_vencimento({"doc_avencer_dias": 30}, agora().date() + timedelta(days=dias)) == esperado


def test_selo_de_vencimento_sem_data():
    assert "Não informado" in selo_vencimento({"doc_avencer_dias": 30}, None)


def test_selo_de_vencimento_na_ficha_segue_o_limiar_configurado(client, db):
    hoje = agora().date()
    dados = {**VEICULO, "venc_crlv": (hoje - timedelta(days=2)).isoformat(), "venc_seguro": (hoje + timedelta(days=12)).isoformat()}
    client.post("/veiculos/novo", data=dados)
    veiculo = _unico(db, Veiculo)
    ficha = client.get(f"/veiculos/{veiculo.id}").text
    assert '<span class="selo selo-critico">Vencido há 2 dias</span>' in ficha
    assert '<span class="selo selo-atencao">Vence em 12 dias</span>' in ficha

    db.add(Config(chave="doc_avencer_dias", valor="10"))
    db.commit()
    assert '<span class="selo selo-ok">Em dia</span>' in client.get(f"/veiculos/{veiculo.id}").text


@pytest.mark.parametrize(
    "digitado,esperado",
    [
        ("1234.56", 1234.56),
        ("1234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("1.234", 1234),
        ("25.000", 25000),
        ("1.234.567", 1234567),
        ("1.234.567,8", 1234567.8),
        ("7.25", 7.25),
        ("926.5", 926.5),
        ("1.23456", 1.23456),
        ("0.125", 0.125),
        ("0,125", 0.125),
        (",5", 0.5),
        ("5,", 5),
    ],
)
def test_numero_em_formato_brasileiro(digitado, esperado):
    form = Form({"x": digitado})
    assert form.numero("x") == pytest.approx(esperado)
    assert form.ok


@pytest.mark.parametrize("digitado", ["1e", "--5", "1e5", "1_000", "1.23,45", "12.34.567", "1,234,567", "1,2.345", "0.125,5", "nan", "inf", "٣", ".", ","])
def test_numero_malformado_e_recusado(digitado):
    form = Form({"x": digitado})
    assert form.numero("x") is None
    assert form.erros["x"] == "Informe um número válido."


@pytest.mark.parametrize("tela", ["veiculos", "motoristas", "rotas"])
def test_campos_numericos_nao_usam_type_number(client, tela):
    # O type=number do navegador em pt-BR troca 1.234,56 por 1.23456 antes do envio.
    pagina = client.get(f"/{tela}/novo").text
    assert 'type="number"' not in pagina
    assert 'inputmode="decimal"' in pagina


def test_milhar_digitado_grava_o_valor_inteiro(client, db):
    dados = {**VEICULO, "capacidade_kg": "25.000", "odometro_km": "120.000", "custo_fixo_mensal": "8.500,50"}
    assert client.post("/veiculos/novo", data=dados).status_code == 303
    veiculo = _unico(db, Veiculo)
    assert (veiculo.capacidade_kg, veiculo.odometro_km, veiculo.custo_fixo_mensal) == (25000, 120000, 8500.5)
    ficha = client.get(f"/veiculos/{veiculo.id}").text
    assert "25.000 kg" in ficha and "120.000 km" in ficha and "R$ 8.500,50" in ficha


@pytest.mark.parametrize("digitado", ["1e", "--5"])
def test_numero_malformado_mostra_mensagem_e_preserva_o_texto(client, db, digitado):
    resposta = client.post("/veiculos/novo", data={**VEICULO, "custo_fixo_mensal": digitado})
    assert resposta.status_code == 422
    assert "Informe um número válido." in resposta.text
    assert f'value="{digitado}"' in resposta.text
    assert _total(db, Veiculo) == 0


def test_salvar_edicao_sem_alterar_mantem_os_valores(client, db):
    dados = {**ROTA, "distancia_km": "1.926,125", "tempo_estimado_h": "14,25", "pedagio_estimado": "0,125", "frete_tabela": "9.800,00"}
    client.post("/rotas/novo", data=dados)
    rota = _unico(db, Rota)
    assert (rota.distancia_km, rota.tempo_estimado_h, rota.pedagio_estimado, rota.frete_tabela) == (1926.125, 14.25, 0.125, 9800)
    edicao = client.get(f"/rotas/{rota.id}/editar").text
    numericos = ("distancia_km", "tempo_estimado_h", "pedagio_estimado", "frete_tabela")
    reenviados = {**dados, **{campo: re.search(rf'name="{campo}"[^>]*value="([^"]*)"', edicao).group(1) for campo in numericos}}
    assert reenviados["distancia_km"] == "1.926,125"
    assert client.post(f"/rotas/{rota.id}/editar", data=reenviados).status_code == 303
    rota = _unico(db, Rota)
    assert (rota.distancia_km, rota.tempo_estimado_h, rota.pedagio_estimado, rota.frete_tabela) == (1926.125, 14.25, 0.125, 9800)


@pytest.mark.parametrize("registro_id", ["abc", "1.5", "99999999999999999999", "9223372036854775808", "-9223372036854775809"])
@pytest.mark.parametrize("tela,modelo,dados,campo", ENTIDADES, ids=IDS)
def test_id_invalido_na_url_da_404_amigavel(client, tela, modelo, dados, campo, registro_id):
    respostas = [
        client.get(f"/{tela}/{registro_id}"),
        client.get(f"/{tela}/{registro_id}/editar"),
        client.post(f"/{tela}/{registro_id}/editar", data=dados),
        client.post(f"/{tela}/{registro_id}/excluir"),
    ]
    for resposta in respostas:
        assert resposta.status_code == 404
        assert "não existe mais" in resposta.text


def test_arquivo_no_lugar_de_campo_de_texto_nao_derruba(client, db):
    resposta = client.post("/clientes/novo", data={"cnpj": CLIENTE["cnpj"]}, files={"nome": ("a.txt", b"x")})
    assert resposta.status_code == 422 and "Campo obrigatório." in resposta.text
    resposta = client.post("/rotas/novo", data=ROTA, files={"ufs_passagem": ("a.txt", b"x")})
    assert resposta.status_code == 303
    assert _unico(db, Rota).ufs_passagem == ""


def test_cnpj_alfanumerico():
    assert normalizar_cnpj("12.ABC.345/01DE-35") == "12.ABC.345/01DE-35"
    assert normalizar_cnpj("12abc34501de35") == "12.ABC.345/01DE-35"
    assert normalizar_cnpj("12ABC34501DEF5") is None  # os 2 últimos são sempre dígitos
    assert normalizar_cnpj("12ABC34501DE3") is None
    assert normalizar_cnpj("12ABC34501DE3$") is None


def test_cadastro_e_busca_de_cnpj_alfanumerico(client, db):
    assert client.post("/clientes/novo", data={**CLIENTE, "cnpj": "12abc34501de35"}).status_code == 303
    assert _unico(db, Cliente).cnpj == "12.ABC.345/01DE-35"
    assert CLIENTE["nome"] in client.get("/clientes", params={"q": "12abc34501de35"}).text


@pytest.mark.parametrize("busca,acha", [("12345678900", True), ("123456", True), ("123.456.789-00", True), ("456.789", True), ("99999", False), ("/", False)])
def test_busca_de_cpf_com_ou_sem_pontuacao(client, busca, acha):
    client.post("/motoristas/novo", data=MOTORISTA)
    assert (MOTORISTA["nome"] in client.get("/motoristas", params={"q": busca}).text) is acha


@pytest.mark.parametrize("busca,acha", [("12345678000190", True), ("12.345.678/0001-90", True), ("678000", True), ("99999", False)])
def test_busca_de_cnpj_com_ou_sem_pontuacao(client, busca, acha):
    client.post("/clientes/novo", data=CLIENTE)
    assert (CLIENTE["nome"] in client.get("/clientes", params={"q": busca}).text) is acha


@pytest.mark.parametrize(
    "tela,dados",
    [("motoristas", MOTORISTA), ("clientes", CLIENTE), ("rotas", ROTA)],
    ids=["motoristas", "clientes", "rotas"],
)
def test_lista_em_ordem_alfabetica_de_ptbr(client, tela, dados):
    for nome in ("Zeta", "Ética Cargas", "alfa log", "Beta"):
        assert client.post(f"/{tela}/novo", data={**dados, "nome": nome}).status_code == 303
    nomes = re.findall(r"<strong>([^<]+)</strong></a>", client.get(f"/{tela}").text)
    assert nomes == ["alfa log", "Beta", "Ética Cargas", "Zeta"]


@pytest.mark.parametrize(
    "valor,esperado",
    [(926.5, "926,5"), (14.25, "14,25"), (25000.0, "25.000"), (0.0, "0"), (1234.56, "1.234,56"), (7.0, "7"), (None, "—")],
)
def test_numero_exato(valor, esperado):
    assert numero_exato(valor) == esperado


def test_ficha_e_lista_nao_arredondam_dados_cadastrais(client, db):
    client.post("/motoristas/novo", data={**MOTORISTA, "comissao_pct": "7.25"})
    motorista = _unico(db, Motorista)
    assert "7,25% do frete" in client.get(f"/motoristas/{motorista.id}").text
    assert "7,25%" in client.get("/motoristas").text

    client.post("/rotas/novo", data={**ROTA, "distancia_km": "926.5", "tempo_estimado_h": "14.25"})
    rota = _unico(db, Rota)
    for pagina in (client.get(f"/rotas/{rota.id}").text, client.get("/rotas").text):
        assert "926,5 km" in pagina and "14,25 h" in pagina

    client.post("/veiculos/novo", data={**VEICULO, "capacidade_kg": "14500,5", "tanque_l": "300,5", "consumo_ref_kmpl": "2,75", "odometro_km": "120000,5"})
    ficha = client.get(f"/veiculos/{_unico(db, Veiculo).id}").text
    assert "14.500,5 kg" in ficha and "300,5 litros" in ficha and "2,75 km/l" in ficha and "120.000,5 km" in ficha


def test_placa_nao_quebra_na_lista(client):
    client.post("/veiculos/novo", data={**VEICULO, "placa": "ABC-1234"})
    assert re.search(r'<td class="nao-quebra"><a href="/veiculos/\d+"><strong>ABC-1234', client.get("/veiculos").text)


@pytest.mark.parametrize("data", ["0026-11-01", "0001-01-01", "9999-12-31"])
@pytest.mark.parametrize("tela, modelo, dados, campo", [
    ("veiculos", Veiculo, VEICULO, "venc_crlv"),
    ("veiculos", Veiculo, VEICULO, "venc_seguro"),
    ("motoristas", Motorista, MOTORISTA, "venc_cnh"),
    ("motoristas", Motorista, MOTORISTA, "venc_mopp"),
])
def test_vencimento_com_ano_implausivel_e_recusado(client, db, tela, modelo, dados, campo, data):
    resposta = client.post(f"/{tela}/novo", data={**dados, campo: data})
    assert resposta.status_code == 422
    assert "Ano improvável" in resposta.text
    assert f'value="{data}"' in resposta.text
    assert db.scalar(select(func.count()).select_from(modelo)) == 0


def test_vencimento_implausivel_e_barrado_tambem_na_edicao(client, db):
    assert client.post("/veiculos/novo", data=VEICULO).status_code == 303
    veiculo = db.scalar(select(Veiculo))
    resposta = client.post(f"/veiculos/{veiculo.id}/editar", data={**VEICULO, "venc_crlv": "0026-11-01"})
    assert resposta.status_code == 422
    db.refresh(veiculo)
    assert veiculo.venc_crlv == date(2027, 3, 1)


@pytest.mark.parametrize("anos, valido", [(-21, False), (-20, True), (0, True), (20, True), (21, False)])
def test_limites_do_vencimento(anos, valido):
    data = date(agora().year + anos, 6, 15)
    form = Form({"venc": data.isoformat()})
    assert form.vencimento("venc") == (data if valido else None)
    assert form.ok is valido


def test_vencimento_opcional_vazio_e_data_invalida():
    form = Form({"venc": "", "ruim": "31/12/2026"})
    assert form.vencimento("venc", obrigatorio=False) is None
    assert form.ok
    assert form.vencimento("ruim") is None
    assert form.erros["ruim"] == "Informe uma data válida."


def test_documento_vencido_recente_continua_aceito(client, db):
    vencido = (agora().date() - timedelta(days=400)).isoformat()
    assert client.post("/veiculos/novo", data={**VEICULO, "venc_crlv": vencido}).status_code == 303


def test_envio_interrompido_nao_gera_excecao():
    mensagens = [{"type": "http.request", "body": b"nome=a", "more_body": True}, {"type": "http.disconnect"}]
    enviadas = []

    async def receber():
        return mensagens.pop(0)

    async def enviar(mensagem):
        enviadas.append(mensagem)

    escopo = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/clientes/novo", "raw_path": b"/clientes/novo", "root_path": "", "query_string": b"",
        "server": ("teste", 80), "client": ("teste", 1),
        "headers": [(b"content-type", b"application/x-www-form-urlencoded"), (b"content-length", b"100")],
    }
    asyncio.run(app(escopo, receber, enviar))
    assert enviadas[0]["status"] == 400
