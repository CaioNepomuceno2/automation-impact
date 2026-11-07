"""Regra de decisão pré-registrada, rótulo de origem do efeito e leitura do efeito de MT (funções puras)."""
import json

import pandas as pd
import pytest

from autoimpact import regra, rotulos
from autoimpact.config import ROOT, VAR_CONFIG, Config, Regra

REGRA = Regra(min_eventos=60, min_controles=100, origem_medido="medido em MS",
              origem_transportado="transportado de MT", fonte_mt=ROOT / "reports")


# ------------------------------------------------------------------ a regra, nos dois ramos e nos limites
@pytest.mark.parametrize("eventos,controles,publica", [
    (72, 87, False),     # o caso real de MS: eventos bastam, controles não
    (60, 100, True),     # os dois limites são "pelo menos"
    (59, 100, False),
    (60, 99, False),
    (116, 209, True),    # MT passaria
    (0, 0, False),
    (500, 500, True),
])
def test_regra_nos_limites(eventos, controles, publica):
    d = regra.decidir(eventos, controles, REGRA)
    assert d.publica_efeito_proprio is publica
    assert d.origem_efeito == ("medido em MS" if publica else "transportado de MT")
    assert (d.n_eventos, d.n_controles, d.min_eventos, d.min_controles) == (eventos, controles, 60, 100)


def test_motivo_diz_o_que_faltou():
    assert "controles nunca tratados 87 < 100" in regra.decidir(72, 87, REGRA).motivo
    assert "eventos tratados 10 < 60" in regra.decidir(10, 500, REGRA).motivo
    m = regra.decidir(10, 20, REGRA).motivo
    assert "eventos" in m and "controles" in m


def _painel_sintetico(n_eventos: int, n_controles: int, n_outros: int = 5) -> pd.DataFrame:
    """Alimentadores × ano com religadores: ``n_eventos`` ganham 3 em 2021, ``n_controles`` ficam em 1, ``n_outros`` oscilam."""
    anos = list(range(2019, 2026))
    linhas = []
    for i in range(n_eventos):
        for y in anos:
            linhas.append({"alimentador": f"0EV{i:03d}", "ano": y, "n_religadores": 1 if y < 2021 else 4})
    for i in range(n_controles):
        for y in anos:
            linhas.append({"alimentador": f"0CT{i:03d}", "ano": y, "n_religadores": 1})
    for i in range(n_outros):
        for y in anos:   # ganha e perde 3: não é evento nem controle
            linhas.append({"alimentador": f"0OU{i:03d}", "ano": y, "n_religadores": 4 if y == 2022 else 1})
    return pd.DataFrame(linhas)


def test_contagem_com_a_definicao_de_mt():
    p = _painel_sintetico(n_eventos=70, n_controles=120)
    ev, ctrl = regra.eventos_e_controles(p)
    assert len(ev) == 70 and set(ev.ano_evento) == {2021} and set(ev.ganho) == {3}
    assert len(ctrl) == 120
    # alimentador que some no meio do painel não é controle
    p = p[~((p.alimentador == "0CT000") & (p.ano == 2023))]
    assert "0CT000" not in set(regra.eventos_e_controles(p)[1])


def test_ramo_medido_e_ramo_transportado_com_dados_sinteticos():
    cfg = Config.load(ROOT / "configs" / "ems.yaml")
    # ramo "medido": 60 eventos e 100 controles (o mínimo exato)
    ev, ctrl, d = regra.decisao_do_painel(_painel_sintetico(60, 100), cfg)
    assert (len(ev), len(ctrl)) == (60, 100) and d.publica_efeito_proprio and d.origem_efeito == "medido em MS"
    # ramo "transportado": controles insuficientes
    ev, ctrl, d = regra.decisao_do_painel(_painel_sintetico(72, 87), cfg)
    assert (len(ev), len(ctrl)) == (72, 87) and not d.publica_efeito_proprio and d.origem_efeito == "transportado de MT"
    # eventos insuficientes
    _, _, d = regra.decisao_do_painel(_painel_sintetico(30, 300), cfg)
    assert not d.publica_efeito_proprio


def test_mt_nao_tem_regra_nem_rotulo():
    ev, ctrl, d = regra.decisao_do_painel(_painel_sintetico(2, 2), Config.load(ROOT / "configs" / "emt.yaml"))
    assert d is None and len(ev) == 2 and len(ctrl) == 2


