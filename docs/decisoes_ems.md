# Decisões de dados e regra de decisão para a Energisa MS (EMS)

Este documento foi escrito e commitado **antes de qualquer estimação de efeito em MS**. Até aqui só rodaram duas
coisas: a montagem dos equipamentos por alimentador a partir da BDGD (`scripts/01_build_equipamentos.py`) e o
diagnóstico de contagem (`scripts/00_diagnostico.py`), que **não estima nada**. As saídas do diagnóstico estão em
[`reports/ems/diagnostico/`](../reports/ems/diagnostico/), e cada tabela abaixo cita o arquivo de onde sai.
Execução de 06/11/2026.

Nomes: **MT** é a Energisa Mato Grosso (EMT), a distribuidora dos resultados publicados neste repositório; **MS** é a
Energisa Mato Grosso do Sul (EMS). "Média tensão" aparece por extenso. As decisões de dados de MS que vêm da base
(`distribution-asset-risk`) estão em `docs/decisoes_ems.md` de lá e **não são repetidas** aqui.

> Projeto independente, sem vínculo com a Energisa ou com a ANEEL. Só dados abertos (ANEEL e IBGE).

## Resumo

| # | Tema | O que os dados de MS mostram | Decisão |
|---|---|---|---|
| 1 | Instalações de religadores | 1.730 religadores (2018) a 2.187 (2024) nos snapshots usados no painel; os ganhos brutos por circuito (1.028) são bem maiores que o saldo (+292 nos circuitos presentes nos dois anos), então o cadastro pode misturar instalação e remanejamento | A definição de evento de MT é mantida; a ressalva fica registrada (seção 2) |
| 2 | Eventos e controles | **72 eventos** tratados e **87 controles** nunca tratados (MT: 116 e 209) | Regra pré-registrada (seção 4) |
| 3 | Regra de decisão | 72 >= 60, mas 87 < 100 | **Não se publica efeito próprio de MS.** Vale o efeito de MT, rotulado **"transportado de MT"** (seção 5) |
| 4 | Cobertura e vínculo de 2026 | Sem nenhum registro em março; 85,8% das falhas (84,1% do CHI) casam com um circuito | 2026 só entra na tabela descritiva de quem abriu o circuito (seção 3) |
| 5 | Linhas repetidas | 799 de 1.466.882 interrupções (0,054%); nada nos demais arquivos lidos aqui | Como na base: ler como publicado (seção 6) |
| 6 | Suposições de MT no código | 10 itens (seção 7) | Todas parametrizadas pela configuração, com o padrão igual a MT |

## 1. Dados de MS que este repositório usa

* **Da base** (`../distribution-asset-risk/data/ems/{interim,processed}`): `interrupcoes_ems.parquet`, `falhas.parquet`,
  `bdgd_feeders_<ano>.parquet`, `crosswalk_<ano>.parquet` e `risco_alimentador.parquet`. O R$ por consumidor-hora de MS vem
  daí (compensações pagas a MS lidas sem as linhas repetidas), **não** do valor de MT.
* **Daqui**: `data/ems/interim/equipamentos_<ano>.parquet` e `subestacoes_<ano>.parquet`, montados com
  `scripts/01_build_equipamentos.py --config configs/ems.yaml` a partir dos 8 zips da BDGD de 31/12 de 2018 a 2025 (a versão
  mais recente de cada ano; ids em [`configs/ems.yaml`](../configs/ems.yaml), conferidos na base). Os zips ficam num cache
  somente leitura; cada um é extraído para o clone, lido e apagado. O de 2025 reaproveita o `.gdb` que a base já manteve.
* **Conferência**: o total de religadores (`TIP_UNID` 32) de `equipamentos_<ano>` é igual, nos 8 anos, ao de `bdgd_feeders_<ano>`
  da base ([`religadores_por_snapshot.csv`](../reports/ems/diagnostico/religadores_por_snapshot.csv), colunas `religadores` e
  `religadores_no_cadastro_do_gridrisk`). Ambos são menores que o total de `UNSEMT` da base (por exemplo, 2.646 contra 2.549 em 2025)
  porque só entram religadores ligados a um circuito que existe na camada `CTMT`.
* O mapeamento de `TIP_UNID` (32 religador, 29/30/53 disjuntor, 35/36 seccionalizador, 22 a 27 chave fusível) é o de MT.
  A base verificou que vale em MS (`TLCD` de 68% nos religadores em 2025, `TUC` 345 só em `TIP_UNID` 32).

## 2. Religadores por snapshot da BDGD (31/12)

