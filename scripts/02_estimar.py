"""Estimação (DiD empilhado, event study, TWFE), robustez, valoração e ranking de subestações.

Saídas em reports/ (ou na pasta ``paths.reports`` da configuração): efeitos_did.csv, event_study.csv,
efeitos_por_unidade.csv, robustez.csv, valor.json, subestacoes.csv, elemento_2026.csv, comparacao_premissas.csv.

Uso: python scripts/02_estimar.py [--config configs/ems.yaml]

Configuração com ``regra_decisao`` (MS): conta eventos e controles com as funções de MT e aplica a regra
pré-registrada (docs/decisoes_ems.md). Sem eventos e controles suficientes, NADA é estimado: o efeito vem dos
resultados publicados de MT, a exposição (CHI, consumidores, frota, R$/CHI) é a do recorte, e todo arquivo de
saída leva ``origem_efeito = "transportado de MT"``. Com eventos e controles suficientes, estima-se o efeito
próprio (``"medido em MS"``) e grava-se ``comparacao_mt.csv`` com o de MT ao lado.
"""
import hashlib
import json
import logging
import warnings

import duckdb
import numpy as np
import pandas as pd

from autoimpact import modelo, painel, regra, valor
from autoimpact.config import carregar_dos_argumentos

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("estimar")
cfg, _ = carregar_dos_argumentos()
OUT = cfg.reports
OUT.mkdir(parents=True, exist_ok=True)
pm = cfg.premissas
modelo.DESFECHOS["chi_regulatorio"] = ("chi_regulatorio", None)

p = painel.carregar(cfg.gridrisk_interim, cfg.interim, cfg.anos_resultado)
p["log_km"] = np.log(p.rede_mt_km.clip(lower=0.1))
p["log_uc"] = np.log(p.n_uc.clip(lower=1))
p.to_parquet(cfg.interim / "painel.parquet", index=False)
log.info("painel: %d linhas, %d alimentadores", len(p), p.alimentador.nunique())

# ------------------------------------------------------------------ eventos, controles e regra de decisão
ev, ctrl, dec = regra.decisao_do_painel(p, cfg)
ORIGEM = None if dec is None else dec.origem_efeito     # None em MT: nenhum rótulo, saídas como sempre foram
MEDIDO = dec is None or dec.publica_efeito_proprio      # False = nada é estimado, o efeito vem de MT
pilha = modelo.empilhar(p, ev, ctrl)
log.info("eventos: %d (coortes %s), controles nunca tratados: %d", len(ev),
         ev.ano_evento.value_counts().sort_index().to_dict(), len(ctrl))
regra.salvar_csv(ev, OUT / "eventos_tratamento.csv", ORIGEM)
if dec is not None:
    log.info("regra de decisão: %s -> %s", dec.motivo, dec.origem_efeito)
    contagens_json = OUT / "diagnostico" / "regra_contagens.json"
    if contagens_json.exists():   # as contagens do diagnóstico commitado têm que ser as deste painel
        registrado = json.loads(contagens_json.read_text(encoding="utf-8"))
        if (registrado["n_eventos"], registrado["n_controles"]) != (dec.n_eventos, dec.n_controles):
            raise SystemExit(f"contagens diferentes das registradas em {contagens_json}: {registrado} x {dec.registro()}")

