"""DiD robusto à adoção escalonada (Callaway & Sant'Anna, escala multiplicativa) ao lado do empilhado e do TWFE.

Protocolo e regras de relato: docs/preregistro_did_escalonado.md. Saídas NOVAS em reports/ (nenhum arquivo
existente é sobrescrito): did_escalonado_att_gt.csv, did_escalonado_eventstudy.csv, did_escalonado_resumo.csv,
did_escalonado_tendencia.csv, did_escalonado_valor.json e figures/07_did_escalonado.png.

Uso: python scripts/05_did_escalonado.py [--config configs/ems.yaml] [--valor reports/valor.json] [--reps 2000]
     [--saida reports]
``--valor``: valor.json da MESMA versão dos dados (o regenerado por 02_estimar.py), usado em D5 e D6.
Os padrões de ``--valor`` e ``--saida`` vêm da pasta ``paths.reports`` da configuração.

Configuração com ``regra_decisao`` (MS): só roda se a regra pré-registrada liberou o efeito próprio; senão, para com
uma mensagem (nada é estimado) e todo arquivo de saída leva ``origem_efeito``.
"""
import argparse
import hashlib
import json
import logging
import warnings
from importlib.metadata import version
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from autoimpact import did_escalonado as de
from autoimpact import modelo, painel, regra
from autoimpact.config import carregar_dos_argumentos

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("did_escalonado")

cfg, resto = carregar_dos_argumentos()
ap = argparse.ArgumentParser()
ap.add_argument("--valor", default=str(cfg.reports / "valor.json"))
ap.add_argument("--reps", type=int, default=de.B_PADRAO)
ap.add_argument("--saida", default=str(cfg.reports))
args = ap.parse_args(resto)
OUT = Path(args.saida)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "figures").mkdir(exist_ok=True)
DES = ["chi", "duracao_h", "n_falhas", "ci_por_falha"]
LIMITE_PP = 5.0

# ------------------------------------------------------------------ dados e tratamento (iguais ao 02_estimar.py)
p = painel.carregar(cfg.gridrisk_interim, cfg.interim, cfg.anos_resultado)
p["log_km"] = np.log(p.rede_mt_km.clip(lower=0.1))
p["log_uc"] = np.log(p.n_uc.clip(lower=1))
ev, ctrl, dec = regra.decisao_do_painel(p, cfg)
if dec is not None and not dec.publica_efeito_proprio:
    raise SystemExit(f"regra de decisão ({dec.motivo}): o efeito próprio não é publicado, então o CS não roda. "
                     f"Origem do efeito: {dec.origem_efeito}")
ORIGEM = None if dec is None else dec.origem_efeito
pilha = modelo.empilhar(p, ev, ctrl)
log.info("painel %d linhas; eventos %d (coortes %s); controles %d", len(p), len(ev),
         ev.ano_evento.value_counts().sort_index().to_dict(), len(ctrl))

# ------------------------------------------------------------------ CS (bootstrap pareado entre desfechos)
dados_ref = de.preparar(p, ev, ctrl, "chi")
contagens = de.sortear(dados_ref, args.reps, de.SEMENTE)
res = {d: de.estimar(p, ev, ctrl, d, contagens=contagens) for d in DES}
for d in DES:
    r = res[d].resumo("post")
    log.info("CS %-13s pós: %+.1f%% [%.1f, %.1f]", d, r["efeito_pct"], r["lo_pct"], r["hi_pct"])
log.info("células descartadas:\n%s", res["chi"].plano.descartadas.to_string())

# ------------------------------------------------------------------ comparadores (mesma versão dos dados)
st_reg = {d: modelo.did_pilha(pilha, d) for d in DES}
st_es = {d: modelo.event_study(pilha, d) for d in DES}
tw_bin = {d: de.twfe_binario(p, ev, ctrl, d) for d in ["chi", "duracao_h"]}
tw_cont = {d: modelo.efeito(p, d, "n_religadores", ["log_km", "log_uc"]) for d in DES}


