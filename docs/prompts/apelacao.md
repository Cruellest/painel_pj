# PROMPT: GERADOR DE RECURSO DE APELAÇÃO

## REGRA HIERÁRQUICA

Este prompt **complementa** o prompt de sistema e **não o substitui**.

Todas as regras do prompt de sistema permanecem válidas, especialmente:
- Regra de silêncio
- Regra de origem da argumentação
- Uso controlado dos autos
- Regras materiais de aplicação de temas
- Regras de estilo e formatação

---

## OBJETIVO

Elaborar **RECURSO DE APELAÇÃO** impugnando sentença desfavorável ao Estado de Mato Grosso do Sul, utilizando **exclusivamente** os fundamentos autorizados via módulos [VALIDADO].

---

## REGRA ABSOLUTA DE IMPUGNAÇÃO

Apelação impugna o que foi decidido **CONTRA** o Estado.

### Vedações

É **PROIBIDO**:
- Recorrer de aspectos decididos **favoravelmente** ao Estado
- Pedir afastamento de providências **não aplicadas** pela sentença
- Insistir no indeferimento de pedidos **já indeferidos**
- Reiterar teses **já acolhidas**

### Princípio Operacional

Antes de utilizar qualquer argumento [VALIDADO], verificar:

**"A sentença decidiu CONTRA o Estado neste ponto?"**
- SIM → Argumento pode ser utilizado
- NÃO → Argumento deve ser **DESCARTADO**

---

## ETAPA OBRIGATÓRIA: ANÁLISE E FILTRAGEM

**ATENÇÃO: Esta etapa é obrigatória mas NÃO deve aparecer na peça final. Execute mentalmente antes de redigir.**

### PASSO 1: MAPEAR A SENTENÇA

Extraia e classifique cada aspecto da sentença:

**a) Dispositivo:**
- Procedência total / parcial / improcedência?
- Quais pedidos foram deferidos?
- Quais pedidos foram indeferidos?

**b) Fundamentação:**
- Quais argumentos do Estado foram rejeitados?
- Quais argumentos do Estado foram acolhidos?
- Quais argumentos do Estado foram ignorados?

**c) Comandos específicos:**
Identifique todos os comandos estabelecidos pela sentença (forma de fornecimento, direcionamento de ente, prazos, multas, bloqueios, honorários, custas, orçamentos, ressarcimento, etc.) e classifique cada um como favorável ou desfavorável ao Estado.

### PASSO 2: CLASSIFICAR CADA ASPECTO

Para cada item acima, classifique:

- **FAVORÁVEL** = Sentença decidiu como o Estado queria → **NÃO RECORRER**
- **DESFAVORÁVEL** = Sentença decidiu contra o Estado → **RECORRER**
- **OMISSO** = Sentença não tratou do tema → **PODE SUSCITAR**
- **NÃO APLICÁVEL** = Não era cabível no caso → **IGNORAR**

### PASSO 3: FILTRAR ARGUMENTOS [VALIDADO]

Para cada argumento [VALIDADO] disponível:

**"A sentença decidiu CONTRA o Estado neste ponto?"**
- SIM → Pode usar
- NÃO → **DESCARTAR** (mesmo sendo [VALIDADO])

### PASSO 4: REDIGIR A APELAÇÃO

Use **APENAS** argumentos que impugnem decisões **DESFAVORÁVEIS** ou **OMISSAS**.

**Esta análise (Passos 1-4) NÃO deve aparecer na peça final.**

---

## TRANSMUTAÇÃO DOS ARGUMENTOS

A classificação da contestação não é estática no recurso:

| Situação na Sentença | Tratamento no Recurso |
|---|---|
| Preliminar rejeitada | Mérito recursal (seção 4 - subseção temática) |
| Preliminar acolhida | **Não recorrer** |
| Mérito rejeitado | Impugnação específica (seção 4 - subseção temática) |
| Mérito acolhido | **Não recorrer** |
| Eventualidade não atendida | Ver regra abaixo |
| Eventualidade atendida | **Não recorrer** |

**Regra especial para eventualidade não atendida:**

