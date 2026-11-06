"""Testes do DiD robusto à adoção escalonada (sintéticos, determinísticos, sem rede)."""
import numpy as np
import pandas as pd
import pytest

from autoimpact import did_escalonado as de
from autoimpact import modelo


def _painel_sintetico(tau: dict, n_ctrl: int = 12, n_coorte: int = 25, escala: float = 1e5, seed: int = 0,
                      anos=range(2019, 2026), tendencia_tratados: float = 0.0):
    """Alimentadores × anos com efeito multiplicativo exp(tau[g](e)) a partir do evento.

    ``tau``: {ano_do_evento: função do tempo relativo e -> efeito em log}. ``escala`` grande = ruído de
    Poisson desprezível. ``tendencia_tratados``: tendência log-linear por ano só nos tratados (sem efeito).
    """
    rng = np.random.default_rng(seed)
    anos = list(anos)
    unidades = [("c", i, None) for i in range(n_ctrl)] + [(f"g{g}", i, g) for g in tau for i in range(n_coorte)]
    choque = dict(zip(anos, rng.normal(0, 0.05, len(anos))))
    linhas, ev = [], []
    for tipo, i, g in unidades:
        nome = f"{tipo}_{i}"
        nivel = rng.normal(0, 0.4)
        if g:
            ev.append({"alimentador": nome, "ano_evento": g})
        for y in anos:
            e = y - g if g else None
            efeito = tau[g](e) if (g and e >= 0) else 0.0
            tend = tendencia_tratados * (y - anos[0]) if g else 0.0
            mu = escala * np.exp(nivel + choque[y] + efeito + tend)
            linhas.append({"alimentador": nome, "ano": y, "chi": float(rng.poisson(mu)),
                           "ci": float(rng.poisson(mu / 2) + 1), "n_falhas": float(rng.poisson(mu / 1e3) + 1),
                           "pos": float(bool(g) and e >= 0)})
    p = pd.DataFrame(linhas)
    return p, pd.DataFrame(ev), pd.Index(sorted(a for a in p.alimentador if a.startswith("c_")))


# ----------------------------------------------------------------------------- simulação do problema
TAU_HETEROGENEO = {2021: lambda e: -0.15 * (e + 1), 2023: lambda e: -0.05}


def _verdade_post(tau: dict) -> float:
    """Efeito verdadeiro que ``post`` estima: média de e = 0, 1, 2 do efeito médio das coortes observáveis em e."""
    ate = 2025
    por_e = [np.mean([t(e) for g, t in tau.items() if g + e <= ate]) for e in (0, 1, 2)]
    return float(np.mean(por_e))


def test_simulacao_twfe_erra_e_cs_recupera():
    """Efeitos que crescem com o tempo e diferem por coorte, com poucos controles.

    O TWFE comum usa a coorte de 2021 (já tratada, efeito crescendo) como controle da de 2023 e subestima o
    efeito por uma margem grande, com IC que não contém a verdade. O CS recupera o efeito verdadeiro.
    O DiD empilhado (o estimador do resultado principal do README) também fica perto da verdade: o CS é uma
    conferência do empilhado, e não uma correção dele.
    """
    p, ev, ctrl = _painel_sintetico(TAU_HETEROGENEO)
    verdade = 100 * (np.exp(_verdade_post(TAU_HETEROGENEO)) - 1)  # -16,05%

    res = de.estimar(p, ev, ctrl, "chi", B=200)
    cs = res.resumo("post")
    assert cs["efeito_pct"] == pytest.approx(verdade, abs=1.0)
    # sem efeito antes do tratamento
    assert abs(res.resumo("e-2")["efeito_pct"]) < 1.0

    tw = de.twfe_binario(p, ev, ctrl, "chi")
    lo, hi = tw.ic95_pct
    assert abs(tw.efeito_pct - verdade) > 6          # erra por mais de 6 p.p. (subestima à metade)
    assert not (lo < verdade < hi)                   # e o IC não contém a verdade
    assert abs(tw.efeito_pct) < 0.6 * abs(verdade)

    st = modelo.did_pilha(modelo.empilhar(p, ev, ctrl), "chi")
    assert st.efeito_pct == pytest.approx(verdade, abs=3.0)
    print(f"simulação (pytest -s): verdade {verdade:.2f}% | CS {cs['efeito_pct']:.2f}% | "
          f"TWFE {tw.efeito_pct:.2f}% (IC {lo:.2f} a {hi:.2f}) | empilhado {st.efeito_pct:.2f}%")


