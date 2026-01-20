# Relatório de Cobertura - Regras Determinísticas

**Gerado em:** 2026-01-20T02:54:46.153977

## Estatísticas Gerais

- Total de prompts determinísticos: 55
- Prompts ativos: 55
- Variáveis usadas: 75
- Prompts com fallback: 2
- Casos de teste gerados: 165

## Operadores Utilizados

- `and`
- `contains`
- `equals`
- `greater_than`
- `in_list`
- `less_or_equal`
- `or`

## Cobertura por Regra

| ID | Nome | Ativo | Variáveis | Casos Teste | Status |
|---|---|---|---|---|---|
| 15 | prel_jef_federal | Sim | 2 | 3 | COBERTA |
| 24 | prel_ileg_dano_moral | Sim | 2 | 3 | COBERTA |
| 27 | prel_nao_comparecimento | Sim | 1 | 3 | COBERTA |
| 44 | mer_enf24h | Sim | 2 | 3 | COBERTA |
| 26 | prel_transf_realizada | Sim | 2 | 3 | COBERTA |
| 29 | mer_cir_escolha_prof | Sim | 1 | 3 | COBERTA |
| 17 | prel_jf_canabidiol | Sim | 2 | 3 | COBERTA |
| 18 | prel_jf_grupo1a | Sim | 2 | 3 | COBERTA |
| 16 | prel_jf_sem_anvisa | Sim | 1 | 3 | COBERTA |
| 20 | prel_inepcia | Sim | 1 | 3 | COBERTA |
| 23 | prel_ileg_educacional | Sim | 2 | 3 | COBERTA |
| 33 | mer_sv_60_61 | Sim | 2 | 3 | COBERTA |
| 48 | mer_restituicao | Sim | 2 | 3 | COBERTA |
| 19 | prel_jf_nao_inc_210sm | Sim | 4 | 3 | COBERTA |
| 25 | prel_fraldas_interesse | Sim | 2 | 3 | COBERTA |
| 45 | mer_custo_efetividade | Sim | 2 | 3 | COBERTA |
| 59 | evt_tema_1033 | Sim | 6 | 3 | COBERTA |
| 55 | evt_mun_homecare | Sim | 1 | 3 | COBERTA |
| 63 | evt_multa | Sim | 2 | 3 | COBERTA |
| 34 | mer_med_pat_div | Sim | 3 | 3 | COBERTA |
| 51 | evt_mun_geral | Sim | 5 | 3 | COBERTA |
| 64 | evt_resp_pessoal | Sim | 2 | 3 | COBERTA |
| 30 | mer_sem_urgencia | Sim | 2 | 3 | COBERTA |
| 36 | mer_med_nao_inc_tema1234 | Sim | 6 | 3 | COBERTA |
| 62 | evt_tres_orcamentos | Sim | 10 | 3 | COBERTA |
| 60 | evt_med_sem_marca | Sim | 2 | 3 | COBERTA |
| 14 | prel_jef_estadual | Sim | 2 | 3 | COBERTA |
| 35 | mer_med_inc_tema1234 | Sim | 2 | 3 | COBERTA |
| 57 | evt_honorarios | Sim | 12 | 3 | COBERTA |
| 22 | mun_793 | Sim | 11 | 3 | COBERTA |
| 47 | mer_dano_moral | Sim | 1 | 3 | COBERTA |
| 43 | mer_homecare | Sim | 1 | 3 | COBERTA |
| 37 | mer_med_nao_inc_tema6 | Sim | 1 | 3 | COBERTA |
| 66 | honorarios_distribuicao_litisc | Sim | 2 | 3 | COBERTA |
| 38 | mer_med_sem_anvisa | Sim | 1 | 3 | COBERTA |
| 54 | evt_mun_insumos | Sim | 1 | 3 | COBERTA |
| 61 | evt_pmvg | Sim | 1 | 3 | COBERTA |
| 71 | orçamento_pacote | Sim | 1 | 3 | COBERTA |
| 40 | mer_insulina | Sim | 1 | 3 | COBERTA |
| 41 | mer_onco_sem_unacon | Sim | 2 | 3 | COBERTA |
| 56 | evt_mun_autismo | Sim | 2 | 3 | COBERTA |
| 28 | mer_cir_sem_esp_sus | Sim | 1 | 3 | COBERTA |
| 42 | mer_fraldas | Sim | 1 | 3 | COBERTA |
| 31 | mer_fila_eletivo | Sim | 4 | 3 | COBERTA |
| 21 | prel_doc_essencial | Sim | 2 | 3 | COBERTA |
| 39 | mer_med_offlabel | Sim | 1 | 3 | COBERTA |
| 32 | mer_dificuldade_gestor | Sim | 4 | 3 | COBERTA |
| 46 | mer_autismo | Sim | 1 | 3 | COBERTA |
| 49 | evt_direcionamento_793 | Sim | 10 | 3 | COBERTA |
| 52 | evt_mun_dieta | Sim | 2 | 3 | COBERTA |
| 50 | evt_mun_gestao_plena | Sim | 4 | 3 | COBERTA |
| 58 | evt_cirurgia_rede_publica | Sim | 2 | 3 | COBERTA |
| 53 | evt_mun_fraldas | Sim | 1 | 3 | COBERTA |
| 65 | honorarios_equidade_tema_1313 | Sim | 1 | 3 | COBERTA |
| 67 | honorarios_sv60_medicamentos_j | Sim | 5 | 3 | COBERTA |

