# Saídas de MS que os outros repositórios consomem

Este documento vale para quem lê o resultado deste repositório para a **Energisa MS (EMS)**: `recloser-performance` e
`substation-health-index`. Os dados de `data/ems/` **não vão para o git** (`data/` está no `.gitignore`) e ficam no clone,
ao lado do `distribution-asset-risk`; o que vai para o git é `reports/ems/`.

> Projeto independente, sem vínculo com a Energisa ou com a ANEEL. Só dados abertos (ANEEL e IBGE).

## Leia primeiro: de onde vem o efeito

Neste repositório, o efeito do religador em MS **não foi medido**. A regra de decisão pré-registrada
([`decisoes_ems.md`](decisoes_ems.md)) exige 60 eventos tratados e 100 controles nunca tratados; MS tem **72 eventos e 87
controles**. Por isso o efeito é o de MT, e todo arquivo de `reports/ems/` traz **`origem_efeito = "transportado de MT"`**
(coluna nos CSV, campo nos JSON, rodapé nas figuras). Quem consome tem que repetir esse rótulo na própria saída.
Se a regra um dia liberar o efeito próprio, o rótulo passa a `"medido em MS"` (ver o fim desta página).

## `reports/ems/valor.json`

Tem **as mesmas chaves, na mesma estrutura**, que o `reports/valor.json` de MT, mais **`origem_efeito`** (primeiro campo). Um
teste (`tests/test_ems_fumaca.py`) confere que o conjunto de chaves é o de MT mais esse campo.
`recloser-performance` lê `rs_por_chi_social`, `rs_por_chi_compensacao`, `frac_chi_regulatorio`, `uc_total`,
`chi_evitado_ano_por_religador` (e o IC), `efeito_chi_pct`; basta apontar o `valor_json` para
`../automation-impact/reports/ems/valor.json`.

**De onde vem cada campo** (no ramo "transportado de MT", que é o desta execução; MS = exposição do recorte, MT = efeito publicado
de MT, lido sem alteração de `reports/efeitos_did.csv`, `reports/efeitos_por_unidade.csv` e `reports/valor.json`):

| Campo | Origem | Valor (execução de 06/11/2026) |
|---|---|---|
| `origem_efeito` | decisão da regra | `transportado de MT` |
| `efeito_chi_pct`, `ic95_chi_pct` | **MT** (idênticos aos de MT) | -16,6% (-24,8% a -7,5%) |
| `twfe_efeito_por_religador_pct`, `frac_efeito_via_duracao_twfe` | **MT** | 57,1% do efeito passa pela duração |
| `eventos`, `religadores_adicionados_nos_eventos`, `ganho_mediano_por_evento` | **MS**: eventos pela definição de MT, usados só como base de exposição (o efeito **não** foi medido neles) | 72; 193; 2 |
| `chi_evitado_ano_eventos`, `chi_evitado_ano_ic95` | CHI de MS antes da instalação nos 72 eventos x efeito de MT | 751 mil (340 mil a 1,12 milhão) |
| `chi_evitado_ano_por_religador`, `..._ic95` | o anterior dividido pelo ganho de religadores dos eventos de MS | 3.893 (1.760 a 5.816) |
| `uc_total` | **MS**: consumidores do cadastro de 2024 (painel de 2025) | 1.458.167 |
| `dec_min_por_religador` | MS | 0,160 |
| `rs_por_chi_compensacao`, `rs_por_chi_social` | **MS**: `risco_alimentador` da base (compensações pagas a MS, sem linhas repetidas), ponderado pelo CHI dos eventos. **Não é o de MT** (R$ 1,93 e R$ 5,94) | R$ 2,15 e R$ 5,56 |
| `frac_chi_regulatorio` | MS (CHI dos eventos) | 52,3% |
| `rs_ano_por_religador_*`, `vpl_religador_*`, `payback_anos_social` | MS x efeito de MT x premissas | VPL social +R$ 52,5 mil; só compensações -R$ 117,1 mil |
| `religadores_2025` | MS: religadores do cadastro de 31/12/2025 (o nome do campo é o de MT) | 2.549 |
| `frota_chi_ano_dependente_dos_religadores`, `frota_chi_marginal_medio_por_religador` | MS: CHI de 2023 a 2025 de cada alimentador x efeito marginal de MT | 5,39 milhões; 2.113 por religador |
| `indisponibilidade_1pp.*` | frota de MS x efeito e fração da duração de MT | 0,63 a 1,27 min de DEC por p.p. |
| `premissas.*` | configuração (as de MT, sem recalibrar) | R$ 160 mil; 20 anos; 8%; R$ 7.000/MWh |
| `carteira_subestacoes.*` | MS (alimentadores longos e pouco protegidos) x efeito de MT | 116 alimentadores; R$ 37,1 mi; VPL social +R$ 47,8 mi |

