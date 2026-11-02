from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


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

    @classmethod
    def load(cls, path: str | Path = ROOT / "configs" / "emt.yaml") -> Config:
        c = yaml.safe_load(Path(path).read_text())
        p = c["paths"]

        def rel(x: str) -> Path:
            q = Path(x)
            return q if q.is_absolute() else ROOT / q

        return cls(
            sigla=c["distribuidora"]["sigla"],
            snapshots={int(k): v for k, v in c["bdgd"]["snapshots"].items()},
            anos_resultado=c["anos_resultado"],
            raw=rel(p["raw"]), interim=rel(p["interim"]), processed=rel(p["processed"]),
            gridrisk_interim=rel(p["gridrisk_interim"]), gridrisk_processed=rel(p["gridrisk_processed"]),
            premissas=c["premissas"],
        )
