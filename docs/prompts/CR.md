# PROMPT: GERADOR DE CONTRARRAZÕES

## REGRA HIERÁRQUICA

Este prompt **complementa** o prompt de sistema. Todas as regras do prompt de sistema permanecem válidas.

---

## OBJETIVO

Elaborar **CONTRARRAZÕES** ao recurso interposto, utilizando **exclusivamente** os fundamentos autorizados via módulos [VALIDADO].

---

## REGRA FUNDAMENTAL

Contrarrazões respondem ao **RECURSO**, não à inicial.

### Teste Obrigatório (aplicar a CADA argumento)

| Pergunta | Resposta | Ação |
|----------|----------|------|
| O recorrente atacou este ponto? | NÃO | **DESCARTAR** |
| O recorrente fez este pedido? | NÃO | **NÃO FORMULAR CONTRAPEDIDO** |

### Vedações

- Reapresentar argumentos sobre pontos **não recorridos**
- Usar argumentos só porque estão marcados como [VALIDADO]
- Incluir eventualidade sobre pontos não recorridos
- Pleitear majoração de honorários em favor do Estado

---

## RECURSO DE MUNICÍPIO (LITISCONSÓRCIO PASSIVO)

Quando o **MUNICÍPIO** interpõe o recurso, o Estado é **litisconsorte passivo**. Argumentos que reduzem ou afastam a condenação **BENEFICIAM O ESTADO**.

### Classificação Obrigatória de TODAS as Teses (inclusive preliminares)

**ATENÇÃO:** Classificar **CADA TESE** do recurso do Município, incluindo preliminares.

| Classificação | Descrição | Tratamento |
|---------------|-----------|------------|
| **PREJUDICIAL** | Transfere responsabilidade ao Estado, exclui o Município, agrava posição do Estado | ✅ **IMPUGNAR** |
| **FAVORÁVEL** | Extingue o processo, afasta ou reduz a condenação, beneficia ambos os réus | ❌ **NÃO IMPUGNAR** |
| **NEUTRO** | Não afeta o Estado | ❌ **NÃO IMPUGNAR** |

**Exemplos de teses PREJUDICIAIS** (impugnar):
- Exclusão do Município do polo passivo
- Transferência de responsabilidade ao Estado
- Concentração da execução no Estado

**Exemplos de teses FAVORÁVEIS** (NÃO impugnar):
- **Inépcia da inicial** (se acolhida, extingue o processo = bom para o Estado)
- **Improcedência do pedido** (afasta a condenação de ambos)
- Prescrição, decadência
- Falta de prova do direito
- Redução de multa ou honorários

### Estrutura em Litisconsórcio

1. **Síntese seletiva**: Apenas teses que serão impugnadas
2. **Mérito cirúrgico**: Apenas pontos prejudiciais
3. **Silêncio estratégico**: Não mencionar teses favoráveis
4. **Pedido específico**: Desprovimento apenas quanto aos pontos impugnados

### Vedações em Litisconsórcio

- Expressões genéricas como "as razões recursais não merecem prosperar"
- Pedir desprovimento total quando só parte das teses é prejudicial
- Defender manutenção integral da sentença quando há teses favoráveis ao Estado

---

## TEMA 793/STF (OBRIGATÓRIO EM SAÚDE)

O Tema 793 estabelece um **binômio**:

| Componente | Significado |
|------------|-------------|
| **Solidariedade jurídica** | Todos podem ser demandados (legitimidade) |
| **Direcionamento executivo** | Cumprimento pelo ente competente |

### Posição do Direcionamento (MUTUAMENTE EXCLUSIVA)

**⚠️ REGRA CRÍTICA:** O direcionamento aparece **OU** no mérito **OU** na eventualidade. **NUNCA NOS DOIS.**

| Estratégia do Estado | Direcionamento vai onde? |
|---------------------|--------------------------|
| Estado **IMPUGNA** o recurso do Município | **APENAS NO MÉRITO** |
| Estado **CONCORDA** com a improcedência | **APENAS NA EVENTUALIDADE** |

**Se Estado IMPUGNA** (quer manter a condenação) → Direcionamento **NO MÉRITO**:
> Ainda que reconhecida a responsabilidade solidária (Tema 793/STF), o próprio precedente impõe que o cumprimento seja direcionado ao ente com competência administrativa primária. A execução deve ser direcionada ao Município.

**Se Estado CONCORDA** com improcedência → Direcionamento **NA EVENTUALIDADE**:
> Caso mantida a procedência, requer-se que a execução seja direcionada ao Município, nos termos do Tema 793/STF.

### Vedações sobre Tema 793

- Invocar apenas para "manter solidariedade" sem direcionamento
- Colocar direcionamento na eventualidade quando Estado **impugna** o recurso
- **REPETIR** o direcionamento (uma vez no mérito, outra na eventualidade)

---

## ANÁLISE PRÉVIA (não incluir na peça)

### Passo 1: Identificar Recorrente
- **AUTOR** → impugnar normalmente
- **MUNICÍPIO** → aplicar regras de litisconsórcio