# ------------------------------------------------------------------ rótulo de origem
def test_rotular_e_salvar_csv(tmp_path):
    df = pd.DataFrame({"a": [1, 2]})
    assert regra.rotular(df, None) is df                       # MT: tabela como está
    assert list(regra.rotular(df, "transportado de MT").columns) == ["a", "origem_efeito"]
    regra.salvar_csv(df, tmp_path / "mt.csv", None)
    regra.salvar_csv(df, tmp_path / "ms.csv", "transportado de MT")
    assert pd.read_csv(tmp_path / "mt.csv").columns.tolist() == ["a"]
    assert pd.read_csv(tmp_path / "ms.csv").origem_efeito.unique().tolist() == ["transportado de MT"]


def test_origem_do_recorte_le_a_decisao_gravada(tmp_path, monkeypatch):
    monkeypatch.delenv(VAR_CONFIG, raising=False)
    mt = Config.load()
    assert regra.origem_do_recorte(mt) is None
    ems = Config.load(ROOT / "configs" / "ems.yaml")
    import dataclasses
    cfg = dataclasses.replace(ems, reports=tmp_path)
    with pytest.raises(SystemExit):                            # sem decisão gravada, o rótulo não é chutado
        regra.origem_do_recorte(cfg)
    (tmp_path / "diagnostico").mkdir()
    (tmp_path / "diagnostico" / "regra_contagens.json").write_text(json.dumps({"origem_efeito": "transportado de MT"}))
    assert regra.origem_do_recorte(cfg) == "transportado de MT"
    (tmp_path / "regra_decisao.json").write_text(json.dumps({"origem_efeito": "medido em MS"}))
    assert regra.origem_do_recorte(cfg) == "medido em MS"     # a decisão do 02 vale mais que a do diagnóstico


# ------------------------------------------------------------------ efeito de MT (somente leitura)
def test_carrega_o_efeito_publicado_de_mt():
    did, por_unidade, valor = regra.carregar_efeito_mt(ROOT / "reports")
    chi = did.set_index("desfecho").loc["chi"]
    assert chi.efeito_pct == pytest.approx(valor["efeito_chi_pct"])
    assert (por_unidade.regressor.nunique(), por_unidade.desfecho.nunique()) == (3, 4)


def test_efeito_de_mt_incompleto_falha(tmp_path):
    for nome in ("efeitos_did.csv", "efeitos_por_unidade.csv", "valor.json"):
        (tmp_path / nome).write_bytes((ROOT / "reports" / nome).read_bytes())
    pd.read_csv(tmp_path / "efeitos_did.csv").query("desfecho != 'duracao_h'").to_csv(tmp_path / "efeitos_did.csv", index=False)
    with pytest.raises(ValueError, match="duracao_h"):
        regra.carregar_efeito_mt(tmp_path)


def test_comparar_com_mt():
    ms = pd.DataFrame({"desfecho": ["chi"], "efeito_pct": [-10.0], "ic95_lo_pct": [-20.0], "ic95_hi_pct": [0.0], "n_alimentadores": [90]})
    mt = pd.DataFrame({"desfecho": ["chi", "n_falhas"], "efeito_pct": [-16.6, -1.1], "ic95_lo_pct": [-24.8, -7.3],
                       "ic95_hi_pct": [-7.5, 5.5], "n_alimentadores": [315, 321]})
    c = regra.comparar_com_mt(ms, mt, "EMS").set_index("desfecho")
    assert list(c.index) == ["chi"]
    assert c.loc["chi", "efeito_pct_ems"] == -10.0 and c.loc["chi", "efeito_pct_mt"] == -16.6
    assert c.loc["chi", "n_alimentadores_ems"] == 90 and c.loc["chi", "n_alimentadores_mt"] == 315


# ------------------------------------------------------------------ rótulos de figura
def test_rotulo_de_meses():
    assert rotulos.rotulo_meses(list(range(1, 8)), 2026) == "jan-jul/2026"                # MT: texto de sempre
    assert rotulos.rotulo_meses([1, 2, 4, 5, 6, 7], 2026) == "jan-fev, abr-jul/2026 (sem mar)"   # MS: sem março
    assert rotulos.rotulo_meses([], 2026) == "2026"

