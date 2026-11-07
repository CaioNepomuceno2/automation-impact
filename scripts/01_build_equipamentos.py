"""Equipamentos (religadores, telecomando, disjuntores) por alimentador em cada snapshot da BDGD.

Reaproveita o GDB já extraído pelo distribution-asset-risk quando existir (sem apagá-lo); os demais snapshots
vêm de uma pasta de zips (``paths.bdgd_zips`` ou ``AUTOIMPACT_BDGD_ZIPS``, só leitura) ou são baixados um a um
(~1 GB cada) e apagados depois de processados.

Uso: python scripts/01_build_equipamentos.py [--config configs/ems.yaml] [ano ...]
"""
import logging

from autoimpact import bdgd
from autoimpact.config import carregar_dos_argumentos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
cfg, resto = carregar_dos_argumentos()
anos = [int(a) for a in resto] or sorted(cfg.snapshots)
for ano in anos:
    if (cfg.interim / f"equipamentos_{ano}.parquet").exists():
        continue
    externo = cfg.gridrisk_interim.parent / "raw" / "bdgd" / str(ano)
    gdbs = [p for p in externo.rglob("*.gdb") if p.is_dir()] if externo.exists() else []
    if gdbs:
        bdgd.build_snapshot(cfg.snapshots[ano], ano, cfg.raw, cfg.interim, gdb=gdbs[0])
        continue
    bdgd.build_snapshot(cfg.snapshots[ano], ano, cfg.raw, cfg.interim, zips=cfg.bdgd_zips)