### Passo 2: Identificar Objeto do Recurso
- O que exatamente o recorrente quer reformar?
- Quais capítulos foram atacados?

### Passo 3: Filtrar Argumentos [VALIDADO]
- Argumento responde ao recurso? SIM → usar. NÃO → descartar.

---

## ESTRUTURA DA PEÇA

### Cabeçalho

**À EGRÉGIA CÂMARA CÍVEL DO TRIBUNAL DE JUSTIÇA DO ESTADO DE MATO GROSSO DO SUL**

[Tipo do Recurso]: [Apelação Cível / Agravo de Instrumento]
Recorrente: [nome]
Recorrido: Estado de Mato Grosso do Sul
Origem: [Vara] da Comarca de [Cidade] - MS
Processo nº: [número CNJ]

### Preâmbulo

O **ESTADO DE MATO GROSSO DO SUL**, pessoa jurídica de direito público interno, representado pela Procuradoria do Estado, vem apresentar **CONTRARRAZÕES** ao recurso interposto pela parte adversa, pelos fatos e fundamentos a seguir expostos.

### Seções

```
## 1. DA SÍNTESE DO RECURSO
## 2. DAS PRELIMINARES DE INADMISSIBILIDADE (se módulo [VALIDADO])
## 3. DO MÉRITO
## 4. DA EVENTUALIDADE (se módulo [VALIDADO] relacionado ao recurso)
## 5. DOS PEDIDOS
```

### Encerramento

Termos em que pede deferimento.

Campo Grande/MS, [DATA POR EXTENSO].

[NOME DO PROCURADOR]
Procurador do Estado
OAB/MS nº [NÚMERO]

---

## REGRAS POR SEÇÃO

### 1. Síntese do Recurso
- Resumo objetivo das razões do recorrente
- Mencionar **apenas** pontos que serão efetivamente impugnados

### 2. Preliminares (se houver módulo [VALIDADO])
- Cada preliminar em subtópico próprio

### 3. Mérito
- **ESPELHO DO RECURSO**: cada subseção corresponde a um argumento **DO RECURSO**
- Seguir a mesma ordem dos argumentos do recurso
- Usar apenas argumentos [VALIDADO] que defendam pontos recorridos
- **PROIBIDO** criar subseções sobre temas que **não foram objeto do recurso**

**Teste para cada subseção:** "O Município recorreu sobre isso?"
- SIM → pode incluir
- NÃO → **PROIBIDO**

### 4. Eventualidade (se houver módulo [VALIDADO])

**REGRA RÍGIDA:** Eventualidade **SÓ EXISTE** se:
1. Houver módulo [VALIDADO] de eventualidade, **E**
2. O ponto foi **OBJETO DO RECURSO**

| O recurso tratou desse tema? | Pode incluir na eventualidade? |
|------------------------------|--------------------------------|
| SIM | ✅ Pode (se houver módulo) |
| NÃO | ❌ **PROIBIDO** |

**Exemplo:** Se o recurso trata de "exclusão do Município" e "improcedência":
- ❌ **NÃO** cabe eventualidade sobre três orçamentos (não foi recorrido)
- ❌ **NÃO** cabe eventualidade sobre PMVG (não foi recorrido)
- ❌ **NÃO** cabe eventualidade sobre restituição de valores (não foi recorrido)
- ❌ **NÃO** cabe direcionamento na eventualidade SE o Estado impugnou no mérito

**IMPORTANTE:** Se o Estado **IMPUGNA** o recurso do Município e coloca o direcionamento no **MÉRITO**, a seção de eventualidade pode ficar **VAZIA** ou **NÃO EXISTIR**. Isso é correto.

### 5. Pedidos

**Recurso de Autor:**
> No mérito, requer-se o desprovimento do recurso e a manutenção da decisão recorrida.

**Recurso de Município (litisconsorte):**
> Requer-se o desprovimento do recurso **quanto à pretensão de [teses prejudiciais específicas]**, mantendo-se [o que deve ser mantido].

---

## TRANSMUTAÇÃO EM SEDE RECURSAL

| Classificação Original | Tratamento nas Contrarrazões |
|------------------------|------------------------------|
| Acolhido e impugnado | Defender como acerto da decisão |
| Rejeitado/não impugnado | **Ignorar** |

---

## VALIDAÇÃO FINAL

### Geral
- [ ] Recorrente identificado (Autor ou Município)?
- [ ] Cada subseção corresponde a tema do recurso?
- [ ] Não há argumentos sobre pontos não recorridos?

### Litisconsórcio (se Município)
- [ ] Teses classificadas (prejudicial/favorável)?
- [ ] Apenas teses prejudiciais impugnadas?
- [ ] Pedido específico (não genérico)?

### Tema 793 (se saúde)
- [ ] Direcionamento incluído?
- [ ] Posição correta (mérito se impugna, eventualidade se concorda)?

### Teste Final
**"O recorrente atacou este ponto?"** → Se NÃO para qualquer seção, **REMOVER**.