O painel usa o cadastro de 31/12 do ano anterior ao do resultado (resultado de 2019 usa o snapshot de 2018 e assim por
diante), então o snapshot de 2025 **não entra** no painel (só na frota atual e na previsão de 2026).

| Snapshot | Circuitos | Circuitos vazios | Religadores | Telecomandados | Circuitos com religador | Rede média tensão (km) | Religadores por 100 km |
|---|---|---|---|---|---|---|---|
| 2018 | 315 | 10 | 1.730 | 800 | 302 | 85.174 | 2,03 |
| 2019 | 423 | 105 | 1.831 | 810 | 311 | 85.813 | 2,13 |
| 2020 | 318 | 2 | 1.851 | 836 | 306 | 86.427 | 2,14 |
| 2021 | 320 | 6 | 1.999 | 831 | 309 | 86.952 | 2,30 |
| 2022 | 349 | 0 | 2.044 | 827 | 342 | 88.305 | 2,31 |
| 2023 | 354 | 0 | 2.117 | 826 | 347 | 89.366 | 2,37 |
| 2024 | 359 | 0 | 2.187 | 823 | 353 | 90.412 | 2,42 |
| 2025 (fora do painel) | 362 | 0 | 2.549 | 1.808 | 358 | 91.453 | 2,79 |

"Circuito vazio" é o que não tem rede de média tensão nem consumidor. O snapshot de 2019 tem 98 circuitos com nome de 3
caracteres, que são o código da subestação (decisões da base, seção 2.1).

Mudança entre snapshots consecutivos, nos circuitos presentes nos dois anos
([`transicoes_religadores.csv`](../reports/ems/diagnostico/transicoes_religadores.csv)):

| Resultado de | Snapshots | Circuitos nos dois | Religadores ganhos | Perdidos | Saldo | Circuitos com ganho >= 2 | Circuitos com perda >= 2 | Eventos da coorte |
|---|---|---|---|---|---|---|---|---|
| 2020 | 2018 a 2019 | 311 | 191 | 113 | +78 | 38 | 20 | 17 |
| 2021 | 2019 a 2020 | 315 | 240 | 199 | +41 | 45 | 41 | 14 |
| 2022 | 2020 a 2021 | 314 | 201 | 75 | +126 | 45 | 11 | 8 |
| 2023 | 2021 a 2022 | 318 | 153 | 243 | -90 | 34 | 44 | 11 |
| 2024 | 2022 a 2023 | 344 | 130 | 50 | +80 | 28 | 7 | 10 |
| 2025 | 2023 a 2024 | 351 | 113 | 56 | +57 | 21 | 8 | 12 |

* Os ganhos brutos somam 1.028 religadores e as perdas, 736, contra um saldo de +292. Um circuito que perde religadores num
  ano e outro que ganha no mesmo ano é compatível com remanejamento de rede (circuitos divididos, renomeados ou criados), e **o
  cadastro não permite separar instalação nova de remanejamento**. MT tem o mesmo padrão (ganhos 2.422 e perdas 1.418 em seis
  transições, saldo +1.004), em escala maior.
* O pico de perdas em 2023 (44 circuitos com perda >= 2, saldo de -90) coincide com a passagem do snapshot de 2021 para o de 2022,
  quando o número de circuitos sobe de 320 para 349. Não investiguei a causa e não afirmo nenhuma.
* Isso importa para o que vem depois: o "evento" é um ganho de 2 ou mais religadores num circuito, e uma parte dos eventos de
  MS pode ser remanejamento, não instalação. Fica como ressalva sobre os números de exposição (seção 5).

## 3. Cobertura e vínculo de 2026

Fonte: [`cobertura_2026.csv`](../reports/ems/diagnostico/cobertura_2026.csv) e `cobertura_ano_parcial` em
[`regra_contagens.json`](../reports/ems/diagnostico/regra_contagens.json).

* O arquivo de interrupções de MS tem registros em janeiro, fevereiro e de abril a julho de 2026. **Março não tem nenhuma
  linha** (em MT tem 27.328; achado da base, seção 3.4 de lá). Os números de 2026 de MS não incluem março.
* Falhas de média tensão, internas e não programadas em 2026: **103.373**. Casam com um circuito de alguma BDGD publicada
  **85,8%** das falhas e **84,1%** do CHI (a base chegou aos mesmos números). O resto usa o `COD_ID` de um cadastro ainda não
  publicado.
* O campo `elemento` (quem abriu o circuito) só existe a partir de 2026, e o preenchimento muda muito por mês: parcela de
  falhas com elemento diferente de "NAO IDENTIFICADO", de 100% em janeiro a 30% em abril (83%, 30%, 70%, 57% e 66% em fevereiro e de abril a julho).
