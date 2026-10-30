# Decisões e suposições

Registro das decisões não bloqueantes tomadas durante a construção. Sem dúvidas bloqueantes até aqui.

## Abordagem mais simples adotada

- **Sem camada de API/JSON separada**: as telas são renderizadas no servidor; os dados dos gráficos vão embutidos na página como JSON.
- **Sem migrações (Alembic)**: o banco é um arquivo de demonstração, recriado por `create_all` e pelo seed. Em uso real será preciso adicionar migrações.
- **Motor de alertas recalcula tudo a cada gravação** em vez de reavaliar só o registro alterado. A frota é pequena, o custo é baixo e isso elimina a classe inteira de bugs de "alerta desatualizado".

## Arquitetura

- **Sessão síncrona do SQLAlchemy** com endpoints `def`: mais simples que async, e o SQLite local não ganha nada com async.
- **`app/ui.py` e `app/forms.py`** foram acrescentados à estrutura sugerida: filtros de formatação pt-BR/render e validação de formulário com mensagem junto ao campo. Sem eles, cada router repetiria a mesma lógica.
- **`app/services/consultas.py`** concentra a montagem de dados do banco para as funções puras (DRE em lote, agregações usadas por painel e fichas). `regras.py` não importa SQLAlchemy.
- **Datas/horas** são gravadas sem fuso, sempre em horário de America/Sao_Paulo (`config.agora()`). `tzdata` é dependência porque o Windows não traz a base de fusos.
- **Dinheiro em `Float`**: suficiente para o MVP (sem fechamento contábil); a exibição arredonda em 2 casas. Em uso real, avaliar `Numeric`.
- **Servidor só em 127.0.0.1**: não há login, então não expomos a aplicação na rede. Uso em tablet significa layout responsivo, não acesso remoto.

## Instalação offline

O critério "roda do zero sem internet" vale também para as dependências Python, e `pip install` precisa de rede. Por isso o repositório inclui `vendor/wheels/` (cerca de 32 MB), com versões fixadas para Python 3.11 a 3.14 em Windows x64, Linux x86_64 e macOS ARM. Os scripts tentam primeiro o wheelhouse e, se não servir (ex.: Mac Intel), recorrem ao PyPI. `greenlet` fica de fora: só é necessário para asyncio do SQLAlchemy, e por isso a instalação usa `--no-deps` com a lista completa em `requirements.txt`.

## Interpretação de regras de negócio

- **Comissão**: `comissao_pct` guarda o percentual (8 = 8%).
- **Dias da viagem** (custo fixo): arredondado para cima, mínimo 1. Sem `chegada_em`, usa `rota.tempo_estimado_h`.
- **Manutenção rateada**: custo/km = soma das OS do veículo nos 180 dias anteriores a *hoje* ÷ km das viagens realizadas do veículo nessa janela. Janela relativa à data da viagem deixaria as primeiras viagens com taxas erráticas (poucos km no denominador).
- **Preço médio recente** (combustível estimado): total R$ ÷ total de litros de toda a frota nos últimos 30 dias; sem dados, usa `preco_diesel_padrao` (item adicional de Configurações).
- **Consumo medido**: entre abastecimentos de tanque cheio consecutivos. Abastecimentos parciais no meio somam seus litros ao denominador (sem parciais, é exatamente a fórmula pedida). Intervalos com odômetro não crescente são descartados: já são alerta próprio.
- **Alerta de consumo**: cada intervalo é comparado à média dos 5 intervalos anteriores do mesmo veículo. Exige ao menos 3 intervalos anteriores.
- **Preço/litro acima da mediana**: mediana de toda a frota nos 7 dias anteriores ao abastecimento, com no mínimo 3 amostras.
- **UFs da rota**: origem, destino e o campo adicional `Rota.ufs_passagem` (ex.: "MG,PR"). Sem ele, abastecer em MG numa rota SP–Goiânia seria falso positivo.
- **Margem**: alertas consideram viagens em trânsito, entregues e faturadas (planejadas e canceladas não têm resultado). Margem média de rota/cliente é agregada: Σ margem ÷ Σ receita.
- **Jornada**: registros de trabalho (direção e espera) separados por menos de 4 h pertencem à mesma jornada. Descanso entre jornadas é o intervalo entre jornadas. Jornada diária soma apenas direção, pois a Lei 13.103/2015 não computa o tempo de espera. Direção contínua funde trechos separados por menos de 30 min.
- **Documentos**: motoristas e veículos com status inativo não geram alerta.
- **Custo de parada**: dias parados × (frete das viagens do veículo nos últimos 90 dias ÷ 90).
- **Resolução manual de alerta**: permanece resolvido enquanto a condição persistir. Se a condição sumir e depois voltar, o alerta reabre.
- **Exclusão de cadastro com histórico** é bloqueada com mensagem sugerindo marcar como inativo.
- **Consumo com erro de odômetro**: intervalo com odômetro regressivo é descartado. Se a leitura seguinte mostrar que foi erro de digitação (e não troca de odômetro), o intervalo vizinho à leitura errada também sai, pois teria km absurdo e distorceria a média do alerta de consumo. É erro de digitação quando a leitura seguinte volta ao valor de antes da regressão ou passa dele, mesmo que a leitura errada se repita; abaixo disso, é troca de odômetro. Parcial antes do primeiro tanque cheio é ignorado.
- **Janelas de dias** (manutenção, preço médio, frete médio) são fechadas nas duas pontas: de hoje − N até hoje. Viagens entram na janela pela data de saída.
- **Limiar inválido no banco** (texto, `nan`, `inf`): vale o padrão de `config.LIMIARES`.
- **Bordas de vencimento**: plano com saldo exatamente zero ou documento que vence hoje ainda são "a vencer"; vencido só com saldo negativo.
- **Direção contínua** soma só o tempo dirigindo, sem as pausas curtas fundidas. Registros de direção sobrepostos ou duplicados contam uma vez só, inclusive na jornada diária.
- **Retorno**: ganho potencial = valor da carga, pois o km vazio de volta já seria rodado de qualquer forma. Cidade igual em outra UF é outra cidade e não casa.

