# PROMPT PARA GERAÇÃO DE CONTESTAÇÃO EM AÇÕES DE SAÚDE

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

Elaborar contestação em defesa do Estado de Mato Grosso do Sul, em ação judicial de saúde, utilizando **exclusivamente** os fundamentos autorizados via módulos [VALIDADO].

---

## ESTRUTURA DA PEÇA

### Endereçamento

**AO JUÍZO DA [VARA] DA COMARCA DE [CIDADE] - MS**

(Adaptar ao caso concreto. Nunca usar o nome do Juiz.)




Processo nº: [número CNJ]
Requerente: [nome completo da parte autora]
Requerido(s): [Estado de Mato Grosso do Sul e outros, se houver]

### Preâmbulo

O **ESTADO DE MATO GROSSO DO SUL**, pessoa jurídica de direito público interno, com sede na capital deste estado, no Parque dos Poderes, Bloco IV, representado pela Procuradoria do Estado, apresenta **CONTESTAÇÃO** nos autos da ação em epígrafe, pelos fatos e fundamentos a seguir expostos.

### Seções da Peça

```
## 1. DOS FATOS
## 2. DAS PRELIMINARES (somente se houver módulo [VALIDADO])
## 3. DO MÉRITO
## 4. DA EVENTUALIDADE (somente se houver módulo [VALIDADO])
## 5. DOS PEDIDOS
```

### Encerramento

Termos em que pede deferimento.

Campo Grande/MS, [DATA POR EXTENSO].

[NOME DO PROCURADOR]
Procurador do Estado
OAB/MS nº [NÚMERO]

---

## FONTE PRIMÁRIA DE VERDADE (TÉCNICA)

O **Parecer do Núcleo de Apoio Técnico do Judiciário (NATJus)** é a fonte central e prioritária para informações técnicas.

### Utilização Obrigatória

Extrair do NATJus:
- Status do medicamento ou procedimento (incorporado, não incorporado, sem registro na ANVISA)
- Indicação terapêutica e adequação ao caso concreto
- Existência de alternativas terapêuticas disponíveis no SUS
- Análise de eficácia, segurança e evidências científicas
- Identificação do ente federativo responsável pelo fornecimento
- Conclusão técnica (favorável ou desfavorável ao pleito)

### Regra de Prevalência Técnica

Havendo divergência entre o parecer do NATJus e outros documentos dos autos (laudos médicos particulares, prescrições, relatórios clínicos), **devem prevalecer as conclusões técnicas do NAT**, cabendo à contestação apontar expressamente tais divergências como fundamento de defesa.

---

## DOCUMENTOS A ANALISAR

### Análise Obrigatória
1. Parecer do NATJus
2. Petição Inicial
3. Decisão liminar ou tutela de urgência, se existente

### Análise Complementar (quando presentes nos autos)
4. Laudos e prescrições médicas
5. Comprovantes de residência e hipossuficiência
6. Documentos administrativos sobre pedido prévio ao SUS
7. Orçamentos apresentados

---

## REGRA CRÍTICA: FONTE DE VERDADE PARA IDENTIFICAÇÃO DOS PEDIDOS

### Princípio Fundamental

Os **PEDIDOS** da ação são definidos **EXCLUSIVAMENTE** pela **PETIÇÃO INICIAL**, não pelos documentos anexos.

A prescrição médica, laudos, receitas e outros anexos são **documentos probatórios** — servem para fundamentar os pedidos, mas **NÃO os definem**.

### Vedação Absoluta

É **PROIBIDO**:
- Considerar como pedido algo que consta apenas na prescrição médica, mas não na inicial
- Confundir medicamentos prescritos com medicamentos efetivamente pedidos
- Ampliar o objeto da lide com base em documentos anexos
- Contestar itens que não foram pedidos na inicial

### Regra de Verificação

Antes de redigir os fatos e o mérito, **verificar com precisão**:

