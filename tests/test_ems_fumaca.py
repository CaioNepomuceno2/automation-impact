"""Teste de fumaça de MS: os scripts rodam de ponta a ponta, nos dois ramos da regra, com dados sintéticos de estilo MS.

Os dados são sintéticos (alimentadores ``0AJ001`` como os de MS, 5 caracteres alfanuméricos completados com zero, e
tipos anuláveis do pyarrow como na base). O efeito de MT que o ramo "transportado" lê é o publicado em ``reports/``
(somente leitura). Um teste final, que só roda se os dados reais de MS estiverem ao lado, confere a decisão real.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoimpact import bdgd
from autoimpact.config import ROOT, VAR_CONFIG, VAR_ZIPS

SNAPSHOTS = list(range(2018, 2026))
ANOS = list(range(2019, 2026))
N = 260
EFEITO = -0.30
MT = ROOT / "reports"


# ------------------------------------------------------------------ dados sintéticos de estilo MS
def _construir(raiz: Path) -> dict:
    rng = np.random.default_rng(11)
    g_int, g_pro = raiz / "gridrisk" / "interim", raiz / "gridrisk" / "processed"
    interim = raiz / "interim"
    for d in (g_int, g_pro, interim):
        d.mkdir(parents=True)
    nomes = [f"0AJ{i:03d}" for i in range(N)]
    coorte = {i: int(rng.choice([2021, 2022, 2023])) for i in range(N // 2)}   # metade recebe religadores
    nivel_f = rng.lognormal(2.2, 0.4, N)
    km_base, uc_base = 80 * rng.lognormal(0, 0.3, N), rng.integers(500, 3000, N)
    choque_f = dict(zip(range(2018, 2026), rng.normal(0, 0.1, 8), strict=True))
    choque_d = dict(zip(range(2018, 2026), rng.normal(0, 0.1, 8), strict=True))
    falhas = []
    for i, nome in enumerate(nomes):
        for y in range(2018, 2026):
            ativo = i in coorte and y >= coorte[i]
            nf = int(rng.poisson(nivel_f[i] * np.exp(choque_f[y])))
            ci = float(rng.poisson(30 * nf)) if nf else 0.0
            dur = 2.0 * np.exp(choque_d[y]) * ((1 + EFEITO) if ativo else 1.0) * rng.lognormal(0, 0.1)
            chi = ci * dur
            falhas.append({"alimentador": nome, "ano": y, "mes": 1, "modo": "EQUIPAMENTO", "n_falhas": nf, "chi": chi,
                           "chi_regulatorio": 0.5 * chi, "ci": ci, "duracao_mediana_h": dur})
    pd.DataFrame(falhas).to_parquet(g_int / "falhas.parquet", index=False)
    for s in SNAPSHOTS:
        nrel = np.array([4.0 if (i in coorte and s + 1 >= coorte[i]) else 1.0 for i in range(N)])
        feeders = pd.DataFrame({
            "alimentador_cod_id": [str(700000 + i) for i in range(N)], "alimentador_nome": nomes,
            "rede_mt_km": km_base * np.exp(rng.normal(0, 0.05, N)),
            "n_uc": pd.array((uc_base * np.exp(rng.normal(0, 0.03, N))).astype(int), dtype="int64[pyarrow]"),
            "frac_rural": rng.uniform(0, 1, N), "n_trafos": rng.integers(20, 200, N).astype(float),
            "n_religadores": pd.array(nrel.astype(int), dtype="int64[pyarrow]")})
        feeders.to_parquet(g_int / f"bdgd_feeders_{s}.parquet", index=False)
        pd.DataFrame({"codigo": feeders.alimentador_cod_id, "alimentador": nomes}).to_parquet(
            g_int / f"crosswalk_{s}.parquet", index=False)
        pd.DataFrame({"alimentador": nomes, "subestacao": [f"S{i % 25}" for i in range(N)], "n_religadores": nrel,
                      "n_religadores_tlcd": np.floor(nrel * rng.uniform(0, 1, N)), "n_disjuntores": 1.0,
                      "n_seccionalizadores": rng.integers(0, 3, N).astype(float),
                      "n_chaves_fusiveis": rng.integers(0, 50, N).astype(float),
                      "n_tlcd_rede": rng.integers(0, 4, N).astype(float), "ano_snapshot": s}
                     ).to_parquet(interim / f"equipamentos_{s}.parquet", index=False)
        pd.DataFrame({"subestacao": [f"S{k}" for k in range(25)], "subestacao_nome": [f"SE {k}" for k in range(25)],
                      "potencia_mva": 30.0, "ano_snapshot": s}).to_parquet(interim / f"subestacoes_{s}.parquet", index=False)
    pd.DataFrame({"alimentador": nomes, "rs_por_chi_compensacao": 1.5, "rs_por_chi_social": 4.0}
                 ).to_parquet(g_pro / "risco_alimentador.parquet", index=False)
    m = rng.choice([1, 2, 4, 5], 120)   # 2026 sem março, como em MS
    chi = rng.uniform(10, 500, 120)
    pd.DataFrame({"cod_interrupcao": [f"2026_{k}" for k in range(120)], "ano": 2026, "mes": m,
                  "elemento": rng.choice(["RELIGADOR", "DISJUNTOR", "CHAVE FUSIVEL", "NAO IDENTIFICADO"], 120),
                  "uc_afetadas": rng.integers(1, 300, 120), "duracao_h": 1.0, "chi": chi, "origem_mt": True,
                  "origem": "INTERNA", "tipo": "NAO PROGRAMADA",
                  "alimentador_cod_id": [str(700000 + int(k)) for k in rng.integers(0, N, 120)],
                  "alimentador_nome": None}).to_parquet(g_int / "interrupcoes_ems.parquet", index=False)
    return {"g_int": g_int, "g_pro": g_pro, "interim": interim}


def _config(raiz: Path, nome: str, min_eventos: int, min_controles: int, ambiente: dict) -> Path:
    yaml = f"""