def _st(d):
    r = st_reg[d]
    lo, hi = r.ic95_pct
    return {"efeito_pct": r.efeito_pct, "lo_pct": lo, "hi_pct": hi}


# ------------------------------------------------------------------ tabelas
att = pd.concat([res[d].celulas for d in DES], ignore_index=True)
regra.salvar_csv(att, OUT / "did_escalonado_att_gt.csv", ORIGEM)

linhas_es = []
for d in DES:
    for nome, tab in [("CS", de.event_study(res[d])), ("CS (coortes com 3 anos pré)", de.event_study(res[d], "pb_"))]:
        linhas_es += tab.assign(estimador=nome)[["desfecho", "estimador", "rel", "efeito_pct", "lo_pct", "hi_pct", "ep"]
                                                ].to_dict("records")
    e = st_es[d]
    linhas_es += e.assign(estimador="empilhado", ep=e.ep)[["desfecho", "estimador", "rel", "efeito_pct", "lo_pct",
                                                           "hi_pct", "ep"]].to_dict("records")
    # CS com a pré-tendência linear descontada (λ = 1)
    pt, rp = res[d].ponto, res[d].replicas
    dl_pt, dl_rp = float(de.declive_pre(pt["e-3"], pt["e-2"])), de.declive_pre(rp["e-3"].to_numpy(), rp["e-2"].to_numpy())
    for tt in de.TEMPOS_ES:
        r = de.resumir(float(pt[f"e{tt}"]) - dl_pt * (tt + 1), rp[f"e{tt}"].to_numpy() - dl_rp * (tt + 1))
        linhas_es.append({"desfecho": d, "estimador": "CS ajustado pela pré-tendência (λ=1)", "rel": tt,
                          **{k: r[k] for k in ["efeito_pct", "lo_pct", "hi_pct", "ep"]}})
es_all = pd.DataFrame(linhas_es).sort_values(["desfecho", "estimador", "rel"])
regra.salvar_csv(es_all, OUT / "did_escalonado_eventstudy.csv", ORIGEM)

resumo = []
for d in DES:
    for chave, nome in [("post", "CS pós (média de e=0,1,2)"), ("simples", "CS simples (células pós ponderadas)"),
                        ("balanceado", "CS balanceado (coortes com e=0,1,2)"), ("pb_post", "CS pós, coortes com 3 anos pré")]:
        r = res[d].resumo(chave)
        resumo.append({"desfecho": d, "estimador": nome, **{k: r[k] for k in ["efeito_pct", "lo_pct", "hi_pct", "ep"]},
                       "p_valor": r["p_boot"], "inferencia": "bootstrap por alimentador (percentis)"})
    r = st_reg[d].registro()
    resumo.append({"desfecho": d, "estimador": "DiD empilhado (did_pilha)", "efeito_pct": r["efeito_pct"],
                   "lo_pct": r["ic95_lo_pct"], "hi_pct": r["ic95_hi_pct"], "ep": r["ep"], "p_valor": r["p_valor"],
                   "inferencia": "erro-padrão agrupado por alimentador"})
    if d in tw_bin:
        r = tw_bin[d].registro()
        resumo.append({"desfecho": d, "estimador": "TWFE binário simples (sem empilhar)", "efeito_pct": r["efeito_pct"],
                       "lo_pct": r["ic95_lo_pct"], "hi_pct": r["ic95_hi_pct"], "ep": r["ep"], "p_valor": r["p_valor"],
                   "inferencia": "erro-padrão agrupado por alimentador"})
    r = tw_cont[d].registro()
    resumo.append({"desfecho": d, "estimador": "TWFE contínuo, por religador (outra unidade)", "efeito_pct": r["efeito_pct"],
                   "lo_pct": r["ic95_lo_pct"], "hi_pct": r["ic95_hi_pct"], "ep": r["ep"], "p_valor": r["p_valor"],
                   "inferencia": "erro-padrão agrupado por alimentador"})