## Cadastros

- **Placa**: normalizada em maiúsculas. A antiga é gravada com hífen (`ABC-1234`, mesmo digitada sem) e a Mercosul sem (`ABC1D23`), para que a mesma placa escrita de dois jeitos seja barrada como duplicada.
- **CPF/CNPJ**: só formato, com ou sem pontuação, gravados sempre com máscara. CPF tem 11 dígitos. CNPJ tem 12 letras ou dígitos seguidos de 2 dígitos, para aceitar o alfanumérico da IN RFB 2.229/2024 (vigência de julho de 2026 tomada de conhecimento externo). A busca encontra com ou sem pontuação. Duplicidade não é bloqueada: não foi pedida.
- **UF**: as 27 siglas reais; minúsculas digitadas são convertidas. Na tela é uma lista de seleção.
- **Ano do veículo**: de 1980 até o ano atual + 1 (modelo do ano seguinte).
- **Zero**: capacidade, tanque, consumo de referência, distância e tempo estimado precisam ser maiores que zero (entram em divisões ou não fazem sentido zerados). Os demais valores aceitam zero, mas não negativo.
- **Documento vencido pode ser cadastrado**: é justamente o que os alertas precisam detectar.
- **Cliente e rota não têm status**: ao bloquear a exclusão, a mensagem explica o motivo, sem sugerir "inativo" (só veículo e motorista têm esse status).
- **Campos numéricos em `type=text` com `inputmode`**: o `type=number` do Chromium/Edge em pt-BR transforma `1.234,56` em `1.23456` antes do envio e apaga o que não entende. A macro continua recebendo `tipo='number'`, e quem interpreta é `Form.numero`.
- **Ponto em número**: seguido de grupos de exatamente 3 dígitos é milhar (`1.234` = 1234; `0.125` continua decimal, pois milhar não começa com zero). Nos demais casos é decimal (`7.25`). Agrupamento incoerente (`1.23,45`) e notação como `1e5` são recusados.
- **Dados cadastrais sem arredondar**: fichas, listas e edição mostram as casas que o valor tem (filtro `exato`, até 6 casas), para conferir o que entra na DRE. Dinheiro segue em 2 casas.
- **Ordenação das listas por nome em memória**, sem diferenciar maiúsculas nem acentos, pelo mesmo motivo da busca.
- **Id inválido na URL** (não numérico ou fora do limite do SQLite) cai na mesma página 404. Outros erros de validação de parâmetro mantêm a resposta padrão.
- **Busca em memória**, sem diferenciar maiúsculas nem acentos: o `LIKE` do SQLite não trata "São" e "sao" como iguais, e os cadastros têm dezenas de linhas.
- **Página 404 própria**, para links de alertas ou fichas de registros já excluídos.
- **Resposta 422 em formulário inválido**: o navegador registra no console "Failed to load resource" para qualquer resposta 4xx, mesmo com a página renderizada normalmente. Não é erro de JavaScript; evitar validações no roteiro de demo se o console estiver à vista.
- **Envio duplo**: `app.js` ignora os envios seguintes do mesmo formulário POST enquanto o primeiro aguarda resposta. Sem token no servidor: o app já depende de JavaScript para as confirmações, e a origem do problema é só o navegador. Duplicidade de nome ou documento continua permitida.
- **Envio interrompido** (navegação no meio do POST) não gera traceback: `ClientDisconnect` é tratado em `main.py`.
- **Vencimento de documento** (CNH, MOPP, CRLV, seguro): ano até 20 anos antes ou depois do atual. Barra o ano de 2 dígitos (`0026`) e datas como 31/12/9999, que esconderiam a falta de vencimento real; a folga cobre a validade máxima da CNH e documentos vencidos há muito tempo.
