"""Configuração do recorte (distribuidora). O padrão é a Energisa MT (``configs/emt.yaml``).

Seleção do recorte: argumento ``--config <arquivo>`` dos scripts ou a variável de ambiente
``AUTOIMPACT_CONFIG``; sem nenhum dos dois vale ``configs/emt.yaml``, que resolve exatamente os
caminhos de sempre (``reports/``, ``data/interim``, ``interrupcoes_emt.parquet`` ...).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PADRAO = ROOT / "configs" / "emt.yaml"
VAR_CONFIG = "AUTOIMPACT_CONFIG"
VAR_ZIPS = "AUTOIMPACT_BDGD_ZIPS"


@dataclass(frozen=True)
class Regra:
    """Regra de decisão pré-registrada: o efeito próprio só é publicado com eventos e controles suficientes."""
    min_eventos: int
    min_controles: int
    origem_medido: str
    origem_transportado: str
    fonte_mt: Path          # pasta ``reports`` de MT, de onde vem o efeito transportado (somente leitura)


@dataclass(frozen=True)
class Config:
    sigla: str
    snapshots: dict[int, str]
    anos_resultado: list[int]
    raw: Path
    interim: Path
    processed: Path
    gridrisk_interim: Path
    gridrisk_processed: Path
    premissas: dict
    nome: str = "Energisa Mato Grosso"
    reports: Path = ROOT / "reports"
    bdgd_zips: Path | None = None
    ocorrencias_incluir: str = "%ENERGISA MATO GROSSO%"
    ocorrencias_excluir: str | None = "%SUL%"
    ano_ocorrencias: int = 2025
    regra: Regra | None = None

    # ------------------------------------------------------------------ derivados (iguais aos valores fixos de MT)
    @property
    def interrupcoes_parquet(self) -> Path:
        """``interrupcoes_<sigla em minúsculas>.parquet`` na pasta do distribution-asset-risk (MT: ``interrupcoes_emt``)."""
        return self.gridrisk_interim / f"interrupcoes_{self.sigla.lower()}.parquet"

    @property
    def ano_cadastro_frota(self) -> int:
        """Snapshot da frota atual de religadores (MT: 2025)."""
        return max(self.snapshots)

    @property
    def ano_cadastro_subestacoes(self) -> int:
        """Último snapshot usado no painel, base do ranking de subestações (MT: 2024)."""
        return max(self.anos_resultado) - 1

    @property
    def anos_chi_recente(self) -> tuple[int, int]:
        """Três últimos anos de resultado, base do CHI anual da frota e das subestações (MT: 2023 a 2025)."""
        return max(self.anos_resultado) - 2, max(self.anos_resultado)

    @property
    def ano_elemento(self) -> int:
        """Ano parcial em que se olha quem abriu o circuito (MT: 2026)."""
        return max(self.snapshots) + 1

    @property
    def ano_placebo_min(self) -> int:
        """Primeiro ano de evento do placebo (dois anos antes do evento ainda precisa haver janela; MT: 2021)."""
        return min(self.anos_resultado) + 2

    @property
    def origem_efeito(self) -> str | None:
        """Rótulo de origem do efeito, na falta de uma decisão da regra (``None`` quando não há regra, como em MT)."""
        return None if self.regra is None else self.regra.origem_medido

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Lê a configuração de ``path``; sem ``path``, de ``AUTOIMPACT_CONFIG`` ou de ``configs/emt.yaml``."""
        if path is None:
            path = os.environ.get(VAR_CONFIG) or CONFIG_PADRAO
        c = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        p = c["paths"]

        def rel(x: str) -> Path:
            q = Path(x)
            return q if q.is_absolute() else ROOT / q

        zips = os.environ.get(VAR_ZIPS) or p.get("bdgd_zips")
        oc = c.get("ocorrencias", {})
        r = c.get("regra_decisao")
        regra = None if r is None else Regra(
            min_eventos=int(r["min_eventos"]), min_controles=int(r["min_controles"]),
            origem_medido=r["origem_medido"], origem_transportado=r["origem_transportado"],
            fonte_mt=rel(r["fonte_mt"]))
        return cls(
            sigla=c["distribuidora"]["sigla"],
            snapshots={int(k): v for k, v in c["bdgd"]["snapshots"].items()},
            anos_resultado=c["anos_resultado"],
            raw=rel(p["raw"]), interim=rel(p["interim"]), processed=rel(p["processed"]),
            gridrisk_interim=rel(p["gridrisk_interim"]), gridrisk_processed=rel(p["gridrisk_processed"]),
            premissas=c["premissas"],
            nome=c["distribuidora"].get("nome", c["distribuidora"]["sigla"]),
            reports=rel(p.get("reports", "reports")),
            bdgd_zips=rel(zips) if zips else None,
            ocorrencias_incluir=oc.get("incluir", "%ENERGISA MATO GROSSO%"),
            ocorrencias_excluir=oc.get("excluir", "%SUL%"),
            ano_ocorrencias=int(oc.get("ano", 2025)),
            regra=regra,
        )


def carregar_dos_argumentos(argv: list[str] | None = None) -> tuple[Config, list[str]]:
    """Lê ``--config <arquivo>`` (ou ``--config=<arquivo>``) de ``argv`` e devolve a configuração e o resto dos argumentos."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    caminho, resto, i = None, [], 0
    while i < len(args):
        a = args[i]
        if a == "--config" and i + 1 < len(args):
            caminho, i = args[i + 1], i + 2
        elif a.startswith("--config="):
            caminho, i = a.split("=", 1)[1], i + 1
        else:
            resto.append(a)
            i += 1
    return Config.load(caminho), resto