## Detalhes das Regras

### Prompt 15: prel_jef_federal

**Título:** Competência do Juizado Especial Federal
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `valor_causa_inferior_60sm`
- `peticao_inicial_uniao_polo_passivo`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 24: prel_ileg_dano_moral

**Título:** Ilegitimidade Passiva do Estado - Dano Moral em Transferência Hospitalar
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_dano_moral`
- `peticao_inicial_pedido_transferencia_hospitalar`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 27: prel_nao_comparecimento

**Título:** Do Não Comparecimento à Audiência
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `decisoes_audiencia_inicial`

**Casos de teste gerados:**

- [POSITIVO] Variável 'decisoes_audiencia_inicial' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'decisoes_audiencia_inicial' NÃO satisfaz condição 'equals'
- [NULL] Variável 'decisoes_audiencia_inicial' é null/ausente (esperado: False)

### Prompt 44: mer_enf24h

**Título:** Atendimento de Enfermagem 24 Horas por Dia
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_pedido_enfermeiro_24h`
- `peticao_inicial_pedido_enfermeiro_24h`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 26: prel_transf_realizada

**Título:** Perda do Objeto - Transferência Hospitalar Realizada
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_paciente_transferido`
- `peticao_inicial_pedido_transferencia_hospitalar`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 29: mer_cir_escolha_prof

**Título:** Não Há Direito à Escolha do Profissional em Face do SUS
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_procedimento_profissional_especifico`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_procedimento_profissional_especifico' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_procedimento_profissional_especifico' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_procedimento_profissional_especifico' é null/ausente (esperado: False)

### Prompt 17: prel_jf_canabidiol

**Título:** Competência da Justiça Federal - Produto à Base de Canabidiol
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_canabidiol`
- `peticao_inicial_uniao_polo_passivo`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 18: prel_jf_grupo1a

**Título:** Competência da Justiça Federal - Medicamentos Grupo 1A CEAF (Tema 1234)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_1a`
- `peticao_inicial_uniao_polo_passivo`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 16: prel_jf_sem_anvisa

**Título:** Competência da Justiça Federal - Medicamento sem Registro na ANVISA (Tema 500)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_sem_anvisa`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_medicamento_sem_anvisa' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_medicamento_sem_anvisa' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_medicamento_sem_anvisa' é null/ausente (esperado: False)

### Prompt 20: prel_inepcia

**Título:** Inépcia da Petição Inicial - Pedido Genérico
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_generico`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_generico' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_generico' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_generico' é null/ausente (esperado: False)

### Prompt 23: prel_ileg_educacional

**Título:** Ilegitimidade Passiva do Estado - Atendimento Educacional
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_professor_apoio`
- `peticao_inicial_professor_ens_basico`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 33: mer_sv_60_61

**Título:** Súmulas Vinculantes nº 60 e 61 sobre Medicamentos
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_medicamento`
- `pareceres_analisou_medicamento`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 48: mer_restituicao

