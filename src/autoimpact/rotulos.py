"""Textos de figuras e tabelas que dependem dos dados do recorte (meses com registro, elemento que mais pesa)."""
from __future__ import annotations

from pathlib import Path

import duckdb

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def meses_com_registro(interrupcoes: Path, ano: int) -> list[int]:
    """Meses (1 a 12) que têm pelo menos uma interrupção no arquivo harmonizado."""
    r = duckdb.sql(f"select distinct mes from read_parquet('{interrupcoes}') where ano = {int(ano)} order by 1").fetchall()
    return [int(m) for (m,) in r]


def rotulo_meses(meses: list[int], ano: int) -> str:
    """``[1..7]`` -> ``jan-jul/2026``; com buraco, ``jan-fev, abr-jul/2026 (sem mar)``."""
    if not meses:
        return str(ano)
    trechos, ini, ant = [], meses[0], meses[0]
    for m in [*meses[1:], None]:
        if m is not None and m == ant + 1:
            ant = m
            continue
        trechos.append(MESES[ini - 1] if ini == ant else f"{MESES[ini - 1]}-{MESES[ant - 1]}")
        ini = ant = m
    faltam = [MESES[m - 1] for m in range(meses[0], meses[-1] + 1) if m not in meses]
    return ", ".join(trechos) + f"/{ano}" + (f" (sem {', '.join(faltam)})" if faltam else "")
