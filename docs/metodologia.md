# Metodologia

Como o projeto mede o efeito de religadores sobre a continuidade, como esse efeito vira minutos de DEC e R$, e
como ler cada resultado. As decisões de tratamento dos dados (camadas da BDGD, regras de evento, ruído cadastral)
estão em [`dados.md`](dados.md); aqui fica o raciocínio e as fórmulas.

## 1. Perguntas

1. **Quanto um religador reduz a continuidade observada?** Efeito médio sobre o CHI, o nº de falhas, os
   consumidores por falha e a duração, em alimentadores que ganharam religadores.
2. **Por onde o efeito passa?** Pelo religamento automático (menos interrupções sustentadas, canal local) ou pelo
   restabelecimento mais rápido (canal que depende de supervisão).
3. **Quanto vale?** CHI evitado, minutos de DEC e R$ por religador, e o custo de cada ponto percentual de
   indisponibilidade da telemetria.
4. **Onde?** Quais subestações e alimentadores concentram o risco e onde mais religadores rendem mais.

## 2. Por que não basta comparar alimentadores com e sem religador

Alimentadores com muitos religadores são, em geral, longos, rurais e críticos: foi por isso que receberam os
equipamentos. Comparar diretamente "com" e "sem" mistura o efeito do religador com o motivo da instalação e pode
até mostrar que religadores "pioram" a continuidade. O projeto usa a variação **no tempo dentro do mesmo
alimentador** (antes e depois de ganhar religadores) e a compara com a variação no mesmo período em alimentadores
que não ganharam. É a lógica de diferenças em diferenças (DiD).

## 3. Dados e painel

| Elemento | Fonte | Detalhe |
|---|---|---|
| Religadores, disjuntores, telecomando por alimentador | BDGD, camada `UNSEMT` | 8 snapshots de 31/12 (2018-2025) |
| Subestação do alimentador, nome e potência da SE | BDGD, `CTMT`, `SUB`, `UNTRAT` | idem |
| Falhas MT, CHI, CI, CHI regulatório | Interrupções ANEEL, via `distribution-asset-risk` | 2019-2025 |
| Tempos de atendimento | Ocorrências emergenciais ANEEL | 2025 |
| R$/CHI | `distribution-asset-risk` | compensações 2022-2025 e custo da energia não suprida |

O painel tem uma linha por alimentador × ano de resultado *y*, com os equipamentos do cadastro de 31/12 de *y-1*
(o religador cadastrado em dez/2022 conta como presente em 2023 inteiro). São 4.311 linhas e 706 alimentadores.

## 4. Pipeline

| Etapa | Script | Funções | Saída |
|---|---|---|---|
| Equipamentos por alimentador e snapshot | `scripts/01_build_equipamentos.py` | `bdgd.equipamentos_por_alimentador`, `bdgd.subestacoes` | `data/interim/` |
| Painel, eventos e controles | `scripts/02_estimar.py` | `painel.montar`, `eventos_tratamento`, `nunca_tratados`, `estaveis` | `reports/eventos_tratamento.csv` |
| DiD empilhado, event study, robustez | `scripts/02_estimar.py` | `modelo.empilhar`, `did_pilha`, `event_study` | `reports/efeitos_did.csv`, `event_study.csv`, `robustez.csv` |
| Efeito por unidade (canais) | `scripts/02_estimar.py` | `modelo.efeito` | `reports/efeitos_por_unidade.csv` |
| Valoração e subestações | `scripts/02_estimar.py` | `valor.*` | `reports/valor.json`, `subestacoes.csv`, `comparacao_premissas.csv` |
| Conferência com estimador robusto à adoção escalonada | `scripts/05_did_escalonado.py` | `did_escalonado.*` | `reports/did_escalonado_*.csv`, `did_escalonado_valor.json` |
| Tempo de atendimento | `scripts/03_atendimento.py` | | `reports/atendimento_2025.csv` |
| Figuras | `scripts/04_figuras.py` | | `reports/figures/` |

## 5. Definições e fórmulas

