# Definição de Objetivos e Métricas — Modelo DEILAS

**Projeto:** Comparativo das Compras Públicas entre Paraíba e Pernambuco (PNCP) com Enriquecimento Socioeconômico (IBGE)  
**Integrantes:** Gabriel da Cunha Prudencio, Gabriel Ferreira Américo, José Adrian Cosmo de Sousa e João Pedro Medeiros Barbosa.  

### Bases de Dados Utilizadas:
1. **Base de Contratações da Paraíba** (PNCP / UF: PB)
2. **Base de Contratações de Pernambuco** (PNCP / UF: PE)
3. **Base de Contas Regionais e PIB dos Municípios** (IBGE SIDRA — Tabela 5938)
4. **Base Demográfica Municipal** (IBGE SIDRA — Tabelas 4709 e 6579)

---

## D — Defina o Objetivo (Perguntas de Negócio)

*(O que queremos descobrir com as análises, em perguntas simples e diretas)*

1. **Qual dos dois estados previu gastar mais dinheiro e abriu mais processos de compras?**
2. **Qual dos dois estados prefere comprar direto de uma empresa e qual prefere abrir disputa para várias empresas concorrerem pelo melhor preço?**
3. **O dinheiro das compras públicas acompanha o tamanho da economia (PIB) de cada cidade ou fica concentrado demais nas capitais?**
4. **Quem gasta mais dinheiro em compras públicas em cada estado: as prefeituras, o governo estadual ou os órgãos federais?**
5. **Para onde vai o dinheiro público: quais áreas (Saúde, Educação, Obras, Transporte, TI) concentram a maior parte dos gastos?**
6. **Quanto o dinheiro das prefeituras pesa na economia real de cada município? Existem cidades que dependem quase que exclusivamente das compras públicas para movimentar o seu PIB?**
7. **As cidades mais ricas (maior PIB por pessoa) gastam mais por habitante e conseguem preços melhores com mais concorrência do que as cidades mais vulneráveis?**

---

## E — Estabeleça as Métricas (Indicadores que Medem os Objetivos)

*(Os números e cálculos práticos das bases de dados que respondem a cada pergunta)*

### 1. Qual dos dois estados previu gastar mais dinheiro e abriu mais processos de compras?
* **Volume Financeiro Estimado Total (R$):** Soma do valor estimado mês a mês por estado.
* **Volume de Processos Abertos:** Total de compras públicas lançadas no portal no período.
* **Ticket Médio por Compra (R$):** Valor médio previsto por contratação ($\frac{\text{Volume Total}}{\text{Total de Compras}}$).

---

### 2. Qual dos dois estados prefere comprar direto de uma empresa e qual prefere abrir disputa para várias empresas concorrerem pelo melhor preço?
* **Porcentagem de Compras Feitas Sem Disputa (%):** Proporção de compras diretas (dispensas e inexigibilidades) sobre o total de contratações.
* **Porcentagem do Dinheiro Destinado a Compras Diretas (%):** Fatia do valor financeiro total previsto que foi destinado a compras sem disputa aberta.
* **Volume em Disputa Aberta vs Compra Direta (R$):** Total em Reais previsto para concorrência pública vs compras diretas.

---

### 3. O dinheiro das compras públicas acompanha o tamanho da economia (PIB) de cada cidade ou fica concentrado demais nas capitais?
* **Peso das Capitais no Dinheiro Público vs no PIB (%):** Comparação entre a fatia do PIB gerada por João Pessoa e Recife e a fatia do dinheiro de compras públicas que elas concentram.
* **Razão de Concentração Capital vs PIB:** $\frac{\% \text{ de Compras Públicas da Capital}}{\% \text{ do PIB da Capital no Estado}}$. *(Valores maiores que 1 indicam concentração excessiva de recursos na capital).*
* **Fatia dos 5 Maiores Órgãos Compradores (%):** Concentração dos gastos nos maiores órgãos de cada estado.
* **Cobertura Territorial:** Quantidade e porcentagem de cidades que abriram compras no portal (em relação aos 223 municípios da PB e 185 de PE).

---

### 4. Quem gasta mais dinheiro em compras públicas em cada estado: as prefeituras, o governo estadual ou os órgãos federais?
* **Volume Financeiro por Nível de Governo (R$ e %):** Total e média do valor previsto dividido entre Prefeituras (Municipal), Governo do Estado (Estadual) e Órgãos Federais.
* **Distribuição dos Gastos por Poder (%):** Participação de cada poder (Executivo, Legislativo e Judiciário) no volume de compras.

---

### 5. Para onde vai o dinheiro público: quais áreas concentram a maior parte dos gastos?
* **Distribuição Orçamentária por Setor (%):** Porcentagem do dinheiro previsto para cada área temática (Saúde, Educação, Obras/Infraestrutura, Transporte/Frota, TI, Assistência Social, etc.).
* **Quantidade de Compras Abertas por Setor:** Número de editais publicados por área em cada estado.
* **Valor Médio de Gasto por Setor (R$):** Ticket médio de um edital de Saúde vs Educação vs Obras.

---

### 6. Quanto o dinheiro das prefeituras pesa na economia real de cada município? Existem cidades que dependem quase que exclusivamente das compras públicas para movimentar o seu PIB?
* **Índice de Intensidade de Compras no PIB Local (%):**
  $$\text{Intensidade} = \frac{\text{Soma dos Valores Licitados pela Prefeitura (R\$)}}{\text{PIB Municipal Oficial do IBGE (R\$)}} \times 100$$
* **Ranking de Dependência Econômica:** Identificação dos 10 municípios da PB e de PE com maior impacto relativo das compras da prefeitura sobre sua economia.
* **Classificação por Faixas de Dependência:**
  * *Alta Dependência Governamental:* Compras representam mais de 10% do PIB da cidade.
  * *Média Dependência:* Compras representam entre 3% e 10% do PIB.
  * *Baixa Dependência:* Compras representam menos de 3% do PIB.

---

### 7. As cidades mais ricas (maior PIB por pessoa) gastam mais por habitante e conseguem preços melhores com mais concorrência do que as cidades mais vulneráveis?
* **Gasto Público Contratado por Habitante (R$/hab):**
  $$\text{Gasto per Capita} = \frac{\text{Valor Total de Compras Licitado no Município (R\$)}}{\text{População Oficial do IBGE}}$$
* **Taxa de Concorrência por Nível de Riqueza (%):** Comparação do percentual de compras com disputa aberta entre as cidades com menor PIB per capita e as de maior PIB per capita.
* **Índice de Transparência por Porte Econômico (%):** Porcentagem de editais com valores ocultos, sob sigilo ou cadastrados com valor zerado (R$ 0,00) em municípios de menor renda vs maior renda.