**"Este item foi PEDIDO na petição inicial?"**
- SIM → Contestar
- NÃO (apenas consta na prescrição/laudo) → **NÃO CONTESTAR**

### Exemplo Prático

```
SITUAÇÃO:
- Prescrição médica: Medicamento A, Medicamento B, Medicamento C
- Petição inicial: Pede apenas Medicamento A

ANÁLISE CORRETA:
- Medicamento A → ✅ CONTESTAR (foi pedido na inicial)
- Medicamento B → ❌ NÃO MENCIONAR (não foi pedido)
- Medicamento C → ❌ NÃO MENCIONAR (não foi pedido)

A contestação deve tratar APENAS do Medicamento A.
```

```
SITUAÇÃO:
- Prescrição médica: Insulina Glargina 100UI + Insulina Asparte
- Petição inicial: Pede apenas Insulina Glargina 100UI

❌ INCORRETO (Fatos):
"A parte autora requer o fornecimento de Insulina Glargina 100UI
e Insulina Asparte..."

✅ CORRETO (Fatos):
"A parte autora requer o fornecimento de Insulina Glargina 100UI..."

→ A Insulina Asparte não foi pedida, logo não deve ser mencionada.
```

### Hierarquia de Fontes para Pedidos

| Documento | Função | Define pedidos? |
|---|---|---|
| Petição Inicial | Define o objeto da lide | ✅ SIM |
| Prescrição Médica | Prova a indicação médica | ❌ NÃO |
| Laudo Médico | Prova a necessidade clínica | ❌ NÃO |
| Parecer NATJus | Análise técnica dos pedidos | ❌ NÃO |
| Decisão Liminar | Define tutela provisória | ❌ NÃO |

### Aplicação nos Fatos

Ao redigir os fatos, informar **apenas** os pedidos que constam na petição inicial:

```
✅ CORRETO:
"A parte autora ajuizou a presente demanda objetivando o fornecimento
do medicamento [X], conforme pedido formulado na petição inicial."

❌ INCORRETO:
"A parte autora ajuizou a presente demanda objetivando o fornecimento
dos medicamentos [X, Y e Z], conforme prescrição médica anexa."
```

---

## REGRAS PARA SEÇÃO DE FATOS

Na redação do tópico **FATOS**, incluir **obrigatoriamente**:

1. **Pedidos da inicial**: Informar expressamente quais são os pedidos formulados **NA PETIÇÃO INICIAL** (não na prescrição médica ou outros anexos)
2. **Conclusão do NATJus**: Indicar a conclusão do parecer em relação ao pleito (favorável ou desfavorável)
3. **Situação da tutela**: Registrar se houve ou não deferimento de tutela de urgência (concedida, indeferida ou ainda não apreciada)
4. **Dados relevantes**: Tipo de tratamento/medicamento, valores, ente indicado como responsável

### Vedações na Seção de Fatos

É **VEDADO**:
- Redigir os fatos de forma genérica ou incompleta, sem menção explícita aos elementos acima
- **Confundir prescrição médica com pedidos** — a prescrição pode conter mais itens do que os efetivamente pedidos
- Mencionar medicamentos/procedimentos que constam apenas em anexos, mas não foram pedidos na inicial
- Ampliar o objeto da demanda com base em documentos probatórios

### Verificação Obrigatória

Antes de redigir os fatos, confirmar:
- [ ] Os pedidos listados estão **expressamente formulados na petição inicial**?
- [ ] Não foram incluídos itens que constam apenas na prescrição/laudo?

---

## REGRAS PARA SEÇÃO DE PRELIMINARES

### Condição de Existência

A seção de preliminares **SÓ EXISTE** se houver módulo [VALIDADO] de preliminar ativado.

Sem módulo [VALIDADO] de preliminar = **SEM SEÇÃO DE PRELIMINARES**.

### Regra de Desenvolvimento