**Título:** Da Restituição de Eventuais Valores Despendidos
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_ressarcimento`
- `peticao_inicial_pedido_restituicao_valores`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 19: prel_jf_nao_inc_210sm

**Título:** Competência da Justiça Federal - Medicamentos Não Incorporados > 210 SM (Tema 1234)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `valor_causa_superior_210sm`
- `pareceres_medicamento_nao_incorporado_sus`
- `uniao_polo_passivo`
- `processo_ajuizado_apos_2024_09_19`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 25: prel_fraldas_interesse

**Título:** Ausência de Interesse Processual - Fraldas
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_fralda_adm`
- `peticao_inicial_pedido_fraldas`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 45: mer_custo_efetividade

**Título:** Custo-Efetividade do Pedido
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_nao_incorporado_sus`
- `valor_causa_numerico`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 59: evt_tema_1033

**Título:** Reembolso a Agente Privado - Tema 1.033
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `residual_transferencia_vaga_hospitalar`
- `sentenca_afastamento_1033_stf`
- `peticao_inicial_pedido_cirurgia`
- `pareceres_analisou_transferencia`
- `decisoes_afastamento_tema_1033_stf`
- `peticao_inicial_pedido_transferencia_hospitalar`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 55: evt_mun_homecare

**Título:** Responsabilidade do Município - Atendimento Domiciliar
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_home_care`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_home_care' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_home_care' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_home_care' é null/ausente (esperado: False)

### Prompt 63: evt_multa

**Título:** Multa Cominatória
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `decisoes_fixacao_multa_cominatoria`
- `sentenca_fixacao_multa_cominatoria`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 34: mer_med_pat_div

**Título:** Medicamento Não Incorporado para Situação Clínica da Parte Autora
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_dosagem_diversa_incorporada`
- `pareceres_patologia_diversa_incorporada`
- `pareceres_dispensacao_diversa_incorporada`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 51: evt_mun_geral

**Título:** Responsabilidade do Município - Procedimentos
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_procedimentos`
- `municipio_polo_passivo`
- `peticao_inicial_pedido_exame`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_consulta`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 64: evt_resp_pessoal

**Título:** Não Responsabilização Pessoal do Agente Público
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `decisoes_responsabilizacao_pessoal_agente`
- `sentenca_responsabilizacao_pessoal`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 30: mer_sem_urgencia

**Título:** Não Há Urgência ou Emergência para o Atendimento
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_carater_exame`
- `pareceres_natureza_cirurgia`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 36: mer_med_nao_inc_tema1234

**Título:** Análise de Medicamentos Não Incorporados - Tema 1234
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_dispensacao_diversa_incorporada`
- `pareceres_medicamento_nao_incorporado_sus`
- `pareceres_dosagem_diversa_incorporada`
- `pareceres_medicamento_oncologico`
- `pareceres_medicamento_oncologico_incorporado`
- `pareceres_patologia_diversa_incorporada`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 62: evt_tres_orcamentos

**Título:** Exigência de Três Orçamentos
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_exame`
- `peticao_inicial_pedido_dieta_suplemento`
- `peticao_inicial_tratamentos`
- `peticao_inicial_pedido_consulta`
- `peticao_inicial_pedido_transferencia_hospitalar`
- `peticao_inicial_pedido_medicamento`
- `peticao_inicial_procedimentos`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_home_care`
- `peticao_inicial_equipamentos_materiais`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 60: evt_med_sem_marca

**Título:** Fornecimento Sem Vinculação a Nome Comercial (se a parte usou o princípio ativo e entre parênteses usou o nome comercial, não é pedido pelo nome comercial)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_medicamento`
- `peticao_inicial_medicamento_nome_comercial`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 14: prel_jef_estadual

**Título:** Competência do Juizado Especial da Fazenda Pública
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `valor_causa_inferior_60sm`
- `peticao_inicial_juizado_justica_comum`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 35: mer_med_inc_tema1234