**CHI** (consumidor-hora interrompido) = Σ UC afetadas × duração (h). **CI** = Σ UC afetadas.
**Decomposição:** `CHI = nº de falhas × (CI / nº de falhas) × (CHI / CI)`, ou seja, frequência × consumidores por
falha × duração média por consumidor. Cada fator é estimado separadamente; a duração e os consumidores por falha
entram como o numerador com o denominador em *offset*.

**Estimador:** Poisson com efeitos fixos (PPML, `pyfixest.fepois`), erros-padrão agrupados por alimentador.
É o estimador padrão para somas não negativas com muitos zeros e cauda longa, como o CHI. Um coeficiente *b* se lê
como variação de `e^b − 1` no desfecho esperado.

**DiD empilhado** (`modelo.empilhar` + `did_pilha`): para cada ano de evento *g*, junta os alimentadores tratados em
*g* e os controles, na janela [g−3, g+2], com efeitos fixos de alimentador × coorte e ano × coorte:

`E[CHI_it] = exp(α_i,g + λ_t,g + b · pós_it)`

O empilhamento evita o viés do DiD com tratamento escalonado, que usaria alimentadores tratados cedo como controle
dos tratados tarde.

**Event study** (`modelo.event_study`): o mesmo modelo com um coeficiente por ano relativo ao evento (−3 a +2),
com o ano −1 como referência. Coeficientes próximos de zero antes do evento sustentam a hipótese de tendências
paralelas; o padrão depois do evento mostra como o efeito evolui.

**Efeito por unidade** (`modelo.efeito`, TWFE contínuo): `E[y_it] = exp(α_i + λ_t + b · n_religadores_it + controles)`,
com controles de log da extensão e log das UC. Usa toda a variação da frota e separa os canais.

**CHI evitado por religador** (`valor.chi_evitado`): `CHI_base × (1 − e^b)`, com o CHI médio pré-tratamento de cada
tratado, somado e dividido pelos 493 religadores adicionados nos eventos.

**DEC** (`valor.dec_minutos`): `CHI / UC totais × 60`, com 2.126.558 UC.

**VPL** (`valor.vpl`): `benefício anual × fator de anuidade(8%, 20 anos) − custo`, com custo ilustrativo de
R$ 160 mil por religador.

**Custo da indisponibilidade** (`valor.custo_indisponibilidade`): para cada alimentador do cadastro de 2025,
`CHI médio 2023-2025 × (e^(−b) − 1)` é o CHI que cada religador evita. Multiplicado pelo nº de religadores, pela
fração do benefício que depende de comunicação e por 1%, dá o CHI perdido por 1 p.p. de indisponibilidade.

## 6. Desenho de validação

| Teste | O que verifica | Resultado |
|---|---|---|
| Tendências anteriores (event study) | tratados e controles andavam juntos antes? | CHI: −3 = +1,8% e −2 = −4,3%, ambos não significativos |
| Placebo (tratamento 2 anos antes) | o método "acha" efeito onde não há? | +9,2%, não significativo |
| Só CHI regulatório | o efeito não vem de dias expurgados? | −13,9% |
| Ganho ≥ 3 religadores | mais equipamentos, mais efeito? | −19,4% |
| Extensão estável (±25%) | divisões de alimentador explicam o efeito? | −20,8%, mais forte |
| Janela curta (−2 a +1) | depende da janela? | −10,6%, menor porque o efeito cresce com o tempo |
| Ganho ≥ 1 religador | um religador sozinho tem efeito detectável? | −4,1%, não significativo |

Na duração, o ano −3 está 19% acima do ano −1: a duração já caía antes nos tratados, e a queda de 20% depois do
evento está superestimada. O CHI, resultado principal, não tem esse problema.

## 7. Premissas

| Premissa | Valor | Fonte | Onde pesa |
|---|---|---|---|
| R$/CHI de compensação | R$ 1,93 por CHI regulatório, que é 76% do CHI (ponderado nos tratados) | compensações ANEEL, via projeto irmão | valor na visão de caixa |
| R$/CHI social | R$ 5,94 por CHI total | idem + energia não suprida a R$ 7.000/MWh (cenário) | valor na visão social |
| Custo do religador | R$ 160 mil | ilustrativo | VPL e payback |
| Vida útil e taxa | 20 anos, 8% a.a. | cenário | VPL |
| Fração do benefício que depende de comunicação | 57% (todo o canal da duração) ou 29% (metade) | decomposição dos canais + premissa | custo da indisponibilidade |

