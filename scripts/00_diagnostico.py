"""Diagnóstico dos dados de religadores do recorte e contagens da regra de decisão pré-registrada.

NÃO estima nenhum efeito: só conta e descreve (docs/decisoes_ems.md). Saídas em ``<reports>/diagnostico/``:
religadores_por_snapshot.csv, transicoes_religadores.csv, eventos_por_coorte.csv, controles_funil.csv,
presenca_alimentadores.csv, cobertura_2026.csv, duplicatas_arquivos.csv, regra_contagens.json e, com
``--referencia-mt``, mt_contagens_referencia.json.

Eventos e controles saem das MESMAS funções de MT (``painel.eventos_tratamento(minimo=2)`` e
``painel.nunca_tratados``) aplicadas ao painel que ``02_estimar.py`` usa. O desfecho (falhas) só entra no painel
e na checagem de vínculo; nenhuma conta aqui olha efeito.

Uso: python scripts/00_diagnostico.py [--config configs/ems.yaml] [--saida pasta] [--referencia-mt configs/emt.yaml]
``--referencia-mt``: configuração de MT, lida SÓ para contar (mesmas funções) e comparar com o recorte; os dados de MT
precisam estar nos caminhos dela. Sem regra na configuração (MT), exige ``--saida`` fora de reports/: o diagnóstico
nunca sobrescreve resultados de MT.
"""
import argparse
import json
import logging
from pathlib import Path

import duckdb
import pandas as pd

from autoimpact import diagnostico, painel, regra, rotulos
from autoimpact.config import Config, carregar_dos_argumentos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("diagnostico")
cfg, resto = carregar_dos_argumentos()
ap = argparse.ArgumentParser()
ap.add_argument("--saida", default=None)
ap.add_argument("--referencia-mt", default=None)
args = ap.parse_args(resto)
if args.saida is None and cfg.regra is None:
    raise SystemExit("sem regra de decisão na configuração (MT): informe --saida fora de reports/")
OUT = Path(args.saida) if args.saida else cfg.reports / "diagnostico"
OUT.mkdir(parents=True, exist_ok=True)

p = painel.carregar(cfg.gridrisk_interim, cfg.interim, cfg.anos_resultado)
ev, ctrl, dec = regra.decisao_do_painel(p, cfg)
ORIGEM = None if dec is None else dec.origem_efeito
anos = sorted(p.ano.unique())
log.info("painel: %d linhas, %d alimentadores; eventos %d, controles %d", len(p), p.alimentador.nunique(), len(ev), len(ctrl))

# ------------------------------------------------------------------ religadores por snapshot, transições, coortes, controles
regra.salvar_csv(diagnostico.religadores_por_snapshot(cfg, anos), OUT / "religadores_por_snapshot.csv", ORIGEM)
regra.salvar_csv(diagnostico.transicoes(p, ev), OUT / "transicoes_religadores.csv", ORIGEM)
regra.salvar_csv(diagnostico.eventos_por_coorte(ev), OUT / "eventos_por_coorte.csv", ORIGEM)
regra.salvar_csv(diagnostico.funil_controles(p, ev, ctrl), OUT / "controles_funil.csv", ORIGEM)
regra.salvar_csv(diagnostico.presenca(p), OUT / "presenca_alimentadores.csv", ORIGEM)

