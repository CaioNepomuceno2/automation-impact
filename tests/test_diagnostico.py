"""Tabelas de diagnóstico dos religadores (só contagem): funções puras sobre um painel pequeno e conhecido."""
import pandas as pd

from autoimpact import diagnostico, regra

ANOS = list(range(2019, 2026))


def _painel() -> pd.DataFrame:
    """3 eventos (ganho de 3 em 2021), 4 controles (1 religador sempre), 1 alimentador que some, 1 nome curto, 2 oscilantes."""
    linhas = []

    def add(nome, valores, anos=ANOS, rede=50.0, uc=1000, chi=100.0):
        for y, v in zip(anos, valores, strict=True):
            linhas.append({"alimentador": nome, "ano": y, "n_religadores": float(v), "rede_mt_km": rede, "n_uc": uc, "chi": chi})

    for i in range(3):
        add(f"0EV{i:03d}", [1, 1, 4, 4, 4, 4, 4])
    for i in range(4):
        add(f"0CT{i:03d}", [1] * 7)
    add("0SOME1", [1, 1, 1], anos=ANOS[:3])                 # só 3 dos 7 anos
    add("000ACA", [0], anos=[2020], rede=0.0, uc=0, chi=0.0)   # nome de 3 caracteres, circuito vazio, um ano só
    for i in range(2):
        add(f"0OS{i:03d}", [1, 1, 1, 4, 1, 1, 1])             # ganha e perde 3: nem evento nem controle
    return pd.DataFrame(linhas)


def test_contagens_do_painel_pequeno():
    p = _painel()
    ev, ctrl = regra.eventos_e_controles(p)
    assert (len(ev), len(ctrl)) == (3, 4)
    funil = diagnostico.funil_controles(p, ev, ctrl)
    f = pd.Series(funil.alimentadores.to_numpy(), index=funil.etapa.str.strip())   # as etapas vêm indentadas
    assert f["alimentadores distintos no painel (qualquer ano)"] == 11
    assert f["presentes nos 7 anos de resultado"] == 9
    assert f["e com amplitude de religadores <= 1 (= controles nunca tratados, definição de MT)"] == 4
    assert f["dos quais sem nenhum religador em nenhum ano"] == 0 and f["dos quais com religador em algum ano"] == 4
    assert f["presentes nos 7 anos, mas com amplitude >= 2"] == 5 and f["dos quais são eventos (ganho >= 2 que persiste)"] == 3
    assert f["não presentes nos 7 anos de resultado"] == 2


def test_transicoes_e_coortes():
    p = _painel()
    ev, _ = regra.eventos_e_controles(p)
    t = diagnostico.transicoes(p, ev).set_index("ano_resultado")
    assert list(t.index) == ANOS[1:]
    # 2021: os 3 eventos ganham 3 cada; as oscilantes ganham 3 em 2022 e perdem 3 em 2023
    assert t.loc[2021, "religadores_ganhos"] == 9 and t.loc[2021, "circuitos_ganho_ge3"] == 3 and t.loc[2021, "eventos_da_coorte"] == 3
    assert t.loc[2022, "religadores_perdidos"] == 0 and t.loc[2022, "circuitos_perda_ge2"] == 0
    assert t.loc[2022, "religadores_ganhos"] == 6 and t.loc[2023, "religadores_perdidos"] == 6
    assert t.loc[2023, "ganho_liquido"] == -6
    c = diagnostico.eventos_por_coorte(ev)
    assert c.to_dict("records") == [{"ano_evento": 2021, "eventos": 3, "religadores_adicionados": 9.0, "ganho_mediano": 3.0,
                                     "ganho_maximo": 3.0, "religadores_antes_medianos": 1.0}]


def test_presenca_separa_nomes_curtos():
    pr = diagnostico.presenca(_painel()).set_index("anos_presentes")
    assert pr.loc[1, "alimentadores"] == 1 and pr.loc[1, "com_nome_de_3_caracteres_ou_menos"] == 1
    assert pr.loc[3, "alimentadores"] == 1 and pr.loc[7, "alimentadores"] == 9


def test_informativo_nao_muda_a_regra():
    p = _painel()
    ev, ctrl = regra.eventos_e_controles(p)
    i = diagnostico.informativo(p, ctrl)
    assert i["eventos_ganho_ge1"] >= len(ev) and i["eventos_ganho_ge3"] == 3
    assert i["controles_amplitude_0"] == 4 and i["controles_com_chi_positivo"] == 4
