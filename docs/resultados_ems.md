# Resultados da Energisa MS (EMS)

> **O efeito do religador em MS NÃO foi medido. Ele é o de MT, "transportado de MT".** A regra de decisão pré-registrada
> ([`decisoes_ems.md`](decisoes_ems.md)) pede 60 eventos tratados **e** 100 controles nunca tratados. MS tem **72 eventos
> e 87 controles**, então o efeito próprio de MS não é publicado. Todo arquivo de `reports/ems/` traz o campo
> **`origem_efeito = "transportado de MT"`**.
>
> O que é de MS aqui é a **exposição**: o CHI dos alimentadores, os consumidores, a frota de religadores, o R$ por consumidor-hora e as
> subestações. O que é de MT é o **efeito** (−16,6% no CHI) e a fração dele que passa pela duração.

Projeto independente, sem vínculo com a Energisa ou com a ANEEL. Só dados abertos (ANEEL e IBGE). Execução de 06/11/2026. Todo número
sai de arquivos regenerados em [`reports/ems/`](../reports/ems/) (cada tabela cita o arquivo).

## 1. Destaques

Fonte: [`reports/ems/valor.json`](../reports/ems/valor.json). A coluna "Origem" diz o que é de MS e o que é de MT; a coluna MT traz, para
comparação, o que o repositório publica para a Energisa MT.

| | MS | MT | Origem do número de MS |
|---|---|---|---|
| Efeito de ganhar religadores sobre o CHI do alimentador | **−16,6%** (IC 95%: −24,8% a −7,5%) | −16,6% | **transportado de MT** (não medido em MS) |
| Eventos tratados / controles nunca tratados | 72 / 87 | 116 / 209 | MS (contagem, regra pré-registrada) |
| CHI evitado por religador instalado | ≈ 3.900 consumidores-hora/ano (IC 95%: 1.800 a 5.800) | ≈ 4.600 (2.100 a 6.800) | CHI de MS antes dos 72 eventos x efeito de MT |
| Minutos de DEC por religador | 0,16 | 0,13 | idem |
| R$ por consumidor-hora (compensação; social) | R$ 2,15; R$ 5,56 | R$ 1,93; R$ 5,94 | **MS** (compensações pagas a MS, sem linhas repetidas) |
| Valor por religador (social; só compensações) | R$ 21,6 mil/ano; R$ 4,4 mil/ano | R$ 27,2 mil; R$ 6,7 mil | MS x efeito de MT |
| VPL em 20 anos, religador de R$ 160 mil (ilustrativo), social; só compensações | **+R$ 52,5 mil**; **−R$ 117,1 mil** | +R$ 107,1 mil; −R$ 94,2 mil | MS x efeito de MT x premissas de MT |
| Payback (social) | 7,4 anos | 5,9 anos | idem |
| Custo de 1 ponto percentual de indisponibilidade da telemetria dos religadores | **0,63 a 1,27 min de DEC/ano**; R$ 76 a 151 mil/ano (social) | 0,7 a 1,4 min; R$ 134 a 268 mil | frota de MS (2.549 religadores) x efeito e fração da duração de MT |
| Subestações que mais pesam: 10% (6 de 63) concentram | **21% do CHI** | 33% (10 de 104) | MS (CHI médio de 2023 a 2025) |
| Carteira ilustrativa: +2 religadores em alimentadores longos e pouco protegidos | 116 alimentadores; R$ 37,1 mi; 65 min de DEC/ano; VPL social +R$ 47,8 mi | 199; R$ 63,7 mi; 78 min; +R$ 99,6 mi | MS x efeito de MT (extrapolação ilustrativa) |

* O R$ por consumidor-hora de MS **não é** o de MT: vem de `risco_alimentador` da base, que lê as compensações de MS com o leitor que remove as
  linhas repetidas (cada linha da EMS vem duas vezes no arquivo da ANEEL). É a mediana, ponderada pelo CHI dos eventos.
* A parcela regulatória do CHI dos 72 eventos de MS é de 52% (MT: 76%). É isso que torna o valor "só compensações" menor em MS.
* As diferenças entre as colunas MS e MT são **descritivas**; não afirmo causa para elas.

## 2. O que este resultado não diz

* **Não é uma medida de MS.** O −16,6% foi estimado em MT. Em MS, os dados de religadores permitem 72 eventos, mas só 87 controles que nunca
  mudaram de nível (o mínimo era 100), e o cadastro mistura instalação e remanejamento (ganhos brutos de 1.028 religadores contra saldo de +292; ver
  `decisoes_ems.md`, seção 2). Se o efeito de MS for parecido com o de MT, os números acima valem; se não for, não.