Primeiro, verificar: **O recurso pede IMPROCEDÊNCIA de algum pedido específico?**
- **NÃO** → Todos os argumentos de eventualidade da contestação viram **MÉRITO** no recurso (não há eventualidade recursal)
- **SIM** → A eventualidade só vai para SUBSIDIÁRIO se tiver **relação de subsidiariedade** com o pedido de improcedência

Exemplo quando **NÃO há pedido de improcedência** (mais comum em saúde):
- Contestação tinha: mérito (improcedência) + eventualidade (direcionamento, honorários, multa)
- Recurso aceita procedência, pede apenas reformas acessórias → **TUDO é MÉRITO** no recurso:
  - "Direcionamento ao Município" → MÉRITO (aceita procedência, quer reformar quem cumpre)
  - "Afastamento de honorários" → MÉRITO (questão autônoma)
  - "Substituição da multa" → MÉRITO (aceita procedência, quer reformar como cumpre)

Exemplo quando **HÁ pedido de improcedência**:
- Recurso pede improcedência de medicamento específico
- "Improcedência do medicamento X (sem registro ANVISA)" → MÉRITO
- "Caso mantida procedência do medicamento X: via PMVG" → SUBSIDIÁRIO (tem relação de subsidiariedade)
- "Direcionamento ao Município para medicamento Y" → MÉRITO (aceita procedência, não é subsidiário)

---

## FONTE PRIMÁRIA DE VERDADE

Utilize o **Parecer do NATJus** como fonte primária para informações técnicas.

Em caso de divergência entre NAT e sentença, utilizar o NAT para reforçar os argumentos [VALIDADO] e apontar expressamente a divergência como fundamento de reforma.

**Vedação:** Não extrair do NATJus teses jurídicas autônomas para impugnar a sentença.

---

## ESTRUTURA DO RECURSO

### Endereçamento

**À EGRÉGIA CÂMARA CÍVEL DO TRIBUNAL DE JUSTIÇA DO ESTADO DE MATO GROSSO DO SUL**

(Adaptar ao caso concreto. Nunca usar o nome do Desembargador.)




Apelação Cível
Apelante: Estado de Mato Grosso do Sul
Apelado(a): [nome completo da parte contrária]
Origem: [Vara] da Comarca de [Cidade] - MS
Processo nº: [número CNJ]

### Preâmbulo

O **ESTADO DE MATO GROSSO DO SUL**, pessoa jurídica de direito público interno, representado pela Procuradoria do Estado, interpõe o presente **RECURSO DE APELAÇÃO**, com fundamento no art. 1.009 do CPC, contra a sentença proferida pelo MM. Juízo da [Vara] da Comarca de [Cidade], pelos fatos e fundamentos a seguir expostos.

### Seções da Peça

**Estrutura padrão (sem pedido de improcedência):**
```
## 1. DA SÍNTESE DA DEMANDA E DA SENTENÇA
## 2. DOS REQUISITOS DE ADMISSIBILIDADE
## 3. DAS PRELIMINARES (somente se houver preliminares de apelação)
## 4. DAS RAZÕES RECURSAIS
### 4.1. [TEMA 1 - ex.: DO DIRECIONAMENTO AO MUNICÍPIO]
### 4.2. [TEMA 2 - ex.: DA SUBSTITUIÇÃO DA MULTA POR BLOQUEIO]
### 4.3. [TEMA 3 - ex.: DOS HONORÁRIOS SUCUMBENCIAIS]
## 5. DO PREQUESTIONAMENTO
## 6. DOS PEDIDOS
```

**Estrutura com eventualidade (quando há pedido de improcedência + subsidiário relacionado):**
```
## 1. DA SÍNTESE DA DEMANDA E DA SENTENÇA
## 2. DOS REQUISITOS DE ADMISSIBILIDADE
## 3. DAS PRELIMINARES (somente se houver preliminares de apelação)
## 4. DAS RAZÕES RECURSAIS
### 4.1. DA IMPROCEDÊNCIA DO PEDIDO DE [MEDICAMENTO/PROCEDIMENTO]
### 4.2. [OUTROS TEMAS - ex.: DO DIRECIONAMENTO AO MUNICÍPIO]
### 4.3. DOS PEDIDOS SUBSIDIÁRIOS
#### 4.3.1. CASO MANTIDA A PROCEDÊNCIA: [ex.: FORNECIMENTO VIA PMVG]
## 5. DO PREQUESTIONAMENTO
## 6. DOS PEDIDOS
```

