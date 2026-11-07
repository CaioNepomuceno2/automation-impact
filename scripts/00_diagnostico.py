"""Diagnóstico dos dados de religadores do recorte e contagens da regra de decisão pré-registrada.

NÃO estima nenhum efeito: só conta e descreve (docs/decisoes_ems.md). Saídas em ``<reports>/diagnostico/``:
religadores_por_snapshot.csv, transicoes_religadores.csv, eventos_por_coorte.csv, controles_funil.csv,
presenca_alimentadores.csv, cobertura_2026.csv, duplicatas_arquivos.csv e regra_contagens.json.

Eventos e controles saem das MESMAS funções de MT (``painel.eventos_tratamento(minimo=2)`` e
``painel.nunca_tratados``) aplicadas ao painel que ``02_estimar.py`` usa. O desfecho (falhas) só entra no painel
e na checagem de vínculo; nenhuma conta aqui olha efeito.

Uso: python scripts/00_diagnostico.py [--config configs/ems.yaml] [--saida pasta]
Sem regra na configuração (MT), exige ``--saida`` fora de reports/: o diagnóstico nunca sobrescreve resultados de MT.
"""
import argparse
import itertools
import json
import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from autoimpact import painel, regra, rotulos
from autoimpact.config import carregar_dos_argumentos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("diagnostico")
cfg, resto = carregar_dos_argumentos()
ap = argparse.ArgumentParser()
ap.add_argument("--saida", default=None)
args = ap.parse_args(resto)
if args.saida is None and cfg.regra is None:
    raise SystemExit("sem regra de decisão na configuração (MT): informe --saida fora de reports/")
OUT = Path(args.saida) if args.saida else cfg.reports / "diagnostico"
OUT.mkdir(parents=True, exist_ok=True)

p = painel.carregar(cfg.gridrisk_interim, cfg.interim, cfg.anos_resultado)
ev, ctrl, dec = regra.decisao_do_painel(p, cfg)
ORIGEM = None if dec is None else dec.origem_efeito
anos = sorted(p.ano.unique())
s = p.pivot_table(index="alimentador", columns="ano", values="n_religadores")
log.info("painel: %d linhas, %d alimentadores; eventos %d, controles %d", len(p), len(s), len(ev), len(ctrl))

# ------------------------------------------------------------------ religadores por snapshot (BDGD de 31/12)
linhas = []
for a in sorted(cfg.snapshots):
    e = pd.read_parquet(cfg.interim / f"equipamentos_{a}.parquet")
    f = pd.read_parquet(cfg.gridrisk_interim / f"bdgd_feeders_{a}.parquet")
    km = float(pd.to_numeric(f.rede_mt_km).sum())
    vazios = int(((pd.to_numeric(f.rede_mt_km).fillna(0) == 0) & (pd.to_numeric(f.n_uc).fillna(0) == 0)).sum())
    linhas.append({"ano_snapshot": a, "usado_no_painel_de": a + 1 if a + 1 in anos else None,
                   "circuitos_equipamentos": len(e), "circuitos_cadastro": len(f), "circuitos_vazios": vazios,
                   "religadores": int(e.n_religadores.sum()), "religadores_no_cadastro_do_gridrisk": int(f.n_religadores.sum()),
                   "religadores_telecomandados": int(e.n_religadores_tlcd.sum()),
                   "circuitos_com_religador": int((e.n_religadores > 0).sum()), "rede_mt_km": km,
                   "religadores_por_100km": float(e.n_religadores.sum() / km * 100) if km else np.nan,
                   "disjuntores": int(e.n_disjuntores.sum()), "seccionalizadores": int(e.n_seccionalizadores.sum())})
snap = pd.DataFrame(linhas)
regra.salvar_csv(snap, OUT / "religadores_por_snapshot.csv", ORIGEM)

# ------------------------------------------------------------------ transições entre anos consecutivos do painel
trans = []
primeiro = ev.groupby("ano_evento").size()
for y0, y1 in itertools.pairwise(anos):
    ambos = s[[y0, y1]].dropna()
    d = ambos[y1] - ambos[y0]
    trans.append({"ano_resultado": y1, "snapshot_de": y0 - 1, "snapshot_ate": y1 - 1, "circuitos_nos_dois": len(ambos),
                  "religadores_ganhos": float(d[d > 0].sum()), "religadores_perdidos": float(-d[d < 0].sum()),
                  "ganho_liquido": float(d.sum()), "circuitos_ganho_ge1": int((d >= 1).sum()),
                  "circuitos_ganho_ge2": int((d >= 2).sum()), "circuitos_ganho_ge3": int((d >= 3).sum()),
                  "circuitos_perda_ge2": int((d <= -2).sum()), "circuitos_estaveis_amplitude_le1": int((d.abs() <= 1).sum()),
                  "eventos_da_coorte": int(primeiro.get(y1, 0))})
regra.salvar_csv(pd.DataFrame(trans), OUT / "transicoes_religadores.csv", ORIGEM)

