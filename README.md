# PNCP Data Pipeline - Comparativo PB vs PE

Pipeline de dados desenvolvido para o projeto comparativo de compras públicas entre **Paraíba (PB)** e **Pernambuco (PE)** via Portal Nacional de Contratações Públicas (PNCP), estruturado de acordo com o modelo de objetivos e métricas DEILAS.

---

## Bases de Dados Utilizadas

O projeto integra três bases de dados públicas oficiais para cruzar as compras governamentais com os indicadores socioeconômicos dos municípios:

1. **Base de Compras Públicas — PNCP (PB e PE)**

   * **Órgão Mantenedor:** Governo Federal / Ministério da Gestão e da Inovação em Serviços Públicos (SEGES-MGI), instituído pela Lei nº 14.133/2021.
   * **Escopo Territorial e Temporal:** Todos os órgãos municipais, estaduais e federais com atuação na Paraíba (PB) e Pernambuco (PE) no período de 2024 a 2026.
   * **Conteúdo:** Editais de licitação, compras diretas (dispensas e inexigibilidades), valores estimados, objetos licitados, modalidades de contratação e dados dos órgãos compradores.
   * **Links de Acesso:** [Portal PNCP](https://pncp.gov.br) | [API de Consulta de Propostas](https://pncp.gov.br/api/consulta/v1/contratacoes/proposta)
2. **Base de Contas Regionais e PIB Municipal — IBGE SIDRA (Tabela 5938)**

   * **Órgão Mantenedor:** Instituto Brasileiro de Geografia e Estatística (IBGE).
   * **Escopo Territorial:** Cobertura de 100% dos municípios analisados: 223 municípios da Paraíba e 185 municípios de Pernambuco (408 municípios ao todo).
   * **Conteúdo:** Produto Interno Bruto (PIB) a preços correntes e valor adicionado bruto municipal (série histórica recente consolidada).
   * **Link de Acesso:** [IBGE SIDRA — Tabela 5938 (PIB dos Municípios)](https://sidra.ibge.gov.br/tabela/5938)
3. **Base Demográfica Municipal — IBGE SIDRA (Tabelas 4709 e 6579)**

   * **Órgão Mantenedor:** Instituto Brasileiro de Geografia e Estatística (IBGE).
   * **Escopo Territorial:** Todos os 408 municípios de PB e PE.
   * **Conteúdo:** População residente oficial do Censo Demográfico 2022 (Tabela 4709) e Estimativas Populacionais Anuais (Tabela 6579), utilizadas para calcular os indicadores de gasto público por habitante e renda per capita.
   * **Links de Acesso:** [IBGE SIDRA — Tabela 4709 (Censo 2022)](https://sidra.ibge.gov.br/tabela/4709) | [IBGE SIDRA — Tabela 6579 (Estimativas)](https://sidra.ibge.gov.br/tabela/6579)

---

## Etapas do Projeto

O ciclo de vida do projeto está dividido em cinco etapas fundamentais:

```text
[ 1. Extração ] ──> [ 2. ETL ] ──> [ 3. Testes de Validação ] ──> [ 4. Carga no Banco ] ──> [ 5. Power BI ]
```

### 1. Extração dos Dados

* Consumo automatizado dos endpoints públicos da API de Consulta do PNCP (`pncp.gov.br/api/consulta`) e da API SIDRA do IBGE (`apisidra.ibge.gov.br`).
* Orquestração via **Prefect** (`@flow` e `@task`) com retentativas automáticas (`retries=2`) em caso de instabilidade.
* Filtro aplicado para contratações no status de recebimento de proposta (`status=recebendo_proposta`) para as UFs `PB` e `PE`.
* Tratamento de paginação, controle de taxa de requisições com backoff exponencial contra HTTP 429 e registro de auditoria em `logs/pipeline.log`.
* Armazenamento dos dados brutos sem perdas em `data/dados_brutos_pncp.json`.
* **Scripts:** `download_pncp.py` e `atualizar_ibge.py`

### 2. ETL (Extração, Transformação e Carga)

* Orquestrado via **Prefect** (`flow_etl_pncp`), com leitura local dos dados brutos da pasta `data/` e logs estruturados em `logs/pipeline.log`.
* Limpeza e higienização de textos, normalização de caracteres, remoção de tags de portais e tratamento de valores nulos.
* Formatação padronizada de identificadores (CNPJ), moedas (R$) e datas (ISO e padrão brasileiro).
* Upsert incremental e idempotente por `ID Contratação PNCP`, removendo automaticamente editais revogados, anulados, suspensos ou cancelados.
* Cruzamento socioeconômico prioritário pelo **`Código IBGE do Município`** (7 dígitos) vindo da API (com fallback por nome normalizado + UF).
* Enriquecimento das variáveis analíticas do modelo DEILAS:
  * Níveis de Governo (Municipal, Estadual, Federal) e Poderes (Executivo, Legislativo, Judiciário).
  * Classificação setorial temática (`Setor / Área`) priorizando **o item/serviço adquirido no `Objeto`** (com secretaria/órgão apenas como fallback).
  * Indicador de Capital vs Interior (João Pessoa e Recife).
  * Modalidade da compra (Compra Direta sem disputa vs Disputa Aberta).
  * Indicador de transparência (`Status do Valor`: informado vs zerado ou sigiloso) e classificação em `Faixa de PIB per Capita`.
* Geração do arquivo tabular consolidado (40 colunas) em `data/editais_pncp_PB_PE.csv`.
* **Script:** `pncp_etl.py`

### 3. Realização de Testes para Validação ao Banco

* Suíte automatizada com **33 testes em `pytest`** (`test_pipeline.py`) executada localmente e nos workflows do GitHub Actions antes de qualquer gravação final.
* Testes unitários e de integração isolados com `tmp_path` e `monkeypatch` para os módulos `download_pncp.py`, `atualizar_ibge.py` e `pncp_etl.py`.
* Validação de esquema (40 colunas obrigatórias), unicidade da chave primária (`ID Contratação PNCP`) e integridade referencial 100% da chave estrangeira (`Código IBGE do Município`).
* Checagem de tipagem numérica para SQL (`INT`/`FLOAT`), regras de negócio DEILAS, registro de `@flow`/`@task` do Prefect e geração de logs em `logs/pipeline.log`.

### 4. Inserção no Banco de Dados

* Criação da estrutura de tabelas no banco de dados relacional (PostgreSQL / MySQL / SQLite).
* Ingestão dos registros tratados da tabela de editais e metadados associados.
* Indexação de colunas estratégicas para consultas rápidas (`UF`, `Município`, `Setor`, `Esfera`, `Data de Publicação`).

### 5. Visualização e Dashboards no Power BI

* Conexão do Power BI diretamente ao banco de dados ou ao arquivo CSV tratado.
* Modelagem dimensional e criação de medidas analíticas em DAX.
* Desenvolvimento dos relatórios e painéis interativos para responder às 7 perguntas de negócio do modelo DEILAS (enriquecido com o PIB Municipal do IBGE):
  1. **Volume Global:** Comparativo de volume financeiro previsto e processos abertos entre PB e PE.
  2. **Competitividade:** Qual estado prefere comprar direto de uma empresa e qual prefere abrir disputa para várias empresas concorrerem pelo melhor preço?
  3. **Concentração Econômica e Espacial:** O dinheiro das compras públicas acompanha o tamanho da economia (PIB) de cada cidade ou fica concentrado demais nas capitais?
  4. **Nível de Governo e Poderes:** Quem gasta mais em cada estado: as prefeituras, o governo estadual ou os órgãos federais?
  5. **Alocação Setorial:** Para onde vai o dinheiro público: quais áreas (Saúde, Educação, Obras, Transporte, TI) concentram a maior parte dos gastos?
  6. **Intensidade Econômica Municipal:** Quanto o dinheiro das prefeituras pesa na economia real de cada município? Existem cidades dependentes das compras públicas para movimentar o seu PIB?
  7. **Riqueza per Capita e Governança:** As cidades com maior renda (PIB per capita) gastam mais por habitante e conseguem preços melhores com mais concorrência do que cidades mais vulneráveis?

---

## Estrutura do Repositório

```text
pncp-data-pipeline/
├── .github/                      # Automacoes e CI/CD
│   └── workflows/
│       ├── pipeline.yml          # Workflow diario do PNCP (Prefect + Pytest)
│       └── ibge_anual.yml        # Workflow anual do IBGE (Prefect + Pytest)
├── data/                         # Armazena os dados do projeto
│   ├── .gitkeep
│   ├── dados_ibge_ufs.csv        # Serie historica oficial do IBGE por Estado (PIB e Populacao)
│   ├── dados_ibge_municipios.csv # Serie historica oficial do IBGE por Municipio (PIB e PIB per capita)
│   ├── dados_brutos_pncp.json    # JSON bruto baixado da API (Etapa 1)
│   └── editais_pncp_PB_PE.csv    # Planilha tratada e consolidada (Etapa 2)
├── logs/                         # Logs rotativos de execucao (gerado automaticamente)
│   └── pipeline.log
├── atualizar_ibge.py             # Script Prefect que consulta a API SIDRA do IBGE (UFs e Municipios)
├── download_pncp.py              # Script Prefect da Etapa 1: Extracao da API do PNCP
├── pncp_etl.py                   # Script Prefect da Etapa 2: Transformacao, limpeza e regras DEILAS
├── test_pipeline.py              # Suite de testes unitarios, integracao e Data Quality (pytest)
├── requirements.txt              # Dependencias do projeto (requests, python-dateutil, pytest, prefect)
├── .gitignore                    # Regras de exclusao do Git (.venv, .vscode, JSONs brutos, logs)
└── README.md                     # Documentacao do projeto
```

---

## Como Executar o Pipeline Localmente

### 1. Criar ambiente virtual e instalar as dependências

```bash
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Executar a Extração (Etapa 1)

```bash
python download_pncp.py
```

*Gera: `data/dados_brutos_pncp.json` e registra eventos em `logs/pipeline.log`*

### 3. Executar o ETL (Etapa 2)

```bash
python pncp_etl.py
```

*Gera: `data/editais_pncp_PB_PE.csv` e registra eventos em `logs/pipeline.log`*

### 4. Executar os Testes de Validação (Etapa 3)

```bash
pytest -v
```

*Executa os 33 testes de unidade, integração e qualidade de dados antes da carga no banco.*

---

## Execucao Automatizada via GitHub Actions

O projeto conta com dois workflows automatizados em `.github/workflows/`:

### 1. Pipeline PNCP (`.github/workflows/pipeline.yml`)

* Executa a extracao (`download_pncp.py`), o ETL (`pncp_etl.py`) orquestrados com **Prefect** e valida toda a base com **`pytest -v`** antes de commitar.
* Pode ser acionado manualmente pela aba **Actions** no GitHub (gatilho `workflow_dispatch`).
* Roda de forma agendada diariamente as 06:00 BRT (09:00 UTC).
* Caso os 33 testes passem, salva e commita o arquivo final `data/editais_pncp_PB_PE.csv` diretamente no repositório GitHub (sem ZIP).

### 2. Atualizacao Anual do PIB IBGE (`.github/workflows/ibge_anual.yml`)

* Executa o script `atualizar_ibge.py` via **Prefect**, consumindo a API oficial SIDRA do IBGE (Tabelas 5938, 6579 e 4709), seguido da validação com **`pytest -v`**.
* Roda anualmente a partir da segunda semana de novembro (`dias 8 a 22 de novembro`, as 09:00 BRT / 12:00 UTC), fazendo 1 tentativa (retry) por dia ate o IBGE publicar a nova edicao das Contas Regionais (ex: PIB de 2024 em novembro de 2026).
* Assim que o novo ano e detectado na API do IBGE e validado nos testes, atualiza e commita automaticamente os arquivos `data/dados_ibge_ufs.csv` e `data/dados_ibge_municipios.csv`. Nos dias seguintes da janela, identifica que o ano-alvo ja foi salvo e encerra imediatamente sem novas requisicoes.

---

## Estrutura da pasta data/

* `data/dados_ibge_ufs.csv`: Tabela dimensão com dados demográficos e econômicos estaduais do IBGE (PIB, população, crescimento real).
* `data/dados_ibge_municipios.csv`: Tabela dimensão com PIB municipal, população e PIB per capita de todos os 408 municípios de PB e PE (2020 a 2023).
* `data/editais_pncp_PB_PE.csv`: Base tratada e consolidada de editais (atualizada automaticamente pelo pipeline e versionada diretamente como CSV).
* `data/dados_brutos_pncp.json`: Arquivo bruto em JSON contendo as contratações públicas extraídas diretamente da API do PNCP (Etapa 1).
* `data/dados_brutos_ibge_pib.json`: Arquivo bruto em JSON com as respostas da API SIDRA do IBGE para o PIB municipal (Tabela 5938).
* `data/dados_brutos_ibge_populacao.json`: Arquivo bruto em JSON com a população municipal oficial do Censo 2022 do IBGE (Tabela 4709).
