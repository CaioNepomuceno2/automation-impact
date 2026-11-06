# Pré-registro: estimador robusto à adoção escalonada

Escrito e commitado **antes** de rodar o estimador novo nos dados reais. Fixa o que será estimado, como, e
o que será dito se o resultado discordar do que o README já publica. Mudanças depois deste commit entram
na seção "Registro de desvios", no fim, com data e motivo.

## 1. Pergunta

O resultado principal (CHI −16,6%) vem do DiD empilhado por coorte (`modelo.empilhar` + `did_pilha`, Poisson
com efeitos fixos, controles nunca tratados). O efeito por religador, que sustenta a conta da indisponibilidade
(R$ 134 a 268 mil/ano por p.p. dos 4.000 religadores), vem do TWFE contínuo
(`modelo.efeito`, efeitos fixos de alimentador e ano). Outros repositórios do portfólio citam esses números
(≈ 4.600 consumidores-hora/ano por religador, R$ 5,94 por consumidor-hora, R$ 50 por p.p. de indisponibilidade).

A adoção é escalonada (coortes de 2020 a 2025) e o efeito cresce com o tempo. Nesse cenário o TWFE comum
pode usar alimentadores já tratados como controle de tratados mais tarde e errar o efeito. O empilhado evita
esse problema por desenho. Um segundo estimador, de família diferente, diz se o número principal e o
efeito por religador aguentam.

**Este trabalho não substitui nenhum número.** Os estimadores existentes continuam publicados. O novo entra ao lado.

## 2. Estimador novo: Callaway & Sant'Anna (2021), controles nunca tratados, escala multiplicativa

Implementação própria em `src/autoimpact/did_escalonado.py`, sem dependência nova.

**Por que própria e não pacote.** `pyfixest` (0.60) tem `event_study(estimator="saturated")` (Sun & Abraham) e
`did2s`; `csdid` e `differences` implementam o Callaway & Sant'Anna. Todos estimam o efeito em **escala
linear** (níveis de CHI). O resultado do projeto é em **%** (Poisson, tendências paralelas multiplicativas), e
alimentadores tratados são maiores e mais críticos que os controles: comparar um efeito em níveis com um em
% misturaria a diferença de escala com a diferença de método. A implementação própria usa a mesma escala do
PPML, cabe em ~150 linhas e é testada (seção 8). Não há versão de pacote a fixar no `pyproject.toml`.

**Definição.** Para a coorte *g* (primeiro ano de resultado com o religador novo, `ano_evento` de
`painel.eventos_tratamento(p, minimo=2)`), o período-base é *g−1*. Para cada ano *t* com −3 ≤ *t−g* ≤ +2,
*t* ≠ *g−1*:

`ATT(g,t) = log[ (N_g,t / D_g,t) / (N_g,g−1 / D_g,g−1) ] − log[ (N_C,t / D_C,t) / (N_C,g−1 / D_C,g−1) ]`

* *N* e *D* são somas, no grupo e no ano, do numerador e do denominador do desfecho. CHI: *N* = CHI, *D* = 1.
  Duração: *N* = CHI, *D* = consumidores interrompidos (CI), o mesmo `offset` do PPML. Nº de falhas: *N* =
  falhas, *D* = 1. Consumidores por falha: *N* = CI, *D* = falhas.
* Grupo *g*: alimentadores da coorte. Grupo *C*: controles nunca tratados (`painel.nunca_tratados`, 209 no
  README). Só entram alimentadores observados **em *t* e em *g−1*** (o painel não é balanceado).
* Sem covariáveis. Igual ao DiD empilhado: mesma lista de tratados, mesmos controles, mesma janela (−3 a +2).
* Célula (*g*,*t*) com menos de 3 alimentadores tratados observados é descartada e listada.
* Em um 2×2 (uma coorte, um ano) este estimador é idêntico ao coeficiente do Poisson com efeitos fixos de
  alimentador e ano. Isso é um teste automático.

