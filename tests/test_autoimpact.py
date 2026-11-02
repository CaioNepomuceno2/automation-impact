import numpy as np
import pandas as pd
import pytest

from autoimpact import bdgd, modelo, painel, valor


def test_equipamentos_por_alimentador():
    sw = pd.DataFrame({"CTMT": ["1", "1", "1", "2", "2"], "TIP_UNID": ["32", "32", "29", "22", "32"],
                       "TLCD": ["1", "0", "1", "0", "0"]})
    ct = pd.DataFrame({"COD_ID": ["1", "2"], "NOME": ["13014", "17001"], "SUB": ["S1", "S2"]})
    eq = bdgd.equipamentos_por_alimentador(sw, ct).set_index("alimentador")
    assert eq.loc["013014", "n_religadores"] == 2
    assert eq.loc["013014", "n_religadores_tlcd"] == 1
    assert eq.loc["013014", "n_disjuntores"] == 1
    # o disjuntor telecomandado da SE não conta como telecomando na rede
    assert eq.loc["013014", "n_tlcd_rede"] == 1
    assert eq.loc["017001", "n_chaves_fusiveis"] == 1


def _painel(serie: dict[str, list[int]], anos=(2019, 2020, 2021, 2022, 2023)) -> pd.DataFrame:
    linhas = [{"alimentador": a, "ano": y, "n_religadores": v} for a, vs in serie.items() for y, v in zip(anos, vs)]
    return pd.DataFrame(linhas)


def test_eventos_tratamento():
    p = _painel({
        "persistente": [2, 2, 5, 5, 5],
        "transitorio": [2, 2, 5, 2, 2],   # ganho que some no snapshot seguinte = ruído cadastral
        "pequeno": [2, 3, 3, 3, 3],
        "estavel": [4, 4, 4, 4, 4],
    })
    ev = painel.eventos_tratamento(p, minimo=2)
    assert ev.alimentador.tolist() == ["persistente"]
    assert ev.ano_evento.iloc[0] == 2021 and ev.ganho.iloc[0] == 3
    assert set(painel.nunca_tratados(p)) == {"pequeno", "estavel"}


def _simulado(efeito: float, n: int = 300, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    anos = np.arange(2019, 2026)
    nivel = rng.lognormal(3, 0.6, n)
    choque_ano = dict(zip(anos, rng.normal(0, 0.15, len(anos))))
    ev_ano = {i: rng.choice([2021, 2022, 2023]) for i in range(n // 2)}  # metade tratada, em coortes
    linhas = []
    for i in range(n):
        for y in anos:
            tratado = i in ev_ano and y >= ev_ano[i]
            mu = nivel[i] * np.exp(choque_ano[y] + (np.log(1 + efeito) if tratado else 0))
            linhas.append({"alimentador": f"a{i}", "ano": y, "n_religadores": 4 if tratado else 1,
                           "chi": rng.poisson(mu * 50), "n_falhas": rng.poisson(mu)})
    p = pd.DataFrame(linhas)
    p["ci"] = p.chi / 3
    ev = pd.DataFrame({"alimentador": [f"a{i}" for i in ev_ano], "ano_evento": list(ev_ano.values())})
    return p, ev


def test_did_empilhado_recupera_efeito_conhecido():
    p, ev = _simulado(efeito=-0.30)
    ctrl = painel.nunca_tratados(p)
    pilha = modelo.empilhar(p, ev, ctrl)
    est = modelo.did_pilha(pilha, "chi")
    assert est.efeito_pct == pytest.approx(-30, abs=4)
    lo, hi = est.ic95_pct
    assert lo < -30 < hi
    es = modelo.event_study(pilha, "chi").set_index("rel")
    # sem efeito antes do tratamento
    assert abs(es.loc[-3, "efeito_pct"]) < 6 and abs(es.loc[-2, "efeito_pct"]) < 6


def test_did_sem_efeito_nao_e_significativo():
    p, ev = _simulado(efeito=0.0, seed=1)
    est = modelo.did_pilha(modelo.empilhar(p, ev, painel.nunca_tratados(p)), "chi")
    lo, hi = est.ic95_pct
    assert lo < 0 < hi


def test_conversoes():
    assert valor.chi_evitado(1000, np.log(0.8)) == pytest.approx(200)
    assert valor.dec_minutos(1_000_000, 2_000_000) == pytest.approx(30)
    assert valor.anuidade(0.08, 20) == pytest.approx(9.818, abs=1e-3)
    assert valor.vpl(10_000, 50_000, 0.08, 20) == pytest.approx(48_181.5, abs=1)
    assert valor.custo_indisponibilidade(1000, 500, pp=1) == pytest.approx(5000)