resumo = pd.DataFrame(resumo)
regra.salvar_csv(resumo, OUT / "did_escalonado_resumo.csv", ORIGEM)

tend, equilibrio = [], {}
for d in ["duracao_h", "chi"]:
    for prefixo in ["", "pb_"]:
        t = de.ajuste_tendencia(res[d], prefixo)
        tend.append(t)
        equilibrio[f"{d}|{t.amostra.iloc[0]}"] = de.lambda_equilibrio(t)
tend = pd.concat(tend, ignore_index=True)
regra.salvar_csv(tend, OUT / "did_escalonado_tendencia.csv", ORIGEM)
pontual = {d: de.ajuste_tendencia_pontual(st_es[d]) for d in ["duracao_h", "chi"]}

# ------------------------------------------------------------------ regras do pré-registro
regras = {}
for d in ["chi", "duracao_h"]:
    regras[f"D1_D2_{d}"] = {**de.divergencia(res[d].resumo("post"), _st(d), LIMITE_PP),
                            "cs": res[d].resumo("post"), "empilhado": _st(d)}
    d3 = {}
    for tt in de.TEMPOS_POS:
        cs_e = res[d].resumo(f"e{tt}")["efeito_pct"]
        st_e = float(st_es[d].set_index("rel").loc[tt, "efeito_pct"])
        d3[f"e{tt}"] = {"cs_pct": cs_e, "empilhado_pct": st_e, "gap_pp": cs_e - st_e, "dispara": bool(abs(cs_e - st_e) > LIMITE_PP)}
    regras[f"D3_{d}"] = d3
    cs_pct = res[d].resumo("post")["efeito_pct"]
    regras[f"D4_{d}"] = {"twfe_binario_pct": tw_bin[d].efeito_pct, "cs_pct": cs_pct,
                         "gap_pp": tw_bin[d].efeito_pct - cs_pct, "dispara": bool(abs(tw_bin[d].efeito_pct - cs_pct) > LIMITE_PP)}

# D5: CHI evitado por religador (mesma fórmula do 02_estimar.py, com o θ_pós do CS no lugar do coeficiente do empilhado)
pre = (pilha[(pilha.tratado == 1) & (pilha.rel < 0)].groupby(["alimentador", "coorte"])[["chi"]].mean().reset_index()
       .merge(ev.rename(columns={"ano_evento": "coorte"}), on=["alimentador", "coorte"]))
ganho_total, ganho_medio = float(pre.ganho.sum()), float(pre.ganho.sum() / len(ev))


def chi_por_religador(theta):
    return float(pre.chi.sum() * (1 - np.exp(theta)) / ganho_total)


valor_base = json.loads(Path(args.valor).read_text())
base_pipeline = chi_por_religador(st_reg["chi"].coef)
r_cs = res["chi"].resumo("post")
reps_chi = res["chi"].replicas["post"].to_numpy()
reps_chi = reps_chi[np.isfinite(reps_chi)]
cs_val = chi_por_religador(r_cs["theta"])
cs_val_ic = [float(chi_por_religador(x)) for x in np.percentile(reps_chi, [97.5, 2.5])]
base_valor = float(valor_base["chi_evitado_ano_por_religador"])
regras["D5"] = {"chi_evitado_por_religador_empilhado_recalculado": base_pipeline,
                "chi_evitado_por_religador_valor_json": base_valor,
                "chi_evitado_por_religador_cs": cs_val, "ic95_cs": cs_val_ic,
                "razao_cs_sobre_empilhado": cs_val / base_pipeline,
                "dispara": bool(abs(cs_val / base_pipeline - 1) > 0.20 or not (cs_val_ic[0] <= base_pipeline <= cs_val_ic[1]))}
