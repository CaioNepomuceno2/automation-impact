"""Tabelas de diagnóstico dos religadores e das contagens da regra de decisão (``scripts/00_diagnostico.py``).

Só contam e descrevem: nenhuma função aqui estima efeito. Servem ao recorte e, lidas em modo somente leitura, a MT
(``referencia_mt``), para comparar as contagens com as mesmas funções.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from autoimpact import painel, regra
from autoimpact.config import Config


def religadores_por_snapshot(cfg: Config, anos_painel: list[int]) -> pd.DataFrame:
    """Circuitos, religadores, telecomandados e densidade em cada snapshot de 31/12 (equipamentos e cadastro da base)."""
    linhas = []
    for a in sorted(cfg.snapshots):
        e = pd.read_parquet(cfg.interim / f"equipamentos_{a}.parquet")
        f = pd.read_parquet(cfg.gridrisk_interim / f"bdgd_feeders_{a}.parquet")
        km = float(pd.to_numeric(f.rede_mt_km).sum())
        vazios = int(((pd.to_numeric(f.rede_mt_km).fillna(0) == 0) & (pd.to_numeric(f.n_uc).fillna(0) == 0)).sum())
        linhas.append({"ano_snapshot": a, "usado_no_painel_de": a + 1 if a + 1 in anos_painel else None,
                       "circuitos_equipamentos": len(e), "circuitos_cadastro": len(f), "circuitos_vazios": vazios,
                       "religadores": int(e.n_religadores.sum()),
                       "religadores_no_cadastro_do_gridrisk": int(f.n_religadores.sum()),
                       "religadores_telecomandados": int(e.n_religadores_tlcd.sum()),
                       "circuitos_com_religador": int((e.n_religadores > 0).sum()), "rede_mt_km": km,
                       "religadores_por_100km": float(e.n_religadores.sum() / km * 100) if km else np.nan,
                       "disjuntores": int(e.n_disjuntores.sum()), "seccionalizadores": int(e.n_seccionalizadores.sum())})
    return pd.DataFrame(linhas)


def transicoes(p: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """Mudança de religadores entre anos consecutivos do painel, nos circuitos presentes nos dois anos."""
    s = p.pivot_table(index="alimentador", columns="ano", values="n_religadores")
    primeiro = ev.groupby("ano_evento").size()
    linhas = []
    for y0, y1 in itertools.pairwise(sorted(p.ano.unique())):
        ambos = s[[y0, y1]].dropna()
        d = ambos[y1] - ambos[y0]
        linhas.append({"ano_resultado": y1, "snapshot_de": y0 - 1, "snapshot_ate": y1 - 1, "circuitos_nos_dois": len(ambos),
                       "religadores_ganhos": float(d[d > 0].sum()), "religadores_perdidos": float(-d[d < 0].sum()),
                       "ganho_liquido": float(d.sum()), "circuitos_ganho_ge1": int((d >= 1).sum()),
                       "circuitos_ganho_ge2": int((d >= 2).sum()), "circuitos_ganho_ge3": int((d >= 3).sum()),
                       "circuitos_perda_ge2": int((d <= -2).sum()),
                       "circuitos_estaveis_amplitude_le1": int((d.abs() <= 1).sum()),
                       "eventos_da_coorte": int(primeiro.get(y1, 0))})
    return pd.DataFrame(linhas)


def eventos_por_coorte(ev: pd.DataFrame) -> pd.DataFrame:
    return (ev.groupby("ano_evento").agg(eventos=("alimentador", "size"), religadores_adicionados=("ganho", "sum"),
                                         ganho_mediano=("ganho", "median"), ganho_maximo=("ganho", "max"),
                                         religadores_antes_medianos=("base", "median")).reset_index())


def _vazio_e_chi(p: pd.DataFrame) -> pd.DataFrame:
    v = p.groupby("alimentador").agg(rede=("rede_mt_km", lambda x: float(pd.to_numeric(x).fillna(0).max())),
                                     uc=("n_uc", lambda x: float(pd.to_numeric(x).fillna(0).max())),
                                     chi=("chi", "sum"))
    v["vazio"] = (v.rede == 0) & (v.uc == 0)
    return v


def funil_controles(p: pd.DataFrame, ev: pd.DataFrame, ctrl: pd.Index) -> pd.DataFrame:
    """De onde saem os controles nunca tratados: presença nos anos, amplitude de religadores, circuito vazio, CHI zero."""
    s = p.pivot_table(index="alimentador", columns="ano", values="n_religadores")
    todos = s.notna().all(axis=1)
    amp = s.max(axis=1) - s.min(axis=1)
    v = _vazio_e_chi(p)
    n_anos = p.ano.nunique()
    etapas = [
        ("alimentadores distintos no painel (qualquer ano)", len(s)),
        (f"presentes nos {n_anos} anos de resultado", int(todos.sum())),
        ("  e com amplitude de religadores <= 1 (= controles nunca tratados, definição de MT)", len(ctrl)),
        ("     dos quais sem nenhum religador em nenhum ano", int((s.loc[ctrl].max(axis=1) == 0).sum())),
        ("     dos quais com religador em algum ano", int((s.loc[ctrl].max(axis=1) > 0).sum())),
        ("     dos quais circuito vazio (sem rede MT e sem consumidor) em todos os anos", int(v.loc[ctrl].vazio.sum())),
        ("     dos quais com CHI de falhas total igual a zero", int((v.loc[ctrl].chi == 0).sum())),
        (f"  presentes nos {n_anos} anos, mas com amplitude >= 2", int((todos & (amp >= 2)).sum())),
        ("     dos quais são eventos (ganho >= 2 que persiste)", int(ev.alimentador.isin(s.index[todos & (amp >= 2)]).sum())),
        (f"não presentes nos {n_anos} anos de resultado", int((~todos).sum())),
    ]
    return pd.DataFrame(etapas, columns=["etapa", "alimentadores"])


def presenca(p: pd.DataFrame) -> pd.DataFrame:
    """Em quantos anos cada alimentador aparece; separa os de nome curto (código de subestação, não de alimentador)."""
    s = p.pivot_table(index="alimentador", columns="ano", values="n_religadores")
    curtos = pd.Series(s.index.str.lstrip("0").str.len() <= 3, index=s.index)
    n = s.notna().sum(axis=1)
    out = pd.DataFrame({"anos_presentes": range(1, p.ano.nunique() + 1)})
    out["alimentadores"] = out.anos_presentes.map(n.value_counts()).fillna(0).astype(int)
    out["com_nome_de_3_caracteres_ou_menos"] = out.anos_presentes.map(n[curtos].value_counts()).fillna(0).astype(int)
    return out


def informativo(p: pd.DataFrame, ctrl: pd.Index) -> dict:
    """Variações das contagens que NÃO entram na regra (só para o leitor ver o quanto a definição pesa)."""
    v = _vazio_e_chi(p)
    return {
        "eventos_ganho_ge1": len(painel.eventos_tratamento(p, minimo=1)),
        "eventos_ganho_ge3": len(painel.eventos_tratamento(p, minimo=3)),
        "controles_amplitude_0": len(painel.nunca_tratados(p, tol=0)),
        "controles_amplitude_le2": len(painel.nunca_tratados(p, tol=2)),
        "controles_sem_circuito_vazio": int((~v.loc[ctrl].vazio).sum()),
        "controles_com_chi_positivo": int((v.loc[ctrl].chi > 0).sum()),
    }


def referencia_mt(cfg_mt: Config, origem: str | None) -> dict:
    """Contagens de MT pelas MESMAS funções, em modo somente leitura (nenhum efeito é reestimado)."""
    p = painel.carregar(cfg_mt.gridrisk_interim, cfg_mt.interim, cfg_mt.anos_resultado)
    ev, ctrl = regra.eventos_e_controles(p)
    funil = funil_controles(p, ev, ctrl)
    snap = religadores_por_snapshot(cfg_mt, sorted(p.ano.unique()))
    tr = transicoes(p, ev)
    return {
        "origem_efeito": origem,
        "descricao": f"Mesmas funções (painel.eventos_tratamento minimo=2 e painel.nunca_tratados) aplicadas ao painel de {cfg_mt.sigla} "
                     f"({cfg_mt.nome}), lido em modo somente leitura dos arquivos da configuração de MT. Só contagem: "
                     "nenhum efeito foi reestimado e nenhum resultado publicado foi tocado. Os números deste arquivo são de MT, "
                     "não de MS; o campo origem_efeito é o rótulo do recorte de MS que o contém.",
        "sigla_referencia": cfg_mt.sigla,
        "n_eventos": len(ev), "n_controles": len(ctrl),
        "coortes": {int(k): int(v) for k, v in ev.groupby("ano_evento").size().items()},
        "funil_dos_controles": dict(zip(funil.etapa.str.strip(), funil.alimentadores.astype(int), strict=True)),
        "somente_informativo_fora_da_regra": informativo(p, ctrl),
        "religadores_por_snapshot": snap[["ano_snapshot", "circuitos_equipamentos", "religadores", "religadores_telecomandados",
                                           "rede_mt_km", "religadores_por_100km"]].to_dict("records"),
        "transicoes_religadores": tr[["ano_resultado", "religadores_ganhos", "religadores_perdidos", "ganho_liquido",
                                      "circuitos_ganho_ge2", "circuitos_perda_ge2", "eventos_da_coorte"]].to_dict("records"),
    }