**Regra:** A seção de "PEDIDOS SUBSIDIÁRIOS" só existe quando há **pedido de improcedência** de algum pedido específico E há **eventualidade com relação de subsidiariedade** a esse pedido. Na maioria dos casos de saúde (reformas acessórias como direcionamento, multa, honorários), usar a estrutura padrão com temas — não há eventualidade.

### Encerramento

Termos em que pede deferimento.

Campo Grande/MS, [DATA POR EXTENSO].

[NOME DO PROCURADOR]
Procurador do Estado
OAB/MS nº [NÚMERO]

---

## REGRAS POR SEÇÃO

### 1. DA SÍNTESE DA DEMANDA E DA SENTENÇA

- Resumo do processo
- Descrição objetiva do dispositivo da sentença
- Mencionar **apenas aspectos desfavoráveis** ao Estado
- Indicar o que se pretende reformar

### 2. DOS REQUISITOS DE ADMISSIBILIDADE

Demonstrar o preenchimento dos pressupostos recursais:
- Tempestividade
- Preparo (ou isenção da Fazenda Pública)
- Legitimidade e interesse recursal
- Regularidade formal

### 3. DAS PRELIMINARES (se houver)

**Incluir esta seção APENAS se houver preliminares de apelação a arguir**, tais como:
- Nulidade da sentença (falta de fundamentação, cerceamento de defesa, etc.)
- Nulidade processual não sanada
- Vícios que impeçam o exame do mérito

Somente se houver módulo [VALIDADO] correspondente.

**Se não houver preliminares, omitir esta seção inteiramente** (a numeração das seções seguintes deve ser ajustada).

### 4. DAS RAZÕES RECURSAIS

Impugnar especificamente cada fundamento desfavorável:
- Citar o trecho da sentença
- Demonstrar o erro judicial
- Apresentar fundamento jurídico correto (apenas se [VALIDADO])

**Organize por temas**, atacando cada fundamento desfavorável separadamente.

**Não mencionar** pontos já decididos favoravelmente.

#### Estrutura padrão: subseções por tema

Na maioria dos casos (quando o Estado pede apenas **reformas parciais**, sem improcedência total), cada aspecto desfavorável da sentença vira uma **subseção temática**:

```
## 4. DAS RAZÕES RECURSAIS
### 4.1. DO DIRECIONAMENTO DA OBRIGAÇÃO AO MUNICÍPIO E DIREITO DE RESSARCIMENTO
### 4.2. DA SUBSTITUIÇÃO DA MULTA COMINATÓRIA POR BLOQUEIO JUDICIAL
### 4.3. DO AFASTAMENTO DOS HONORÁRIOS SUCUMBENCIAIS
### 4.4. DA DISTRIBUIÇÃO DOS HONORÁRIOS ENTRE OS LITISCONSORTES
```

Cada subseção é um **pedido de mérito autônomo**. Não há hierarquia entre eles — todos buscam reformar aspectos específicos da sentença.

**IMPORTANTE - Argumentos conexos ficam na mesma subseção:**

Quando argumentos tratam da mesma questão jurídica, devem ficar **juntos**:
- Direcionamento ao Município + direito de ressarcimento = mesma subseção (decorrem da mesma tese de repartição de competências)
- Afastamento de honorários + distribuição entre litisconsortes = subseções separadas (são questões distintas)

#### Estrutura alternativa: mérito + subsidiário (rara)

Usar subseções "4.1. DO MÉRITO" e "4.2. DOS PEDIDOS SUBSIDIÁRIOS" **APENAS** quando:
1. O Estado pede **IMPROCEDÊNCIA TOTAL** da ação, E
2. Há pedidos **condicionados** à manutenção da procedência

Nesse caso:
- 4.1. DO MÉRITO: pedido de improcedência e fundamentos
- 4.2. DOS PEDIDOS SUBSIDIÁRIOS: "Caso mantida a procedência, então..."

#### 4.2. DOS PEDIDOS SUBSIDIÁRIOS (se houver)

**REGRA FUNDAMENTAL - Quando existe eventualidade:**

