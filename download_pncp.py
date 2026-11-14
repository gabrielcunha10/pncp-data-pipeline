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

MODALIDADES_PNCP = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)


def _carregar_cache_json(output_json: str) -> dict:
    """Carrega registros existentes do JSON bruto indexados por numeroControlePNCP."""
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
            return {}
    return itens_por_id


def _obter_data_inicial_incremental(
    state_json: str,
    itens_por_id: dict,
    full_refresh: bool,
    hoje: datetime,
) -> Optional[str]:
    """Retorna YYYYMMDD para busca incremental se houver cache e estado recente válidos."""
    if full_refresh or not itens_por_id or not state_json or not os.path.exists(state_json):
        return None
    try:
        with open(state_json, "r", encoding="utf-8") as f:
            estado = json.load(f)
        ultima_str = estado.get("ultima_execucao")
        if not ultima_str:
            return None
        ultima_dt = datetime.strptime(ultima_str, "%Y-%m-%d")
        if (hoje.date() - ultima_dt.date()).days > 15:
            return None
        # Margem de 1 dia para evitar perda de atualizacoes na virada de fuso/dia
        data_inicio = ultima_dt - timedelta(days=1)
        return data_inicio.strftime("%Y%m%d")
    except Exception:
        return None


def _salvar_estado_sync(state_json: Optional[str], hoje: datetime) -> None:
    """Persiste a data da última sincronização bem-sucedida."""
    if not state_json:
        return
    os.makedirs(os.path.dirname(os.path.abspath(state_json)), exist_ok=True)
    with open(state_json, "w", encoding="utf-8") as f:
        json.dump(
            {"ultima_execucao": hoje.strftime("%Y-%m-%d"), "atualizado_em": hoje.isoformat(timespec="seconds")},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _edital_em_aberto(item: dict, agora: datetime) -> bool:
    """Verifica se o edital ainda possui prazo de proposta aberto."""
    enc_str = item.get("dataEncerramentoProposta")
    if not enc_str:
        return False
    try:
        enc_dt = datetime.fromisoformat(str(enc_str).replace("Z", "+00:00"))
        if enc_dt.tzinfo is not None:
            enc_dt = enc_dt.replace(tzinfo=None)
        return enc_dt >= agora
    except ValueError:
        return True


def _consultar_pagina_api(session: requests.Session, url: str, uf: str, pagina: int) -> Optional[dict]:
    """Consulta uma página da API do PNCP com tratamento de 204 e backoff para 429."""
    max_tentativas = 8
    for tentativa in range(1, max_tentativas + 1):
        time.sleep(1.0)
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 204:
                return {"totalPaginas": 0, "data": []}
            if resp.status_code == 429:
                espera = min(3.0 * (2 ** (tentativa - 1)), 30.0)
                logger.warning(f"[Rate Limit 429] Aguardando {espera:.1f}s antes de tentar novamente ({tentativa}/{max_tentativas})...")
                time.sleep(espera)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            espera = min(2.0 * tentativa, 20.0)
            if tentativa == max_tentativas:
                logger.error(f"Falha ao consultar página {pagina} de {uf}: {e}")
            else:
                time.sleep(espera)
    return None


@task(name="Extrair Editais API PNCP", retries=2, retry_delay_seconds=5, log_prints=True)
def baixar_dados_brutos(
    ufs=("PB", "PE"),
    data_final: Optional[str] = None,
    output_json: str = os.path.join("data", "dados_brutos_pncp.json"),
    state_json: Optional[str] = None,
    full_refresh: Optional[bool] = None,
):
    """
    Fase de Extração Incremental e Idempotente (Extract):
    Consome a API pública do PNCP e realiza Upsert (Update + Insert) pelo
    identificador único 'numeroControlePNCP' no arquivo data/dados_brutos_pncp.json.
    Quando já existe cache e estado recente, consulta apenas /contratacoes/atualizacao
    desde a última execução; caso contrário, realiza carga completa via /proposta.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
    agora = datetime.now()

    if state_json is None:
        state_json = os.path.join(os.path.dirname(os.path.abspath(output_json)), "pncp_sync_state.json")

    if full_refresh is None:
        full_refresh = os.getenv("PNCP_FULL_REFRESH", "").strip().lower() in ("1", "true", "sim", "yes")

    if not data_final:
        data_final = (agora + timedelta(days=60)).strftime("%Y%m%d")

    itens_por_id = _carregar_cache_json(output_json)
    qtd_antes = len(itens_por_id)
    data_inicial_inc = _obter_data_inicial_incremental(state_json, itens_por_id, full_refresh, agora)
    modo_incremental = data_inicial_inc is not None

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 5.1; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })

    logger.info("=" * 70)
    logger.info("   PNCP - EXTRAÇÃO INCREMENTAL E IDEMPOTENTE DA API")
    logger.info(f"   UFs: {', '.join(ufs)} | Modo: {'Incremental (/atualizacao desde ' + data_inicial_inc + ')' if modo_incremental else 'Carga Completa (/proposta)'}")
    logger.info(f"   Registros já existentes em cache: {qtd_antes}")
    logger.info("=" * 70)

    novos_extraidos = 0
    atualizados_extraidos = 0
    expirados_removidos = 0

    if modo_incremental:
        # Remove do cache editais cujo prazo de proposta já encerrou
        chaves_expiradas = [k for k, v in itens_por_id.items() if not _edital_em_aberto(v, agora)]
        for k in chaves_expiradas:
            itens_por_id.pop(k, None)
        expirados_removidos += len(chaves_expiradas)

        data_final_inc = agora.strftime("%Y%m%d")
        for uf in ufs:
            uf = uf.upper().strip()
            total_uf = 0
            logger.info(f"Buscando atualizações incrementais da UF: {uf} ({data_inicial_inc} -> {data_final_inc})...")

            for mod in MODALIDADES_PNCP:
                pagina = 1
                total_paginas = 1
                while pagina <= total_paginas:
                    url = (
                        f"https://pncp.gov.br/api/consulta/v1/contratacoes/atualizacao"
                        f"?dataInicial={data_inicial_inc}&dataFinal={data_final_inc}"
                        f"&codigoModalidadeContratacao={mod}&uf={uf}&pagina={pagina}&tamanhoPagina=50"
                    )
                    data = _consultar_pagina_api(session, url, uf, pagina)
                    if not data:
                        logger.warning(f"Interrompendo coleta incremental de {uf} (modalidade {mod}) na página {pagina}.")
                        break

                    total_paginas = data.get("totalPaginas", 0)
                    itens = data.get("data", [])
                    if not itens:
                        break

                    for item in itens:
                        item["_uf_consulta"] = uf
                        chave = item.get("numeroControlePNCP")
                        if not chave:
                            continue
                        if _edital_em_aberto(item, agora):
                            if chave in itens_por_id:
                                atualizados_extraidos += 1
                            else:
                                novos_extraidos += 1
                            itens_por_id[chave] = item
                        elif chave in itens_por_id:
                            itens_por_id.pop(chave, None)
                            expirados_removidos += 1
                        total_uf += 1

                    pagina += 1

            logger.info(f"[{uf}] Extração incremental finalizada ({total_uf} atualizações lidas)")
    else:
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
                data = _consultar_pagina_api(session, url, uf, pagina)
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

    _salvar_estado_sync(state_json, agora)

    logger.info("=" * 70)
    logger.info("   Extração Incremental Concluída!")
    logger.info(f"   - Novos editais inéditos adicionados: {novos_extraidos}")
    logger.info(f"   - Editais existentes sincronizados:   {atualizados_extraidos}")
    logger.info(f"   - Editais encerrados removidos:       {expirados_removidos}")
    logger.info(f"   - Total único consolidado no JSON:    {len(lista_consolidada)}")
    logger.info("=" * 70)


@flow(name="Flow 1 - Extração Incremental PNCP", log_prints=True)
def flow_extracao_pncp():
    baixar_dados_brutos()


if __name__ == "__main__":
    flow_extracao_pncp()
