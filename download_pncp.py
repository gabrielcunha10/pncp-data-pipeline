import os
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional
import requests
from prefect import flow, task


def obter_logger(nome: str = "download_pncp") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger(nome)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh = RotatingFileHandler(
            os.path.join("logs", "pipeline.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
        logger.propagate = False
    return logger


logger = obter_logger()


@task(name="Extrair Editais API PNCP", retries=2, retry_delay_seconds=5, log_prints=True)
def baixar_dados_brutos(
    ufs=("PB", "PE"),
    data_final: Optional[str] = None,
    output_json: str = os.path.join("data", "dados_brutos_pncp.json")
):
    """
    Fase de Extração Incremental e Idempotente (Extract):
    Consome a API pública do PNCP e realiza Upsert (Update + Insert) pelo
    identificador único 'numeroControlePNCP' no arquivo data/dados_brutos_pncp.json.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)

    if not data_final:
        data_final = (datetime.now() + timedelta(days=60)).strftime("%Y%m%d")

    # Carrega base bruta existente (se houver) para garantir extração incremental sem duplicatas
    itens_por_id = {}
    if os.path.exists(output_json):
        try:
            with open(output_json, "r", encoding="utf-8") as f:
                existentes = json.load(f)
                for item in existentes:
                    chave = item.get("numeroControlePNCP")
                    if chave:
                        itens_por_id[chave] = item
        except Exception:
            itens_por_id = {}

    qtd_antes = len(itens_por_id)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })

    logger.info("=" * 70)
    logger.info("   PNCP - EXTRAÇÃO INCREMENTAL E IDEMPOTENTE DA API")
    logger.info(f"   UFs: {', '.join(ufs)} | Status: Recebendo Proposta")
    logger.info(f"   Registros já existentes em cache: {qtd_antes}")
    logger.info("=" * 70)

    novos_extraidos = 0
    atualizados_extraidos = 0

    for uf in ufs:
        uf = uf.upper().strip()
        pagina = 1
        total_paginas = 1
        total_uf = 0

        logger.info(f"Baixando dados da UF: {uf}...")

        while pagina <= total_paginas:
            url = (
                f"https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
                f"?uf={uf}&dataFinal={data_final}&pagina={pagina}&tamanhoPagina=50"
            )

            data = None
            max_tentativas = 8
            for tentativa in range(1, max_tentativas + 1):
                time.sleep(1.0)
                try:
                    resp = session.get(url, timeout=30)
                    if resp.status_code == 429:
                        espera = min(3.0 * (2 ** (tentativa - 1)), 30.0)
                        logger.warning(f"[Rate Limit 429] Aguardando {espera:.1f}s antes de tentar novamente ({tentativa}/{max_tentativas})...")
                        time.sleep(espera)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    espera = min(2.0 * tentativa, 20.0)
                    if tentativa == max_tentativas:
                        logger.error(f"Falha ao consultar página {pagina} de {uf}: {e}")
                    else:
                        time.sleep(espera)

            if not data:
                logger.warning(f"Interrompendo coleta de {uf} na página {pagina}.")
                break

            total_paginas = data.get("totalPaginas", 1)
            itens = data.get("data", [])

            for item in itens:
                item["_uf_consulta"] = uf
                chave = item.get("numeroControlePNCP")
                if chave:
                    if chave in itens_por_id:
                        atualizados_extraidos += 1
                    else:
                        novos_extraidos += 1
                    itens_por_id[chave] = item
                total_uf += 1

            logger.info(f"[{uf}] Página {pagina}/{total_paginas} baixada ({total_uf} itens lidos)")
            pagina += 1

    lista_consolidada = list(itens_por_id.values())
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(lista_consolidada, f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("   Extração Incremental Concluída!")
    logger.info(f"   - Novos editais inéditos adicionados: {novos_extraidos}")
    logger.info(f"   - Editais existentes sincronizados:   {atualizados_extraidos}")
    logger.info(f"   - Total único consolidado no JSON:    {len(lista_consolidada)}")
    logger.info("=" * 70)


@flow(name="Flow 1 - Extração Incremental PNCP", log_prints=True)
def flow_extracao_pncp():
    baixar_dados_brutos()


if __name__ == "__main__":
    flow_extracao_pncp()
