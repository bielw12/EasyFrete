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