Ressalvas que seguem com o número (detalhes em [`decisoes_ems.md`](decisoes_ems.md), seção 5): o efeito de MT foi medido sobre o CHI total e
em MS o CHI expurgado pesa mais; parte dos 72 eventos de MS pode ser remanejamento e não instalação; e a fração do efeito que passa pela duração
herda a fragilidade à pré-tendência do README de MT.

## Outros arquivos de `reports/ems/`

Todos com `origem_efeito`:

| Arquivo | O que é |
|---|---|
| `regra_decisao.json` | A decisão: contagens, mínimos, motivo, coortes e o `sha256` dos 3 arquivos de MT de onde o efeito foi lido |
| `eventos_tratamento.csv` | Os 72 eventos de MS (alimentador, ano do evento, ganho, religadores antes) |
| `subestacoes.csv` | 63 subestações de MS: CHI anual 2023 a 2025, DEC, candidatos e CHI evitável com +2 religadores (efeito de MT) |
| `elemento_2026.csv` | Quem abriu o circuito em 2026 (jan-fev e abr-jul; março não tem registro) |
| `atendimento_2025.csv` | Preparo, deslocamento e execução das ocorrências emergenciais de 2025 (só se o download foi possível; ver `resultados_ems.md`) |
| `figures/04_subestacoes.png`, `05_disponibilidade.png`, `06_elemento_2026.png` | Figuras (rodapé com `origem_efeito`) |
| `diagnostico/*` | Contagens e checagens de dados que sustentam a regra (religadores por snapshot, eventos por coorte, funil de controles, cobertura de 2026, linhas repetidas) |

**Não existem em MS** (nada foi estimado): `efeitos_did.csv`, `event_study.csv`, `efeitos_por_unidade.csv`, `robustez.csv`,
`comparacao_premissas.csv`, `did_escalonado_*` e as figuras 01 a 03 e 07.

## `data/ems/` (no clone, fora do git)

`data/ems/interim/`:

| Arquivo | O que é | Linhas |
|---|---|---|
| `equipamentos_<ano>.parquet` (2018 a 2025) | Equipamentos por alimentador no cadastro de 31/12: `alimentador` (chave canônica, `CTMT.NOME` com zeros à esquerda até 6 caracteres, ex.: `0AJO51`), `subestacao`, `n_religadores` (`TIP_UNID` 32), `n_religadores_tlcd`, `n_disjuntores` (29, 30, 53), `n_seccionalizadores` (35, 36), `n_chaves_fusiveis` (22 a 27), `n_tlcd_rede` (telecomando exceto disjuntor), `ano_snapshot` | 315, 423, 318, 320, 349, 354, 359, 362 |
| `subestacoes_<ano>.parquet` | `subestacao`, `subestacao_nome`, `potencia_mva`, `ano_snapshot` | 111 em 2024 |
| `painel.parquet` | Alimentador x ano de resultado (2019 a 2025): atributos de rede e equipamentos do cadastro do ano anterior, `n_falhas`, `chi`, `chi_regulatorio`, `ci`, `ci_por_falha`, `duracao_h`, `religadores_100km`, `log_km`, `log_uc` | 2.438 (482 alimentadores) |

* A chave `alimentador` é a mesma de `../distribution-asset-risk/data/ems/interim/` (`falhas.parquet`, `bdgd_feeders_<ano>.parquet`,
  `crosswalk_<ano>.parquet`). Em MT são 6 dígitos; em MS, 5 caracteres alfanuméricos com um zero na frente.
* Os totais de religadores de `equipamentos_<ano>` são iguais aos de `bdgd_feeders_<ano>` da base (1.730, 1.831, 1.851, 1.999, 2.044, 2.117, 2.187 e
  2.549). Só entram religadores ligados a um circuito da camada `CTMT`.
* `data/ems/raw/` é temporário: cada `.gdb` é extraído do zip do cache somente leitura, lido e apagado.

## Se a regra liberar o efeito próprio de MS

Com 60 eventos e 100 controles ou mais, `02_estimar.py` estima o efeito de MS (`origem_efeito = "medido em MS"`), grava `efeitos_did.csv`,
`event_study.csv`, `efeitos_por_unidade.csv`, `robustez.csv`, `comparacao_premissas.csv` e **`comparacao_mt.csv`** (o efeito de MT ao lado), e `05_did_escalonado.py`
roda a conferência de Callaway & Sant'Anna e a sensibilidade à pré-tendência. `valor.json` mantém o mesmo esquema; `efeito_chi_pct`, `twfe_*` e
`frac_efeito_via_duracao_twfe` passam a ser de MS. Os dois ramos são testados com dados sintéticos (`tests/test_ems_fumaca.py`).
