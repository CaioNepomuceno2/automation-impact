"""Decomposição do tempo de atendimento emergencial (preparo, deslocamento, execução) da EMT.

Fonte: ANEEL, Ocorrências Emergenciais nas Redes de Distribuição (Parquet anual, Brasil inteiro).
O telecomando e a supervisão atuam sobretudo em preparo (detectar e despachar) e deslocamento
(ir direto ao trecho certo); a execução é o reparo em si.
"""
import duckdb
import requests

from autoimpact.config import ROOT, Config

cfg = Config.load()
ANO = 2025
URL = ("https://dadosabertos.aneel.gov.br/api/3/action/package_show?id="
       "ocorrencias-emergenciais-nas-redes-de-distribuicao")
recursos = requests.get(URL, timeout=60).json()["result"]["resources"]
url = next(r["url"] for r in recursos if r["url"].endswith(f"-{ANO}.parquet"))
raw = cfg.raw / "ocorrencias"
raw.mkdir(parents=True, exist_ok=True)
arq = raw / f"ocorrencias_{ANO}.parquet"
if not arq.exists():
    with requests.get(url, stream=True, timeout=1200) as r:
        r.raise_for_status()
        with open(arq, "wb") as f:
            f.writelines(r.iter_content(1 << 22))
out = duckdb.sql(f"""
    with o as (
        select MdaPreparo as preparo, MdaDeslocamento as deslocamento, MdaExecucao as execucao,
               DscOcorrenciaAberta like 'INTERNA;NAO PROGRAMADA%' as interna_np
        from read_parquet('{arq}')
        where NomAgente ilike '%ENERGISA MATO GROSSO%' and NomAgente not ilike '%SUL%'
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
out.to_csv(ROOT / "reports" / "atendimento_2025.csv", index=False)
print(out.round(3).to_string(index=False))
arq.unlink()
