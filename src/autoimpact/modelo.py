"""Estimadores: Poisson com efeitos fixos (PPML) de alimentador e ano, erros-padrão por alimentador.

PPML é o estimador padrão para contagens e somas não negativas com muitos zeros (CHI, CI):
o coeficiente ``b`` de um regressor se lê como variação de ``exp(b) - 1`` no desfecho esperado.
Razões (UC por interrupção, duração por UC) entram como o numerador com o denominador em
``offset``: E[CI] = n_falhas · exp(...) estima o efeito sobre CI por falha.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyfixest as pf

DESFECHOS = {
    # nome: (numerador, exposição ou None)
    "n_falhas": ("n_falhas", None),
    "chi": ("chi", None),
    "ci_por_falha": ("ci", "n_falhas"),
    "duracao_h": ("chi", "ci"),
}


@dataclass
class Efeito:
    desfecho: str
    regressor: str
    coef: float
    ep: float
    n: int
    n_alimentadores: int

    @property
    def efeito_pct(self) -> float:
        return 100 * (np.exp(self.coef) - 1)

    @property
    def ic95_pct(self) -> tuple[float, float]:
        return 100 * (np.exp(self.coef - 1.96 * self.ep) - 1), 100 * (np.exp(self.coef + 1.96 * self.ep) - 1)

    @property
    def p_valor(self) -> float:
        from scipy.stats import norm
        return float(2 * norm.sf(abs(self.coef / self.ep)))

    def registro(self) -> dict:
        lo, hi = self.ic95_pct
        return {"desfecho": self.desfecho, "regressor": self.regressor, "coef": self.coef, "ep": self.ep,
                "efeito_pct": self.efeito_pct, "ic95_lo_pct": lo, "ic95_hi_pct": hi, "p_valor": self.p_valor,
                "n": self.n, "n_alimentadores": self.n_alimentadores}


def ppml_fe(df: pd.DataFrame, y: str, x: list[str], fe: list[str], exposicao: str | None = None,
            cluster: str = "alimentador"):
    """Poisson com efeitos fixos (pyfixest), erros-padrão agrupados por ``cluster``.

    Devolve ``(coeficientes, erros-padrão, dados usados)``. Grupos sem variação no desfecho
    (sempre zero) não identificam nada e são removidos.
    """
    d = df.dropna(subset=[y, *x] + ([exposicao] if exposicao else [])).copy()
    if exposicao:
        d = d[d[exposicao] > 0]
        d["_log_expo"] = np.log(d[exposicao].astype(float))
    for f in fe:
        d = d[d.groupby(f)[y].transform("sum") > 0]
    d = d.rename(columns={y: "_y"})
    d["_y"] = d["_y"].astype(float)
    for c in x:
        d[c] = d[c].astype(float)
    fml = f"_y ~ {' + '.join(x)} | {' + '.join(fe)}"
    r = pf.fepois(fml, data=d, vcov={"CRV1": cluster}, offset="_log_expo" if exposicao else None,
                  iwls_maxiter=100)
    return r.coef(), r.se(), d.rename(columns={"_y": y})


def efeito(df: pd.DataFrame, desfecho: str, regressor: str, controles: list[str] | None = None,
           fe: tuple[str, ...] = ("alimentador", "ano")) -> Efeito:
    """Efeito de uma unidade a mais de ``regressor`` (TWFE Poisson, efeitos fixos de alimentador e ano)."""
    num, expo = DESFECHOS[desfecho]
    b, se, d = ppml_fe(df, num, [regressor, *(controles or [])], list(fe), exposicao=expo)
    return Efeito(desfecho, regressor, float(b[regressor]), float(se[regressor]), len(d),
                  int(d.alimentador.nunique()))


def empilhar(p: pd.DataFrame, eventos: pd.DataFrame, controles: pd.Index, janela: tuple[int, int] = (-3, 2),
             ) -> pd.DataFrame:
    """Diferenças em diferenças empilhado (stacked DiD) por coorte de tratamento.

    Para cada ano de evento ``g``, junta os alimentadores tratados em ``g`` e os nunca tratados,
    restritos à janela ``[g + janela[0], g + janela[1]]``. Cada coorte vira um "experimento"
    com seus próprios efeitos fixos, o que evita comparar tratados tardios com tratados cedo.
    """
    pilhas = []
    for g, ev in eventos.groupby("ano_evento"):
        anos = range(g + janela[0], g + janela[1] + 1)
        trat = p[p.alimentador.isin(ev.alimentador) & p.ano.isin(anos)].assign(tratado=1)
        ctrl = p[p.alimentador.isin(controles) & p.ano.isin(anos)].assign(tratado=0)
        s = pd.concat([trat, ctrl]).assign(coorte=g, rel=lambda d, g=g: d.ano - g)
        pilhas.append(s)
    out = pd.concat(pilhas, ignore_index=True)
    out["alim_coorte"] = out.alimentador + "_" + out.coorte.astype(str)
    out["ano_coorte"] = out.ano.astype(str) + "_" + out.coorte.astype(str)
    out["pos"] = ((out.rel >= 0) & (out.tratado == 1)).astype(int)
    return out


def event_study(pilha: pd.DataFrame, desfecho: str, ref: int = -1) -> pd.DataFrame:
    num, expo = DESFECHOS[desfecho]
    d = pilha.copy()
    rels = sorted(r for r in d.rel.unique() if r != ref)
    cols = []
    for r in rels:
        c = f"rel_{r}".replace("-", "m")
        d[c] = ((d.rel == r) & (d.tratado == 1)).astype(float)
        cols.append(c)
    b, se, _ = ppml_fe(d, num, cols, ["alim_coorte", "ano_coorte"], exposicao=expo)
    out = pd.DataFrame({"rel": rels, "coef": [b[c] for c in cols], "ep": [se[c] for c in cols]})
    out["efeito_pct"] = 100 * (np.exp(out.coef) - 1)
    out["lo_pct"] = 100 * (np.exp(out.coef - 1.96 * out.ep) - 1)
    out["hi_pct"] = 100 * (np.exp(out.coef + 1.96 * out.ep) - 1)
    out = pd.concat([out, pd.DataFrame({"rel": [ref], "coef": [0.0], "ep": [0.0], "efeito_pct": [0.0],
                                        "lo_pct": [0.0], "hi_pct": [0.0]})]).sort_values("rel")
    return out.assign(desfecho=desfecho)


def did_pilha(pilha: pd.DataFrame, desfecho: str) -> Efeito:
    num, expo = DESFECHOS[desfecho]
    b, se, d = ppml_fe(pilha, num, ["pos"], ["alim_coorte", "ano_coorte"], exposicao=expo)
    return Efeito(desfecho, "pos_tratamento", float(b["pos"]), float(se["pos"]), len(d),
                  int(d.alimentador.nunique()))