DES = ["chi", "chi_regulatorio", "n_falhas", "ci_por_falha", "duracao_h"]
if MEDIDO:
    did = pd.DataFrame([modelo.did_pilha(pilha, d).registro() for d in DES])
    regra.salvar_csv(did, OUT / "efeitos_did.csv", ORIGEM)
    es = pd.concat([modelo.event_study(pilha, d) for d in ["chi", "n_falhas", "ci_por_falha", "duracao_h"]])
    regra.salvar_csv(es, OUT / "event_study.csv", ORIGEM)
    log.info("DiD:\n%s", did[["desfecho", "efeito_pct", "ic95_lo_pct", "ic95_hi_pct", "p_valor"]].round(3))

    # ------------------------------------------------------------------ efeito por unidade (TWFE contínuo)
    por_unidade = pd.DataFrame([
        modelo.efeito(p, d, reg, ["log_km", "log_uc"]).registro()
        for reg in ["n_religadores", "n_religadores_tlcd", "n_tlcd_rede"]
        for d in ["chi", "n_falhas", "ci_por_falha", "duracao_h"]
    ])
    regra.salvar_csv(por_unidade, OUT / "efeitos_por_unidade.csv", ORIGEM)

    # ------------------------------------------------------------------ robustez
    def _r(nome, pil, d="chi"):
        return {"teste": nome, **modelo.did_pilha(pil, d).registro()}


    g = p.groupby("alimentador").rede_mt_km
    km_est = g.max() / g.min()
    km_est = km_est[km_est <= 1.25].index
    placebo = ev.assign(ano_evento=ev.ano_evento - 2).query(f"ano_evento >= {cfg.ano_placebo_min}")
    pre = p.merge(ev[["alimentador", "ano_evento"]], on="alimentador", how="left")
    pre = pre[pre.ano_evento.isna() | (pre.ano < pre.ano_evento)].drop(columns="ano_evento")
    rob = pd.DataFrame([
        _r("principal (ganho >= 2 religadores)", pilha),
        _r("só CHI regulatório (sem expurgo)", pilha, "chi_regulatorio"),
        _r("ganho >= 1 religador", modelo.empilhar(p, painel.eventos_tratamento(p, minimo=1), ctrl)),
        _r("ganho >= 3 religadores", modelo.empilhar(p, painel.eventos_tratamento(p, minimo=3), ctrl)),
        _r("só alimentadores com extensão estável (±25%)",
           modelo.empilhar(p[p.alimentador.isin(km_est)], ev[ev.alimentador.isin(km_est)], ctrl.intersection(km_est))),
        _r("placebo: tratamento falso 2 anos antes", modelo.empilhar(pre, placebo, ctrl)),
        _r("janela curta (-2 a +1)", modelo.empilhar(p, ev, ctrl, janela=(-2, 1))),
    ])
    regra.salvar_csv(rob, OUT / "robustez.csv", ORIGEM)
    log.info("robustez:\n%s", rob[["teste", "efeito_pct", "ic95_lo_pct", "ic95_hi_pct", "p_valor"]].round(3))
    if dec is not None:   # o efeito de MT ao lado, para comparação
        did_mt, _, _ = regra.carregar_efeito_mt(cfg.regra.fonte_mt)
        regra.salvar_csv(regra.comparar_com_mt(did, did_mt, cfg.sigla), OUT / "comparacao_mt.csv", ORIGEM)

else:
    # Efeito de MT já publicado (somente leitura); nada é estimado neste recorte.
    did, por_unidade, _ = regra.carregar_efeito_mt(cfg.regra.fonte_mt)
    log.info("efeito transportado de MT (%s): CHI %.1f%%", cfg.regra.fonte_mt,
             float(did.set_index("desfecho").loc["chi"].efeito_pct))

# ------------------------------------------------------------------ valoração
pu = por_unidade.set_index(["regressor", "desfecho"])
risco = pd.read_parquet(cfg.gridrisk_processed / "risco_alimentador.parquet").set_index("alimentador")
uc_total = float(p[p.ano == max(cfg.anos_resultado)].n_uc.sum())
pre_trat = (pilha[(pilha.tratado == 1) & (pilha.rel < 0)].groupby(["alimentador", "coorte"])
            [["chi", "chi_regulatorio"]].mean().reset_index())
pre_trat = pre_trat.merge(ev.rename(columns={"ano_evento": "coorte"}), on=["alimentador", "coorte"])
d_chi = did.set_index("desfecho").loc["chi"]
chi_evitado_total = float((pre_trat.chi * (1 - np.exp(d_chi.coef))).sum())
chi_evitado_lo = float((pre_trat.chi * (1 - np.exp(d_chi.coef + 1.96 * d_chi.ep))).sum())
chi_evitado_hi = float((pre_trat.chi * (1 - np.exp(d_chi.coef - 1.96 * d_chi.ep))).sum())
ganho_total = float(pre_trat.ganho.sum())
chi_por_religador = chi_evitado_total / ganho_total

w = pre_trat.set_index("alimentador").chi
rs_comp = float(np.average(risco.reindex(w.index).rs_por_chi_compensacao.fillna(risco.rs_por_chi_compensacao.median()),
                           weights=w))
rs_soc = float(np.average(risco.reindex(w.index).rs_por_chi_social.fillna(risco.rs_por_chi_social.median()),
                          weights=w))
