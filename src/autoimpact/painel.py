"""Painel alimentador × ano: equipamentos em 31/12 de y-1 e continuidade observada em y.

Desfechos (falhas de MT, internas, não programadas, por alimentador canônico):

* ``n_falhas``  interrupções sustentadas no ano;
* ``chi``       consumidor-hora interrompido;
* ``ci``        consumidores interrompidos (soma de UC afetadas);
* ``ci_por_falha`` UC afetadas por interrupção: é onde o seccionamento atua;
* ``duracao_h`` CHI / CI, duração média ponderada por UC: é onde o telecomando atua.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EQUIP = ["n_religadores", "n_religadores_tlcd", "n_disjuntores", "n_seccionalizadores", "n_chaves_fusiveis",
         "n_tlcd_rede"]


def desfechos_anuais(falhas: pd.DataFrame) -> pd.DataFrame:
    """Soma as falhas mensais por modo para alimentador × ano."""
    d = falhas.groupby(["alimentador", "ano"], as_index=False)[["n_falhas", "chi", "chi_regulatorio", "ci"]].sum()
    d["ci_por_falha"] = d.ci / d.n_falhas.replace(0, np.nan)
    d["duracao_h"] = d.chi / d.ci.replace(0, np.nan)
    return d


def montar(falhas: pd.DataFrame, equip: dict[int, pd.DataFrame], feeders: dict[int, pd.DataFrame],
           anos: list[int]) -> pd.DataFrame:
    """Uma linha por alimentador × ano de resultado ``y``, com cadastro de 31/12 de ``y-1``.

    ``equip[a]``: saída de ``bdgd.equipamentos_por_alimentador`` do snapshot ``a``;
    ``feeders[a]``: atributos de rede do snapshot ``a`` (rede_mt_km, n_uc, frac_rural...).
    Alimentadores sem nenhuma falha no ano entram com zero.
    """
    des = desfechos_anuais(falhas)
    linhas = []
    for y in anos:
        if y - 1 not in equip or y - 1 not in feeders:
            continue
        f = (feeders[y - 1].rename(columns={"alimentador_nome": "alimentador"})
             .drop_duplicates("alimentador")[["alimentador", "rede_mt_km", "n_uc", "frac_rural", "n_trafos"]])
        e = equip[y - 1].drop(columns=["ano_snapshot"], errors="ignore")
        df = f.merge(e, on="alimentador", how="inner").assign(ano=y)
        df = df.merge(des[des.ano == y], on=["alimentador", "ano"], how="left")
        linhas.append(df)
    p = pd.concat(linhas, ignore_index=True)
    p[["n_falhas", "chi", "chi_regulatorio", "ci"]] = p[["n_falhas", "chi", "chi_regulatorio", "ci"]].fillna(0)
    p["religadores_100km"] = p.n_religadores / p.rede_mt_km.replace(0, np.nan) * 100
    return p


def estaveis(p: pd.DataFrame, tol: float = 0.2) -> pd.Index:
    """Alimentadores cuja extensão e nº de UC variam menos que ``tol`` em todo o período.

    Divisões e transferências de carga mudam o tamanho do alimentador e confundem o efeito
    dos equipamentos; esta amostra restrita serve de teste de robustez.
    """
    g = p.groupby("alimentador")
    ok = ((g.rede_mt_km.max() / g.rede_mt_km.min().replace(0, np.nan) <= 1 + tol)
          & (g.n_uc.max() / g.n_uc.min().replace(0, np.nan) <= 1 + tol) & (g.ano.nunique() == p.ano.nunique()))
    return ok[ok].index


def eventos_tratamento(p: pd.DataFrame, col: str = "n_religadores", minimo: int = 2) -> pd.DataFrame:
    """Primeiro ano em que o alimentador ganha ``minimo`` ou mais equipamentos de uma vez e os mantém.

    Devolve ``alimentador``, ``ano_evento`` (primeiro ano de resultado com o equipamento novo) e
    o tamanho do ganho. Ganhos seguidos de queda no snapshot seguinte são tratados como ruído
    cadastral e descartados. Alimentadores "nunca tratados" são os que nunca variam mais que 1.
    """
    s = p.pivot_table(index="alimentador", columns="ano", values=col).sort_index(axis=1)
    anos = list(s.columns)
    out = []
    for alim, row in s.iterrows():
        for i in range(1, len(anos)):
            a0, a1 = row[anos[i - 1]], row[anos[i]]
            if np.isnan(a0) or np.isnan(a1):
                continue
            ganho = a1 - a0
            if ganho >= minimo:
                depois = row[anos[i:]].dropna()
                if (depois >= a1 - 0.5).all():
                    out.append({"alimentador": alim, "ano_evento": anos[i], "ganho": ganho, "base": a0})
                break
            if ganho <= -minimo:
                break
    return pd.DataFrame(out, columns=["alimentador", "ano_evento", "ganho", "base"])


def nunca_tratados(p: pd.DataFrame, col: str = "n_religadores", tol: int = 1) -> pd.Index:
    s = p.pivot_table(index="alimentador", columns="ano", values=col)
    amp = s.max(axis=1) - s.min(axis=1)
    return amp[(amp <= tol) & s.notna().all(axis=1)].index


def carregar(gridrisk_interim: Path, interim: Path, anos: list[int]) -> pd.DataFrame:
    falhas = pd.read_parquet(gridrisk_interim / "falhas.parquet")
    snaps = sorted({a - 1 for a in anos})
    equip = {a: pd.read_parquet(interim / f"equipamentos_{a}.parquet") for a in snaps}
    feeders = {a: pd.read_parquet(gridrisk_interim / f"bdgd_feeders_{a}.parquet") for a in snaps}
    return montar(falhas, equip, feeders, anos)