* **O CHI de MS é diferente.** O CHI expurgado pesa mais em MS (a base mede 50% a 58% do CHI das falhas em 2023 a 2025, contra 26% em MT), e o
  efeito de MT foi medido sobre o CHI total.
* **O canal da duração é frágil à pré-tendência.** A faixa de 0,63 a 1,27 min de DEC por p.p. usa a fração do efeito que passa pela duração (57%),
  que é a de MT. Em MT, a duração já caía antes da instalação nos alimentadores tratados: descontando em linha reta essa tendência, a queda de 20% vai
  a −3% (IC 95%: −17% a +15%) e o IC passa a conter zero (README, seção "Conferência com um estimador robusto à adoção escalonada", e Limitações). A faixa de
  MS **herda essa fragilidade** e não deve ser lida como robusta.
* **Premissas ilustrativas.** O custo do religador (R$ 160 mil), a vida de 20 anos, a taxa de 8% e o custo da energia não suprida (R$ 7.000/MWh) são as
  premissas de MT, sem recalibrar para MS.

## 3. Comparação descritiva MS x MT

Normalizada por consumidor e por km. Fonte: `reports/ems/subestacoes.csv` e `reports/subestacoes.csv` (cadastro de 2024; CHI médio por ano de 2023 a 2025 das
falhas de média tensão, internas e não programadas, com expurgo incluído).

| | MS | MT |
|---|---|---|
| Alimentadores | 359 | 673 |
| Rede de média tensão (km) | 90.412 | 204.945 |
| Consumidores | 1,46 milhão | 2,13 milhões |
| Consumidores por km | 16,1 | 10,4 |
| Religadores | 2.187 | 3.647 |
| Religadores por 100 km | 2,42 | 1,78 |
| CHI anual das falhas | 19,3 milhões | 26,2 milhões |
| CHI por consumidor (h/ano) | 13,2 | 12,3 |
| CHI por km (h/ano) | 213 | 128 |
| Parcela do CHI nas 10% subestações que mais pesam | 21% | 33% |

Em MS há mais consumidores e mais religadores por km de rede que em MT, e o CHI por consumidor é parecido. Isso não diz nada sobre o efeito do religador.

## 4. Quem abriu o circuito (2026) e o tempo de atendimento (2025)

**2026** (`reports/ems/elemento_2026.csv`, falhas de média tensão, internas e não programadas; **janeiro, fevereiro e abril a julho: março não tem registro**):
o religador abriu 20 mil interrupções (32% do CHI; 211 consumidores por evento e 2,4 h de duração média), a chave fusível 18%, o transformador 19% e o
disjuntor da subestação **1%** (577 interrupções). 24% do CHI não tem elemento identificado, e a parcela de falhas com elemento preenchido vai de
100% em janeiro a 30% em abril, então essas parcelas não são estáveis. Em MT, o disjuntor responde por cerca de 1/4 do CHI no mesmo recorte
(`reports/elemento_2026.csv`); a diferença é descritiva, e o preenchimento e o buraco de março de MS podem pesar nela.

**Atendimento em 2025** (`reports/ems/atendimento_2025.csv`, ocorrências emergenciais da ANEEL, 240.039 internas não programadas da EMS): 82% do tempo foi preparo
(mediana de 3,3 h), 8% deslocamento e 9% execução. Em MT: 89%, 6% e 5%. O arquivo da ANEEL não tem linhas repetidas para a EMS (245.157 linhas, 245.157 distintas).

## 5. Subestações

`reports/ems/subestacoes.csv` (63 subestações) e `figures/04_subestacoes.png`: Jardim, Sidrolândia e Iguatemi são as três que mais pesam no CHI (4,1%, 3,6% e 3,4%). O
"evitável" da figura usa o efeito de MT (rótulo `transportado de MT`) e é uma extrapolação do efeito médio. Nenhuma subestação é recomendada aqui sem validar o
efeito em MS.

## 6. Como reproduzir

```bash
export AUTOIMPACT_CONFIG=configs/ems.yaml
export AUTOIMPACT_BDGD_ZIPS=<pasta com os zips da BDGD de MS, somente leitura>
python scripts/01_build_equipamentos.py   # equipamentos por snapshot -> data/ems/interim
python scripts/00_diagnostico.py          # contagens da regra, sem estimar nada
python scripts/02_estimar.py              # aplica a regra; valor.json, subestacoes, elemento_2026
python scripts/04_figuras.py              # figuras 04 a 06
python scripts/03_atendimento.py          # baixa o arquivo nacional de ocorrências de 2025 e agrega a EMS
python scripts/05_did_escalonado.py       # só roda se a regra liberar o efeito próprio (hoje: recusa)
```

Os arquivos de `data/ems/` e o esquema de `valor.json` estão em [`saidas_ems.md`](saidas_ems.md).