**Título:** Análise de Medicamentos Incorporados ao SUS - Tema 1234
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_analisou_insulina`
- `pareceres_medicamento_incorporado_sus`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 57: evt_honorarios

**Título:** Não Condenação em Honorários de Sucumbência
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_exame`
- `peticao_inicial_pedido_fraldas`
- `peticao_inicial_pedido_consulta`
- `pareceres_medicamento_cbaf`
- `peticao_inicial_internacao_involuntaria`
- `peticao_inicial_pedido_transferencia_hospitalar`
- `peticao_inicial_pedido_medicamento`
- `uniao_polo_passivo`
- `peticao_inicial_pedido_professor_apoio`
- `municipio_polo_passivo`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_dieta_suplemento`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 22: mun_793

**Título:** Litisconsórcio Necessário do Município (Tema 793)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_home_care`
- `peticao_inicial_pedido_exame`
- `peticao_inicial_pedido_fraldas`
- `peticao_inicial_pedido_consulta`
- `peticao_inicial_internacao_involuntaria`
- `peticao_inicial_pedido_transferencia_hospitalar`
- `peticao_inicial_pedido_professor_apoio`
- `municipio_polo_passivo`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_treatmento_autismo`
- `peticao_inicial_pedido_dieta_suplemento`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 47: mer_dano_moral

**Título:** Não Há Dano Moral
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_dano_moral`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_dano_moral' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_dano_moral' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_dano_moral' é null/ausente (esperado: False)

### Prompt 43: mer_homecare

**Título:** Atendimento em Regime de Home Care
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_home_care`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_home_care' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_home_care' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_home_care' é null/ausente (esperado: False)

### Prompt 37: mer_med_nao_inc_tema6

**Título:** Análise de Medicamentos Não Incorporados - Tema 6
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_nao_incorporado_sus`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_medicamento_nao_incorporado_sus' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_medicamento_nao_incorporado_sus' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_medicamento_nao_incorporado_sus' é null/ausente (esperado: False)

### Prompt 66: honorarios_distribuicao_litisconsortes

**Título:** Distribuição da Responsabilidade pelos Honorários entre Litisconsortes (Art. 87, § 1º, CPC)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `sentenca_multiplos_entes_condenados`
- `sentenca_honorarios_divididos_litisconsortes`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 38: mer_med_sem_anvisa

**Título:** Medicamento Sem Registro na ANVISA - Tema 500
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_sem_anvisa`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_medicamento_sem_anvisa' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_medicamento_sem_anvisa' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_medicamento_sem_anvisa' é null/ausente (esperado: False)

### Prompt 54: evt_mun_insumos

**Título:** Responsabilidade do Município - Insumos e Equipamentos
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_equipamentos_materiais`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_equipamentos_materiais' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_equipamentos_materiais' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_equipamentos_materiais' é null/ausente (esperado: False)

### Prompt 61: evt_pmvg

**Título:** Preço Máximo de Venda ao Governo (PMVG)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_medicamento`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_medicamento' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_medicamento' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_medicamento' é null/ausente (esperado: False)

### Prompt 71: orçamento_pacote

**Título:** INADMISSÃO DE ORÇAMENTO DO TIPO "PACOTE" 
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_cirurgia`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_cirurgia' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_cirurgia' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_cirurgia' é null/ausente (esperado: False)

### Prompt 40: mer_insulina

**Título:** O SUS Fornece Insulinas Semelhantes
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_analisou_insulina`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_analisou_insulina' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_analisou_insulina' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_analisou_insulina' é null/ausente (esperado: False)

### Prompt 41: mer_onco_sem_unacon

**Título:** A Parte Autora Não Buscou o Atendimento Oncológico do SUS
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_oncologico`
- `pareceres_onco_cacon_unacon`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 56: evt_mun_autismo

**Título:** Responsabilidade do Município - Terapias TEA
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_tratamento_autismo`
- `peticao_inicial_pedido_treatmento_autismo`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 28: mer_cir_sem_esp_sus

**Título:** Não Há Indicação Cirúrgica por Médico Especialista do SUS
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_laudo_medico_sus`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_laudo_medico_sus' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_laudo_medico_sus' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_laudo_medico_sus' é null/ausente (esperado: True)

### Prompt 42: mer_fraldas

**Título:** Fraldas Descartáveis
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_fraldas`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_fraldas' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_fraldas' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_fraldas' é null/ausente (esperado: False)

### Prompt 31: mer_fila_eletivo

**Título:** É Preciso Respeitar a Fila de Atendimento Eletivo
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_inserido_sisreg`
- `pareceres_natureza_cirurgia`
- `pareceres_tempo_sisreg_dias`
- `pareceres_carater_exame`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 21: prel_doc_essencial