Cada preliminar autorizada via módulo [VALIDADO] deve:
- Ter subtópico próprio (### 2.N.)
- Ser desenvolvida com aderência estrita ao caso concreto
- Não ultrapassar o escopo do módulo validado

É **PROIBIDO** criar preliminares por inferência, analogia ou "pertinência ao caso".

---

## REGRAS PARA SEÇÃO DE MÉRITO

### Função da Seção

O mérito tem função **estritamente aplicativa**: aplicar a lógica técnica constante dos pareceres dos autos aos fundamentos jurídicos **já validados**.

### Vedação de Criação

É **PROIBIDO**:
- Criar objeções jurídicas não autorizadas por módulo [VALIDADO]
- Introduzir temas, súmulas ou precedentes não validados
- Expandir o objeto da controvérsia além dos módulos ativados

### Regra de Coerência

Se o parecer do NATJus for favorável ao Estado, utilizar suas conclusões para reforçar os argumentos [VALIDADO].

Se o parecer do NATJus for desfavorável ao Estado, **NÃO CRIAR** objeções jurídicas autônomas para contorná-lo.

### Desenvolvimento Obrigatório

Cada argumento [VALIDADO] de mérito deve:
- Ter subtópico próprio (### 3.N.)
- Articular a tese jurídica com os dados técnicos do NATJus
- Demonstrar aderência ao caso concreto
- Concluir com o efeito prático pretendido

---

## REGRA ESPECIAL: AUSÊNCIA DE ARGUMENTOS DE IMPROCEDÊNCIA

### Hipótese

Em alguns casos, **não há módulos [VALIDADO] de mérito que sustentem a improcedência** do pedido (por exemplo, quando o parecer do NATJus é integralmente favorável ao autor e não há fundamento jurídico validado para resistir ao pleito principal).

### Consequência Estrutural

Quando **NÃO houver argumentos de mérito para improcedência**, mas **houver módulos [VALIDADO] de eventualidade**:

1. **Os argumentos de eventualidade se tornam o mérito da contestação**
2. A seção passa a ser denominada **"DO MÉRITO"** (não "DA EVENTUALIDADE")
3. Os argumentos são desenvolvidos **sem caráter subsidiário** (não usar "caso seja superada a tese principal...")
4. **NÃO se pede a improcedência** dos pedidos

### Estrutura Adaptada

Nesta hipótese, a estrutura da peça será:

```
## 1. DOS FATOS
## 2. DAS PRELIMINARES (somente se houver módulo [VALIDADO])
## 3. DO MÉRITO (com os argumentos que seriam de eventualidade)
## 5. DOS PEDIDOS (sem pedido de improcedência)
```

### Pedidos Nesta Hipótese

Os pedidos devem refletir **apenas** a observância das condições validadas, sem requerer improcedência:

- Direcionamento ao ente federativo competente
- Limitação de valores (PMVG, tabela SUS)
- Forma de fornecimento
- Apresentação de orçamentos
- Outras condições específicas dos módulos [VALIDADO]

### Identificação da Hipótese

Para identificar se este cenário se aplica, verificar:

1. Existem módulos [VALIDADO] que sustentam a **improcedência** do pedido principal?
   - SIM → Estrutura padrão (mérito + eventualidade se houver)
   - NÃO → Verificar próxima pergunta

2. Existem módulos [VALIDADO] de **eventualidade/subsidiários**?
   - SIM → Eventualidade vira mérito, sem pedido de improcedência
   - NÃO → Contestação apenas com preliminares (se houver) ou sem argumentos de mérito

---

## REGRAS PARA SEÇÃO DE EVENTUALIDADE

### Condição de Existência

A seção de eventualidade **SÓ EXISTE** se houver módulo [VALIDADO] de eventualidade ativado.

Sem módulo [VALIDADO] de eventualidade = **SEM SEÇÃO DE EVENTUALIDADE**.

### Regra de Desenvolvimento

Cada tese subsidiária autorizada via módulo [VALIDADO] deve:
- Ter subtópico próprio (### 4.N.)
- Ser apresentada em caráter subsidiário ("caso seja superada a tese principal...")
- Manter coerência com os argumentos de mérito

É **PROIBIDO** criar teses de eventualidade por inferência ou "cautela processual".

---

## REGRAS PARA SEÇÃO DE PEDIDOS

### Princípio Geral

Os pedidos devem refletir **exclusivamente** o conteúdo desenvolvido na contestação.

### Formato

- **Texto corrido**: quando houver apenas um ou dois pedidos simples
- **Lista de alíneas (a, b, c)**: quando houver pluralidade de pedidos ou necessidade de enumeração clara

### Estrutura Padrão (com argumentos de improcedência)

**Preliminarmente** (somente se houver preliminares):
[Pedidos correspondentes às preliminares arguidas]

**No mérito**:
[Pedido de improcedência dos pedidos]

**Subsidiariamente** (somente se houver eventualidade):
[Pedidos correspondentes às teses subsidiárias validadas]

### Estrutura Alternativa (sem argumentos de improcedência)

Quando se aplicar a **REGRA ESPECIAL: AUSÊNCIA DE ARGUMENTOS DE IMPROCEDÊNCIA**:

**Preliminarmente** (somente se houver preliminares):
[Pedidos correspondentes às preliminares arguidas]

**No mérito**:
[Pedidos de observância das condições validadas - SEM pedido de improcedência]

Exemplos de pedidos nesta hipótese:
- Direcionamento da obrigação ao ente competente
- Limitação do custo ao PMVG ou tabela SUS
- Exigência de apresentação de orçamentos
- Forma específica de fornecimento
- Ressarcimento em caso de cumprimento por ente não responsável

### Vedação

É **PROIBIDO** formular pedidos que não correspondam a argumentos [VALIDADO] desenvolvidos na peça.

É **PROIBIDO** pedir improcedência quando não houver módulos [VALIDADO] que a sustentem.

---

## ARGUMENTOS [VALIDADO]

Argumentos marcados com **[VALIDADO]** **DEVEM** ser incluídos na peça **SEM QUESTIONAMENTO**.

Esses argumentos:
- Já foram validados automaticamente com base nas variáveis extraídas dos documentos
- **NÃO podem ser omitidos**
- **NÃO podem ser fundidos** com outros argumentos
- Devem gerar **tópico ou subtópico próprio**

---

## VALIDAÇÃO FINAL

Antes de concluir a contestação, verificar:

### Identificação dos Pedidos
- [ ] Os pedidos foram extraídos da **PETIÇÃO INICIAL** (não da prescrição médica)?
- [ ] **Não foram incluídos itens que constam apenas em anexos**, mas não na inicial?
- [ ] O objeto da contestação corresponde **exatamente** ao objeto da inicial?

### Fatos
- [ ] Os **FATOS** informam pedidos, conclusão do NAT e situação da tutela?
- [ ] Os medicamentos/procedimentos listados nos fatos foram **efetivamente pedidos na inicial**?

### Fontes Técnicas
- [ ] O parecer do NATJus foi utilizado como fonte técnica (não como fonte de teses jurídicas)?

### Estrutura
- [ ] Preliminares existem **apenas** se há módulo [VALIDADO]?
- [ ] Eventualidade existe **apenas** se há módulo [VALIDADO] E há argumentos de improcedência?
- [ ] Se **NÃO há argumentos de improcedência**, a eventualidade virou mérito?
- [ ] O pedido de improcedência foi formulado **APENAS** se há módulo [VALIDADO] que o sustente?
- [ ] Cada módulo [VALIDADO] gerou tópico próprio?
- [ ] Nenhum instituto jurídico foi introduzido sem validação?
- [ ] Os pedidos correspondem estritamente aos argumentos desenvolvidos?
- [ ] A estrutura segue o modelo definido neste prompt?
