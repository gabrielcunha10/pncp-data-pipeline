# PNCP Data Pipeline - Comparativo PB vs PE

Pipeline de dados desenvolvido para o projeto comparativo de compras públicas entre **Paraíba (PB)** e **Pernambuco (PE)** via Portal Nacional de Contratações Públicas (PNCP), estruturado de acordo com o modelo de objetivos e métricas DEILAS.

---

## Etapas do Projeto

O ciclo de vida do projeto está dividido em cinco etapas fundamentais:

```text
[ 1. Extração ] ──> [ 2. ETL ] ──> [ 3. Testes de Validação ] ──> [ 4. Carga no Banco ] ──> [ 5. Power BI ]
```

### 1. Extração dos Dados
* Consumo automatizado dos endpoints públicos da API de Consulta do PNCP (`pncp.gov.br/api/consulta`).
* Filtro aplicado para contratações no status de recebimento de proposta (`status=recebendo_proposta`) para as UFs `PB` e `PE`.
* Tratamento de paginação e controle de taxa de requisições com retentativas automáticas e backoff exponencial contra HTTP 429.
* Armazenamento dos dados brutos sem perdas em `data/dados_brutos_pncp.json`.
* **Script:** `download_pncp.py`

### 2. ETL (Extração, Transformação e Carga)
* Leitura local dos dados brutos da pasta `data/`.
* Limpeza e higienização de textos, normalização de caracteres e tratamento de valores nulos.
* Formatação padronizada de identificadores (CNPJ), moedas (R$) e datas (ISO e padrão brasileiro).
* Enriquecimento das variáveis analíticas do modelo DEILAS:
  * Níveis de Governo (Municipal, Estadual, Federal).
  * Poderes (Executivo, Legislativo, Judiciário).
  * Classificação setorial temática (Saúde, Educação, Obras, Transporte, Informática, Outros).
  * Indicador de Capital vs Interior (João Pessoa e Recife).
  * Modalidade da compra (Compra Direta sem disputa vs Disputa Aberta).
  * Indicador de transparência (valores informados vs zerados ou sigilosos).
* Geração do arquivo tabular consolidado em `data/editais_pncp_PB_PE.csv`.
* **Script:** `pncp_etl.py`

### 3. Realização de Testes para Validação ao Banco
* Validação do esquema e dos tipos de dados antes do carregamento no banco.
* Verificação de chaves primárias e unicidade (ID Contratação PNCP).
* Checagem de integridade referencial e consistência de valores numéricos e datas.
* Testes de sanidade para garantir aderência ao modelo de dados relacional.

### 4. Inserção no Banco de Dados
* Criação da estrutura de tabelas no banco de dados relacional (PostgreSQL / MySQL / SQLite).
* Ingestão dos registros tratados da tabela de editais e metadados associados.
* Indexação de colunas estratégicas para consultas rápidas (`UF`, `Município`, `Setor`, `Esfera`, `Data de Publicação`).

### 5. Visualização e Dashboards no Power BI
* Conexão do Power BI diretamente ao banco de dados ou ao arquivo CSV tratado.
* Modelagem dimensional e criação de medidas analíticas em DAX.
* Desenvolvimento dos relatórios e painéis interativos para responder às 6 perguntas de negócio do modelo DEILAS:
  1. Comparativo de volume financeiro previsto e processos abertos entre PB e PE.
  2. Proporção de compras diretas vs processos com disputa aberta.
  3. Concentração de recursos nas capitais e nos maiores órgãos vs distribuição no interior.
  4. Distribuição dos gastos por nível de governo (prefeituras, estado e federal) e por poder.
  5. Concentração orçamentária por setor temático (Saúde, Educação, Obras, TI e Transporte).
  6. Indicadores de transparência e compras com valores previamente divulgados vs ocultos.

---

## Estrutura do Repositório

```text
pncp-data-pipeline/
├── data/                         # Armazena os dados do projeto
│   ├── .gitkeep
│   ├── dados_ibge_ufs.csv        # Tabela dimensão oficial do IBGE (PIB e População)
│   ├── dados_brutos_pncp.json    # JSON bruto baixado da API (Etapa 1)
│   └── editais_pncp_PB_PE.csv    # Planilha tratada e consolidada (Etapa 2)
├── download_pncp.py              # Script da Etapa 1: Extração da API
├── pncp_etl.py                   # Script da Etapa 2: Transformação e regras DEILAS
├── requirements.txt              # Dependências do projeto
├── .gitignore                    # Regras de exclusão do Git
└── README.md                     # Documentação do projeto
```

---

## Como Executar o Pipeline Localmente

### 1. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 2. Executar a Extração (Etapa 1)

```bash
python download_pncp.py
```
*Gera: `data/dados_brutos_pncp.json`*

### 3. Executar o ETL (Etapa 2)

```bash
python pncp_etl.py
```
*Gera: `data/editais_pncp_PB_PE.csv`*

---

## Por que a pasta data/ está no .gitignore?

Arquivos de dados (JSON e CSV) não são versionados diretamente no repositório Git porque:
* Evitam o inchaço do histórico de commits, mantendo o repositório leve para clonar e atualizar.
* Mudam com frequência a cada nova consulta executada.
* Podem ser reproduzidos integralmente a qualquer momento executando os scripts do pipeline.
O arquivo `data/.gitkeep` garante que a pasta vazia exista no repositório de qualquer membro da equipe.