# ------------------------------------------------------------------ cobertura de 2026 e vínculo com a BDGD
itr = cfg.interrupcoes_parquet
cw = pd.concat([pd.read_parquet(cfg.gridrisk_interim / f"crosswalk_{a}.parquet") for a in sorted(cfg.snapshots)])
cod = pd.DataFrame({"codigo": cw.codigo.astype(str).unique()})
con = duckdb.connect()
con.register("cod", cod)
cob = con.sql(f"""
    with f as (
        select *, cast(coalesce(alimentador_cod_id, alimentador_nome) as varchar) as codigo
        from read_parquet('{itr}')
        where ano between {cfg.ano_elemento - 1} and {cfg.ano_elemento} and origem_mt and origem = 'INTERNA'
              and tipo = 'NAO PROGRAMADA'
    )
    select f.ano, f.mes, count(*) as falhas, sum(chi) as chi,
           avg(case when coalesce(elemento, 'NAO IDENTIFICADO') in ('NAO IDENTIFICADO', 'NAO INFORMADO')
                    then 0.0 else 1.0 end) as frac_elemento_informado,
           avg(case when cod.codigo is not null then 1.0 else 0.0 end) as frac_falhas_com_circuito,
           sum(case when cod.codigo is not null then chi else 0.0 end) / sum(chi) as frac_chi_com_circuito
    from f left join cod on f.codigo = cod.codigo
    group by 1, 2 order by 1, 2
""").df()
regra.salvar_csv(cob.round(8), OUT / "cobertura_2026.csv", ORIGEM)   # arredonda: a soma paralela do duckdb varia no último dígito
meses = rotulos.meses_com_registro(itr, cfg.ano_elemento)
anual = con.sql(f"""
    with f as (
        select *, cast(coalesce(alimentador_cod_id, alimentador_nome) as varchar) as codigo
        from read_parquet('{itr}')
        where ano = {cfg.ano_elemento} and origem_mt and origem = 'INTERNA' and tipo = 'NAO PROGRAMADA'
    )
    select count(*) as falhas, avg(case when cod.codigo is not null then 1.0 else 0.0 end) as frac_falhas_com_circuito,
           sum(case when cod.codigo is not null then chi else 0.0 end) / sum(chi) as frac_chi_com_circuito
    from f left join cod on f.codigo = cod.codigo
""").df().iloc[0]

# ------------------------------------------------------------------ linhas repetidas (count(*) x distinct) nos arquivos lidos
arquivos = [itr, cfg.gridrisk_interim / "falhas.parquet", cfg.gridrisk_processed / "risco_alimentador.parquet"]
arquivos += [cfg.gridrisk_interim / f"bdgd_feeders_{a}.parquet" for a in sorted(cfg.snapshots)]
arquivos += [cfg.gridrisk_interim / f"crosswalk_{a}.parquet" for a in sorted(cfg.snapshots)]
arquivos += [cfg.interim / f"equipamentos_{a}.parquet" for a in sorted(cfg.snapshots)]
dups = []
for arq in arquivos:
    r = duckdb.sql(f"select (select count(*) from read_parquet('{arq}')) as n, "
                   f"(select count(*) from (select distinct * from read_parquet('{arq}'))) as d").fetchall()[0]
    dups.append({"arquivo": arq.name, "linhas": r[0], "distintas": r[1], "repetidas": r[0] - r[1],
                 "pct_repetidas": 100 * (r[0] - r[1]) / r[0] if r[0] else 0.0})
regra.salvar_csv(pd.DataFrame(dups), OUT / "duplicatas_arquivos.csv", ORIGEM)

# ------------------------------------------------------------------ contagens da regra
reg = {
    "origem_efeito": ORIGEM,
    **(dec.registro() if dec else {"n_eventos": len(ev), "n_controles": len(ctrl)}),
    "definicao": {"evento": "painel.eventos_tratamento(p, minimo=2): primeiro ano de resultado em que o alimentador ganha 2 ou "
                            "mais religadores de uma vez em relação ao snapshot anterior e mantém o ganho até o fim",
                  "controle": "painel.nunca_tratados(p): presente nos 7 anos de resultado e com amplitude de religadores <= 1"},
    "coortes": {int(k): int(v) for k, v in ev.groupby("ano_evento").size().items()},
    "somente_informativo_fora_da_regra": diagnostico.informativo(p, ctrl),
    "cobertura_ano_parcial": {"ano": cfg.ano_elemento, "meses_com_registro": meses,
                              "rotulo": rotulos.rotulo_meses(meses, cfg.ano_elemento),
                              "falhas": int(anual.falhas), "frac_falhas_com_circuito": float(anual.frac_falhas_com_circuito),
                              "frac_chi_com_circuito": float(anual.frac_chi_com_circuito)},
}
(OUT / "regra_contagens.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
if args.referencia_mt:   # MT só para contar, com as mesmas funções (somente leitura)
    ref = diagnostico.referencia_mt(Config.load(args.referencia_mt), ORIGEM)
    (OUT / "mt_contagens_referencia.json").write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("referência %s: %d eventos, %d controles", ref["sigla_referencia"], ref["n_eventos"], ref["n_controles"])
log.info("regra: %s", json.dumps({k: reg[k] for k in ("origem_efeito", "n_eventos", "n_controles")}, ensure_ascii=False))
log.info("pronto: %s", sorted(x.name for x in OUT.iterdir()))