frac_reg = float(pre_trat.chi_regulatorio.sum() / pre_trat.chi.sum())
rs_ano_comp = chi_por_religador * frac_reg * rs_comp
rs_ano_soc = chi_por_religador * rs_soc
anos_vida, taxa, custo = pm["vida_religador_anos"], pm["taxa_desconto"], pm["custo_religador_rs"]

# ------------------------------------------------------------------ valor da disponibilidade (frota inteira)
# O efeito por religador dos eventos vale para alimentadores críticos que receberam pacotes; para a frota
# inteira usa-se o efeito marginal do TWFE (cada religador a mais reduz o CHI do próprio alimentador em
# 1 - exp(b)), aplicado ao CHI de cada alimentador. CHI = falhas x UC por falha x duração: o canal da
# frequência (religamento automático) é local; o da duração (saber na hora que o religador abriu, e onde)
# depende de supervisão e comando. A fração dependente de comunicação é a parte do efeito que passa pela duração.
b = {d: pu.loc[("n_religadores", d), "coef"] for d in ["chi", "n_falhas", "ci_por_falha", "duracao_h"]}
frac_duracao = float(np.clip(b["duracao_h"] / b["chi"], 0, 1))
falhas_all = pd.read_parquet(cfg.gridrisk_interim / "falhas.parquet")
chi_recente = falhas_all[falhas_all.ano.between(*cfg.anos_chi_recente)].groupby("alimentador").chi.sum() / 3
eq25 = pd.read_parquet(cfg.interim / f"equipamentos_{cfg.ano_cadastro_frota}.parquet").set_index("alimentador")
frota = eq25[["n_religadores"]].join(chi_recente.rename("chi_ano")).fillna({"chi_ano": 0})
frota["chi_marginal"] = frota.chi_ano * (np.exp(-b["chi"]) - 1)  # CHI que cada religador evita, no seu alimentador
frota["rs_social"] = risco.rs_por_chi_social.reindex(frota.index).fillna(rs_soc)
frota["rs_comp"] = risco.rs_por_chi_compensacao.reindex(frota.index).fillna(rs_comp)
n_religadores_2025 = float(frota.n_religadores.sum())
chi_frota = float((frota.n_religadores * frota.chi_marginal).sum())
rs_frota_soc = float((frota.n_religadores * frota.chi_marginal * frota.rs_social).sum())
rs_frota_comp = float((frota.n_religadores * frota.chi_marginal * frota.rs_comp).sum()) * frac_reg

indisp = {}
for nome, s_ in [("canal_duracao_inteiro", frac_duracao), ("metade_do_canal_duracao", frac_duracao / 2)]:
    chi_pp = valor.custo_indisponibilidade(chi_frota * s_, 1, pp=1)
    indisp[nome] = {"fracao_dependente_de_comunicacao": s_, "chi_ano_por_pp": chi_pp,
                    "dec_min_por_pp": valor.dec_minutos(chi_pp, uc_total),
                    "rs_ano_por_pp_social": rs_frota_soc * s_ / 100,
                    "rs_ano_por_pp_compensacao": rs_frota_comp * s_ / 100}

val = {
    "eventos": len(ev), "religadores_adicionados_nos_eventos": ganho_total,
    "ganho_mediano_por_evento": float(ev.ganho.median()),
    "efeito_chi_pct": float(d_chi.efeito_pct), "ic95_chi_pct": [float(d_chi.ic95_lo_pct), float(d_chi.ic95_hi_pct)],
    "chi_evitado_ano_eventos": chi_evitado_total, "chi_evitado_ano_ic95": [chi_evitado_lo, chi_evitado_hi],
    "chi_evitado_ano_por_religador": chi_por_religador,
    "chi_evitado_ano_por_religador_ic95": [chi_evitado_lo / ganho_total, chi_evitado_hi / ganho_total],
    "uc_total": uc_total,
    "dec_min_por_religador": valor.dec_minutos(chi_por_religador, uc_total),
    "rs_por_chi_compensacao": rs_comp, "rs_por_chi_social": rs_soc, "frac_chi_regulatorio": frac_reg,
    "rs_ano_por_religador_compensacao": rs_ano_comp, "rs_ano_por_religador_social": rs_ano_soc,
    "vpl_religador_compensacao": valor.vpl(rs_ano_comp, custo, taxa, anos_vida),
    "vpl_religador_social": valor.vpl(rs_ano_soc, custo, taxa, anos_vida),
    "payback_anos_social": custo / rs_ano_soc if rs_ano_soc > 0 else None,
    "twfe_efeito_por_religador_pct": {d: float(100 * (np.exp(v) - 1)) for d, v in b.items()},
    "frac_efeito_via_duracao_twfe": frac_duracao,
    "religadores_2025": n_religadores_2025,
    "frota_chi_ano_dependente_dos_religadores": chi_frota,
    "frota_chi_marginal_medio_por_religador": chi_frota / n_religadores_2025,
    "indisponibilidade_1pp": indisp,
    "premissas": {"custo_religador_rs": custo, "vida_anos": anos_vida, "taxa_desconto": taxa,
                  "custo_ens_rs_mwh": pm["custo_ens_rs_mwh"]},
}
if ORIGEM is not None:   # mesmo esquema de MT mais o campo de origem do efeito (primeiro campo)
    val = {"origem_efeito": ORIGEM, **val}