if abs(base_pipeline / base_valor - 1) > 1e-6:
    log.warning("o empilhado recalculado (%.3f) difere do valor.json informado (%.3f)", base_pipeline, base_valor)

# D6: custo do p.p. de indisponibilidade com o efeito do CS (diagnóstico; conversão sob hipótese log-linear na dose)
b_tw = tw_cont["chi"].coef
b_tw_ic = [b_tw - 1.96 * tw_cont["chi"].ep, b_tw + 1.96 * tw_cont["chi"].ep]
s_tw = float(valor_base["frac_efeito_via_duracao_twfe"])
th_chi, th_dur = res["chi"].replicas["post"].to_numpy(), res["duracao_h"].replicas["post"].to_numpy()
lam1_dur_pt, lam1_dur_rp = de.pos_ajustado_resultado(res["duracao_h"], 1.0)


def fator(th_c, th_d):
    b_cs = th_c / ganho_medio
    s_cs = np.clip(th_d / th_c, 0, 1)
    return (np.exp(-b_cs) - 1) / (np.exp(-b_tw) - 1) * s_cs / s_tw, b_cs, s_cs


f_pt, b_cs_pt, s_cs_pt = fator(r_cs["theta"], res["duracao_h"].resumo("post")["theta"])
f_aj, _, s_aj = fator(r_cs["theta"], lam1_dur_pt)
f_rp, _, _ = fator(th_chi, th_dur)
f_rp_aj, _, _ = fator(th_chi, lam1_dur_rp)
ind = valor_base["indisponibilidade_1pp"]
alt = {}
for nome, f, f_reps in [("sem_ajuste", f_pt, f_rp), ("com_ajuste_pre_tendencia", f_aj, f_rp_aj)]:
    ok = np.isfinite(f_reps)
    alt[nome] = {"fator_sobre_valor_publicado": float(f), "fator_ic95": [float(x) for x in np.nanpercentile(f_reps[ok], [2.5, 97.5])]}
    for k, rot in [("canal_duracao_inteiro", "inteiro"), ("metade_do_canal_duracao", "metade")]:
        alt[nome][f"dec_min_por_pp_{rot}"] = float(ind[k]["dec_min_por_pp"] * f)
        alt[nome][f"rs_ano_por_pp_social_{rot}"] = float(ind[k]["rs_ano_por_pp_social"] * f)
publ = [ind["metade_do_canal_duracao"]["dec_min_por_pp"], ind["canal_duracao_inteiro"]["dec_min_por_pp"]]
for v in alt.values():
    lo, hi = v["dec_min_por_pp_metade"], v["dec_min_por_pp_inteiro"]
    v["sobrepoe_faixa_publicada"] = bool(max(lo, publ[0]) <= min(hi, publ[1]))
regras["D6"] = {"b_por_religador_twfe": b_tw, "b_por_religador_twfe_ic95": b_tw_ic, "b_por_religador_cs_equivalente": float(b_cs_pt),
                "ganho_medio": ganho_medio, "fracao_duracao_twfe": s_tw, "fracao_duracao_cs": float(s_cs_pt),
                "fracao_duracao_cs_ajustada": float(s_aj), "faixa_publicada_dec_min_por_pp": publ, "alternativas": alt,
                "dispara": bool(not (b_tw_ic[0] <= b_cs_pt <= b_tw_ic[1]) or not alt["sem_ajuste"]["sobrepoe_faixa_publicada"]),
                "nota": "conversão ilustrativa: supõe efeito log-linear na dose (θ_pós dividido pelo ganho médio)"}