**Agregação** (tempo relativo *e* = *t−g*):

* `θ(e)`: média de `ATT(g,g+e)` entre as coortes observáveis em *e*, ponderada pelo nº de tratados na célula.
  Event study: *e* de −3 a +2, com *e* = −1 igual a zero por construção.
* **`θ_pós` (resumo principal)**: média simples de `θ(0)`, `θ(1)` e `θ(2)` (um peso por tempo relativo).
* Secundários: `θ_simples` (média das células pós ponderada pelo nº de tratados) e `θ_balanceado` (só coortes
  com *e* = 0, 1 e 2 observáveis). Servem para separar efeito de ponderação de efeito de método.
* Tudo na escala do log; o efeito em % é `100·(exp(θ) − 1)`.

**Inferência.** Bootstrap por alimentador (cada alimentador é um cluster), estratificado por coorte e pelo
grupo de controle, com reposição dentro de cada estrato. **B = 2000, semente 20261106** (`numpy.random.default_rng`).
Os pesos de agregação são recalculados em cada réplica. IC 95% pelos percentis 2,5 e 97,5 do log do efeito.
Erro-padrão = desvio-padrão das réplicas. Os controles são reamostrados uma vez por réplica e usados por todas as
coortes, o que preserva a covariância entre elas.

## 3. Desfechos

* Principal: **CHI** (`chi`).
* **Duração** média por consumidor (`duracao_h` = CHI/CI).
* Canais, só descritivos: nº de falhas e consumidores por falha.

## 4. Comparadores, na **mesma versão dos dados**

Tudo abaixo é recalculado pelo script novo com o painel regenerado (seção 7), e não lido dos CSVs commitados.

1. DiD empilhado (`modelo.empilhar`, `did_pilha`, `event_study`): resumo e event study.
2. TWFE binário simples (um indicador "pós-evento", efeitos fixos de alimentador e ano, tratados e controles,
   sem empilhar), pelo mesmo `modelo.efeito`. É o estimador que a simulação mostra errar. Só diagnóstico.
3. TWFE contínuo por religador (`reports/efeitos_por_unidade.csv`), que alimenta a conta da indisponibilidade.

## 5. Regras de divergência (decididas agora)

O limite é **5 pontos percentuais** na escala do efeito em %. Ele é de ordem de um erro-padrão do empilhado
(IC de −24,8% a −7,5% para o CHI, ou seja, erro-padrão perto de 4,4 p.p.).

* **D1, CHI, resumo.** Dispara se `|θ_pós(CS) − efeito empilhado| > 5 p.p.`, ou se o IC do CS não contém o ponto
  do empilhado (ou o contrário), ou se só um dos dois ICs contém zero.
* **D2, duração, resumo.** Mesma regra.
* **D3, por tempo relativo.** Para *e* = 0, 1, 2, `|θ(e)(CS) − coeficiente do empilhado| > 5 p.p.` em qualquer um
  vai para o README como ressalva (a diferença de ponderação entre os dois resumos fica visível aqui).
* **D4, TWFE binário.** `|TWFE binário − θ_pós(CS)| > 5 p.p.` é descrito como "o TWFE simples diverge", só diagnóstico.
* **D5, valor por religador.** CHI evitado por religador com o `θ_pós(CS)`, pela mesma fórmula de
  `02_estimar.py` (CHI pré-tratamento de cada evento × (1 − e^θ), dividido pelos religadores adicionados).
  Dispara se diferir mais de 20% do valor regenerado do empilhado, ou se o IC do CS não contiver esse valor.