(OUT / "valor.json").write_text(json.dumps(val, indent=2, ensure_ascii=False))
log.info("valor: %s", json.dumps({k: v for k, v in val.items() if not isinstance(v, dict)}, ensure_ascii=False))

# ------------------------------------------------------------------ premissas do distribution-asset-risk
# (compara a premissa com o efeito medido; só faz sentido quando o efeito foi medido neste recorte)
if MEDIDO:
    comp = pd.DataFrame([
        {"intervencao": "religador (pacote)", "premissa_reducao_chi_alimentador_pct": -45 * 0.5,
         "medido_pct": float(d_chi.efeito_pct), "ic95": f"[{d_chi.ic95_lo_pct:.1f}, {d_chi.ic95_hi_pct:.1f}]",
         "nota": "premissa: eficácia 0,45 x alcance 0,5 por pacote de até 4 religadores; medido: evento típico de +2 a +5"},
        {"intervencao": "telecomando (2 chaves)", "premissa_reducao_chi_alimentador_pct": -35 * 0.6,
         "medido_pct": float(100 * (np.exp(2 * pu.loc[("n_tlcd_rede", "chi"), "coef"]) - 1)),
         "ic95": "[{:.1f}, {:.1f}]".format(*(100 * (np.exp(2 * (pu.loc[("n_tlcd_rede", "chi"), "coef"] + s * 1.96
                                                              * pu.loc[("n_tlcd_rede", "chi"), "ep"])) - 1)
                                             for s in (-1, 1))),
         "nota": "premissa: eficácia 0,35 x alcance 0,6; medido: 2 x efeito por equipamento telecomandado na rede (TWFE)"},
    ])
    regra.salvar_csv(comp, OUT / "comparacao_premissas.csv", ORIGEM)

# ------------------------------------------------------------------ subestações
falhas = pd.read_parquet(cfg.gridrisk_interim / "falhas.parquet")
chi3 = falhas[falhas.ano.between(*cfg.anos_chi_recente)].groupby("alimentador").chi.sum() / 3
eq = pd.read_parquet(cfg.interim / f"equipamentos_{cfg.ano_cadastro_subestacoes}.parquet").set_index("alimentador")
fe = pd.read_parquet(cfg.gridrisk_interim / f"bdgd_feeders_{cfg.ano_cadastro_subestacoes}.parquet").rename(
    columns={"alimentador_nome": "alimentador"}).drop_duplicates("alimentador").set_index("alimentador")