**Título:** Falta de Documento Essencial - Prescrição Médica
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_medicamento`
- `documento_e_prescricao_medica`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 39: mer_med_offlabel

**Título:** Medicamento para Uso Off Label - Tema 106
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_medicamento_off_label`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_medicamento_off_label' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_medicamento_off_label' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_medicamento_off_label' é null/ausente (esperado: False)

### Prompt 32: mer_dificuldade_gestor

**Título:** É Preciso Considerar a Dificuldade Real do Gestor Estadual
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_consulta`
- `peticao_inicial_pedido_exame`
- `pareceres_inserido_core`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 46: mer_autismo

**Título:** Não É Aconselhável a Predefinição de Método Específico - TEA
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_terapia_especifica_autismo`

**Casos de teste gerados:**

- [POSITIVO] Variável 'pareceres_terapia_especifica_autismo' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'pareceres_terapia_especifica_autismo' NÃO satisfaz condição 'equals'
- [NULL] Variável 'pareceres_terapia_especifica_autismo' é null/ausente (esperado: False)

### Prompt 49: evt_direcionamento_793

**Título:** Direcionamento e Direito de Ressarcimento - Tema 793
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_exame`
- `peticao_inicial_pedido_fraldas`
- `peticao_inicial_equipamentos_materiais`
- `peticao_inicial_pedido_consulta`
- `peticao_inicial_pedido_transferencia_hospitalar`
- `municipio_polo_passivo`
- `peticao_inicial_pedido_treatmento_autismo`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_home_care`
- `peticao_inicial_pedido_dieta_suplemento`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 52: evt_mun_dieta

**Título:** Responsabilidade do Município - Alimentação e Nutrição
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_analisou_dieta`
- `peticao_inicial_pedido_dieta_suplemento`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 50: evt_mun_gestao_plena

**Título:** Responsabilidade do Município - Gestão Plena
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_municipio_acao`
- `peticao_inicial_pedido_cirurgia`
- `peticao_inicial_pedido_exame`
- `peticao_inicial_procedimentos`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa

### Prompt 58: evt_cirurgia_rede_publica

**Título:** Realização da Cirurgia pela Rede Pública
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `pareceres_analisou_cirurgia`
- `peticao_inicial_pedido_cirurgia`

**Casos de teste gerados:**

- [NEGATIVO] OR: todas as condições são falsas
- [POSITIVO] OR: apenas primeira condição é verdadeira
- [POSITIVO] OR: apenas última condição é verdadeira

### Prompt 53: evt_mun_fraldas

**Título:** Responsabilidade do Município - Fraldas
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `peticao_inicial_pedido_fraldas`

**Casos de teste gerados:**

- [POSITIVO] Variável 'peticao_inicial_pedido_fraldas' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'peticao_inicial_pedido_fraldas' NÃO satisfaz condição 'equals'
- [NULL] Variável 'peticao_inicial_pedido_fraldas' é null/ausente (esperado: False)

### Prompt 65: honorarios_equidade_tema_1313

**Título:** Honorários por Equidade em Demandas de Saúde (Tema 1.313/STJ)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `sentenca_criterio_honorarios`

**Casos de teste gerados:**

- [POSITIVO] Variável 'sentenca_criterio_honorarios' satisfaz condição 'equals' com valor esperado
- [NEGATIVO] Variável 'sentenca_criterio_honorarios' NÃO satisfaz condição 'equals'
- [NULL] Variável 'sentenca_criterio_honorarios' é null/ausente (esperado: False)

### Prompt 67: honorarios_sv60_medicamentos_jf

**Título:** Ausência de Condenação do Estado em Honorários em Demandas de Medicamentos na Justiça Federal (Súmula Vinculante nº 60)
**Tipo:** conteudo
**Ativo:** Sim

**Regra (texto original):**
> None

**Variáveis utilizadas:**
- `sentenca_condenacao_honorarios`
- `peticao_inicial_pedido_medicamento`
- `uniao_polo_passivo`
- `sentenca_entes_condenados_lista`
- `estado_polo_passivo`

**Casos de teste gerados:**

- [POSITIVO] AND: todas as condições são verdadeiras
- [NEGATIVO] AND: primeira condição é falsa
- [NEGATIVO] AND: última condição é falsa