def test_simulacao_cs_recupera_cada_tempo_relativo():
    p, ev, ctrl = _painel_sintetico(TAU_HETEROGENEO, escala=2e3, seed=3)
    res = de.estimar(p, ev, ctrl, "chi", B=200)
    for e in (0, 1, 2):
        verdade = 100 * (np.exp(np.mean([t(e) for g, t in TAU_HETEROGENEO.items() if g + e <= 2025])) - 1)
        r = res.resumo(f"e{e}")
        assert r["lo_pct"] < verdade < r["hi_pct"], (e, verdade, r)


# ----------------------------------------------------------------------------- equivalência com o PPML
def test_att_2x2_igual_ao_poisson_com_efeitos_fixos():
    rng = np.random.default_rng(5)
    linhas, ev = [], []
    for i in range(14):
        tratado = i < 6
        base = rng.uniform(20, 200)
        for y in (2021, 2022):
            mu = base * (1.1 if y == 2022 else 1.0) * (0.8 if (tratado and y == 2022) else 1.0)
            linhas.append({"alimentador": f"a{i}", "ano": y, "chi": float(rng.poisson(mu) + 1), "ci": 1.0,
                           "n_falhas": 1.0, "pos": float(tratado and y == 2022)})
        if tratado:
            ev.append({"alimentador": f"a{i}", "ano_evento": 2022})
    p, ev = pd.DataFrame(linhas), pd.DataFrame(ev)
    ctrl = pd.Index([f"a{i}" for i in range(6, 14)])
    ppml, _, _ = modelo.ppml_fe(p, "chi", ["pos"], ["alimentador", "ano"])
    res = de.estimar(p, ev, ctrl, "chi", B=30)
    assert res.ponto["e0"] == pytest.approx(float(ppml["pos"]), abs=1e-6)


def test_att_calculo_manual():
    """3 tratados 10 -> 15 e 3 controles 20 -> 22: ATT = log(1,5 / 1,1)."""
    linhas, ev = [], []
    for i in range(3):
        for y, v in ((2020, 10.0), (2021, 15.0)):
            linhas.append({"alimentador": f"t{i}", "ano": y, "chi": v, "ci": 1.0, "n_falhas": 1.0})
        ev.append({"alimentador": f"t{i}", "ano_evento": 2021})
    for i in range(3):
        for y, v in ((2020, 20.0), (2021, 22.0)):
            linhas.append({"alimentador": f"c{i}", "ano": y, "chi": v, "ci": 1.0, "n_falhas": 1.0})
    p, ev = pd.DataFrame(linhas), pd.DataFrame(ev)
    att, w = de.att_celulas(de.planejar(de.preparar(p, ev, pd.Index(["c0", "c1", "c2"]), "chi")))
    assert att == pytest.approx([np.log(1.5 / 1.1)])
    assert w == pytest.approx([3.0])


# ----------------------------------------------------------------------------- pré-tendência
def test_ajuste_de_tendencia_remove_tendencia_diferencial_linear():
    """Tratados com tendência de -8%/ano e efeito nulo: o efeito bruto aparece, o ajustado volta a zero."""
    tau_zero = {2021: lambda e: 0.0, 2022: lambda e: 0.0}
    p, ev, ctrl = _painel_sintetico(tau_zero, tendencia_tratados=-0.08, seed=2)
    res = de.estimar(p, ev, ctrl, "chi", B=200)
    bruto = res.resumo("post")
    assert bruto["efeito_pct"] < -10 and bruto["hi_pct"] < -5     # parece um efeito de -15%
    tab = de.ajuste_tendencia(res).set_index("lambda")
    assert tab.loc[0.0, "efeito_pct"] == pytest.approx(bruto["efeito_pct"])
    assert tab.loc[1.0, "efeito_pct"] == pytest.approx(0.0, abs=0.5)
    assert tab.loc[1.0, "lo_pct"] < 0 < tab.loc[1.0, "hi_pct"]
    eq = de.lambda_equilibrio(tab.reset_index())
    assert 0.9 <= eq["lambda_ponto_zero"] <= 1.1
    # a versão restrita às coortes com 3 anos pré também zera (aqui só a coorte de 2022 tem)
    tab_pb = de.ajuste_tendencia(res, prefixo="pb_").set_index("lambda")
    assert tab_pb.loc[1.0, "efeito_pct"] == pytest.approx(0.0, abs=0.5)