* **D6, custo do p.p. de indisponibilidade (diagnóstico secundário).** O efeito por religador equivalente ao
  CS é `θ_pós / ganho médio` (4,25), **sob a hipótese forte de efeito log-linear na dose**. A fração via
  duração do CS é `clip(θ_pós(duração)/θ_pós(CHI), 0, 1)`. O custo alternativo por p.p. é o valor regenerado
  vezes `(e^(−b_CS) − 1)/(e^(−b_TWFE) − 1)` vezes `fração_CS/fração_TWFE`, o que reproduz a conta de
  `02_estimar.py` porque ela é linear nesses dois fatores. Dispara se `b_CS` cair fora do IC 95% do TWFE
  contínuo, ou se a faixa alternativa (metade e todo o canal) não se sobrepuser à faixa publicada.

**O que acontece se disparar.** Os números do cabeçalho do README **não mudam**. Entram: (i) uma subseção nova
com a tabela completa e a leitura em português simples; (ii) uma ressalva na seção Limitações; (iii) se D1 ou D2
dispararem, uma linha logo abaixo da tabela "Resultados em uma tela". Os outros repositórios do portfólio citam
≈ 4.600 consumidores-hora/ano por religador, R$ 5,94/CH e R$ 50 por p.p. Esses valores não são editados aqui, e se
D5 ou D6 dispararem, isso é dito de forma explícita e fica para decisão do mantenedor.

Se nada disparar, a subseção diz "concordante" e mostra os números.

## 6. Sensibilidade à pré-tendência (duração, e CHI por completeza)

O event study da duração tem o ano −3 acima do ano −1. O ajuste é uma **extrapolação linear da tendência anterior**:

* Com `θ(−1) = 0`, o declive é `δ = (−2·θ(−3) − 1·θ(−2)) / 5` (mínimos quadrados sobre *e* = −3, −2, −1,
  passando por zero em −1).
* Efeito ajustado: `θ_aj(e; λ) = θ(e) − λ·δ·(e+1)`, para *e* = 0, 1, 2; resumo = média dos três.
  `λ = 1` é o ajuste principal (a tendência continua inteira). Grade de λ de 0 a 1,5 em passos de 0,05.
* A incerteza vem do mesmo bootstrap: o declive é reestimado em cada réplica.
* Relatado: efeito ajustado e IC em λ = 0, 0,25, 0,5, 0,75, 1; e o **λ de equilíbrio**: o menor λ em que a
  estimativa pontual chega a zero, e o menor λ em que o IC passa a conter zero.
* Robustez: o mesmo cálculo só com as coortes que têm os três anos pré observáveis (*g* ≥ 2022), para
  afastar mudança de composição entre *e* = −3 e *e* = −1. E o ajuste aplicado aos coeficientes pontuais do
  event study empilhado (sem IC).
* Não uso HonestDiD (Rambachan & Roth): não há implementação em Python que eu possa verificar. O λ de equilíbrio
  responde ao mesmo tipo de pergunta ("quanto da tendência anterior precisaria continuar?") com um modelo mais
  simples, e deve ser lido como tal.

**O que será escrito no README, decidido agora:**

* Se o IC do efeito ajustado na duração (λ = 1) **contém zero**: "A queda de 20% na duração não se distingue de
  zero depois de descontar a tendência linear anterior (ajustado: X%, IC 95% de Y a Z). O canal da duração, e
  por isso a faixa de 0,7 a 1,4 min de DEC por p.p. de indisponibilidade (que usa a fração do efeito que passa
  pela duração), não é robusto a essa tendência. Os números do cabeçalho não mudaram, mas ficam sinalizados."
* Se o IC **exclui zero**: "A queda na duração sobrevive ao ajuste: X% (IC de Y a Z), mais fraca que os −20%."
* Se o ponto ajustado for zero ou positivo, isso é dito sem suavizar.
* A frase da limitação ("a duração já caía antes…") é atualizada com esses números e com o λ de equilíbrio.
* O CHI recebe o mesmo ajuste. Se o resultado do CHI também não sobreviver, isso é dito com o mesmo destaque.

## 7. Linha de base e versão dos dados

