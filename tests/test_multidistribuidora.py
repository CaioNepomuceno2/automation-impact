"""Multi-distribuidora: o padrão continua sendo a Energisa MT, e MS só escreve em subpastas ``ems``."""
import zipfile
from pathlib import Path

import pytest

from autoimpact import bdgd
from autoimpact.config import CONFIG_PADRAO, ROOT, VAR_CONFIG, VAR_ZIPS, Config, carregar_dos_argumentos

EMS = ROOT / "configs" / "ems.yaml"


@pytest.fixture(autouse=True)
def _sem_variaveis(monkeypatch):
    monkeypatch.delenv(VAR_CONFIG, raising=False)
    monkeypatch.delenv(VAR_ZIPS, raising=False)


# ------------------------------------------------------------------ guarda de MT: o padrão não mudou
def test_padrao_resolve_exatamente_os_caminhos_de_mt():
    cfg = Config.load()
    assert CONFIG_PADRAO == ROOT / "configs" / "emt.yaml"
    assert cfg == Config.load(CONFIG_PADRAO)
    assert cfg.sigla == "EMT"
    assert cfg.raw == ROOT / "data/raw"
    assert cfg.interim == ROOT / "data/interim"
    assert cfg.processed == ROOT / "data/processed"
    assert cfg.reports == ROOT / "reports"
    assert cfg.gridrisk_interim == ROOT / "../distribution-asset-risk/data/interim"
    assert cfg.gridrisk_processed == ROOT / "../distribution-asset-risk/data/processed"
    assert cfg.interrupcoes_parquet == ROOT / "../distribution-asset-risk/data/interim/interrupcoes_emt.parquet"
    assert cfg.bdgd_zips is None
    assert cfg.regra is None and cfg.origem_efeito is None