meta = {"semente": de.SEMENTE, "replicas": int(args.reps), "janela": list(de.JANELA), "min_tratados": de.MIN_TRATADOS,
        "limite_pp": LIMITE_PP, "eventos": len(ev), "controles": len(ctrl), "religadores_adicionados": ganho_total,
        "coortes": {int(k): int(v) for k, v in ev.ano_evento.value_counts().sort_index().items()},
        "valor_json_usado": {"arquivo": Path(args.valor).name, "sha256": hashlib.sha256(Path(args.valor).read_bytes()).hexdigest()},
        "versoes": {k: version(k) for k in ["numpy", "pandas", "pyfixest", "scipy"]},
        "celulas_descartadas": res["chi"].plano.descartadas.to_dict("records"),
        "celulas_por_tempo_relativo": {int(k): int(v) for k, v in res["chi"].celulas.groupby("e").size().items()}}
if ORIGEM is not None:
    meta = {"origem_efeito": ORIGEM, **meta}
saida = {"meta": meta, "regras": regras, "pre_tendencia": {"equilibrio": equilibrio, "empilhado_pontual": pontual}}
(OUT / "did_escalonado_valor.json").write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=float))
for k, v in regras.items():
    log.info("%s -> %s", k, v if k != "D6" else {x: v[x] for x in ["dispara", "b_por_religador_cs_equivalente", "fracao_duracao_cs"]})

# ------------------------------------------------------------------ figura
AZUL, LARANJA, VERDE, CINZA = "#2a78d6", "#eb6834", "#1baf7a", "#8a8a8a"
plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e5e5e5", "font.size": 9, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})
fig, axs = plt.subplots(1, 3, figsize=(14.5, 3.9))
for ax, d, titulo in [(axs[0], "chi", "CHI"), (axs[1], "duracao_h", "Duração média por consumidor")]:
    for nome, cor, desloc, estilo in [("empilhado", AZUL, -0.12, "o-"), ("CS", LARANJA, 0.12, "s-"),
                                      ("CS ajustado pela pré-tendência (λ=1)", VERDE, 0.0, "^--")]:
        if d == "chi" and nome.startswith("CS ajustado"):
            continue
        t = es_all[(es_all.desfecho == d) & (es_all.estimador == nome)].sort_values("rel")
        x = t.rel + desloc
        ax.errorbar(x, t.efeito_pct, yerr=[t.efeito_pct - t.lo_pct, t.hi_pct - t.efeito_pct], fmt=estilo, color=cor,
                    ms=4, lw=1.4, capsize=2, label={"empilhado": "DiD empilhado (resultado do README)",
                                                    "CS": "Callaway & Sant'Anna"}.get(nome, "CS, descontando a tendência anterior"))
    ax.axhline(0, color="#555", lw=0.8)
    ax.axvline(-0.5, color="#555", lw=0.8, ls=":")
    ax.set_title(titulo, loc="left", fontweight="bold", fontsize=10)
    ax.set_xlabel("anos desde a instalação")
    ax.set_xticks(range(-3, 3))
axs[0].set_ylabel("efeito (%) vs. controles nunca tratados")
axs[1].legend(frameon=False, fontsize=7, loc="upper right")
t = tend[(tend.desfecho == "duracao_h") & (tend.amostra == "todas")]
axs[2].fill_between(t["lambda"], t.lo_pct, t.hi_pct, color=VERDE, alpha=0.18, lw=0)
axs[2].plot(t["lambda"], t.efeito_pct, color=VERDE, lw=2)
axs[2].axhline(0, color="#555", lw=0.8)
axs[2].set_xlabel("λ: fração da tendência anterior que continua depois da instalação")
axs[2].set_ylabel("efeito pós-instalação na duração (%)")
axs[2].set_title("Duração: quanto da tendência anterior sustenta a queda?", loc="left", fontweight="bold", fontsize=10)
fig.suptitle("Estimador robusto à adoção escalonada ao lado do resultado principal (IC 95%)"
             + ("" if ORIGEM is None else f" - efeito {ORIGEM}"), x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
fig.savefig(OUT / "figures" / "07_did_escalonado.png", bbox_inches="tight")
plt.close(fig)
log.info("pronto: %s", sorted(x.name for x in OUT.glob("did_escalonado_*")))