se_nome = pd.read_parquet(cfg.interim / f"subestacoes_{cfg.ano_cadastro_subestacoes}.parquet").set_index("subestacao")
a = eq[["subestacao", "n_religadores"]].join(fe[["rede_mt_km", "n_uc"]]).join(chi3.rename("chi_ano"))
a["chi_ano"] = a.chi_ano.fillna(0)
a["religadores_100km"] = a.n_religadores / a.rede_mt_km.replace(0, np.nan) * 100
dens_med = a.loc[a.rede_mt_km >= 30, "religadores_100km"].median()
candidato = (a.rede_mt_km >= 30) & (a.religadores_100km < dens_med)
a["chi_evitavel"] = np.where(candidato, a.chi_ano * (1 - np.exp(d_chi.coef)), 0.0)
a["rs_por_chi_social"] = risco.rs_por_chi_social.reindex(a.index).fillna(rs_soc)
a["rs_evitavel_social"] = a.chi_evitavel * a.rs_por_chi_social
se = a.groupby("subestacao").agg(alimentadores=("chi_ano", "size"), rede_mt_km=("rede_mt_km", "sum"),
                                 n_uc=("n_uc", "sum"), religadores=("n_religadores", "sum"),
                                 chi_ano=("chi_ano", "sum"), candidatos=("chi_evitavel", lambda s: int((s > 0).sum())),
                                 chi_evitavel=("chi_evitavel", "sum"), rs_evitavel_social=("rs_evitavel_social", "sum"))
se = se.join(se_nome[["subestacao_nome", "potencia_mva"]]).sort_values("chi_ano", ascending=False)
se["frac_chi"] = se.chi_ano / se.chi_ano.sum()
se["frac_chi_acum"] = se.frac_chi.cumsum()
se["dec_min"] = se.chi_ano / uc_total * 60
se["dec_min_evitavel"] = se.chi_evitavel / uc_total * 60
regra.salvar_csv(se.reset_index(), OUT / "subestacoes.csv", ORIGEM)
k10 = max(1, round(len(se) * 0.1))
log.info("SEs: %d; top 10%% (%d) = %.1f%% do CHI; densidade mediana %.2f religadores/100 km",
         len(se), k10, 100 * se.frac_chi.iloc[:k10].sum(), dens_med)

# ------------------------------------------------------------------ 2026: quem interrompeu (elemento)
it = cfg.interrupcoes_parquet
el = duckdb.sql(f"""
    select coalesce(elemento, 'NAO INFORMADO') as elemento, count(*) as interrupcoes,
           avg(uc_afetadas) as uc_media, median(uc_afetadas) as uc_mediana, avg(duracao_h) as duracao_media_h,
           sum(chi) as chi
    from read_parquet('{it}')
    where ano = {cfg.ano_elemento} and origem_mt and origem = 'INTERNA' and tipo = 'NAO PROGRAMADA'
    group by 1 order by chi desc
""").df()
el["frac_chi"] = el.chi / el.chi.sum()
regra.salvar_csv(el, OUT / "elemento_2026.csv", ORIGEM)
log.info("elemento 2026:\n%s", el.round(3).to_string())

# ------------------------------------------------------------------ carteira ilustrativa pelas SEs
GANHO = float(ev.ganho.median())
cand = a[a.chi_evitavel > 0]
invest = len(cand) * GANHO * custo
rs_soc_ano = float(cand.rs_evitavel_social.sum())
carteira = {"alimentadores_candidatos": len(cand), "religadores_por_alimentador": GANHO,
            "investimento_rs": invest, "chi_evitado_ano": float(cand.chi_evitavel.sum()),
            "dec_min_evitado_ano": valor.dec_minutos(float(cand.chi_evitavel.sum()), uc_total),
            "rs_ano_social": rs_soc_ano, "vpl_social": valor.vpl(rs_soc_ano, invest, taxa, anos_vida),
            "densidade_mediana_religadores_100km": float(dens_med),
            "criterio": "rede_mt_km >= 30 e densidade de religadores abaixo da mediana"}
v = json.loads((OUT / "valor.json").read_text())
v["carteira_subestacoes"] = carteira
(OUT / "valor.json").write_text(json.dumps(v, indent=2, ensure_ascii=False))
log.info("carteira: %s", carteira)

# ------------------------------------------------------------------ registro da regra de decisão
if dec is not None:
    fonte = {} if MEDIDO else {n: hashlib.sha256((cfg.regra.fonte_mt / n).read_bytes()).hexdigest()
                               for n in ("efeitos_did.csv", "efeitos_por_unidade.csv", "valor.json")}
    reg = {"origem_efeito": ORIGEM, **dec.registro(), "coortes": {int(k): int(v) for k, v in
           ev.ano_evento.value_counts().sort_index().items()},
           "efeito_de_mt_lido_de": None if MEDIDO else {"pasta": str(cfg.regra.fonte_mt.name), "sha256": fonte}}
    (OUT / "regra_decisao.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False))
    log.info("regra_decisao: %s", reg["origem_efeito"])
