"""Figuras do README a partir dos artefatos em reports/."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from autoimpact.config import ROOT

R = ROOT / "reports"
F = R / "figures"
F.mkdir(parents=True, exist_ok=True)
AZUL, LARANJA, CINZA, VERDE = "#2a78d6", "#eb6834", "#8a8a8a", "#1baf7a"
plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e5e5e5", "font.size": 10,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})


def br(x, casas=0):
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# 1. Event study
es = pd.read_csv(R / "event_study.csv")
nomes = {"chi": "CHI (consumidor-hora interrompido)", "duracao_h": "Duração média por consumidor",
         "n_falhas": "Nº de interrupções sustentadas", "ci_por_falha": "Consumidores por interrupção"}
fig, axs = plt.subplots(1, 4, figsize=(14, 3.6), sharey=True)
for ax, (d, nome) in zip(axs, nomes.items()):
    e = es[es.desfecho == d].sort_values("rel")
    cor = AZUL if d in ("chi", "duracao_h") else CINZA
    ax.fill_between(e.rel, e.lo_pct, e.hi_pct, color=cor, alpha=0.18, lw=0)
    ax.plot(e.rel, e.efeito_pct, "o-", color=cor, lw=2)
    ax.axhline(0, color="#555", lw=0.8)
    ax.axvline(-0.5, color="#555", lw=0.8, ls=":")
    ax.set_title(nome, fontsize=10, loc="left", fontweight="bold")
    ax.set_xlabel("anos desde a instalação")
    ax.set_xticks(e.rel)
axs[0].set_ylabel("efeito (%) vs. alimentadores sem religador novo")
fig.suptitle("CHI: sem tendência antes da instalação e queda depois. A duração já caía antes (ver limitações). IC 95%",
             x=0.01, ha="left", fontweight="bold")
fig.tight_layout()
fig.savefig(F / "01_event_study.png", bbox_inches="tight")
plt.close(fig)

# 2. Decomposição dos canais (DiD)
did = pd.read_csv(R / "efeitos_did.csv").set_index("desfecho")
ordem = ["chi", "n_falhas", "ci_por_falha", "duracao_h"]
rot = ["CHI total", "Interrupções\nsustentadas", "Consumidores\npor interrupção", "Duração média\npor consumidor"]
fig, ax = plt.subplots(figsize=(7.5, 3.6))
y = did.loc[ordem]
cores = [AZUL if (hi < 0) else CINZA for hi in y.ic95_hi_pct]
ax.bar(rot, y.efeito_pct, color=cores, width=0.55)
ax.errorbar(rot, y.efeito_pct, yerr=[y.efeito_pct - y.ic95_lo_pct, y.ic95_hi_pct - y.efeito_pct], fmt="none",
            ecolor="#333", capsize=4, lw=1)
for i, v in enumerate(y.efeito_pct):
    ax.text(i, 1.5 if v < 0 else v + 1.5, f"{br(v, 1)}%", ha="center", fontsize=9)
ax.axhline(0, color="#555", lw=0.8)
ax.set_ylabel("efeito médio pós-instalação (%)")
ax.set_title("O ganho vem da duração, não de menos falhas\n(azul: IC 95% inteiro abaixo de zero)",
             loc="left", fontweight="bold", fontsize=10)
fig.tight_layout()
fig.savefig(F / "02_canais.png", bbox_inches="tight")
plt.close(fig)

# 3. Robustez
rob = pd.read_csv(R / "robustez.csv").iloc[::-1]
fig, ax = plt.subplots(figsize=(7.5, 3.4))
cores = [LARANJA if "placebo" in t else AZUL for t in rob.teste]
ax.errorbar(rob.efeito_pct, range(len(rob)), xerr=[rob.efeito_pct - rob.ic95_lo_pct, rob.ic95_hi_pct - rob.efeito_pct],
            fmt="none", ecolor="#555", capsize=3, lw=1)
ax.scatter(rob.efeito_pct, range(len(rob)), color=cores, zorder=3, s=40)
ax.set_yticks(range(len(rob)), rob.teste)
ax.axvline(0, color="#555", lw=0.8)
ax.set_xlabel("efeito sobre o CHI (%), IC 95%")
ax.set_title("Robustez: o efeito se mantém; o placebo não acusa nada", loc="left", fontweight="bold", fontsize=10)
fig.tight_layout()
fig.savefig(F / "03_robustez.png", bbox_inches="tight")
plt.close(fig)

# 4. Subestações
se = pd.read_csv(R / "subestacoes.csv").head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5))
nome = se.subestacao_nome.fillna(se.subestacao.astype(str)).str.replace("SE ", "").str.replace(r" \d+.*KV", "", regex=True)
ax.barh(nome, se.dec_min, color="#c9d9ee", label="contribuição ao DEC (min/ano, 2023-2025)")
ax.barh(nome, se.dec_min_evitavel, color=AZUL, label="evitável com +2 religadores nos alimentadores pouco protegidos")
for i, (v, n) in enumerate(zip(se.dec_min, se.alimentadores)):
    ax.text(v + 0.4, i, f"{br(v, 1)} min · {n} alim.", va="center", fontsize=8)
ax.set_xlabel("minutos de DEC da EMT por ano")
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.12), ncol=1, fontsize=8, frameon=False)
ax.set_title("As 15 subestações que mais pesam no DEC", loc="left", fontweight="bold", fontsize=10)
ax.grid(axis="y", visible=False)
fig.tight_layout()
fig.savefig(F / "04_subestacoes.png", bbox_inches="tight")
plt.close(fig)

# 5. Valor da disponibilidade
v = json.loads((R / "valor.json").read_text())
ind = v["indisponibilidade_1pp"]
disp = np.arange(80, 100.5, 0.5)
fig, ax = plt.subplots(figsize=(7.5, 3.6))
for k, cor, rotulo in [("canal_duracao_inteiro", AZUL, "todo o canal da duração depende de comunicação"),
                       ("metade_do_canal_duracao", VERDE, "metade do canal da duração depende")]:
    ax.plot(disp, (100 - disp) * ind[k]["dec_min_por_pp"], color=cor, lw=2, label=rotulo)
ax.set_xlabel("disponibilidade da telemetria/telecomando dos religadores (%)")
ax.set_ylabel("DEC perdido (min/ano)")
ax.invert_xaxis()
ax.legend(frameon=False, fontsize=8)
ax.set_title(f"Cada ponto de indisponibilidade custa {br(ind['metade_do_canal_duracao']['dec_min_por_pp'], 1)} a "
             f"{br(ind['canal_duracao_inteiro']['dec_min_por_pp'], 1)} min de DEC por ano",
             loc="left", fontweight="bold", fontsize=10)
fig.tight_layout()
fig.savefig(F / "05_disponibilidade.png", bbox_inches="tight")
plt.close(fig)

# 6. Quem interrompe (2026)
el = pd.read_csv(R / "elemento_2026.csv")
el = el[el.frac_chi >= 0.01].iloc[::-1]
fig, ax = plt.subplots(figsize=(7.5, 3))
cmap = {"DISJUNTOR": LARANJA, "RELIGADOR": AZUL, "CHAVE FUSIVEL": CINZA}
ax.barh(el.elemento.str.title(), 100 * el.frac_chi, color=[cmap.get(e, "#bbb") for e in el.elemento])
for i, (f, u, d) in enumerate(zip(el.frac_chi, el.uc_media, el.duracao_media_h)):
    ax.text(100 * f + 0.5, i, f"{br(100 * f, 0)}% · {br(u, 0)} UC/evento · {br(d, 1)} h", va="center", fontsize=8)
ax.set_xlabel("% do CHI de falhas MT, jan-jul/2026")
ax.set_title("Quem abriu o circuito: o disjuntor da subestação responde por ~1/4 do CHI", loc="left",
             fontweight="bold", fontsize=10)
ax.set_xlim(0, 60)
ax.grid(axis="y", visible=False)
fig.tight_layout()
fig.savefig(F / "06_elemento_2026.png", bbox_inches="tight")
plt.close(fig)
print(sorted(p.name for p in F.glob("*.png")))
