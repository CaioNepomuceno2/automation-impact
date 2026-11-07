"""Equipamentos de proteção e manobra por alimentador em cada snapshot da BDGD.

O download e a leitura seguem o pipeline do projeto
`distribution-asset-risk <https://github.com/CaioNepomuceno2/distribution-asset-risk>`_.
Aqui só interessa a camada ``UNSEMT`` (unidades seccionadoras de média tensão), com
tipo (``TIP_UNID``) e telecomando (``TLCD``), e o nome operacional de cada circuito
(``CTMT.NOME``), que é a chave estável entre snapshots.

Domínio ``TIP_UNID`` (Manual de Instruções da BDGD, Anexo II): 32 religador,
29/30/53 disjuntor, 35/36 seccionalizador, 22-27 chaves fusíveis, 33/34 seccionadoras.
"""
from __future__ import annotations

import logging
import shutil
import time
import zipfile
from pathlib import Path

import pandas as pd
import pyogrio
import requests

log = logging.getLogger(__name__)

ARCGIS_DATA = "https://www.arcgis.com/sharing/rest/content/items/{item}/data"

TIPOS = {
    "religador": {"32"},
    "disjuntor": {"29", "30", "53"},
    "seccionalizador": {"35", "36"},
    "chave_fusivel": {"22", "23", "24", "25", "26", "27"},
    "seccionadora": {"33", "34"},
}


def zip_do_cache(zips: Path, item: str) -> Path:
    """Zip ``bdgd_<ano>_<item>.gdb.zip`` de uma pasta de cache (somente leitura: nunca é movido nem apagado)."""
    achados = sorted(zips.glob(f"bdgd_*_{item}.gdb.zip"))
    if len(achados) != 1:
        raise FileNotFoundError(f"esperava 1 zip do item {item} em {zips}, achei {len(achados)}")
    return achados[0]


def download(item: str, dest: Path, retries: int = 4, zips: Path | None = None) -> Path:
    """Baixa e descompacta um snapshot; devolve o caminho do .gdb.

    Com ``zips`` (pasta de cache), extrai o zip de lá para ``dest`` e não baixa nada: se o item não estiver no
    cache, falha em vez de ir à rede.
    """
    dest.mkdir(parents=True, exist_ok=True)
    existing = [p for p in dest.rglob("*.gdb") if p.is_dir()]
    if existing:
        return existing[0]
    if zips is not None:
        with zipfile.ZipFile(zip_do_cache(zips, item)) as z:
            z.extractall(dest)
        return next(p for p in dest.rglob("*.gdb") if p.is_dir())
    zpath = dest / f"{item}.gdb.zip"
    for attempt in range(retries):
        try:
            with requests.get(ARCGIS_DATA.format(item=item), stream=True, timeout=3000) as r:
                r.raise_for_status()
                with open(zpath, "wb") as f:
                    f.writelines(r.iter_content(1 << 22))
            break
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    zpath.unlink()
    return next(p for p in dest.rglob("*.gdb") if p.is_dir())


