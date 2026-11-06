"""DiD robusto à adoção escalonada: Callaway & Sant'Anna (2021) em escala multiplicativa.

Complementa, sem substituir, o DiD empilhado e o TWFE de ``modelo``. Definições e regras de relato
em ``docs/preregistro_did_escalonado.md``.

* ``ATT(g,t)``: para a coorte ``g`` (primeiro ano de resultado com o religador novo) e o ano ``t``,
  compara a razão de somas do grupo tratado entre ``t`` e ``g-1`` com a razão de somas dos controles
  nunca tratados no mesmo intervalo. É o log da razão de razões; em um 2x2 coincide com o coeficiente
  do Poisson com efeitos fixos (PPML) de ``modelo``, então a escala é a mesma do resultado principal.
* Agregação por tempo relativo ``e = t - g`` e resumo pós-tratamento (média de ``e`` = 0, 1, 2).
* Erro-padrão e IC: bootstrap por alimentador, estratificado por coorte e controles.
* Sensibilidade à pré-tendência: extrapolação linear da tendência anterior, com o declive
  reestimado em cada réplica do bootstrap.

Desfechos de razão (duração = CHI/CI) usam o numerador e o denominador de ``modelo.DESFECHOS``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from autoimpact import modelo

JANELA = (-3, 2)
MIN_TRATADOS = 3
B_PADRAO = 2000
SEMENTE = 20261106
TEMPOS_ES = (-3, -2, 0, 1, 2)  # e = -1 é a referência (zero por construção)
TEMPOS_POS = (0, 1, 2)
LAMBDAS = tuple(round(x, 2) for x in np.arange(0, 1.5001, 0.05))


# --------------------------------------------------------------------------------- dados e plano
@dataclass
class Dados:
    """Alimentadores × anos: numerador, denominador e máscara de observação."""
    anos: np.ndarray
    unidades: np.ndarray       # nome do alimentador
    estrato: np.ndarray        # ano da coorte (> 0) ou 0 para controle nunca tratado
    n: np.ndarray              # (U, T), 0 onde não observado
    d: np.ndarray              # (U, T), 0 onde não observado
    obs: np.ndarray            # (U, T) bool


@dataclass
class Plano:
    """Células (g, t) a estimar, com o que é preciso para recalcular rápido a cada réplica."""
    g: np.ndarray
    t: np.ndarray
    e: np.ndarray
    n_tratados: np.ndarray                 # alimentadores tratados na célula (amostra original)
    idx_g: list[np.ndarray]                # posições das unidades da coorte
    x_g: list[np.ndarray]                  # (k, 5): m·N_t, m·D_t, m·N_b, m·D_b, m
    idx_c: list[np.ndarray]
    x_c: list[np.ndarray]
    grupos: dict[str, np.ndarray]          # chave de agregação -> posições das células
    descartadas: pd.DataFrame = field(default_factory=pd.DataFrame)


def preparar(p: pd.DataFrame, eventos: pd.DataFrame, controles, desfecho: str) -> Dados:
    """Monta as matrizes alimentador × ano do desfecho. ``eventos``: alimentador, ano_evento."""
    num, den = modelo.DESFECHOS[desfecho]
    ev = eventos.drop_duplicates("alimentador").set_index("alimentador").ano_evento
    ctrl = pd.Index(controles).difference(ev.index)
    nomes = list(ev.index) + list(ctrl)
    sub = p[p.alimentador.isin(nomes)]
    anos = np.array(sorted(sub.ano.unique()))
    wn = sub.pivot(index="alimentador", columns="ano", values=num).reindex(index=nomes, columns=anos)
    obs = wn.notna().to_numpy().copy()
    if den is None:
        wd = pd.DataFrame(1.0, index=wn.index, columns=wn.columns)
    else:
        wd = sub.pivot(index="alimentador", columns="ano", values=den).reindex(index=nomes, columns=anos)
        obs = obs & wd.notna().to_numpy()
    estrato = np.array([int(ev[a]) for a in ev.index] + [0] * len(ctrl))
    n = np.where(obs, wn.to_numpy(dtype=float), 0.0)
    d = np.where(obs, wd.to_numpy(dtype=float), 0.0)
    return Dados(anos, np.array(nomes), estrato, n, d, obs)


def planejar(dados: Dados, janela: tuple[int, int] = JANELA, min_tratados: int = MIN_TRATADOS) -> Plano:
    anos = list(dados.anos)
    idx_ctrl = np.flatnonzero(dados.estrato == 0)
    coortes = sorted({int(g) for g in dados.estrato if g > 0})
    reg = {k: [] for k in ["g", "t", "e", "n_tratados"]}
    idx_g, x_g, idx_c, x_c, desc = [], [], [], [], []
    for g in coortes:
        if g - 1 not in anos:
            desc.append({"g": g, "e": None, "motivo": "sem ano-base g-1"})
            continue
        ib = anos.index(g - 1)
        ig = np.flatnonzero(dados.estrato == g)
        for e in range(janela[0], janela[1] + 1):
            if e == -1 or g + e not in anos:
                continue
            it = anos.index(g + e)
            mg = dados.obs[ig, it] & dados.obs[ig, ib]
            mc = dados.obs[idx_ctrl, it] & dados.obs[idx_ctrl, ib]
            if mg.sum() < min_tratados or mc.sum() < min_tratados:
                desc.append({"g": g, "e": e, "motivo": f"tratados={int(mg.sum())}, controles={int(mc.sum())}"})
                continue
            reg["g"].append(g)
            reg["t"].append(g + e)
            reg["e"].append(e)
            reg["n_tratados"].append(int(mg.sum()))
            idx_g.append(ig)
            idx_c.append(idx_ctrl)
            x_g.append(_colunas(dados, ig, it, ib, mg))
            x_c.append(_colunas(dados, idx_ctrl, it, ib, mc))
    arr = {k: np.array(v) for k, v in reg.items()}
    g_, e_ = arr["g"], arr["e"]
    por_coorte = {g: set(e_[g_ == g]) for g in set(g_)}
    bal = [g for g, es in por_coorte.items() if set(TEMPOS_POS) <= es]
    pre_bal = [g for g, es in por_coorte.items() if {-3, -2, *TEMPOS_POS} <= es]
    grupos: dict[str, np.ndarray] = {}
    for tt in TEMPOS_ES:
        grupos[f"e{tt}"] = np.flatnonzero(e_ == tt)
        grupos[f"pb_e{tt}"] = np.flatnonzero((e_ == tt) & np.isin(g_, pre_bal))
        if tt >= 0:
            grupos[f"bal_e{tt}"] = np.flatnonzero((e_ == tt) & np.isin(g_, bal))
    grupos["simples"] = np.flatnonzero(e_ >= 0)
    return Plano(g_, arr["t"], e_, arr["n_tratados"], idx_g, x_g, idx_c, x_c, grupos,
                 pd.DataFrame(desc, columns=["g", "e", "motivo"]))


def _colunas(dados: Dados, idx: np.ndarray, it: int, ib: int, m: np.ndarray) -> np.ndarray:
    mf = m.astype(float)
    return np.column_stack([mf * dados.n[idx, it], mf * dados.d[idx, it],
                            mf * dados.n[idx, ib], mf * dados.d[idx, ib], mf])


# --------------------------------------------------------------------------------- estimação
def _razao_log(s: np.ndarray) -> float:
    """log[(N_t/D_t)/(N_b/D_b)] a partir de (N_t, D_t, N_b, D_b); NaN se alguma soma não for positiva."""
    if min(s[0], s[1], s[2], s[3]) <= 0:
        return np.nan
    return float(np.log(s[0] / s[1]) - np.log(s[2] / s[3]))


def att_celulas(plano: Plano, contagem: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """ATT(g,t) de todas as células e o nº (ponderado) de tratados em cada uma.

    ``contagem``: quantas vezes cada unidade entra na amostra (réplica do bootstrap); ``None`` = amostra original.
    """
    k = len(plano.g)
    att, w = np.full(k, np.nan), np.zeros(k)
    for j in range(k):
        cg = np.ones(len(plano.idx_g[j])) if contagem is None else contagem[plano.idx_g[j]]
        cc = np.ones(len(plano.idx_c[j])) if contagem is None else contagem[plano.idx_c[j]]
        sg, sc = cg @ plano.x_g[j], cc @ plano.x_c[j]
        att[j] = _razao_log(sg[:4]) - _razao_log(sc[:4])
        w[j] = sg[4]
    return att, w


def _media_ponderada(att: np.ndarray, w: np.ndarray, pos: np.ndarray) -> float:
    if len(pos) == 0:
        return np.nan
    a, ww = att[pos], w[pos]
    ok = np.isfinite(a) & (ww > 0)
    return float(np.sum(ww[ok] * a[ok]) / np.sum(ww[ok])) if ok.any() else np.nan


def agregar(plano: Plano, att: np.ndarray, w: np.ndarray) -> dict[str, float]:
    """θ(e) por tempo relativo, resumo pós-tratamento e variantes (log do efeito)."""
    out: dict[str, float] = {}
    for tt in TEMPOS_ES:
        out[f"e{tt}"] = _media_ponderada(att, w, plano.grupos[f"e{tt}"])
        out[f"pb_e{tt}"] = _media_ponderada(att, w, plano.grupos[f"pb_e{tt}"])
    for pre in ["", "pb_"]:
        v = [out[f"{pre}e{tt}"] for tt in TEMPOS_POS]
        out[f"{pre}post"] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
    out["simples"] = _media_ponderada(att, w, plano.grupos["simples"])
    vb = [_media_ponderada(att, w, plano.grupos[f"bal_e{tt}"]) for tt in TEMPOS_POS]
    out["balanceado"] = float(np.nanmean(vb)) if np.isfinite(vb).any() else np.nan
    return out


def sortear(dados: Dados, B: int = B_PADRAO, semente: int = SEMENTE) -> np.ndarray:
    """Contagens de bootstrap (B × unidades): reamostra com reposição dentro de cada estrato.

    Os mesmos sorteios servem para todos os desfechos (réplicas pareadas), desde que as unidades sejam as mesmas.
    """
    rng = np.random.default_rng(semente)
    cont = np.zeros((B, len(dados.unidades)), dtype=np.int32)
    for s in sorted(set(dados.estrato)):
        pos = np.flatnonzero(dados.estrato == s)
        sorteio = rng.integers(0, len(pos), size=(B, len(pos)))
        for b in range(B):
            cont[b, pos] = np.bincount(sorteio[b], minlength=len(pos))
    return cont


@dataclass
class Resultado:
    desfecho: str
    plano: Plano
    celulas: pd.DataFrame
    ponto: pd.Series
    replicas: pd.DataFrame

    def resumo(self, chave: str) -> dict:
        """Estimativa, erro-padrão e IC 95% (percentis) do log do efeito para uma chave de ``agregar``."""
        return resumir(float(self.ponto[chave]), self.replicas[chave].to_numpy())


def resumir(theta: float, reps: np.ndarray) -> dict:
    """Estimativa, EP e IC 95% (percentis das réplicas) a partir do log do efeito e das réplicas."""
    reps = reps[np.isfinite(reps)]
    if len(reps) < 20 or not np.isfinite(theta):
        return {"theta": theta, "efeito_pct": _pct(theta), "ep": np.nan, "lo_pct": np.nan, "hi_pct": np.nan,
                "p_boot": np.nan, "n_replicas": len(reps)}
    lo, hi = np.percentile(reps, [2.5, 97.5])
    p = 2 * min(np.mean(reps <= 0), np.mean(reps >= 0))
    return {"theta": theta, "efeito_pct": _pct(theta), "ep": float(np.std(reps, ddof=1)), "lo_pct": _pct(lo),
            "hi_pct": _pct(hi), "p_boot": float(min(1.0, max(p, 1 / (len(reps) + 1)))), "n_replicas": len(reps)}


def _pct(theta: float) -> float:
    return float(100 * (np.exp(theta) - 1))


def estimar(p: pd.DataFrame, eventos: pd.DataFrame, controles, desfecho: str, contagens: np.ndarray | None = None,
            B: int = B_PADRAO, semente: int = SEMENTE, janela: tuple[int, int] = JANELA,
            min_tratados: int = MIN_TRATADOS) -> Resultado:
    """CS por célula, agregações e bootstrap. Passe ``contagens`` (de ``sortear``) para réplicas pareadas."""
    dados = preparar(p, eventos, controles, desfecho)
    plano = planejar(dados, janela, min_tratados)
    att, w = att_celulas(plano)
    ponto = pd.Series(agregar(plano, att, w))
    if contagens is None:
        contagens = sortear(dados, B, semente)
    reps = []
    for c in contagens:
        a, ww = att_celulas(plano, c)
        reps.append(agregar(plano, a, ww))
    cel = pd.DataFrame({"desfecho": desfecho, "coorte": plano.g, "ano": plano.t, "e": plano.e,
                        "n_tratados": plano.n_tratados, "att_log": att, "efeito_pct": [_pct(x) for x in att]})
    return Resultado(desfecho, plano, cel.sort_values(["coorte", "e"]).reset_index(drop=True), ponto,
                     pd.DataFrame(reps))


def event_study(res: Resultado, prefixo: str = "") -> pd.DataFrame:
    """θ(e) em % com IC 95% para e = -3..2; e = -1 é a referência. ``prefixo='pb_'``: coortes com 3 anos pré."""
    linhas = []
    for tt in range(JANELA[0], JANELA[1] + 1):
        if tt == -1:
            linhas.append({"rel": tt, "theta": 0.0, "efeito_pct": 0.0, "ep": 0.0, "lo_pct": 0.0, "hi_pct": 0.0})
            continue
        r = res.resumo(f"{prefixo}e{tt}")
        linhas.append({"rel": tt, **{k: r[k] for k in ["theta", "efeito_pct", "ep", "lo_pct", "hi_pct"]}})
    return pd.DataFrame(linhas).assign(desfecho=res.desfecho)


# --------------------------------------------------------------------------------- pré-tendência
def declive_pre(theta_m3: np.ndarray | float, theta_m2: np.ndarray | float):
    """Declive por ano da tendência anterior: mínimos quadrados em e = -3, -2, -1 passando por zero em -1."""
    return (-2.0 * np.asarray(theta_m3) - 1.0 * np.asarray(theta_m2)) / 5.0


def pos_ajustado(theta_e: dict[int, np.ndarray | float], delta, lam: float) -> np.ndarray:
    """Média de θ(e) − λ·δ·(e+1) para e = 0, 1, 2 (só os e disponíveis); devolve um vetor (uma entrada por réplica)."""
    d = np.atleast_1d(np.asarray(delta, dtype=float))
    partes = [np.atleast_1d(np.asarray(theta_e[e], dtype=float)) - lam * d * (e + 1) for e in TEMPOS_POS]
    return np.nanmean(np.vstack(partes), axis=0)


def pos_ajustado_resultado(res: Resultado, lam: float, prefixo: str = "") -> tuple[float, np.ndarray]:
    """θ_pós ajustado pela pré-tendência (ponto e réplicas) para um λ."""
    pt, rp = res.ponto, res.replicas
    d_pt = float(declive_pre(pt[f"{prefixo}e-3"], pt[f"{prefixo}e-2"]))
    d_rp = declive_pre(rp[f"{prefixo}e-3"].to_numpy(), rp[f"{prefixo}e-2"].to_numpy())
    th_pt = {e: float(pt[f"{prefixo}e{e}"]) for e in TEMPOS_POS}
    th_rp = {e: rp[f"{prefixo}e{e}"].to_numpy() for e in TEMPOS_POS}
    return float(pos_ajustado(th_pt, d_pt, lam)[0]), pos_ajustado(th_rp, d_rp, lam)


def ajuste_tendencia(res: Resultado, prefixo: str = "", lambdas=LAMBDAS) -> pd.DataFrame:
    """Efeito pós-tratamento ajustado pela extrapolação linear da pré-tendência, para cada λ.

    λ = 0 é o efeito sem ajuste; λ = 1, a tendência anterior continua inteira. O declive é
    reestimado em cada réplica do bootstrap, então o IC inclui a incerteza da tendência.
    """
    d_pt = float(declive_pre(res.ponto[f"{prefixo}e-3"], res.ponto[f"{prefixo}e-2"]))
    linhas = []
    for lam in lambdas:
        theta, reps = pos_ajustado_resultado(res, lam, prefixo)
        linhas.append({"lambda": lam, "declive_por_ano": d_pt, **resumir(theta, reps)})
    return pd.DataFrame(linhas).assign(desfecho=res.desfecho, amostra="pre-balanceada" if prefixo else "todas")


def lambda_equilibrio(tab: pd.DataFrame) -> dict:
    """Menor λ da grade em que o IC passa a conter zero, e λ analítico em que o ponto chega a zero."""
    t = tab.sort_values("lambda")
    base = t.iloc[0]
    sinal = np.sign(base.efeito_pct)
    contem0 = (t.lo_pct <= 0) & (t.hi_pct >= 0)
    lam_ic = float(t.loc[contem0, "lambda"].iloc[0]) if contem0.any() else None
    cruza = t[np.sign(t.efeito_pct) != sinal]
    lam_pt = float(cruza["lambda"].iloc[0]) if len(cruza) and sinal != 0 else None
    return {"lambda_ic_contem_zero": lam_ic, "lambda_ponto_zero": lam_pt}


def ajuste_tendencia_pontual(es: pd.DataFrame, col: str = "coef") -> dict:
    """Mesmo ajuste (λ = 1) nos coeficientes do event study empilhado (só ponto, sem IC)."""
    c = es.set_index("rel")[col]
    delta = float(declive_pre(c[-3], c[-2]))
    th = {e: float(c[e]) for e in TEMPOS_POS}
    return {"declive_por_ano": delta, "post_sem_ajuste": float(np.mean(list(th.values()))),
            "post_ajustado": float(pos_ajustado(th, delta, 1.0)[0])}


# --------------------------------------------------------------------------------- comparador
def twfe_binario(p: pd.DataFrame, eventos: pd.DataFrame, controles, desfecho: str) -> modelo.Efeito:
    """TWFE comum: um indicador "pós-evento", efeitos fixos de alimentador e ano, sem empilhar nem coortes."""
    ev = eventos.drop_duplicates("alimentador").set_index("alimentador").ano_evento
    sub = p[p.alimentador.isin(ev.index) | p.alimentador.isin(controles)].copy()
    sub["pos_bin"] = (sub.ano >= sub.alimentador.map(ev).fillna(10_000)).astype(float)
    return modelo.efeito(sub, desfecho, "pos_bin", fe=("alimentador", "ano"))


# --------------------------------------------------------------------------------- regra de divergência
def divergencia(cs: dict, ref: dict, limite_pp: float = 5.0) -> dict:
    """Regra D1/D2 do pré-registro: o CS diverge da referência (empilhado)?

    ``cs`` e ``ref``: dicts com ``efeito_pct``, ``lo_pct``, ``hi_pct``. Dispara se a diferença passar de
    ``limite_pp``, se o IC de um não contiver o ponto do outro, ou se só um dos dois ICs contiver zero.
    """
    motivos = []
    gap = cs["efeito_pct"] - ref["efeito_pct"]
    if abs(gap) > limite_pp:
        motivos.append(f"diferença de {gap:+.1f} p.p. (limite {limite_pp:g})")
    if not cs["lo_pct"] <= ref["efeito_pct"] <= cs["hi_pct"]:
        motivos.append("o IC do CS não contém o ponto do empilhado")
    if not ref["lo_pct"] <= cs["efeito_pct"] <= ref["hi_pct"]:
        motivos.append("o IC do empilhado não contém o ponto do CS")
    if (cs["lo_pct"] <= 0 <= cs["hi_pct"]) != (ref["lo_pct"] <= 0 <= ref["hi_pct"]):
        motivos.append("só um dos dois ICs contém zero")
    return {"gap_pp": float(gap), "dispara": bool(motivos), "motivos": motivos}
