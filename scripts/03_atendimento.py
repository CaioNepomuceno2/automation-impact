"""Decomposição do tempo de atendimento emergencial (preparo, deslocamento, execução) da distribuidora do recorte.

Fonte: ANEEL, Ocorrências Emergenciais nas Redes de Distribuição (Parquet anual, Brasil inteiro).
O telecomando e a supervisão atuam sobretudo em preparo (detectar e despachar) e deslocamento
(ir direto ao trecho certo); a execução é o reparo em si.

Uso: python scripts/03_atendimento.py [--config configs/ems.yaml]
O filtro do agente (``ocorrencias.incluir`` / ``excluir``) e o ano vêm da configuração. Baixa o arquivo nacional
do ano (centenas de MB) e o apaga ao fim. Antes de agregar, confere linhas repetidas (count(*) x distinct).
"""
import duckdb
import requests

from autoimpact import regra
from autoimpact.config import carregar_dos_argumentos

cfg, _ = carregar_dos_argumentos()
ANO = cfg.ano_ocorrencias
URL = ("https://dadosabertos.aneel.gov.br/api/3/action/package_show?id="
       "ocorrencias-emergenciais-nas-redes-de-distribuicao")
recursos = requests.get(URL, timeout=60).json()["result"]["resources"]
url = next(r["url"] for r in recursos if r["url"].endswith(f"-{ANO}.parquet"))
raw = cfg.raw / "ocorrencias"
raw.mkdir(parents=True, exist_ok=True)
arq = raw / f"ocorrencias_{ANO}.parquet"
if not arq.exists():
    parcial = arq.with_name(arq.name + ".parcial")   # só vira o arquivo final quando o download termina
    with requests.get(url, stream=True, timeout=1200) as r:
        r.raise_for_status()
        with open(parcial, "wb") as f:
            f.writelines(r.iter_content(1 << 22))
    parcial.rename(arq)
agente = f"NomAgente ilike '{cfg.ocorrencias_incluir}'"
if cfg.ocorrencias_excluir:
    agente += f" and NomAgente not ilike '{cfg.ocorrencias_excluir}'"
dup = duckdb.sql(f"""
    select (select count(*) from read_parquet('{arq}') where {agente}) as linhas,
           (select count(*) from (select distinct * from read_parquet('{arq}') where {agente})) as distintas
""").df()
print("linhas do agente:", dup.to_dict("records")[0])
print(duckdb.sql(f"select NomAgente, count(*) as linhas from read_parquet('{arq}') where {agente} group by 1 order by 2 desc").df()
      .to_string(index=False))   # confere que o filtro pegou só o agente do recorte
out = duckdb.sql(f"""
    with o as (
        select MdaPreparo as preparo, MdaDeslocamento as deslocamento, MdaExecucao as execucao,
               DscOcorrenciaAberta like 'INTERNA;NAO PROGRAMADA%' as interna_np
        from read_parquet('{arq}')
        where {agente}
          and MdaPreparo >= 0 and MdaDeslocamento >= 0 and MdaExecucao >= 0
    )
    select interna_np, count(*) as ocorrencias,
           median(preparo) as preparo_mediana_min, median(deslocamento) as deslocamento_mediana_min,
           median(execucao) as execucao_mediana_min,
           sum(preparo) / sum(preparo + deslocamento + execucao) as frac_preparo,
           sum(deslocamento) / sum(preparo + deslocamento + execucao) as frac_deslocamento,
           sum(execucao) / sum(preparo + deslocamento + execucao) as frac_execucao
    from o group by 1 order by 1 desc
""").df()
cfg.reports.mkdir(parents=True, exist_ok=True)
regra.salvar_csv(out, cfg.reports / f"atendimento_{ANO}.csv", regra.origem_do_recorte(cfg))
print(out.round(3).to_string(index=False))
arq.unlink()