coortes = (ev.groupby("ano_evento").agg(eventos=("alimentador", "size"), religadores_adicionados=("ganho", "sum"),
                                         ganho_mediano=("ganho", "median"), ganho_maximo=("ganho", "max"),
                                         religadores_antes_medianos=("base", "median")).reset_index())
regra.salvar_csv(coortes, OUT / "eventos_por_coorte.csv", ORIGEM)

# ------------------------------------------------------------------ funil dos controles nunca tratados
todos_os_anos = s.notna().all(axis=1)
amp = s.max(axis=1) - s.min(axis=1)
vazio = p.groupby("alimentador").agg(rede=("rede_mt_km", lambda x: float(pd.to_numeric(x).fillna(0).max())),
                                     uc=("n_uc", lambda x: float(pd.to_numeric(x).fillna(0).max())),
                                     chi=("chi", "sum"))
vazio["vazio"] = (vazio.rede == 0) & (vazio.uc == 0)
funil = [
    ("alimentadores distintos no painel (qualquer ano)", len(s)),
    ("presentes nos 7 anos de resultado", int(todos_os_anos.sum())),
    ("  e com amplitude de religadores <= 1 (= controles nunca tratados, definição de MT)", len(ctrl)),
    ("     dos quais sem nenhum religador em nenhum ano", int((s.loc[ctrl].max(axis=1) == 0).sum())),
    ("     dos quais com religador em algum ano", int((s.loc[ctrl].max(axis=1) > 0).sum())),
    ("     dos quais circuito vazio (sem rede MT e sem consumidor) em todos os anos", int(vazio.loc[ctrl].vazio.sum())),
    ("     dos quais com CHI de falhas total igual a zero", int((vazio.loc[ctrl].chi == 0).sum())),
    ("  presentes nos 7 anos, mas com amplitude >= 2", int((todos_os_anos & (amp >= 2)).sum())),
    ("     dos quais são eventos (ganho >= 2 que persiste)", int(ev.alimentador.isin(s.index[todos_os_anos & (amp >= 2)]).sum())),
    ("não presentes nos 7 anos de resultado", int((~todos_os_anos).sum())),
]
regra.salvar_csv(pd.DataFrame(funil, columns=["etapa", "alimentadores"]), OUT / "controles_funil.csv", ORIGEM)

# em quantos dos 7 anos cada alimentador aparece (quem some ou aparece no meio não é evento nem controle)
nomes_curtos = pd.Series(s.index.str.lstrip("0").str.len() <= 3, index=s.index)   # código de subestação, não de alimentador
presenca = s.notna().sum(axis=1)
pres = pd.DataFrame({"anos_presentes": range(1, len(anos) + 1)})
pres["alimentadores"] = pres.anos_presentes.map(presenca.value_counts()).fillna(0).astype(int)
pres["com_nome_de_3_caracteres_ou_menos"] = pres.anos_presentes.map(presenca[nomes_curtos].value_counts()).fillna(0).astype(int)
regra.salvar_csv(pres, OUT / "presenca_alimentadores.csv", ORIGEM)

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
regra.salvar_csv(cob, OUT / "cobertura_2026.csv", ORIGEM)
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
info = {
    "eventos_ganho_ge1": len(painel.eventos_tratamento(p, minimo=1)),
    "eventos_ganho_ge3": len(painel.eventos_tratamento(p, minimo=3)),
    "controles_amplitude_0": len(painel.nunca_tratados(p, tol=0)),
    "controles_amplitude_le2": len(painel.nunca_tratados(p, tol=2)),
    "controles_sem_circuito_vazio": int((~vazio.loc[ctrl].vazio).sum()),
    "controles_com_chi_positivo": int((vazio.loc[ctrl].chi > 0).sum()),
}
reg = {
    "origem_efeito": ORIGEM,
    **(dec.registro() if dec else {"n_eventos": len(ev), "n_controles": len(ctrl)}),
    "definicao": {"evento": "painel.eventos_tratamento(p, minimo=2): primeiro ano de resultado em que o alimentador ganha 2 ou "
                            "mais religadores de uma vez em relação ao snapshot anterior e mantém o ganho até o fim",
                  "controle": "painel.nunca_tratados(p): presente nos 7 anos de resultado e com amplitude de religadores <= 1"},
    "coortes": {int(k): int(v) for k, v in primeiro.items()},
    "somente_informativo_fora_da_regra": info,
    "cobertura_ano_parcial": {"ano": cfg.ano_elemento, "meses_com_registro": meses,
                              "rotulo": rotulos.rotulo_meses(meses, cfg.ano_elemento),
                              "falhas": int(anual.falhas), "frac_falhas_com_circuito": float(anual.frac_falhas_com_circuito),
                              "frac_chi_com_circuito": float(anual.frac_chi_com_circuito)},
}
(OUT / "regra_contagens.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
log.info("regra: %s", json.dumps({k: reg[k] for k in ("origem_efeito", "n_eventos", "n_controles")}, ensure_ascii=False))
log.info("pronto: %s", sorted(x.name for x in OUT.iterdir()))
