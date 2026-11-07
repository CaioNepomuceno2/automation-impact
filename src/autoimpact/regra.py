"""Regra de decisão pré-registrada e rótulo de origem do efeito (recortes que não são MT).

Para uma distribuidora com poucos religadores novos, o efeito próprio não se sustenta. A regra, escrita antes de
qualquer estimação (``docs/decisoes_ems.md``), diz quando ele pode ser publicado:

* conta-se, com as MESMAS funções de MT (``painel.eventos_tratamento(minimo=2)`` e ``painel.nunca_tratados``),
  os alimentadores tratados (eventos) e os controles nunca tratados;
* com ``n_eventos >= min_eventos`` E ``n_controles >= min_controles``, publica-se o efeito medido no próprio
  recorte (``origem_efeito = "medido em MS"``), com o de MT ao lado para comparação;
* senão, **não se estima nada** e vale o efeito de MT lido dos resultados publicados, rotulado
  ``"transportado de MT"``. A exposição (CHI, consumidores, frota, R$/CHI) continua sendo a do recorte.

Sem o bloco ``regra_decisao`` na configuração (caso de MT), nada muda: não há decisão nem rótulo.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from autoimpact import painel
from autoimpact.config import Config, Regra

MINIMO_GANHO = 2  # tamanho mínimo do ganho que define um evento (o mesmo de MT)


@dataclass(frozen=True)
class Decisao:
    n_eventos: int
    n_controles: int
    min_eventos: int
    min_controles: int
    publica_efeito_proprio: bool
    origem_efeito: str
    motivo: str

    def registro(self) -> dict:
        return asdict(self)


def decidir(n_eventos: int, n_controles: int, regra: Regra) -> Decisao:
    """Aplica a regra: os dois limites são "pelo menos" (``>=``)."""
    falta = []
    if n_eventos < regra.min_eventos:
        falta.append(f"eventos tratados {n_eventos} < {regra.min_eventos}")
    if n_controles < regra.min_controles:
        falta.append(f"controles nunca tratados {n_controles} < {regra.min_controles}")
    publica = not falta
    motivo = (f"{n_eventos} eventos (mínimo {regra.min_eventos}) e {n_controles} controles (mínimo {regra.min_controles})"
              if publica else "; ".join(falta))
    return Decisao(n_eventos, n_controles, regra.min_eventos, regra.min_controles, publica,
                   regra.origem_medido if publica else regra.origem_transportado, motivo)


def eventos_e_controles(p: pd.DataFrame) -> tuple[pd.DataFrame, pd.Index]:
    """Eventos e controles pela definição de MT (ganho de 2 ou mais religadores que persiste; amplitude de até 1)."""
    return painel.eventos_tratamento(p, minimo=MINIMO_GANHO), painel.nunca_tratados(p)


def decisao_do_painel(p: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.Index, Decisao | None]:
    """Eventos, controles e a decisão (``None`` quando a configuração não tem regra, como em MT)."""
    ev, ctrl = eventos_e_controles(p)
    return ev, ctrl, (None if cfg.regra is None else decidir(len(ev), len(ctrl), cfg.regra))


def rotular(df: pd.DataFrame, origem: str | None) -> pd.DataFrame:
    """Acrescenta a coluna ``origem_efeito`` (sem rótulo, devolve a tabela como está)."""
    return df if origem is None else df.assign(origem_efeito=origem)


def salvar_csv(df: pd.DataFrame, caminho: Path, origem: str | None) -> None:
    rotular(df, origem).to_csv(caminho, index=False)


def carregar_efeito_mt(fonte: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Efeito de MT já publicado (somente leitura): ``efeitos_did.csv``, ``efeitos_por_unidade.csv`` e ``valor.json``."""
    did = pd.read_csv(fonte / "efeitos_did.csv")
    por_unidade = pd.read_csv(fonte / "efeitos_por_unidade.csv")
    valor = json.loads((fonte / "valor.json").read_text(encoding="utf-8"))
    faltam = [d for d in ("chi", "chi_regulatorio", "n_falhas", "ci_por_falha", "duracao_h") if d not in set(did.desfecho)]
    pu = set(zip(por_unidade.regressor, por_unidade.desfecho, strict=True))
    faltam += [f"{r}/{d}" for r in ("n_religadores", "n_religadores_tlcd", "n_tlcd_rede")
               for d in ("chi", "n_falhas", "ci_por_falha", "duracao_h") if (r, d) not in pu]
    if faltam:
        raise ValueError(f"resultados de MT incompletos em {fonte}: faltam {faltam}")
    return did, por_unidade, valor
