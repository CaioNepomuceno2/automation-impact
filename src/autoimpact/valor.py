"""Conversão do efeito estimado em CHI evitado, minutos de DEC e R$."""
from __future__ import annotations

import numpy as np


def chi_evitado(chi_base: float, coef: float, unidades: float = 1.0) -> float:
    """CHI/ano evitado ao adicionar ``unidades`` a um alimentador com CHI esperado ``chi_base``.

    O modelo é log-linear (PPML): E[CHI] = base · exp(coef · unidades).
    """
    return float(chi_base * (1 - np.exp(coef * unidades)))


def dec_minutos(chi: float, uc_total: float) -> float:
    """Contribuição em minutos de DEC do sistema (DEC = CHI / UC)."""
    return float(chi / uc_total * 60)


def anuidade(taxa: float, anos: int) -> float:
    """Fator que converte um fluxo anual constante em valor presente."""
    return float((1 - (1 + taxa) ** -anos) / taxa)


def vpl(beneficio_anual: float, custo: float, taxa: float, anos: int) -> float:
    return float(beneficio_anual * anuidade(taxa, anos) - custo)


def custo_indisponibilidade(beneficio_telecomando_anual: float, n_equipamentos: float, pp: float = 1.0) -> float:
    """R$/ano perdidos por ``pp`` pontos percentuais de indisponibilidade do telecomando.

    Premissa: o benefício do telecomando só existe enquanto o equipamento está supervisionado e
    comandável, então ele escala linearmente com a disponibilidade. O religamento automático local
    não depende de comunicação e fica de fora desta conta.
    """
    return float(beneficio_telecomando_anual * n_equipamentos * pp / 100)
