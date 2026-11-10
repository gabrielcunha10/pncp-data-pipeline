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
│       ├── pipeline.yml          # Workflow diario do PNCP (Extracao e ETL)
│       └── ibge_anual.yml        # Workflow anual do IBGE (Novembro com retry diario)
├── data/                         # Armazena os dados do projeto
│   ├── .gitkeep
│   ├── dados_ibge_ufs.csv        # Serie historica oficial do IBGE por Estado (PIB e Populacao)
│   ├── dados_ibge_municipios.csv # Serie historica oficial do IBGE por Municipio (PIB e PIB per capita)
│   ├── dados_brutos_pncp.json    # JSON bruto baixado da API (Etapa 1)
│   └── editais_pncp_PB_PE.csv    # Planilha tratada e consolidada (Etapa 2)
├── atualizar_ibge.py             # Script que consulta a API SIDRA do IBGE (UFs e Municipios)
├── download_pncp.py              # Script da Etapa 1: Extracao da API do PNCP
├── pncp_etl.py                   # Script da Etapa 2: Transformacao e regras DEILAS
├── requirements.txt              # Dependencias do projeto
├── .gitignore                    # Regras de exclusao do Git
└── README.md                     # Documentacao do projeto
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

## Execucao Automatizada via GitHub Actions

O projeto conta com dois workflows automatizados em `.github/workflows/`:

### 1. Pipeline PNCP (`.github/workflows/pipeline.yml`)
* Executa a extracao (`download_pncp.py`) e o ETL (`pncp_etl.py`) em ambiente virtualizado Ubuntu.
* Pode ser acionado manualmente pela aba **Actions** no GitHub (gatilho `workflow_dispatch`).
* Roda de forma agendada diariamente as 06:00 BRT (09:00 UTC).
* Salva e commita o arquivo final `data/editais_pncp_PB_PE.csv` diretamente no repositório GitHub (arquivo .csv avulso, sem necessidade de baixar arquivos compactados .zip).

### 2. Atualizacao Anual do PIB IBGE (`.github/workflows/ibge_anual.yml`)
* Executa o script `atualizar_ibge.py`, que consome a API oficial SIDRA do IBGE (Tabelas 5938, 6579 e 4709).
* Roda anualmente a partir da segunda semana de novembro (`dias 8 a 22 de novembro`, as 09:00 BRT / 12:00 UTC), fazendo 1 tentativa (retry) por dia ate o IBGE publicar a nova edicao das Contas Regionais (ex: PIB de 2024 em novembro de 2026).
* Assim que o novo ano e detectado na API do IBGE, atualiza e commita automaticamente os arquivos `data/dados_ibge_ufs.csv` e `data/dados_ibge_municipios.csv`. Nos dias seguintes da janela, identifica que o ano-alvo ja foi salvo e encerra imediatamente sem novas requisicoes.

---

## Estrutura da pasta data/

* `data/dados_ibge_ufs.csv`: Tabela dimensao com dados demograficos e economicos estaduais do IBGE (PIB, populacao, crescimento real).
* `data/dados_ibge_municipios.csv`: Tabela dimensao com PIB municipal, populacao e PIB per capita de todos os municipios de PB e PE (2020 a 2023).
* `data/editais_pncp_PB_PE.csv`: Base tratada e consolidada de editais (atualizada automaticamente pelo pipeline e versionada diretamente como CSV).
* `data/dados_brutos_pncp.json`: Arquivo bruto temporario de extracao da API (ignorado pelo Git para manter o repositorio limpo).