Antes de qualquer número novo, o pipeline completo (`distribution-asset-risk` e depois os scripts 01 a 04 daqui) roda
com o código **inalterado**, em clones separados, e os `reports/` regenerados são comparados com os commitados.
Os dados abertos da ANEEL são revisados com o tempo, então a diferença por revisão de dados é reportada à parte do
efeito do método.

Critério decidido agora:

* **Reproduz:** mesmo nº de eventos (116) e de controles (209); efeitos do CHI e da duração dentro de 1 p.p.;
  CHI evitado por religador dentro de 5%.
* **Reproduz com revisão de dados:** nº de eventos e controles dentro de 5%; efeitos dentro de 3 p.p.; CHI evitado
  dentro de 15%. Segue, com a tabela das diferenças, e toda comparação do método novo usa a versão regenerada.
* **Não reproduz:** qualquer coisa fora disso. Para e reporta, sem publicar mistura.

## 8. Testes

* **Fumaça do núcleo:** painel sintético minúsculo, determinístico, sem rede, poucos segundos.
* **Equivalência 2×2:** uma coorte, um ano: o estimador é igual ao `fepois` com efeitos fixos de alimentador e ano.
* **Simulação do problema:** coortes com efeitos heterogêneos que crescem com o tempo e poucos controles. O TWFE
  binário erra por margem grande; o CS recupera o efeito verdadeiro. O DiD empilhado também é calculado na
  simulação, e o resultado é relatado como ele sair (se também recuperar, o CS é uma conferência do empilhado, e
  não uma correção dele).
* **Ajuste de pré-tendência:** painel com tendência diferencial linear e efeito nulo: o efeito bruto é diferente de zero
  e o ajustado volta a zero.

## 9. Saídas (arquivos novos; nenhum arquivo existente é sobrescrito)

`reports/did_escalonado_att_gt.csv` (todas as células), `did_escalonado_eventstudy.csv` (CS e empilhado lado a lado),
`did_escalonado_resumo.csv` (resumos e comparadores), `did_escalonado_tendencia.csv` (sensibilidade),
`did_escalonado_valor.json` (D5, D6, metadados, semente, versões) e `figures/07_did_escalonado.png`.
Produzidos por `scripts/05_did_escalonado.py`.

## Registro de desvios

Registrados depois de rodar, em 06/11/2026. Nenhum muda uma regra de relato.

1. **Linha de base.** O critério da seção 7 foi aplicado ao CHI e à duração (mesmo nº de eventos e de controles,
   116 e 209; efeitos idênticos até 1e-7; CHI evitado por religador idêntico). Os arquivos de continuidade da ANEEL
   republicados em 05/11/2026 trazem cada linha duplicada (ver `docs/dados.md`), o que dobra o R$/CHI de compensação do
   projeto irmão. O CHI e os efeitos não dependem disso, e `valor.json` só reproduz inteiro (até 3e-9) com as
   duplicatas removidas. A comparação do estimador novo usa o `valor.json` regenerado com as duplicatas removidas.
2. **Pacotes.** A seção 2 diz que `csdid`, `differences` e `pyfixest` estimam em escala linear. Só verifiquei que o
   `pyfixest` 0.60 expõe `event_study`, `did2s`, `lpdid` e `SaturatedEventStudy`. Não instalei `csdid` nem `differences`:
   a afirmação vem da definição aditiva do Callaway & Sant'Anna clássico, e não de um teste meu.
3. **D3** foi aplicada ao CHI e à duração (o texto não dizia quais desfechos).
4. **Dependência.** `geopandas` passou a constar no `pyproject.toml`: `pyogrio.read_dataframe` exige, e a instalação do
   zero falhava no script 01 sem ele.
5. **p-valor** da tabela de resumo: bootstrap para o CS e assintótico (erro-padrão agrupado) para os demais; a coluna
   `inferencia` diz qual.
6. **Reprodutibilidade.** Reexecutar o script 05 dá resultados idênticos para o CS, o event study e a tendência
   (bit a bit). As linhas do PPML (empilhado, TWFE) variam na casa de 1e-13 entre execuções.