distribuidora: {{sigla: EMS, nome: Energisa Mato Grosso do Sul}}
paths:
  raw: {(raiz / 'raw').as_posix()}
  interim: {ambiente['interim'].as_posix()}
  processed: {(raiz / 'processed').as_posix()}
  reports: {(raiz / ('reports_' + nome)).as_posix()}
  gridrisk_interim: {ambiente['g_int'].as_posix()}
  gridrisk_processed: {ambiente['g_pro'].as_posix()}
bdgd:
  snapshots: {{{', '.join(f'{a}: item{a}' for a in SNAPSHOTS)}}}
anos_resultado: {ANOS}
regra_decisao:
  min_eventos: {min_eventos}
  min_controles: {min_controles}
  origem_medido: "medido em MS"
  origem_transportado: "transportado de MT"
  fonte_mt: {MT.as_posix()}
premissas: {{custo_ens_rs_mwh: 7000, taxa_desconto: 0.08, vida_religador_anos: 20, custo_religador_rs: 160000}}
"""
    arq = raiz / f"ems_{nome}.yaml"
    arq.write_text(yaml, encoding="utf-8")
    return arq


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("ems")
    return raiz, _construir(raiz)


def _rodar(script: str, cfg: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in (VAR_CONFIG, VAR_ZIPS)}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--config", str(cfg), *args],
                       check=False, capture_output=True, text=True, encoding="utf-8", env=env, cwd=cfg.parent)
    if ok:
        assert r.returncode == 0, f"{script} falhou:\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}"
    return r


def _chaves(d: dict, prefixo: str = "") -> set[str]:
    out = set()
    for k, v in d.items():
        out.add(prefixo + k)
        if isinstance(v, dict):
            out |= _chaves(v, prefixo + k + ".")
    return out


def _todos_os_csv_tem_origem(pasta: Path, origem: str):
    arquivos = sorted(pasta.rglob("*.csv"))
    assert arquivos
    for a in arquivos:
        assert "origem_efeito" in pd.read_csv(a, nrows=1).columns, a.name
        assert set(pd.read_csv(a).origem_efeito) == {origem}, a.name


# ------------------------------------------------------------------ ramo "transportado de MT" (controles insuficientes)
@pytest.fixture(scope="module")
def ramo_transportado(ambiente):
    raiz, amb = ambiente
    cfg = _config(raiz, "transp", min_eventos=5, min_controles=10_000, ambiente=amb)
    _rodar("00_diagnostico.py", cfg)
    _rodar("02_estimar.py", cfg)
    _rodar("04_figuras.py", cfg)
    return cfg, raiz / "reports_transp"


def test_transportado_regra_e_rotulos(ramo_transportado):
    _, rep = ramo_transportado
    r = json.loads((rep / "regra_decisao.json").read_text(encoding="utf-8"))
    assert r["origem_efeito"] == "transportado de MT" and r["publica_efeito_proprio"] is False
    assert (r["n_eventos"], r["n_controles"]) == (N // 2, N // 2)
    assert set(r["efeito_de_mt_lido_de"]["sha256"]) == {"efeitos_did.csv", "efeitos_por_unidade.csv", "valor.json"}
    _todos_os_csv_tem_origem(rep, "transportado de MT")
    assert json.loads((rep / "valor.json").read_text(encoding="utf-8"))["origem_efeito"] == "transportado de MT"
    assert json.loads((rep / "diagnostico" / "regra_contagens.json").read_text(encoding="utf-8"))["origem_efeito"] == \
        "transportado de MT"


def test_transportado_nao_estima_nada_em_ms(ramo_transportado):
    cfg, rep = ramo_transportado
    for nome in ("efeitos_did.csv", "event_study.csv", "efeitos_por_unidade.csv", "robustez.csv", "comparacao_premissas.csv",
                 "comparacao_mt.csv"):
        assert not (rep / nome).exists(), nome
    assert sorted(p.name for p in (rep / "figures").glob("*.png")) == ["04_subestacoes.png", "05_disponibilidade.png",
                                                                      "06_elemento_2026.png"]
    r = _rodar("05_did_escalonado.py", cfg, "--reps", "20", ok=False)    # o CS recusa rodar
    assert r.returncode != 0 and "transportado de MT" in (r.stdout + r.stderr)
    assert not list(rep.glob("did_escalonado_*"))


def test_transportado_valor_json_tem_o_esquema_de_mt_mais_a_origem(ramo_transportado):
    _, rep = ramo_transportado
    ms = json.loads((rep / "valor.json").read_text(encoding="utf-8"))
    mt = json.loads((MT / "valor.json").read_text(encoding="utf-8"))
    assert _chaves(ms) == _chaves(mt) | {"origem_efeito"}
    # o efeito é o de MT (lido de reports/, nada reestimado); só difere no último bit do exp() de outra máquina
    for k in ("efeito_chi_pct", "ic95_chi_pct", "twfe_efeito_por_religador_pct", "frac_efeito_via_duracao_twfe"):
        assert ms[k] == pytest.approx(mt[k], rel=1e-12), k
    # a exposição e o R$/CHI são os do recorte: os sintéticos (1,5 e 4,0), e não os de MT (1,93 e 5,94)
    assert ms["rs_por_chi_social"] == pytest.approx(4.0) and ms["rs_por_chi_compensacao"] == pytest.approx(1.5)
    assert ms["rs_por_chi_social"] != mt["rs_por_chi_social"]
    assert ms["eventos"] == N // 2 and ms["religadores_adicionados_nos_eventos"] == 3 * (N // 2)
    assert ms["religadores_2025"] == float(pd.read_parquet(
        Path(ramo_transportado[1]).parent / "interim" / "equipamentos_2025.parquet").n_religadores.sum())
    assert ms["chi_evitado_ano_eventos"] > 0 and ms["chi_evitado_ano_por_religador"] > 0   # exposição de MS x efeito de MT


def test_02_falha_se_as_contagens_divergirem_das_do_diagnostico(ramo_transportado):
    cfg, rep = ramo_transportado
    arq = rep / "diagnostico" / "regra_contagens.json"
    original = arq.read_text(encoding="utf-8")
    try:
        d = json.loads(original)
        d["n_eventos"] += 1
        arq.write_text(json.dumps(d), encoding="utf-8")
        r = _rodar("02_estimar.py", cfg, ok=False)
        assert r.returncode != 0 and "contagens diferentes" in (r.stdout + r.stderr)
    finally:
        arq.write_text(original, encoding="utf-8")


# ------------------------------------------------------------------ ramo "medido em MS" (eventos e controles suficientes)
@pytest.fixture(scope="module")
def ramo_medido(ambiente):
    raiz, amb = ambiente
    cfg = _config(raiz, "medido", min_eventos=60, min_controles=100, ambiente=amb)
    _rodar("00_diagnostico.py", cfg)
    _rodar("02_estimar.py", cfg)
    _rodar("04_figuras.py", cfg)
    _rodar("05_did_escalonado.py", cfg, "--reps", "40")
    return cfg, raiz / "reports_medido"


def test_medido_publica_o_efeito_de_ms_com_o_de_mt_ao_lado(ramo_medido):
    _, rep = ramo_medido
    r = json.loads((rep / "regra_decisao.json").read_text(encoding="utf-8"))
    assert r["origem_efeito"] == "medido em MS" and r["publica_efeito_proprio"] is True
    did = pd.read_csv(rep / "efeitos_did.csv").set_index("desfecho")
    chi = did.loc["chi"]
    assert chi.efeito_pct == pytest.approx(100 * EFEITO, abs=6)         # recupera o efeito sintético (-30%)
    assert chi.ic95_lo_pct < 100 * EFEITO < chi.ic95_hi_pct
    cmp_ = pd.read_csv(rep / "comparacao_mt.csv").set_index("desfecho")
    mt = pd.read_csv(MT / "efeitos_did.csv").set_index("desfecho")
    assert cmp_.loc["chi", "efeito_pct_ems"] == pytest.approx(chi.efeito_pct)
    assert cmp_.loc["chi", "efeito_pct_mt"] == pytest.approx(mt.loc["chi", "efeito_pct"])     # o de MT, ao lado
    for nome in ("event_study.csv", "efeitos_por_unidade.csv", "robustez.csv", "comparacao_premissas.csv"):
        assert (rep / nome).exists(), nome
    _todos_os_csv_tem_origem(rep, "medido em MS")
    assert json.loads((rep / "valor.json").read_text(encoding="utf-8"))["origem_efeito"] == "medido em MS"


def test_medido_roda_a_conferencia_cs_e_a_sensibilidade_com_rotulo(ramo_medido):
    _, rep = ramo_medido
    assert (rep / "figures" / "07_did_escalonado.png").exists()
    assert {"01_event_study.png", "02_canais.png", "03_robustez.png"} <= {p.name for p in (rep / "figures").glob("*.png")}
    sai = json.loads((rep / "did_escalonado_valor.json").read_text(encoding="utf-8"))
    assert sai["meta"]["origem_efeito"] == "medido em MS" and "D6" in sai["regras"]
    tend = pd.read_csv(rep / "did_escalonado_tendencia.csv")      # sensibilidade à pré-tendência
    assert set(tend.origem_efeito) == {"medido em MS"} and {"duracao_h", "chi"} <= set(tend.desfecho)
    # o D5 e o D6 usaram o valor.json de MS (da mesma pasta), e não o de MT
    assert sai["meta"]["valor_json_usado"]["sha256"] != hashlib.sha256((MT / "valor.json").read_bytes()).hexdigest()
    assert sai["meta"]["valor_json_usado"]["sha256"] == hashlib.sha256((rep / "valor.json").read_bytes()).hexdigest()


def test_medido_valor_json_tem_o_mesmo_esquema(ramo_medido):
    _, rep = ramo_medido
    ms = json.loads((rep / "valor.json").read_text(encoding="utf-8"))
    mt = json.loads((MT / "valor.json").read_text(encoding="utf-8"))
    assert _chaves(ms) == _chaves(mt) | {"origem_efeito"}
    assert ms["efeito_chi_pct"] == pytest.approx(100 * EFEITO, abs=6)


# ------------------------------------------------------------------ chaves de MS e suposições de MT
def test_equipamentos_com_nomes_de_circuito_de_ms():
    """``CTMT.NOME`` de MS tem 5 caracteres alfanuméricos: completa com zero até 6 (``0AJO51``), como a base."""
    sw = pd.DataFrame({"CTMT": ["1", "1", "2", "3"], "TIP_UNID": ["32", "32", "32", "29"], "TLCD": ["1", "0", "1", "0"]})
    ct = pd.DataFrame({"COD_ID": ["1", "2", "3"], "NOME": ["AJO51", "AJO52", "ACA"], "SUB": ["S1", "S1", "S2"]})
    eq = bdgd.equipamentos_por_alimentador(sw, ct).set_index("alimentador")
    assert set(eq.index) == {"0AJO51", "0AJO52", "000ACA"}        # segundo código do mesmo circuito e nome de 3 caracteres
    assert eq.loc["0AJO51", "n_religadores"] == 2 and eq.loc["0AJO51", "n_religadores_tlcd"] == 1
    assert eq.loc["0AJO52", "n_religadores"] == 1 and eq.loc["000ACA", "n_disjuntores"] == 1


def test_scripts_nao_tem_suposicoes_de_mt_no_codigo():
    proibido = ["interrupcoes_emt", 'ROOT / "reports"', "Config.load()", "ENERGISA MATO GROSSO", "da EMT"]
    for script in sorted((ROOT / "scripts").glob("*.py")):
        texto = script.read_text(encoding="utf-8")
        for p in proibido:
            assert p not in texto, f"{script.name}: {p!r}"


@pytest.mark.skipif(not (ROOT.parent / "distribution-asset-risk" / "data" / "ems" / "interim" / "falhas.parquet").exists()
                    or not (ROOT / "data" / "ems" / "interim" / "equipamentos_2024.parquet").exists(),
                    reason="dados reais de MS não estão ao lado (base e equipamentos)")
def test_decisao_real_de_ms_confere_com_o_documento():
    """Com os dados reais, a decisão registrada em docs/decisoes_ems.md: 72 eventos, 87 controles, 'transportado de MT'."""
    from autoimpact import painel, regra
    from autoimpact.config import Config
    cfg = Config.load(ROOT / "configs" / "ems.yaml")
    p = painel.carregar(cfg.gridrisk_interim, cfg.interim, cfg.anos_resultado)
    ev, ctrl, d = regra.decisao_do_painel(p, cfg)
    assert (len(ev), len(ctrl)) == (72, 87)
    assert d.origem_efeito == "transportado de MT" and not d.publica_efeito_proprio