* **Uso em MS:** o painel de estimação vai de 2019 a 2025, então 2026 não entra em nenhum efeito. Entra só em
  `elemento_2026.csv`, uma tabela descritiva de quem abriu o circuito, com o buraco de março e a ressalva do preenchimento.

## 4. Eventos, controles e a regra de decisão pré-registrada

### 4.1 Definições (as de MT, sem alterar nada)

As duas contagens usam as **mesmas funções de MT**, sem mudar parâmetro, aplicadas ao mesmo painel de `02_estimar.py`:

* **Evento** = `painel.eventos_tratamento(p, minimo=2)`: o primeiro ano de resultado em que o alimentador ganha 2 ou mais
  religadores de uma vez em relação ao snapshot anterior e **mantém** o ganho (nunca cai abaixo do novo nível menos 0,5) até o
  fim do painel. Uma queda de 2 ou mais antes de um ganho encerra a busca. Conta-se um alimentador por evento.
* **Controle nunca tratado** = `painel.nunca_tratados(p)`: alimentador presente nos **7 anos** de resultado (2019 a 2025) e com
  amplitude (máximo menos mínimo) de religadores de **no máximo 1**.
* O painel é o de MT: alimentador × ano, junção interna entre `bdgd_feeders` e `equipamentos` do snapshot do ano anterior. Nenhum
  filtro de circuito vazio, de extensão ou de consumidores foi acrescentado.

### 4.2 Contagens

Fonte: [`regra_contagens.json`](../reports/ems/diagnostico/regra_contagens.json), [`eventos_por_coorte.csv`](../reports/ems/diagnostico/eventos_por_coorte.csv),
[`controles_funil.csv`](../reports/ems/diagnostico/controles_funil.csv), [`presenca_alimentadores.csv`](../reports/ems/diagnostico/presenca_alimentadores.csv)
e, para MT, [`mt_contagens_referencia.json`](../reports/ems/diagnostico/mt_contagens_referencia.json) (mesmas funções sobre o painel de MT
regenerado em 06/11/2026; os 116 eventos conferem com `reports/eventos_tratamento.csv`, e nada de MT foi reestimado).

| | MS | MT |
|---|---|---|
| Alimentadores distintos no painel | 482 | 706 |
| Presentes nos 7 anos | 299 | 548 |
| **Eventos tratados** | **72** | 116 |
| Coortes (2020, 2021, 2022, 2023, 2024, 2025) | 17, 14, 8, 11, 10, 12 | 18, 10, 18, 27, 21, 22 |
| Religadores adicionados nos eventos (mediana por evento) | 193 (2) | 493 (2) |
| **Controles nunca tratados** | **87** | 209 |

Funil dos controles de MS: dos 299 alimentadores presentes nos 7 anos, 87 têm amplitude <= 1 (3 sem nenhum religador em nenhum ano
e 84 com), 212 têm amplitude >= 2 (61 deles são eventos) e nenhum é circuito vazio. Dos 183 que **não** estão nos 7 anos, 117 aparecem em um
ano só (98 deles com nome de 3 caracteres, o código de subestação do snapshot de 2019) e os outros 66 entram ou saem no meio do período.

Variações **apenas informativas, fora da regra** (não mudam a decisão e não foram usadas para escolhê-la): eventos com ganho >= 1: 119
(MT 151); com ganho >= 3: 34 (MT 87); controles com amplitude 0: 25 (MT 67); controles com amplitude <= 2: 151 (MT 309); controles
com CHI total positivo: 84 (MT 199).

### 4.3 A regra (pré-registrada)

> Aplicando a **mesma** definição de evento e de controle que MT usa, o efeito próprio de MS só é publicado se houver **pelo
> menos 60 eventos tratados E pelo menos 100 alimentadores controle nunca tratados**.
>
> * **Se não houver:** NÃO se publica efeito específico de MS. Usa-se o efeito de MT, rotulado explicitamente **"transportado de
>   MT"** (não medido em MS), e isso aparece em destaque no README e em todos os arquivos de saída (campo `origem_efeito`).
> * **Se houver:** publica-se o efeito de MS com intervalo de confiança e, ao lado, o de MT para comparação. Rodam também a conferência de
>   Callaway & Sant'Anna e a sensibilidade à pré-tendência (`scripts/05_did_escalonado.py`).