def _s(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip()


def classificar(tip_unid: pd.Series) -> pd.Series:
    """Tipo de equipamento a partir do código ``TIP_UNID``."""
    t = _s(tip_unid)
    out = pd.Series("outro", index=t.index, dtype="object")
    for nome, codigos in TIPOS.items():
        out[t.isin(codigos)] = nome
    return out


def equipamentos_por_alimentador(sw: pd.DataFrame, ctmt: pd.DataFrame) -> pd.DataFrame:
    """Contagem de equipamentos por alimentador canônico (nome operacional), com e sem telecomando.

    ``sw``: colunas CTMT, TIP_UNID, TLCD. ``ctmt``: colunas COD_ID, NOME, SUB.
    Disjuntores são os equipamentos de saída na subestação; os demais estão na rede.
    """
    sw = sw.assign(CTMT=_s(sw.CTMT), tipo=classificar(sw.TIP_UNID), tlcd=_s(sw.TLCD) == "1")
    ct = pd.DataFrame({"CTMT": _s(ctmt.COD_ID), "alimentador": _s(ctmt.NOME).str.zfill(6),
                       "subestacao": _s(ctmt.SUB)})
    sw = sw.merge(ct, on="CTMT", how="inner")
    g = sw.groupby("alimentador")
    out = pd.DataFrame({
        "n_religadores": g.apply(lambda d: (d.tipo == "religador").sum(), include_groups=False),
        "n_religadores_tlcd": g.apply(lambda d: ((d.tipo == "religador") & d.tlcd).sum(), include_groups=False),
        "n_disjuntores": g.apply(lambda d: (d.tipo == "disjuntor").sum(), include_groups=False),
        "n_seccionalizadores": g.apply(lambda d: (d.tipo == "seccionalizador").sum(), include_groups=False),
        "n_chaves_fusiveis": g.apply(lambda d: (d.tipo == "chave_fusivel").sum(), include_groups=False),
        # telecomando na rede: tudo exceto o disjuntor de saída da SE
        "n_tlcd_rede": g.apply(lambda d: (d.tlcd & (d.tipo != "disjuntor")).sum(), include_groups=False),
    })
    out = ct.drop_duplicates("alimentador").set_index("alimentador")[["subestacao"]].join(out, how="left")
    return out.fillna(0).reset_index()


def _read(gdb: Path, layer: str, cols: list[str]) -> pd.DataFrame:
    camadas = {n for n, _ in pyogrio.list_layers(gdb)}
    layer = next(c for c in [layer, layer.upper()] if c in camadas)
    fields = set(pyogrio.read_info(gdb, layer=layer)["fields"])
    alias = {"NOME": ["NOME", "NOM"]}
    origem = {c: next(a for a in alias.get(c, [c]) if a in fields) for c in cols
              if any(a in fields for a in alias.get(c, [c]))}
    df = pyogrio.read_dataframe(gdb, layer=layer, read_geometry=False, columns=list(origem.values()))
    df = df.rename(columns={v: k for k, v in origem.items()})
    for c in set(cols) - set(origem):
        df[c] = None
    return df


def subestacoes(gdb: Path) -> pd.DataFrame:
    """Nome e potência instalada (MVA) de cada subestação do snapshot."""
    sub = _read(gdb, "SUB", ["COD_ID", "NOME"])
    sub = pd.DataFrame({"subestacao": _s(sub.COD_ID), "subestacao_nome": _s(sub.NOME)})
    try:
        tr = _read(gdb, "UNTRAT", ["SUB", "POT_NOM"])
        tr = pd.DataFrame({"subestacao": _s(tr.SUB), "pot": pd.to_numeric(tr.POT_NOM, errors="coerce")})
        pot = tr.groupby("subestacao").pot.sum().rename("potencia_mva")
        sub = sub.merge(pot.reset_index(), on="subestacao", how="left")
    except (StopIteration, KeyError):
        sub["potencia_mva"] = None
    return sub


def build_snapshot(item: str, ano: int, raw: Path, interim: Path, keep_gdb: bool = False,
                   gdb: Path | None = None, zips: Path | None = None) -> Path:
    """Equipamentos e subestações de um snapshot. ``gdb``: .gdb já extraído (não é apagado); ``zips``: cache de zips."""
    dest = raw / "bdgd" / str(ano)
    externo = gdb is not None
    gdb = gdb if externo else download(item, dest, zips=zips)
    sw = _read(gdb, "UNSEMT", ["CTMT", "TIP_UNID", "TLCD"])
    ct = _read(gdb, "CTMT", ["COD_ID", "NOME", "SUB"])
    eq = equipamentos_por_alimentador(sw, ct).assign(ano_snapshot=ano)
    interim.mkdir(parents=True, exist_ok=True)
    out = interim / f"equipamentos_{ano}.parquet"
    eq.to_parquet(out, index=False)
    subestacoes(gdb).assign(ano_snapshot=ano).to_parquet(interim / f"subestacoes_{ano}.parquet", index=False)
    log.info("BDGD %s: %d alimentadores, %d religadores (%d telecomandados)", ano, len(eq),
             eq.n_religadores.sum(), eq.n_religadores_tlcd.sum())
    if not keep_gdb and not externo:
        shutil.rmtree(dest, ignore_errors=True)
    return out
