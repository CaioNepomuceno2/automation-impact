# Decisões de dados

## Fontes

| Fonte | Uso | Período |
|---|---|---|
| ANEEL, BDGD (PRODIST Módulo 10), camada `UNSEMT` | religadores (`TIP_UNID` 32), disjuntores (29/30/53), seccionalizadores, chaves fusíveis e flag de telecomando (`TLCD`) por circuito | snapshots de 31/12 de 2018 a 2025 |
| ANEEL, BDGD, camadas `CTMT`, `SUB` e `UNTRAT` | nome operacional do circuito, subestação, nome e potência da SE | idem |
| ANEEL, Interrupções nas Redes de Distribuição (via `distribution-asset-risk`) | falhas de MT internas não programadas por alimentador e ano: nº, CHI, CI, CHI regulatório | 2019 a 2025 (2026 parcial) |
| ANEEL, Ocorrências Emergenciais | tempos de preparo, deslocamento e execução | 2025 |
| `distribution-asset-risk` | atributos de rede por alimentador (extensão, UC, ruralidade) e R$/CHI (compensação e visão social) | idem |

## Painel

* Uma linha por **alimentador × ano de resultado y** (2019 a 2025), com equipamentos e atributos do cadastro de
  **31/12 de y-1** e continuidade observada em y. São 4.311 linhas e 706 alimentadores.
* Alimentadores sem falha no ano entram com zero.
* Desfechos derivados:
  * `ci_por_falha` = CI / nº de falhas;
  * `duracao_h` = CHI / CI, a duração média ponderada por consumidor.
  * Esses dois são estimados como o numerador com o denominador em *offset* no PPML.

## Tratamento e controles

* **Evento:** primeiro ano em que o alimentador ganha **2 ou mais religadores** de um snapshot para o seguinte e
  os mantém em todos os snapshots posteriores (tolerância de meio equipamento). Se a primeira grande variação
  for uma queda de 2 ou mais, o alimentador não entra como tratado.
* **Controles:** alimentadores presentes em todos os anos cuja quantidade de religadores varia no máximo 1 em
  todo o período.
* **DiD empilhado:** para cada ano de evento g, tratados em g e controles na janela [g−3, g+2], com efeitos fixos
  de alimentador×coorte e ano×coorte. Isso evita o viés do TWFE com tratamento escalonado, que compara tratados
  tardios com tratados cedo.
* **TWFE contínuo** (efeito por unidade): Poisson com efeitos fixos de alimentador e ano e controles de log da
  extensão da rede e log das UC. Usa toda a variação da frota, inclusive ganhos de 1 religador.

## Valoração

* **Por religador (eventos):** CHI anual médio pré-tratamento de cada tratado × (1 − e^b) do DiD, somado e
  dividido pelo total de religadores adicionados.
* **Frota (disponibilidade):** para cada alimentador do cadastro de 2025, o CHI médio de 2023-2025 × (e^(−b) − 1)
  do TWFE é o CHI que cada religador dele evita. Esse valor é multiplicado pelo nº de religadores, pela fração
  dependente de comunicação e por 1%.
* **DEC:** CHI / UC totais (2.126.558 UC no cadastro de dez/2024) × 60.
* **R$/CHI:** visão de compensação (R$/CHI regulatório × fração regulatória do CHI) e visão social
  (compensação + energia não suprida a R$ 7.000/MWh), ambas do `distribution-asset-risk`, ponderadas pelo CHI
  dos alimentadores tratados.

## Ruído cadastral conhecido

* `DAT_CON` dos religadores: 2.100 dos 4.060 religadores do cadastro de 2025 têm conexão em 2024
  (recadastramento). Não é usado.
* `TLCD`: os religadores telecomandados vão de 1.142 (cadastro 2022) para 811 (2023), na mesma transição em que o
  `COD_ID` dos circuitos mudou. O efeito do telecomando cadastral é reportado em
  `reports/efeitos_por_unidade.csv`, mas não sustenta conclusão.
* Divisões e transferências de carga mudam o tamanho dos alimentadores. Por isso há o teste de robustez só com
  alimentadores de extensão estável.