def test_padrao_mantem_snapshots_premissas_e_janelas_de_mt():
    cfg = Config.load()
    assert cfg.snapshots == {
        2018: "b6900e72a13946b6a2dc015aaf6d6ccd", 2019: "f15e84cabd564d31869c3af5d7855376",
        2020: "bc9ef518725a416a99e08c99e2d979d1", 2021: "13d6ff510a4c4a7fac64f0e119beb245",
        2022: "94a1b3fa56e3442fb8a2b3a8a3dc4df8", 2023: "f6095aa7e5c64119ab46e3efe46b77d5",
        2024: "8fed7443387d4d04a361e7f4d1edea64", 2025: "02a120db1b5149709f8d371c21635adc"}
    assert cfg.anos_resultado == [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    assert cfg.premissas == {"custo_ens_rs_mwh": 7000, "taxa_desconto": 0.08, "vida_religador_anos": 20,
                             "custo_religador_rs": 160000}
    # anos que os scripts tinham fixos no código de MT
    assert cfg.ano_cadastro_frota == 2025
    assert cfg.ano_cadastro_subestacoes == 2024
    assert cfg.anos_chi_recente == (2023, 2025)
    assert cfg.ano_elemento == 2026
    assert cfg.ano_placebo_min == 2021
    # filtro das ocorrências emergenciais de MT
    assert (cfg.ocorrencias_incluir, cfg.ocorrencias_excluir, cfg.ano_ocorrencias) == ("%ENERGISA MATO GROSSO%", "%SUL%", 2025)


def test_variavel_de_ambiente_e_argumento_escolhem_a_configuracao(monkeypatch):
    monkeypatch.setenv(VAR_CONFIG, str(EMS))
    assert Config.load().sigla == "EMS"
    monkeypatch.delenv(VAR_CONFIG)
    assert Config.load().sigla == "EMT"
    cfg, resto = carregar_dos_argumentos(["--config", str(EMS), "2020", "2021"])
    assert cfg.sigla == "EMS" and resto == ["2020", "2021"]
    cfg, resto = carregar_dos_argumentos([f"--config={EMS}"])
    assert cfg.sigla == "EMS" and resto == []
    cfg, resto = carregar_dos_argumentos(["2019"])
    assert cfg.sigla == "EMT" and resto == ["2019"]


# ------------------------------------------------------------------ MS: só subpastas ems, nada de MT
def test_ems_escreve_so_em_subpastas_ems_e_le_so_dados_de_ms():
    ems, mt = Config.load(EMS), Config.load()
    assert ems.sigla == "EMS" and ems.nome == "Energisa Mato Grosso do Sul"
    assert ems.reports == ROOT / "reports" / "ems"
    for destino in (ems.raw, ems.interim, ems.processed, ems.reports):
        assert "ems" in destino.relative_to(ROOT).parts
        assert destino not in (mt.raw, mt.interim, mt.processed, mt.reports)
    assert ems.gridrisk_interim == ROOT / "../distribution-asset-risk/data/ems/interim"
    assert ems.gridrisk_processed == ROOT / "../distribution-asset-risk/data/ems/processed"
    assert ems.interrupcoes_parquet.name == "interrupcoes_ems.parquet"
    assert ems.interrupcoes_parquet != mt.interrupcoes_parquet
    assert (ems.ocorrencias_incluir, ems.ocorrencias_excluir) == ("%ENERGISA MATO GROSSO DO SUL%", None)


def test_ems_snapshots_sao_os_oito_itens_conferidos():
    ems = Config.load(EMS)
    assert ems.snapshots == {
        2018: "5382c59d7cc7494a9a1f8cd865187457", 2019: "b83ad867a35b43189f41b68988f7f0b6",
        2020: "fe56dce0714f4b6795d3b23130f5898a", 2021: "933af69c57dd41ea8f6048118b8d07e7",
        2022: "ff5242147c86428e88971941a35c7cd1", 2023: "975f18dfdb0c479cb237893c5b296ca9",
        2024: "b7fad4cd388845a08a01643599ec747b", 2025: "9a1ce360865f4358b31e9fb2d016aac9"}
    # ficam de fora o item avulso de 31/10/2022 e o snapshot de 2023 de 17/12/2024
    assert not {"c3585ae516f340b596617827d60da5ef", "b8c585ae35224ac8aa0648587ec61bcb"} & set(ems.snapshots.values())
    assert ems.anos_resultado == Config.load().anos_resultado
    assert ems.premissas == Config.load().premissas


def test_ems_traz_a_regra_pre_registrada():
    r = Config.load(EMS).regra
    assert (r.min_eventos, r.min_controles) == (60, 100)
    assert (r.origem_medido, r.origem_transportado) == ("medido em MS", "transportado de MT")
    assert r.fonte_mt == ROOT / "reports"          # resultados publicados de MT, só leitura
    assert Config.load(EMS).origem_efeito == "medido em MS"


# ------------------------------------------------------------------ BDGD a partir de uma pasta de zips (cache só leitura)
def _gdb_zip(pasta: Path, item: str, ano: int) -> Path:
    z = pasta / f"bdgd_{ano}_{item}.gdb.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Teste.gdb/a00000001.gdbtable", b"x")
    return z


def test_download_extrai_do_cache_sem_mexer_no_zip(tmp_path):
    cache, dest = tmp_path / "cache", tmp_path / "raw" / "2020"
    cache.mkdir()
    z = _gdb_zip(cache, "abc123", 2020)
    antes = z.read_bytes()
    gdb = bdgd.download("abc123", dest, zips=cache)
    assert gdb.name == "Teste.gdb" and gdb.is_relative_to(dest)
    assert z.exists() and z.read_bytes() == antes          # o cache não é tocado
    assert bdgd.download("abc123", dest, zips=cache) == gdb  # idempotente


def test_download_com_cache_falha_em_vez_de_ir_a_rede(tmp_path):
    (tmp_path / "cache").mkdir()
    with pytest.raises(FileNotFoundError):
        bdgd.download("naoexiste", tmp_path / "dest", zips=tmp_path / "cache")
