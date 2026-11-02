"""Equipamentos (religadores, telecomando, disjuntores) por alimentador em cada snapshot da BDGD.

Reaproveita o GDB de 2025 já extraído pelo distribution-asset-risk quando existir; os demais
snapshots são baixados um a um (~1 GB cada) e apagados depois de processados.
"""
import logging
import sys

from autoimpact import bdgd
from autoimpact.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
cfg = Config.load()
anos = [int(a) for a in sys.argv[1:]] or sorted(cfg.snapshots)
for ano in anos:
    if (cfg.interim / f"equipamentos_{ano}.parquet").exists():
        continue
    externo = cfg.gridrisk_interim.parent / "raw" / "bdgd" / str(ano)
    dest = cfg.raw / "bdgd" / str(ano)
    if externo.exists() and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(externo.resolve(), target_is_directory=True)
        bdgd.build_snapshot(cfg.snapshots[ano], ano, cfg.raw, cfg.interim, keep_gdb=True)
        dest.unlink()
        continue
    bdgd.build_snapshot(cfg.snapshots[ano], ano, cfg.raw, cfg.interim)