Os limites (60 e 100) e a definição vêm do pedido do projeto e são anteriores a qualquer contagem. A configuração está em
`regra_decisao` de [`configs/ems.yaml`](../configs/ems.yaml), e a regra é a função `autoimpact.regra.decidir` (os dois limites são "pelo
menos", ou seja, `>=`). Dois pontos de transparência:

1. As contagens da seção 4.2 foram calculadas **antes** de escrever esta seção, porque o diagnóstico exige contá-las. Nenhum efeito foi
   estimado em MS, e nenhuma definição (ganho mínimo de 2, tolerância de 1, presença nos 7 anos) foi tocada depois de ver os números.
2. `02_estimar.py` recalcula as contagens e **falha** se forem diferentes das registradas em `regra_contagens.json`.

### 4.4 Resultado da regra

| Critério | Mínimo | MS | Atende? |
|---|---|---|---|
| Eventos tratados | 60 | 72 | sim |
| Controles nunca tratados | 100 | 87 | **não** |

**Decisão: `origem_efeito = "transportado de MT"`.** O limite de controles não é atingido por 13 alimentadores, e a variação informativa mais
próxima da definição (84 controles com CHI positivo) não o alcança. Em MS, o pool de controles é pequeno: só 299 dos 482 alimentadores
existem nos 7 anos (os outros 183 aparecem ou somem entre snapshots; 98 são códigos de subestação do snapshot de 2019) e 212 dos 299 mudam de nível de religadores.

## 5. O que acontece no ramo "transportado de MT"

**Não se estima nada em MS:** nem o DiD empilhado, nem o event study, nem o TWFE (efeito por unidade), nem a robustez, nem a
conferência de Callaway & Sant'Anna, nem a sensibilidade à pré-tendência. `05_did_escalonado.py` recusa rodar. Não existem
`efeitos_did.csv`, `event_study.csv`, `efeitos_por_unidade.csv`, `robustez.csv`, `comparacao_premissas.csv` nem as figuras 01 a 03 e 07 em `reports/ems/`.

**De MT** (resultados publicados, lidos sem alteração; o `sha256` de cada arquivo fica em `reports/ems/regra_decisao.json`):

* `reports/efeitos_did.csv`: coeficiente e erro-padrão do CHI (efeito de -16,6%, IC 95% de -24,8% a -7,5%).
* `reports/efeitos_por_unidade.csv`: efeito de cada religador a mais em CHI, frequência, consumidores por falha e duração (TWFE), de onde sai a
  fração do efeito que passa pela duração (57%).

**De MS** (a exposição): o CHI antes da instalação dos 72 eventos de MS, o total de consumidores, o CHI anual de 2023 a 2025 de cada alimentador,
os 2.549 religadores do cadastro de 2025, a fração regulatória do CHI, o R$ por consumidor-hora (compensações e custo social de MS) e o
ranking de subestações. O esquema de `reports/ems/valor.json` é o de MT mais `origem_efeito`; a origem campo a campo está em
[`saidas_ems.md`](saidas_ems.md).

**Ressalvas do transporte** (descritivas, sem afirmar causa):

* O efeito de MT foi medido sobre o CHI total. Em MS o CHI expurgado pesa mais (a base mede 50% a 58% do CHI das falhas em 2023 a 2025,
  contra 26% em MT), então a mistura do que se chama "CHI" é diferente.
* Parte dos 72 eventos de MS pode ser remanejamento e não instalação (seção 2). Os valores "por religador" de MS dividem o CHI evitado pelo ganho
  de religadores desses eventos, e herdam essa incerteza.
* O custo do ponto percentual de indisponibilidade herda a fração do efeito que passa pela duração de MT, o canal que é frágil à
  pré-tendência (ressalva do README de MT, mantida).
* O R$ por consumidor-hora é o de MS; o custo da energia não suprida (R$ 7.000/MWh), a vida do religador, a taxa de desconto e o custo do
  religador são as premissas ilustrativas de MT, sem recalibrar.

## 6. Linhas repetidas (`count(*)` contra `count(distinct *)`)

Todo arquivo lido pelos scripts deste repositório, em [`duplicatas_arquivos.csv`](../reports/ems/diagnostico/duplicatas_arquivos.csv):

| Arquivo | Linhas | Distintas | Repetidas |
|---|---|---|---|
| `interrupcoes_ems.parquet` (ANEEL, harmonizado pela base) | 1.466.882 | 1.466.083 | 799 (0,054%) |
| `falhas.parquet` | 132.345 | 132.345 | 0 |
| `risco_alimentador.parquet` | 362 | 362 | 0 |
| `bdgd_feeders_<ano>`, `crosswalk_<ano>`, `equipamentos_<ano>` (24 arquivos) | | | 0 |

* As 799 linhas repetidas de interrupções são todas de 2018 a 2020 (381, 352 e 66, achado da base) e pesam menos de 0,03% do CHI de cada ano. Mesma
  decisão da base: ler como publicado.
* Os arquivos nacionais de **indicadores e compensações** da ANEEL não são lidos aqui; entram só através de `risco_alimentador`, que a base produz com
  o leitor que remove duplicatas (EMS: 441.408 linhas, 220.704 distintas na compensação; cada linha vem duas vezes). O R$ por CHI de MS (mediana de R$ 1,87 de
  compensação e R$ 4,75 social por alimentador) está na ordem do de MT com a remoção (R$ 1,93 e R$ 5,94), e não no dobro dele.
* O arquivo nacional de **ocorrências emergenciais** (`03_atendimento.py`) tem a mesma conferência embutida no script, antes da agregação.

## 7. Suposições de MT encontradas neste repositório

| Onde | Suposição de MT | Tratamento |
|---|---|---|
| `scripts/02_estimar.py` | arquivo `interrupcoes_emt.parquet` fixo | `Config.interrupcoes_parquet`: `interrupcoes_<sigla em minúsculas>.parquet`; o de MT segue `interrupcoes_emt.parquet` |
| `scripts/02`, `03`, `04`, `05` | pasta `reports/` na raiz (`ROOT / "reports"`) | `paths.reports` na configuração; padrão `reports`. MS: `reports/ems` |
| `scripts/05_did_escalonado.py` | `--valor` e `--saida` apontavam para `reports/` antes de ler a configuração, o que alimentaria o D5 e o D6 de MS com o `valor.json` de MT | a configuração é lida primeiro e os padrões saem dela |
| `scripts/03_atendimento.py` | filtro `ENERGISA MATO GROSSO` sem `SUL` (que exclui MS por construção) e `ANO = 2025` | `ocorrencias.incluir/excluir/ano` na configuração |
| `scripts/02_estimar.py` | anos 2023-2025, snapshots 2024 e 2025, ano 2026 e placebo a partir de 2021 | derivados de `snapshots` e `anos_resultado` (`Config.anos_chi_recente` etc.), com os mesmos valores em MT (testado) |
| `scripts/04_figuras.py` | "DEC da EMT", "2023-2025", "jan-jul/2026", título "o disjuntor responde por ~1/4 do CHI" e títulos com as conclusões de MT | sigla, anos e meses vêm dos dados; fora de MT os títulos são neutros e o texto de quem abriu o circuito sai da tabela |
| `scripts/01_build_equipamentos.py` | `symlink` do `.gdb` da base (falha no Windows sem privilégio) e download direto | lê o `.gdb` da base sem apagá-lo; os demais vêm de uma pasta de zips somente leitura (`paths.bdgd_zips`) ou do ArcGIS Hub |
| `src/autoimpact/bdgd.py` | `CTMT.NOME` com 6 dígitos (`zfill(6)`) | já completa com zeros até 6 caracteres, o que dá `0AJO51` em MS e coincide com a chave da base (testado) |
| `configs/emt.yaml` | recorte fixo de MT | `configs/ems.yaml`; `--config` ou `AUTOIMPACT_CONFIG`; o padrão continua `emt.yaml` |
| README e `docs/` de MT | textos de MT | **não reescritos**; MS tem seção própria no README e `docs/resultados_ems.md` |

Sem mudança necessária: a definição de falha (média tensão, interna, não programada), os desfechos do painel, os estimadores e os filtros de
alimentador por nome (não há filtro por UF, município, código IBGE ou `TUC` neste repositório).

## 8. O que não foi feito

* **Efeito próprio de MS:** não medido (seção 4.4). Se a BDGD ou a regra mudarem, basta rodar `scripts/00_diagnostico.py`, que refaz a contagem e a decisão;
  `02` e `05` seguem a decisão automaticamente.
* **Remanejamento versus instalação:** não separado (seção 2); o cadastro não tem a informação.
* **Buracos de 2026 e de outubro de 2021:** só registro, como na base.

## Como reproduzir

```bash
export AUTOIMPACT_CONFIG=configs/ems.yaml                  # ou --config em cada script
export AUTOIMPACT_BDGD_ZIPS=<pasta com os zips bdgd_<ano>_<item>.gdb.zip>   # somente leitura
python scripts/01_build_equipamentos.py                    # data/ems/interim/equipamentos_<ano>.parquet
python scripts/00_diagnostico.py                           # reports/ems/diagnostico/ (contagens, sem estimar nada)
# opcional: recontar MT com as mesmas funções (só leitura; os dados de MT têm que estar nos caminhos de configs/emt.yaml)
python scripts/00_diagnostico.py --referencia-mt configs/emt.yaml   # grava mt_contagens_referencia.json
```