A fração dependente de comunicação é a premissa mais importante para o uso operacional. Os dados separam o canal
da frequência (local) do canal da duração, mas não provam que toda a redução de duração vem da supervisão. Por isso
o custo da indisponibilidade aparece como faixa (0,7 a 1,4 min de DEC por p.p.) e o roteiro de adoção do README
propõe medi-la com os dados de disponibilidade do SCADA.

## 8. Como interpretar cada resultado

* **−16,6% no CHI:** efeito médio, sobre o CHI anual do alimentador, de ganhar um pacote de religadores (2 a 5),
  para alimentadores parecidos com os que receberam. Não é a eficácia de cada religador isolado.
* **−30% dois anos depois:** o efeito cresce com o tempo, provavelmente com o ajuste da coordenação da proteção e
  da operação. Planos que avaliam a obra só no primeiro ano subestimam o retorno.
* **4.600 CHI/ano e R$ 27 mil/ano por religador:** média dos pacotes estudados. Em alimentadores com CHI menor, o
  valor é menor.
* **VPL positivo na visão social e negativo só com compensações:** a compensação regulatória sozinha não paga o
  religador; o valor está na continuidade entregue ao cliente.
* **0,7 a 1,4 min de DEC por p.p. de indisponibilidade:** ordem de grandeza para priorizar a comunicação; deve ser
  substituída por um número medido quando houver dados de disponibilidade por equipamento.
* **Telecomando sem efeito:** a premissa de catálogo (−21%) não tem apoio no cadastro público, cujo flag de
  telecomando é instável. Não é evidência de que a automação não funcione.

## 9. Conferência com um estimador robusto à adoção escalonada

Protocolo fixado antes dos resultados em [`preregistro_did_escalonado.md`](preregistro_did_escalonado.md); código em
`autoimpact.did_escalonado` e `scripts/05_did_escalonado.py`. Resultados e leitura no README.

**Por que.** O resultado principal vem do DiD empilhado, que já evita comparar tratados tardios com tratados cedo. O
efeito por religador da conta da indisponibilidade vem do TWFE contínuo, que não tem essa proteção. Um estimador de
outra família diz se o resultado principal aguenta.

**Estimador (Callaway & Sant'Anna, controles nunca tratados, escala multiplicativa).** Para a coorte *g* e o ano *t*,
com base em *g−1*:
`ATT(g,t) = log[(N_g,t / D_g,t) / (N_g,g−1 / D_g,g−1)] − log[(N_C,t / D_C,t) / (N_C,g−1 / D_C,g−1)]`,
com *N* e *D* somas do numerador e do denominador do desfecho (CHI: *D* = 1; duração: *N* = CHI, *D* = CI). Em um 2×2
é igual ao coeficiente do PPML com efeitos fixos (teste automático). Agregação: `θ(e)` por tempo relativo (ponderada
pelo nº de tratados), resumo pós = média de `θ(0)`, `θ(1)`, `θ(2)`. Mesma janela (−3 a +2), mesmos tratados e controles
do empilhado.

**Inferência.** Bootstrap por alimentador, estratificado por coorte e controles, 2.000 réplicas, semente 20261106,
com os mesmos sorteios para todos os desfechos.

**Pré-tendência.** Declive `δ = (−2·θ(−3) − θ(−2)) / 5` (mínimos quadrados em *e* = −3, −2, −1, zero em −1);
efeito ajustado `θ(e) − λ·δ·(e+1)`, com λ de 0 a 1,5. O declive é reestimado em cada réplica. Não é o HonestDiD de
Rambachan & Roth: é uma extrapolação linear com a incerteza do declive, e o λ em que o IC passa a conter zero responde a
uma pergunta parecida ("quanto da tendência anterior precisa continuar?").

**Regras de divergência** (limite de 5 p.p., IC cruzado, zero em só um IC; CHI evitado por religador com 20%) e o que vai
para o README em cada caso estão no pré-registro. Os números do cabeçalho do README não são alterados por esta conferência.