Eventualidade recursal **SÓ EXISTE** quando há **PEDIDO DE IMPROCEDÊNCIA** de algum pedido específico da ação.

O pedido subsidiário deve ter **relação de subsidiariedade** com o pedido de improcedência:
- **Pedido principal**: IMPROCEDÊNCIA de determinado pedido (ex.: medicamento, procedimento)
- **Pedido subsidiário**: alternativa CASO mantida a procedência daquele pedido específico

**REGRA DE DISTINÇÃO MÉRITO × EVENTUALIDADE:**

| Tipo de pedido recursal | Classificação |
|---|---|
| Pedido de **IMPROCEDÊNCIA** de algum pedido da ação | MÉRITO (pode gerar eventualidade relacionada) |
| Pedido de **DIRECIONAMENTO** ao Município | MÉRITO (não gera eventualidade - aceita procedência) |
| Pedido de **SUBSTITUIÇÃO** de multa por bloqueio | MÉRITO (não gera eventualidade - aceita procedência) |
| Pedido de **AFASTAMENTO** de honorários | MÉRITO (não gera eventualidade - questão autônoma) |
| Pedido **SUBSIDIÁRIO** ao de improcedência | EVENTUALIDADE (ex.: "se procedente: via PMVG") |

**Quando NÃO há eventualidade:**

Se o Estado **aceita a procedência** do pedido e quer apenas reformar **aspectos acessórios** (quem cumpre, como cumpre, prazo, multa, honorários), **NÃO há eventualidade** — são pedidos de mérito autônomos.

```
SITUAÇÃO: Estado aceita procedência, pede apenas reformas acessórias

❌ INCORRETO (separar em mérito e eventualidade):
Mérito:
  - Direcionamento ao Município
Eventualidade:
  - Substituição da multa por bloqueio
  - Afastamento dos honorários

✅ CORRETO (tudo no mérito, organizado por temas):
Razões Recursais:
  - 4.1. DO DIRECIONAMENTO AO MUNICÍPIO E DIREITO DE RESSARCIMENTO
  - 4.2. DA SUBSTITUIÇÃO DA MULTA COMINATÓRIA POR BLOQUEIO JUDICIAL
  - 4.3. DO AFASTAMENTO DOS HONORÁRIOS SUCUMBENCIAIS
(Não há seção de eventualidade - nenhum pedido é de improcedência)
```

**Quando HÁ eventualidade:**

Se o Estado pede **IMPROCEDÊNCIA** de algum pedido específico, pode haver eventualidade **relacionada a esse pedido**.

```
SITUAÇÃO: Ação com 3 medicamentos procedentes, Estado recorre de 1 pedindo improcedência

Razões Recursais:
  - 4.1. DA IMPROCEDÊNCIA DO PEDIDO DE FORNECIMENTO DO MEDICAMENTO X
    (ausência de registro ANVISA, existência de alternativa terapêutica, etc.)
Pedidos Subsidiários:
  - 4.2. CASO MANTIDA A PROCEDÊNCIA: FORNECIMENTO VIA PMVG
    (aplicação do Tema 1.161/STJ, aquisição pelo menor preço)

→ A eventualidade tem RELAÇÃO DE SUBSIDIARIEDADE com o pedido de improcedência
```

```
SITUAÇÃO: Estado pede improcedência total + direcionamento subsidiário

Razões Recursais:
  - 4.1. DA IMPROCEDÊNCIA (ausência dos requisitos)
Pedidos Subsidiários:
  - 4.2. CASO MANTIDA A PROCEDÊNCIA: DIRECIONAMENTO AO MUNICÍPIO
  - 4.3. CASO MANTIDA A PROCEDÊNCIA: FORNECIMENTO VIA SUS
```

```
SITUAÇÃO: Múltiplos pedidos - improcedência de um + reformas acessórias de outros

Razões Recursais:
  - 4.1. DA IMPROCEDÊNCIA DO PEDIDO DE MEDICAMENTO X (não tem registro ANVISA)
  - 4.2. DO DIRECIONAMENTO AO MUNICÍPIO PARA O MEDICAMENTO Y (aceita procedência)
  - 4.3. DA SUBSTITUIÇÃO DA MULTA POR BLOQUEIO
Pedidos Subsidiários:
  - 4.4. CASO MANTIDA A PROCEDÊNCIA DO MEDICAMENTO X: VIA PMVG

→ Eventualidade só existe para o pedido de improcedência (4.1 → 4.4)
→ Os demais são mérito autônomo (não geram eventualidade)
```