def test_declive_e_ajuste_pontual():
    assert de.declive_pre(0.2, 0.1) == pytest.approx((-0.4 - 0.1) / 5)
    es = pd.DataFrame({"rel": [-3, -2, -1, 0, 1, 2], "coef": [0.2, 0.1, 0.0, -0.1, -0.2, -0.3]})
    aj = de.ajuste_tendencia_pontual(es)
    assert aj["post_sem_ajuste"] == pytest.approx(-0.2)
    assert aj["post_ajustado"] == pytest.approx(-0.2 - aj["declive_por_ano"] * 2)


# ----------------------------------------------------------------------------- bootstrap
def test_sorteio_estratificado_e_reprodutivel():
    p, ev, ctrl = _painel_sintetico(TAU_HETEROGENEO, n_ctrl=6, n_coorte=5)
    dados = de.preparar(p, ev, ctrl, "chi")
    c1, c2 = de.sortear(dados, 25, 7), de.sortear(dados, 25, 7)
    assert (c1 == c2).all()
    assert not (c1 == de.sortear(dados, 25, 8)).all()
    for s in set(dados.estrato):
        assert (c1[:, dados.estrato == s].sum(axis=1) == (dados.estrato == s).sum()).all()


# ----------------------------------------------------------------------------- fumaça do núcleo
def test_fumaca_nucleo_minusculo():
    """Painel minúsculo ponta a ponta: estimar, event study, tendência, TWFE; determinístico."""
    tau = {2021: lambda e: -0.2, 2022: lambda e: -0.1}
    p, ev, ctrl = _painel_sintetico(tau, n_ctrl=5, n_coorte=3, escala=500, seed=11, anos=range(2019, 2024))
    r1 = de.estimar(p, ev, ctrl, "duracao_h", B=40)
    r2 = de.estimar(p, ev, ctrl, "duracao_h", B=40)
    pd.testing.assert_frame_equal(r1.replicas, r2.replicas)
    assert np.isfinite(r1.ponto["post"]) and np.isfinite(r1.resumo("post")["ep"])
    es = de.event_study(r1)
    assert list(es.rel) == [-3, -2, -1, 0, 1, 2] and es.loc[es.rel == -1, "efeito_pct"].item() == 0
    assert set(r1.celulas.columns) >= {"coorte", "ano", "e", "n_tratados", "att_log", "efeito_pct"}
    tab = de.ajuste_tendencia(r1)
    assert len(tab) == len(de.LAMBDAS) and tab["lambda"].iloc[0] == 0
    tw = de.twfe_binario(p, ev, ctrl, "chi")
    assert np.isfinite(tw.coef) and tw.n_alimentadores == 11


def test_regra_de_divergencia():
    ref = {"efeito_pct": -16.6, "lo_pct": -24.8, "hi_pct": -7.5}
    perto = {"efeito_pct": -15.0, "lo_pct": -23.0, "hi_pct": -6.0}
    assert not de.divergencia(perto, ref)["dispara"]
    longe = {"efeito_pct": -23.0, "lo_pct": -30.0, "hi_pct": -15.0}
    r = de.divergencia(longe, ref)
    assert r["dispara"] and r["gap_pp"] == pytest.approx(-6.4)
    zero = {"efeito_pct": -12.0, "lo_pct": -26.0, "hi_pct": 3.0}   # IC com zero, o de referência não tem
    assert any("zero" in m for m in de.divergencia(zero, ref)["motivos"])