**Resumo operacional:**

1. O Estado pede **IMPROCEDÊNCIA** de algum pedido específico?
   - NÃO → **Não há eventualidade.** Todos os pedidos são mérito autônomo.
   - SIM → Pode haver eventualidade **relacionada ao pedido de improcedência**.

2. O pedido subsidiário tem **relação de subsidiariedade** com o pedido de improcedência?
   - SIM → É eventualidade válida (ex.: improcedência do medicamento → se procedente: PMVG)
   - NÃO → É mérito autônomo (ex.: direcionamento ao município é independente)

Somente incluir esta seção se houver módulo [VALIDADO] de eventualidade **E** existir pedido de improcedência **E** a eventualidade tiver relação de subsidiariedade com esse pedido.

### 5. DO PREQUESTIONAMENTO

Requerer ao Tribunal que se manifeste expressamente sobre os dispositivos legais e constitucionais invocados nas razões recursais, para fins de eventual interposição de recursos às instâncias superiores.

**Finalidade**: Viabilizar o acesso ao STF e STJ, caso necessário.

**Formato**: Pedido para que o acórdão aprecie expressamente:
- Dispositivos constitucionais invocados (ex.: art. 196, art. 198, § 1º, da CF)
- Dispositivos legais federais invocados (ex.: arts. 7º e 18 da Lei 8.080/90)

**ATENÇÃO - Temas vinculantes:**
- **NÃO** prequestionar o "Tema" em si (ex.: "Tema 793", "Tema 106")
- **SIM** prequestionar os **dispositivos legais e constitucionais** subjacentes ao tema
- Exemplo: Em vez de "prequestionar o Tema 793", prequestionar o "art. 198, § 1º, da CF" e o "art. 7º da Lei 8.080/90", que fundamentam a tese fixada naquele tema

É permitido **mencionar** o tema vinculante no corpo do prequestionamento para contextualização, mas o objeto do prequestionamento são os **dispositivos normativos**, não a numeração do tema.

### 6. DOS PEDIDOS

**Apenas** sobre o que se busca reformar:
- Conhecimento e provimento do recurso
- Reforma da sentença nos pontos especificados
- Resultado específico pretendido

**É PROIBIDO formular pedidos sobre aspectos favoráveis ou não aplicados.**

---

## DIRETRIZES

- **Dialeticidade:** Atacar cada fundamento desfavorável individualmente
- **Pertinência:** Só argumentar sobre o decidido **CONTRA** o Estado
- **Coerência:** Não pedir afastamento do que não foi aplicado
- **Especificidade:** Citar trechos da sentença antes de rebatê-los

---

## ARGUMENTOS [VALIDADO] - REGRA ESPECIAL PARA RECURSOS

**Argumento [VALIDADO] = juridicamente correto**
**Argumento aplicável = juridicamente correto + impugna decisão desfavorável**

Usar um argumento porque ele **IMPUGNA** algo decidido contra o Estado, não porque existe na lista.

Um argumento [VALIDADO] que não impugna aspecto desfavorável **DEVE SER DESCARTADO**.

---

## VALIDAÇÃO FINAL

- [ ] A sentença foi integralmente analisada?
- [ ] Cada argumento impugna algo **DESFAVORÁVEL**?
- [ ] Não há pedidos sobre aspectos favoráveis?
- [ ] O NATJus foi utilizado como fonte técnica (não como fonte de teses)?
- [ ] A análise de filtragem **NÃO** aparece na peça?
- [ ] Nenhum instituto jurídico foi introduzido sem validação?
- [ ] A estrutura segue o modelo definido neste prompt?
- [ ] Argumentos conexos estão **JUNTOS NO MÉRITO** (não separados entre mérito e eventualidade)?
- [ ] O prequestionamento menciona **dispositivos normativos**, não números de temas?
- [ ] **Se NÃO há pedido de improcedência, a seção de eventualidade foi OMITIDA?**
- [ ] **Se há eventualidade, ela tem relação de subsidiariedade com o pedido de improcedência?**
