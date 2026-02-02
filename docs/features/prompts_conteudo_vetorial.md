# Prompts de Conteúdo - Base de Conhecimento Jurídico PGE-MS

Extraído em: 2026-01-22 11:54:56
Total de módulos: 55

---

## Formato para Embedding Vetorial

Cada módulo abaixo contém:
- **ID**: Identificador único no banco
- **Nome**: Slug identificador
- **Título**: Nome legível do argumento
- **Categoria/Subcategoria**: Classificação hierárquica
- **Condição de Ativação**: Quando usar este argumento (texto legado)
- **Regra Determinística**: Condição em linguagem natural (nova)
- **Regras por Tipo de Peça**: Condições específicas por tipo
- **Conteúdo**: O texto do argumento jurídico

### Sugestão de Texto para Embedding:
```
TÍTULO: {titulo}
CATEGORIA: {categoria} > {subcategoria}
QUANDO USAR: {condicao_ativacao ou regra_texto_original}
CONTEÚDO: {conteudo}
```

---

## 1. Reembolso a Agente Privado - Tema 1.033

| Campo | Valor |
|-------|-------|
| **ID** | 59 |
| **Nome** | `evt_tema_1033` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Cirurgia |
| **Modo Ativação** | deterministic |
| **Ordem** | 1 |

### Condição de Ativação (Legado)

> Quando for pleiteada cirurgia de responsabilidade estadual ou houver discussão a respeito do Tema 1.033 ou se tratar de transferência hospitalar

### Conteúdo

```markdown
## REEMBOLSO PELO PODER PÚBLICO A AGENTE PRIVADO DE SAÚDE EM CUMPRIMENTO DE ORDEM JUDICIAL (TEMA 1.033)

O Supremo Tribunal Federal discutiu se as despesas de hospital particular que, por ordem judicial, prestou serviços a paciente que não conseguiu vaga no sistema público devem ser pagas pelo ente público segundo preço arbitrado pelo prestador do serviço ou de acordo com a tabela do SUS.

Esse debate ocorreu no Recurso Extraordinário nº 666.094 (Tema 1.033), à luz dos arts. 5º; 196; e 199, § 1º, todos da CRFB, que resultou na seguinte tese de repercussão geral:

> O ressarcimento de serviços de saúde prestados por unidade privada em favor de paciente do Sistema Único de Saúde, em cumprimento de ordem judicial, deve utilizar como critério o mesmo que é adotado para o ressarcimento do Sistema Único de Saúde por serviços prestados a beneficiários de planos de saúde.

Portanto, já foram ponderados os princípios constitucionais em aparente conflito para situação fática reproduzida nestes autos. Caso os atendimentos decorrentes de eventual condenação judicial nesta demanda exijam a participação da iniciativa privada, pede-se seja fixado no título executivo judicial que o ente público devedor estará obrigado a ressarcir o agente privado credor segundo os parâmetros fixados no Tema 1.033 do STF.
```

### Texto para Embedding

```
TÍTULO: Reembolso a Agente Privado - Tema 1.033
CATEGORIA: Eventualidade > Cirurgia
QUANDO USAR: Quando for pleiteada cirurgia de responsabilidade estadual ou houver discussão a respeito do Tema 1.033 ou se tratar de transferência hospitalar
CONTEÚDO: ## REEMBOLSO PELO PODER PÚBLICO A AGENTE PRIVADO DE SAÚDE EM CUMPRIMENTO DE ORDEM JUDICIAL (TEMA 1.033)

O Supremo Tribunal Federal discutiu se as despesas de hospital particular que, por ordem judicial, prestou serviços a paciente que não conseguiu vaga no sistema público devem ser pagas pelo ente público segundo preço arbitrado pelo prestador do serviço ou de acordo com a tabela do SUS.

Esse debate ocorreu no Recurso Extraordinário nº 666.094 (Tema 1.033), à luz dos arts. 5º; 196; e 199, § 1º...
```

---

## 2. Realização da Cirurgia pela Rede Pública

| Campo | Valor |
|-------|-------|
| **ID** | 58 |
| **Nome** | `evt_cirurgia_rede_publica` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Cirurgia |
| **Modo Ativação** | deterministic |
| **Ordem** | 2 |

### Condição de Ativação (Legado)

> Quando for pleiteada cirurgia

### Conteúdo

```markdown
## REALIZAÇÃO DA CIRURGIA PELA REDE PÚBLICA COM PROFISSIONAIS E MATERIAIS DISPONIBILIZADOS PELO SUS

O procedimento requerido é disponibilizado no SUS. Igualmente, os materiais necessários ao tratamento também são fornecidos na rede pública. Portanto, não é preciso realizar o atendimento na rede privada ou adquirir materiais extraordinários. Caso o fosse, o pagamento de honorários a médico do SUS é descabido e o uso da OPME deveria estar fundado na Medicina Baseada em Evidências. Nesse sentido são os Enunciados nº 29, 59 e 79 da Jornada de Direito da Saúde do CNJ.
```

### Texto para Embedding

```
TÍTULO: Realização da Cirurgia pela Rede Pública
CATEGORIA: Eventualidade > Cirurgia
QUANDO USAR: Quando for pleiteada cirurgia
CONTEÚDO: ## REALIZAÇÃO DA CIRURGIA PELA REDE PÚBLICA COM PROFISSIONAIS E MATERIAIS DISPONIBILIZADOS PELO SUS

O procedimento requerido é disponibilizado no SUS. Igualmente, os materiais necessários ao tratamento também são fornecidos na rede pública. Portanto, não é preciso realizar o atendimento na rede privada ou adquirir materiais extraordinários. Caso o fosse, o pagamento de honorários a médico do SUS é descabido e o uso da OPME deveria estar fundado na Medicina Baseada em Evidências. Nesse sentido s...
```

---

## 3. Direcionamento e Direito de Ressarcimento - Tema 793

| Campo | Valor |
|-------|-------|
| **ID** | 49 |
| **Nome** | `evt_direcionamento_793` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 3 |

### Condição de Ativação (Legado)

> Quando o município estiver no polo passivo e o pedido envolver cirurgia, consulta, exame, dieta, fraldas, insumos/equipamentos, home care ou autismo. 

### Conteúdo

```markdown
## DIRECIONAMENTO E DIREITO DE RESSARCIMENTO EM FACE DO ENTE RESPONSÁVEL PELO CUMPRIMENTO (TEMA 793)

Em 2019, o Supremo Tribunal Federal concluiu o julgamento dos EDcl no RE n° 855.178/SE (Tema 793) e, ao interpretar os arts. 23, inciso II; o 196; e o 198, todos da CRFB, fixou em repercussão geral que:

> Os entes da federação, em decorrência da competência comum, são solidariamente responsáveis nas demandas prestacionais na área da saúde, e diante dos critérios constitucionais de descentralização e hierarquização, compete à autoridade judicial direcionar o cumprimento conforme as regras de repartição de competências e determinar o ressarcimento a quem suportou o ônus financeiro.

Em vista disso, o Estado de Mato Grosso do Sul não questiona sua legitimidade passiva, mas pede o direcionamento do cumprimento em face do município responsável e o direito de ressarcimento, caso custeie a obrigação com recursos próprios, em observância às regras de repartição de responsabilidades no SUS, que passa a expor.
```

### Texto para Embedding

```
TÍTULO: Direcionamento e Direito de Ressarcimento - Tema 793
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando o município estiver no polo passivo e o pedido envolver cirurgia, consulta, exame, dieta, fraldas, insumos/equipamentos, home care ou autismo. 
CONTEÚDO: ## DIRECIONAMENTO E DIREITO DE RESSARCIMENTO EM FACE DO ENTE RESPONSÁVEL PELO CUMPRIMENTO (TEMA 793)

Em 2019, o Supremo Tribunal Federal concluiu o julgamento dos EDcl no RE n° 855.178/SE (Tema 793) e, ao interpretar os arts. 23, inciso II; o 196; e o 198, todos da CRFB, fixou em repercussão geral que:

> Os entes da federação, em decorrência da competência comum, são solidariamente responsáveis nas demandas prestacionais na área da saúde, e diante dos critérios constitucionais de descentraliza...
```

---

## 4. Responsabilidade do Município - Atendimento Domiciliar

| Campo | Valor |
|-------|-------|
| **ID** | 55 |
| **Nome** | `evt_mun_homecare` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 4 |

### Condição de Ativação (Legado)

> Quando for pleiteado atendimento domiciliar (home care).

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO POR ATENDIMENTO DOMICILIAR

O Serviço de Atendimento Domiciliar (SAD) é obrigação dos municípios. A Política Nacional de Atenção Básica (PNAB) prevê a realização de visita e atendimento em domicílio, com profissionais municipais. Isso está a cargo da Equipe de Atenção Domiciliar (EAD) ou da Equipe do Núcleo Ampliado de Saúde da Família (ENASF).

São oferecidos atendimentos com médico, fisioterapeuta, fonoaudiólogo, psicólogo, pediatra, terapeuta ocupacional, nutricionista, odontólogo, farmacêutico, assistente social e outros. Portanto, a eficácia da decisão judicial depende do direcionamento da obrigação ao município responsável pela gestão desse serviço.

### FREQUÊNCIA DE ATENDIMENTO DOMICILIAR A SER ESTABELECIDA PELA EQUIPE DO MUNICÍPIO

A frequência do tratamento domiciliar deve ser estabelecida pela equipe da Unidade Básica de Saúde ou do SAD. Além de ser habilitada para prestar o melhor atendimento, a gestão municipal tem capacidade institucional para gerenciar seus servidores.

Se todo juízo obrigasse o ente público a prestar serviço em periodicidade prescrita por um profissional que desconhece a administração pública e que não acompanhará o desenvolvimento do paciente, haveria prejuízo para todos os usuários do SUS. Em vista disso, pede-se que a definição dos profissionais e da quantidade de sessões fique a cargo do ente competente.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência por algum motivo (coisa rara).
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Atendimento Domiciliar
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando for pleiteado atendimento domiciliar (home care).
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO POR ATENDIMENTO DOMICILIAR

O Serviço de Atendimento Domiciliar (SAD) é obrigação dos municípios. A Política Nacional de Atenção Básica (PNAB) prevê a realização de visita e atendimento em domicílio, com profissionais municipais. Isso está a cargo da Equipe de Atenção Domiciliar (EAD) ou da Equipe do Núcleo Ampliado de Saúde da Família (ENASF).

São oferecidos atendimentos com médico, fisioterapeuta, fonoaudiólogo, psicólogo, pediatra, terapeuta ocupacional, nut...
```

---

## 5. Responsabilidade do Município - Procedimentos

| Campo | Valor |
|-------|-------|
| **ID** | 51 |
| **Nome** | `evt_mun_geral` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 5 |

### Condição de Ativação (Legado)

> Quando o município estiver no polo passivo e o pedido envolver procedimentos (cirurgia , consulta ou exame). 

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO DE {{ municipio }} PELO AGENDAMENTO E PELA REALIZAÇÃO DE PROCEDIMENTOS

A competência pela gestão e a execução de serviços de saúde é dos municípios. Se o serviço requerido não estiver habilitado em seu território, cabe ao município de residência do paciente pactuar com o município de referência nessa especialidade pelo Programa de Pactuação Integrada (PPI). Ao fazê-lo, aquele ente autoriza a transferência automática de parcela dos recursos federais a ele programados em favor desse último ente.

Aos estados incumbem tarefas de acompanhamento, controle, avaliação e apoios técnico e financeiro. Nessa organização, só o município de residência tem acesso à funcionalidade de solicitar atendimento no SISREG para seus administrados. Por seu turno, só o município de referência tem acesso à funcionalidade de agendar o atendimento e possui pessoal capacitado para executar os serviços regulados.

Consequentemente, a efetividade da tutela jurisdicional dependerá do direcionamento da obrigação ao município responsável pela etapa do atendimento em que ocorrer a omissão administrativa, sem prejuízo do direito de ressarcimento ao Estado, se custeá-la subsidiariamente com recursos próprios, conforme entende o TJMS.

#### orientação para LLM: normalmente esse tópico fica na eventualidade.
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Procedimentos
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando o município estiver no polo passivo e o pedido envolver procedimentos (cirurgia , consulta ou exame). 
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO DE {{ municipio }} PELO AGENDAMENTO E PELA REALIZAÇÃO DE PROCEDIMENTOS

A competência pela gestão e a execução de serviços de saúde é dos municípios. Se o serviço requerido não estiver habilitado em seu território, cabe ao município de residência do paciente pactuar com o município de referência nessa especialidade pelo Programa de Pactuação Integrada (PPI). Ao fazê-lo, aquele ente autoriza a transferência automática de parcela dos recursos federais a ele progra...
```

---

## 6. Responsabilidade do Município - Alimentação e Nutrição

| Campo | Valor |
|-------|-------|
| **ID** | 52 |
| **Nome** | `evt_mun_dieta` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 6 |

### Condição de Ativação (Legado)

> Quando for pleiteado fornecimento de dieta ou suplemento alimentar.

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO POR SERVIÇOS DE ALIMENTAÇÃO E NUTRIÇÃO

Os serviços de saúde relacionados à alimentação e nutrição são competências dos municípios (Art. 18, inciso IV, alínea "c", da Lei nº 8.080/90). Outrossim, a Nova Política Nacional de Alimentação atribui à Atenção Básica a responsabilidade pelo atendimento de pessoas com necessidades alimentares especiais.

Diante disso, a obrigação deve ser direcionada ao município de residência da parte autora, sem prejuízo do direito de ressarcimento ao Estado, se custeá-lo com recursos próprios.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência por algum motivo (coisa rara).
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Alimentação e Nutrição
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando for pleiteado fornecimento de dieta ou suplemento alimentar.
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO POR SERVIÇOS DE ALIMENTAÇÃO E NUTRIÇÃO

Os serviços de saúde relacionados à alimentação e nutrição são competências dos municípios (Art. 18, inciso IV, alínea "c", da Lei nº 8.080/90). Outrossim, a Nova Política Nacional de Alimentação atribui à Atenção Básica a responsabilidade pelo atendimento de pessoas com necessidades alimentares especiais.

Diante disso, a obrigação deve ser direcionada ao município de residência da parte autora, sem prejuízo do direito de...
```

---

## 7. Responsabilidade do Município - Gestão Plena

| Campo | Valor |
|-------|-------|
| **ID** | 50 |
| **Nome** | `evt_mun_gestao_plena` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 7 |

### Condição de Ativação (Legado)

> Quando o município de residência for habilitado na Gestão Plena do Sistema Municipal (Aquidauana, Amambai, Aparecida do Taboado, Campo Grande, Cassilândia, Chapadão do Sul, Corumbá, Costa Rica, Coxim, Dourados, Ivinhema, Jardim, Maracajú, Naviraí, Nova Andradina, Paranaíba, Rio Brilhante, Rio Verde de Mato Grosso, São Gabriel do Oeste, Sidrolândia, Três Lagoas). APLICA-SE SOMENTE PARA AÇÕES DE CIRURGIAS, EXAMES E PROCEDIMENTOS. 

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO DE {{ municipio }} PELO AGENDAMENTO E PELA REALIZAÇÃO DE PROCEDIMENTOS

O município requerido é habilitado na Gestão Plena do Sistema Municipal. Isso significa que assumiu o comando único sobre os prestadores do seu território. Assim, somente ele pode autorizar procedimentos de média e alta complexidade e efetivar os pagamentos.

Em contrapartida, ele recebe em seu Fundo Municipal de Saúde o total de recursos federais correspondente ao limite financeiro programado para atender a população própria e a de outros estados com ele pactuados no Programa de Pactuação Integrada (PPI).

Portanto, a efetividade da tutela jurisdicional dependerá do direcionamento da obrigação ao município, sem prejuízo do direito de ressarcimento ao Estado, se custeá-la subsidiariamente com recursos próprios, conforme entende o TJMS.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência por algum motivo (coisa rara).
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Gestão Plena
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando o município de residência for habilitado na Gestão Plena do Sistema Municipal (Aquidauana, Amambai, Aparecida do Taboado, Campo Grande, Cassilândia, Chapadão do Sul, Corumbá, Costa Rica, Coxim, Dourados, Ivinhema, Jardim, Maracajú, Naviraí, Nova Andradina, Paranaíba, Rio Brilhante, Rio Verde de Mato Grosso, São Gabriel do Oeste, Sidrolândia, Três Lagoas). APLICA-SE SOMENTE PARA AÇÕES DE CIRURGIAS, EXAMES E PROCEDIMENTOS. 
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO DE {{ municipio }} PELO AGENDAMENTO E PELA REALIZAÇÃO DE PROCEDIMENTOS

O município requerido é habilitado na Gestão Plena do Sistema Municipal. Isso significa que assumiu o comando único sobre os prestadores do seu território. Assim, somente ele pode autorizar procedimentos de média e alta complexidade e efetivar os pagamentos.

Em contrapartida, ele recebe em seu Fundo Municipal de Saúde o total de recursos federais correspondente ao limite financeiro programa...
```

---

## 8. Responsabilidade do Município - Fraldas

| Campo | Valor |
|-------|-------|
| **ID** | 53 |
| **Nome** | `evt_mun_fraldas` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 8 |

### Condição de Ativação (Legado)

> Quando for pleiteado fornecimento de fraldas.

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO POR FRALDAS

A prestação de serviços assistenciais e o fornecimento de insumos de saúde são competências dos municípios. Como exemplo, o Município de Campo Grande está condenado em Ação Civil Pública a implantar política pública de dispensação administrativa gratuita de fraldas descartáveis aos moradores da Capital. Nos termos da decisão:

> Destarte, em razão dos argumentos expostos, julgo em parte procedentes os pedidos formulados na inicial para condenar o requerido a implantar política pública de dispensação administrativa gratuita de fraldas descartáveis aos munícipes de Campo Grande, com a ressalva de que o material de higiene deverá ser fornecido aos interessados que não possuam recursos próprios para adquiri-lo, mesmo que pelo Programa Farmácia Popular do Brasil ("Aqui Tem Farmácia Popular"), e que comprovem a imprescindibilidade ou necessidade do insumo mediante apresentação de solicitação ou receita médica expedida pelo médico que assiste o paciente na rede pública municipal de saúde.

Em vista disso, se o pedido de fornecimento de fraldas for julgado procedente, a obrigação deve ser direcionada ao município, sem prejuízo do direito de ressarcimento ao Estado, se custeá-la com recursos próprios.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência por algum motivo (coisa rara).
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Fraldas
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando for pleiteado fornecimento de fraldas.
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO POR FRALDAS

A prestação de serviços assistenciais e o fornecimento de insumos de saúde são competências dos municípios. Como exemplo, o Município de Campo Grande está condenado em Ação Civil Pública a implantar política pública de dispensação administrativa gratuita de fraldas descartáveis aos moradores da Capital. Nos termos da decisão:

> Destarte, em razão dos argumentos expostos, julgo em parte procedentes os pedidos formulados na inicial para condenar o re...
```

---

## 9. Responsabilidade do Município - Terapias TEA

| Campo | Valor |
|-------|-------|
| **ID** | 56 |
| **Nome** | `evt_mun_autismo` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 9 |

### Condição de Ativação (Legado)

> Quando for pleiteado tratamento para TEA.

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO PELO AGENDAMENTO E PELA REALIZAÇÃO DE TERAPIAS SEM DISTINÇÃO DE MÉTODO

As terapias multidisciplinares sem distinção do método estão disponíveis no SUS e são agendadas no sistema municipal de regulação de vagas (SISREG). Ainda que o município de residência da parte autora não disponha do serviço em seu território, o pedido é inserido no sistema e direcionado à Central Reguladora do município de referência, com o qual aquele deve(ria) estar pactuado.

Nessa relação, o município executor (referência) recebe parcela dos recursos federais que seriam destinados ao município solicitante (residência) para custear o atendimento à população desse ente público. Noutro cenário, se o município de residência não mantém pactuação com nenhum ente para realizar os atendimentos que não oferece em seu território, ele recebe os recursos federais e os aplica em outras finalidades.

Em qualquer situação, só o município de residência tem acesso à funcionalidade de solicitar atendimento no SISREG para seus administrados. Por seu turno, só o município gestor da Central Reguladora (que pode ser o próprio município de residência) tem acesso à funcionalidade de agendar o atendimento. Igualmente, só o município de referência possui pessoal capacitado para executar os serviços regulados.

Portanto, a eficácia da decisão judicial dependerá do direcionamento da obrigação ao município responsável pela etapa do atendimento em que se verificar a omissão administrativa.

### ELABORAÇÃO DO PROJETO TERAPÊUTICO SINGULAR (PTS) POR PROFISSIONAIS DA REDE PÚBLICA

O Judiciário deve analisar os impactos práticos de suas decisões na política pública de saúde. O médico prescritor não tem conhecimento da existência de profissionais (das redes pública ou privada) para atender nas proximidades da residência do paciente e das rotinas da família e da criança. Ocorre que o sucesso do tratamento pleiteado exige intensa participação familiar.

Assim como a medicina limitou-se ao diagnóstico e à indicação dos profissionais responsáveis pelos cuidados do paciente, o Direito deve conformar-se à realidade, sob pena de inefetividade. O PTS deve ser elaborado pelos profissionais de diferentes especialidades indicadas pelo médico, não pelo próprio prescritor. São esses profissionais do SUS que estabelecerão a carga horária e a metodologia adequadas, juntamente com a família do paciente.

Portanto, pede-se que o PTS seja elaborado e executado por profissionais da rede pública, segundo as condicionantes operacionais do sistema.

#### orientação para LLM: esse tópico fica na eventualidade
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Terapias TEA
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando for pleiteado tratamento para TEA.
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO PELO AGENDAMENTO E PELA REALIZAÇÃO DE TERAPIAS SEM DISTINÇÃO DE MÉTODO

As terapias multidisciplinares sem distinção do método estão disponíveis no SUS e são agendadas no sistema municipal de regulação de vagas (SISREG). Ainda que o município de residência da parte autora não disponha do serviço em seu território, o pedido é inserido no sistema e direcionado à Central Reguladora do município de referência, com o qual aquele deve(ria) estar pactuado.

Nessa relaç...
```

---

## 10. Responsabilidade do Município - Insumos e Equipamentos

| Campo | Valor |
|-------|-------|
| **ID** | 54 |
| **Nome** | `evt_mun_insumos` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Direcionamento |
| **Modo Ativação** | deterministic |
| **Ordem** | 10 |

### Condição de Ativação (Legado)

> Quando for pleiteado fornecimento de insumos e equipamentos.

### Conteúdo

```markdown
### RESPONSABILIDADE DO MUNICÍPIO POR INSUMOS E EQUIPAMENTOS

O fornecimento de insumos e equipamentos é competência municipal (Art. 18, inciso V, da Lei nº 8.080/90). Diante disso, o fornecimento do pedido deve ser direcionado ao município de residência da parte autora, sem prejuízo do direito de ressarcimento ao Estado, se custeá-lo com recursos próprios.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência por algum motivo (coisa rara).
```

### Texto para Embedding

```
TÍTULO: Responsabilidade do Município - Insumos e Equipamentos
CATEGORIA: Eventualidade > Direcionamento
QUANDO USAR: Quando for pleiteado fornecimento de insumos e equipamentos.
CONTEÚDO: ### RESPONSABILIDADE DO MUNICÍPIO POR INSUMOS E EQUIPAMENTOS

O fornecimento de insumos e equipamentos é competência municipal (Art. 18, inciso V, da Lei nº 8.080/90). Diante disso, o fornecimento do pedido deve ser direcionado ao município de residência da parte autora, sem prejuízo do direito de ressarcimento ao Estado, se custeá-lo com recursos próprios.

#### orientação para LLM: normalmente esse tópico fica na eventualidade. ele só vai para o mérito quando não houver pedido de improcedência...
```

---

## 11. Não Responsabilização Pessoal do Agente Público

| Campo | Valor |
|-------|-------|
| **ID** | 64 |
| **Nome** | `evt_resp_pessoal` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Execução |
| **Modo Ativação** | deterministic |
| **Ordem** | 11 |

### Condição de Ativação (Legado)

> SOMENTE ALEGAR QUANDO O ATO JUDICIAL TIVER DETERMINADO RESPONSABILIZAÇÃO PESSOAL DO AGENTE PÚBLICO. (O SIMPLES PEDIDO DA PARTE NÃO DEVE ATIVAR ESSE MÓDULO)

### Conteúdo

```markdown
## NÃO HÁ RESPONSABILIDADE PESSOAL DO AGENTE PÚBLICO PELO INADIMPLEMENTO DE OBRIGAÇÃO DO ENTE PÚBLICO

A sanção aplicada ao ente público não pode ser estendida ao agente público. Isso porque não existe norma que responsabilize diretamente a pessoa natural representante da pessoa jurídica de direito público ainda que pelo descumprimento de ordem judicial. Além de violar o devido processo, essa conduta do magistrado ignora a teoria do órgão, que orienta a Administração Pública.

Igualmente, não cabe responsabilização administrativa ou penal do gestor. A teoria dos poderes implícitos explica que "quem pode o mais, pode o menos". Em sentido contrário, quem não pode o menos, não pode o mais. Se o Superior Tribunal de Justiça afirma que a multa é restrita ao réu, não pode o agente sofrer sanção mais gravosa. É o que também entende o TJMS.
```

### Texto para Embedding

```
TÍTULO: Não Responsabilização Pessoal do Agente Público
CATEGORIA: Eventualidade > Execução
QUANDO USAR: SOMENTE ALEGAR QUANDO O ATO JUDICIAL TIVER DETERMINADO RESPONSABILIZAÇÃO PESSOAL DO AGENTE PÚBLICO. (O SIMPLES PEDIDO DA PARTE NÃO DEVE ATIVAR ESSE MÓDULO)
CONTEÚDO: ## NÃO HÁ RESPONSABILIDADE PESSOAL DO AGENTE PÚBLICO PELO INADIMPLEMENTO DE OBRIGAÇÃO DO ENTE PÚBLICO

A sanção aplicada ao ente público não pode ser estendida ao agente público. Isso porque não existe norma que responsabilize diretamente a pessoa natural representante da pessoa jurídica de direito público ainda que pelo descumprimento de ordem judicial. Além de violar o devido processo, essa conduta do magistrado ignora a teoria do órgão, que orienta a Administração Pública.

Igualmente, não ca...
```

---

## 12. Exigência de Três Orçamentos

| Campo | Valor |
|-------|-------|
| **ID** | 62 |
| **Nome** | `evt_tres_orcamentos` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Execução |
| **Modo Ativação** | deterministic |
| **Ordem** | 12 |

### Condição de Ativação (Legado)

> Sempre. Aplicável a qualquer pedido de fornecimento.

### Conteúdo

```markdown
## EXIGÊNCIA DE TRÊS ORÇAMENTOS

É prudente exigir três orçamentos para a compra do objeto na rede privada. Essa medida visa à economia e probidade na aquisição direta de bens ou serviços pelo Estado na via judicial. Nesse sentido recomenda o Enunciado nº 56 do CNJ.
```

### Texto para Embedding

```
TÍTULO: Exigência de Três Orçamentos
CATEGORIA: Eventualidade > Execução
QUANDO USAR: Sempre. Aplicável a qualquer pedido de fornecimento.
CONTEÚDO: ## EXIGÊNCIA DE TRÊS ORÇAMENTOS

É prudente exigir três orçamentos para a compra do objeto na rede privada. Essa medida visa à economia e probidade na aquisição direta de bens ou serviços pelo Estado na via judicial. Nesse sentido recomenda o Enunciado nº 56 do CNJ.
```

---

## 13. Multa Cominatória

| Campo | Valor |
|-------|-------|
| **ID** | 63 |
| **Nome** | `evt_multa` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Execução |
| **Modo Ativação** | deterministic |
| **Ordem** | 13 |

### Condição de Ativação (Legado)

> SOMENTE ALEGAR QUANDO O ATO JUDICIAL TIVER FIXADO MULTA. (O SIMPLES PEDIDO DA PARTE NÃO DEVE ATIVAR ESSE MÓDULO)

### Conteúdo

```markdown
## MULTA COMINATÓRIA

A finalidade da multa é dar efetividade à decisão judicial e coibir a desídia do devedor. No entanto, circunstâncias externas também atrasam o cumprimento. Nesse passo, a multa não é o meio coercitivo adequado às demandas de saúde. O bloqueio judicial é o único efetivo, além de mais célere e menos oneroso. Nesse sentido é o Enunciado nº 74 do CNJ e o entendimento do TJMS.
```

### Texto para Embedding

```
TÍTULO: Multa Cominatória
CATEGORIA: Eventualidade > Execução
QUANDO USAR: SOMENTE ALEGAR QUANDO O ATO JUDICIAL TIVER FIXADO MULTA. (O SIMPLES PEDIDO DA PARTE NÃO DEVE ATIVAR ESSE MÓDULO)
CONTEÚDO: ## MULTA COMINATÓRIA

A finalidade da multa é dar efetividade à decisão judicial e coibir a desídia do devedor. No entanto, circunstâncias externas também atrasam o cumprimento. Nesse passo, a multa não é o meio coercitivo adequado às demandas de saúde. O bloqueio judicial é o único efetivo, além de mais célere e menos oneroso. Nesse sentido é o Enunciado nº 74 do CNJ e o entendimento do TJMS.
```

---

## 14. Não Condenação em Honorários de Sucumbência

| Campo | Valor |
|-------|-------|
| **ID** | 57 |
| **Nome** | `evt_honorarios` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Honorários |
| **Modo Ativação** | deterministic |
| **Ordem** | 14 |

### Condição de Ativação (Legado)

> Quando a União estiver no polo passivo (para medicamentos) ou quando o município estiver no polo passivo (para obrigações municipais). SE APLICA QUANDO HOUVER PEDIDO DE DIRECIONAMENTO DA OBRIGAÇÃO AO MUNICÍPIO E NÃO SE APLICA ÀS DEMANDAS DO JUIZADO. F

### Conteúdo

```markdown
## NÃO CONDENAÇÃO EM HONORÁRIOS DE SUCUMBÊNCIA

Os honorários sucumbenciais incumbem àquele que deu causa ao processo, consoante o princípio da causalidade (Art. 85, § 10, do CPC). O cancelamento da súmula nº 421 do STJ e a tese fixada no Tema 1.002 do STF não alteram essa conclusão. O raciocínio é referendado pelo STJ, segundo o qual o princípio da sucumbência adotado pelo Código de Processo Civil está contido no princípio da causalidade.

Na situação em análise, não há legislação que imponha ao Estado de Mato Grosso do Sul a prestação de saúde objeto desta demanda, que é obrigação do Município. Portanto, não há omissão do ente estadual. Por outro lado, haveria violação ao princípio da legalidade (Art. 37 da CRFB), se agentes públicos ou instituições estaduais prestassem atendimento sem previsão em lei ou em determinação judicial.

Logo, pede-se que o Estado de Mato Grosso do Sul não seja condenado ao pagamento de honorários sucumbenciais, sob a ótica do princípio da causalidade, pois não deu causa à lide.

### orientação para LLM: esse tópico fica na eventualidade
```

### Texto para Embedding

```
TÍTULO: Não Condenação em Honorários de Sucumbência
CATEGORIA: Eventualidade > Honorários
QUANDO USAR: Quando a União estiver no polo passivo (para medicamentos) ou quando o município estiver no polo passivo (para obrigações municipais). SE APLICA QUANDO HOUVER PEDIDO DE DIRECIONAMENTO DA OBRIGAÇÃO AO MUNICÍPIO E NÃO SE APLICA ÀS DEMANDAS DO JUIZADO. F
CONTEÚDO: ## NÃO CONDENAÇÃO EM HONORÁRIOS DE SUCUMBÊNCIA

Os honorários sucumbenciais incumbem àquele que deu causa ao processo, consoante o princípio da causalidade (Art. 85, § 10, do CPC). O cancelamento da súmula nº 421 do STJ e a tese fixada no Tema 1.002 do STF não alteram essa conclusão. O raciocínio é referendado pelo STJ, segundo o qual o princípio da sucumbência adotado pelo Código de Processo Civil está contido no princípio da causalidade.

Na situação em análise, não há legislação que imponha a...
```

---

## 15. Preço Máximo de Venda ao Governo (PMVG)

| Campo | Valor |
|-------|-------|
| **ID** | 61 |
| **Nome** | `evt_pmvg` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 15 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento.

### Conteúdo

```markdown
## PREÇO MÁXIMO DE VENDA AO GOVERNO (PMVG)

No Tema 1234, o Supremo Tribunal Federal limitou a compra de medicamentos na via judicial ao Preço Máximo de Venda ao Governo (PMVG), estabelecido pela Câmara de Regulação do Mercado de Medicamentos (CMED). Nos termos da decisão:

> 3.2) Na determinação judicial de fornecimento do medicamento, o magistrado deverá estabelecer que o valor de venda do medicamento seja limitado ao preço com desconto, proposto no processo de incorporação na Conitec (se for o caso, considerando o venire contra factum proprium/tu quoque e observado o índice de reajuste anual de preço de medicamentos definido pela CMED), ou valor já praticado pelo ente em compra pública, aquele que seja identificado como menor valor, tal como previsto na parte final do art. 9º na Recomendação 146, de 28.11.2023, do CNJ. Sob nenhuma hipótese, poderá haver pagamento judicial às pessoas físicas/jurídicas acima descritas em valor superior ao teto do PMVG, devendo ser operacionalizado pela serventia judicial junto ao fabricante ou distribuidor.

Para fins de orientar o cumprimento, deverá constar no título executivo que não será aceito orçamento com valor superior ao PMVG.
```

### Texto para Embedding

```
TÍTULO: Preço Máximo de Venda ao Governo (PMVG)
CATEGORIA: Eventualidade > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento.
CONTEÚDO: ## PREÇO MÁXIMO DE VENDA AO GOVERNO (PMVG)

No Tema 1234, o Supremo Tribunal Federal limitou a compra de medicamentos na via judicial ao Preço Máximo de Venda ao Governo (PMVG), estabelecido pela Câmara de Regulação do Mercado de Medicamentos (CMED). Nos termos da decisão:

> 3.2) Na determinação judicial de fornecimento do medicamento, o magistrado deverá estabelecer que o valor de venda do medicamento seja limitado ao preço com desconto, proposto no processo de incorporação na Conitec (se for ...
```

---

## 16. Fornecimento Sem Vinculação a Nome Comercial (se a parte usou o princípio ativo e entre parênteses usou o nome comercial, não é pedido pelo nome comercial)

| Campo | Valor |
|-------|-------|
| **ID** | 60 |
| **Nome** | `evt_med_sem_marca` |
| **Categoria** | Eventualidade |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 16 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento por nome comercial ou marca específica.

### Conteúdo

```markdown
## FORNECIMENTO SEM VINCULAÇÃO A NOME COMERCIAL OU MARCA ESPECÍFICA

O pedido de nome comercial ou marca específica, sem justificativa técnica, é vedado pela lei. O Poder Público adquire medicamentos pelo princípio ativo e insumos pelo fabricante vencedor do processo licitatório, sem preferência por marcas específicas (Art. 41, inciso I, alínea "a", da Lei nº 14.133/21).

Pelo contrário, a legislação dá preferência ao medicamento genérico em condição de igualdade de preço com os demais (Art. 3º, § 2º, da Lei nº 9.787/99). Portanto, em razão do princípio da concentração da defesa, pede-se não condicionar a obrigação a nome comercial ou marca específica.
```

### Texto para Embedding

```
TÍTULO: Fornecimento Sem Vinculação a Nome Comercial (se a parte usou o princípio ativo e entre parênteses usou o nome comercial, não é pedido pelo nome comercial)
CATEGORIA: Eventualidade > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento por nome comercial ou marca específica.
CONTEÚDO: ## FORNECIMENTO SEM VINCULAÇÃO A NOME COMERCIAL OU MARCA ESPECÍFICA

O pedido de nome comercial ou marca específica, sem justificativa técnica, é vedado pela lei. O Poder Público adquire medicamentos pelo princípio ativo e insumos pelo fabricante vencedor do processo licitatório, sem preferência por marcas específicas (Art. 41, inciso I, alínea "a", da Lei nº 14.133/21).

Pelo contrário, a legislação dá preferência ao medicamento genérico em condição de igualdade de preço com os demais (Art. 3º,...
```

---

## 17. INADMISSÃO DE ORÇAMENTO DO TIPO "PACOTE" 

| Campo | Valor |
|-------|-------|
| **ID** | 71 |
| **Nome** | `orçamento_pacote` |
| **Categoria** | Eventualidade |
| **Subcategoria** | N/A |
| **Modo Ativação** | deterministic |
| **Ordem** | 0 |

### Condição de Ativação (Legado)

> Quando a ação envolver cirurgia. 

### Regras por Tipo de Peça

- **contestacao**: petição inicial pede consulta

### Conteúdo

```markdown
###INADMISSÃO DE ORÇAMENTO DO TIPO "PACOTE" 

As propostas de orçamento para realização do procedimento requerido na rede privada devem discriminar especificadamente os serviços e produtos incluídos no preço. A prática de listar esses itens e apresentar tão somente um valor global – chamado orçamento "pacote" – não permite que o Estado analise se o custo daquilo que se contrata está de acordo com os valores praticados no SUS, tampouco com valores de mercado. Portanto, pede-se seja condicionado eventual sequestro de recursos públicos à clara identificação dos bens e serviços custeados.

#### orientação para LLM: esse tópico vai na eventualidade (após a aplicação do tema 1033 caso ele seja usado) 
```

### Texto para Embedding

```
TÍTULO: INADMISSÃO DE ORÇAMENTO DO TIPO "PACOTE" 
CATEGORIA: Eventualidade > Geral
QUANDO USAR: Quando a ação envolver cirurgia. 
EM CONTESTACAO: petição inicial pede consulta
CONTEÚDO: ###INADMISSÃO DE ORÇAMENTO DO TIPO "PACOTE" 

As propostas de orçamento para realização do procedimento requerido na rede privada devem discriminar especificadamente os serviços e produtos incluídos no preço. A prática de listar esses itens e apresentar tão somente um valor global – chamado orçamento "pacote" – não permite que o Estado analise se o custo daquilo que se contrata está de acordo com os valores praticados no SUS, tampouco com valores de mercado. Portanto, pede-se seja condicionado e...
```

---

## 18. Distribuição da Responsabilidade pelos Honorários entre Litisconsortes (Art. 87, § 1º, CPC)

| Campo | Valor |
|-------|-------|
| **ID** | 66 |
| **Nome** | `honorarios_distribuicao_litisconsortes` |
| **Categoria** | honorarios |
| **Subcategoria** | distribuicao_litisconsorcio |
| **Modo Ativação** | deterministic |
| **Ordem** | 0 |

### Condição de Ativação (Legado)

> Quando houver litisconsórcio passivo em demanda contra o Estado e a decisão recorrida não houver discriminado a parcela de responsabilidade de cada litisconsorte no pagamento dos honorários sucumbenciais.

### Conteúdo

```markdown
## Distribuição Expressa da Responsabilidade pelo Pagamento dos Honorários Sucumbenciais (Art. 87, § 1º, do CPC)

Considerando que o ente estadual não é o único a sucumbir no polo passivo, torna-se necessária a distribuição expressa da responsabilidade pelo pagamento desta verba, com fundamento no Art. 87, § 1º, do CPC. No entanto, a decisão não esclareceu o montante devido por cada litisconsorte. Isso é prejudicial ao embargante, que pode ser compelido a custear o valor total da sucumbência, em virtude da solidariedade do § 2º do Art. 87 do CPC.

Portanto, a decisão merece ser integrada para consignar que o Estado seja responsável por 50% (cinquenta por cento) do valor devido a título de honorários sucumbenciais.
```

### Texto para Embedding

```
TÍTULO: Distribuição da Responsabilidade pelos Honorários entre Litisconsortes (Art. 87, § 1º, CPC)
CATEGORIA: honorarios > distribuicao_litisconsorcio
QUANDO USAR: Quando houver litisconsórcio passivo em demanda contra o Estado e a decisão recorrida não houver discriminado a parcela de responsabilidade de cada litisconsorte no pagamento dos honorários sucumbenciais.
CONTEÚDO: ## Distribuição Expressa da Responsabilidade pelo Pagamento dos Honorários Sucumbenciais (Art. 87, § 1º, do CPC)

Considerando que o ente estadual não é o único a sucumbir no polo passivo, torna-se necessária a distribuição expressa da responsabilidade pelo pagamento desta verba, com fundamento no Art. 87, § 1º, do CPC. No entanto, a decisão não esclareceu o montante devido por cada litisconsorte. Isso é prejudicial ao embargante, que pode ser compelido a custear o valor total da sucumbência, em...
```

---

## 19. Honorários por Equidade em Demandas de Saúde (Tema 1.313/STJ)

| Campo | Valor |
|-------|-------|
| **ID** | 65 |
| **Nome** | `honorarios_equidade_tema_1313` |
| **Categoria** | honorarios |
| **Subcategoria** | equidade_saude |
| **Modo Ativação** | deterministic |
| **Ordem** | 1 |

### Condição de Ativação (Legado)

> Quando o processo envolver demanda de saúde contra o Poder Público e a decisão recorrida houver fixado os honorários advocatícios em percentual sobre o valor da causa, em vez de arbitrá-los por equidade. 

### Conteúdo

```markdown
## Honorários em Demandas de Saúde: Fixação por Equidade (Tema 1.313/STJ)

Em 16/06/2025, o Superior Tribunal de Justiça decidiu o REsp 2169102/AL e o REsp 2166690/RN, submetidos à sistemática dos recursos repetitivos, na forma do Art. 1.036 do CPC (Tema 1.313). A questão em discussão era saber se, nas demandas em que se pleiteia do Estado prestações de saúde, os honorários sucumbenciais devem ser fixados com base no valor da prestação ou da causa (art. 85, §§ 2º, 3º e 4º, III, CPC), ou arbitrados por apreciação equitativa (art. 85, § 8º, do CPC). Desse debate resultou a seguinte tese vinculante, para fins do Art. 927, inciso II, do CPC:

> Nas demandas em que se pleiteia do Poder Público a satisfação do direito à saúde, os honorários advocatícios são fixados por apreciação equitativa, sem aplicação do art. 85, § 8º-A, do CPC.

O Tribunal de Justiça de Mato Grosso do Sul também adota esse entendimento. Segundo a 2ª, a 3ª e a 5ª Câmaras Cíveis, em demandas de saúde cujo objeto seja uma obrigação de fazer, não há como mensurar o proveito econômico por tratar-se de direito constitucional à saúde. O raciocínio é aplicável às obrigações de dar, haja vista que não se pretende somente o medicamento, produto, equipamento, insumo ou procedimento individualizado, senão todo o necessário ao tratamento da condição de saúde da parte autora.

Portanto, reconhecido que a presente demanda possui valor inestimável, impõe-se a fixação dos honorários de sucumbência por equidade, na forma do Art. 85, § 8º, do CPC.
```

### Texto para Embedding

```
TÍTULO: Honorários por Equidade em Demandas de Saúde (Tema 1.313/STJ)
CATEGORIA: honorarios > equidade_saude
QUANDO USAR: Quando o processo envolver demanda de saúde contra o Poder Público e a decisão recorrida houver fixado os honorários advocatícios em percentual sobre o valor da causa, em vez de arbitrá-los por equidade. 
CONTEÚDO: ## Honorários em Demandas de Saúde: Fixação por Equidade (Tema 1.313/STJ)

Em 16/06/2025, o Superior Tribunal de Justiça decidiu o REsp 2169102/AL e o REsp 2166690/RN, submetidos à sistemática dos recursos repetitivos, na forma do Art. 1.036 do CPC (Tema 1.313). A questão em discussão era saber se, nas demandas em que se pleiteia do Estado prestações de saúde, os honorários sucumbenciais devem ser fixados com base no valor da prestação ou da causa (art. 85, §§ 2º, 3º e 4º, III, CPC), ou arbitrad...
```

---

## 20. Ausência de Condenação do Estado em Honorários em Demandas de Medicamentos na Justiça Federal (Súmula Vinculante nº 60)

| Campo | Valor |
|-------|-------|
| **ID** | 67 |
| **Nome** | `honorarios_sv60_medicamentos_jf` |
| **Categoria** | honorarios |
| **Subcategoria** | isencao_estado_medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 2 |

### Condição de Ativação (Legado)

> Quando o processo tramitar na Justiça Federal, envolver demanda por medicamentos contra o Estado e houver condenação do ente estadual ao pagamento de honorários sucumbenciais. ATENÇÃO: NÃO SE APLICA A CONTESTAÇÃO EM SEDE DE JUIZADO ESPECIAL

### Conteúdo

```markdown
## O Estado Não Deve Honorários em Demanda por Medicamento na Justiça Federal por Força da Súmula Vinculante nº 60

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC, afetado à sistemática de repercussão geral (Tema 1234), que debateu a judicialização de medicamentos. Além disso, aprovou o seguinte enunciado de súmula vinculante:

> **Súmula Vinculante nº 60.** O pedido e a análise administrativos de fármacos na rede pública de saúde, a judicialização do caso, bem ainda seus desdobramentos (administrativos e jurisdicionais) devem observar os termos dos 3 (três) acordos interfederativos (e seus fluxos) homologados pelo Supremo Tribunal Federal, em governança judicial colaborativa, no tema 1.234 da sistemática da repercussão geral (RE 1.366.243).

Assim, decidiu-se que os honorários sucumbenciais incumbem àquele que deu causa ao processo, consoante o princípio da causalidade (Art. 85, § 10, do CPC). Nos termos da decisão:

> 3.1) Figurando somente a União no polo passivo, cabe ao magistrado, se necessário, promover a inclusão do Estado ou Município para possibilitar o cumprimento efetivo da decisão, o que não importará em responsabilidade financeira nem em ônus de sucumbência, devendo ser realizado o ressarcimento pela via acima indicada em caso de eventual custo financeiro ser arcado pelos referidos entes.

Logo, o Estado de Mato Grosso do Sul não deve ser condenado ao pagamento de honorários sucumbenciais, sob a ótica do princípio da causalidade, pois não deu causa à lide.
```

### Texto para Embedding

```
TÍTULO: Ausência de Condenação do Estado em Honorários em Demandas de Medicamentos na Justiça Federal (Súmula Vinculante nº 60)
CATEGORIA: honorarios > isencao_estado_medicamentos
QUANDO USAR: Quando o processo tramitar na Justiça Federal, envolver demanda por medicamentos contra o Estado e houver condenação do ente estadual ao pagamento de honorários sucumbenciais. ATENÇÃO: NÃO SE APLICA A CONTESTAÇÃO EM SEDE DE JUIZADO ESPECIAL
CONTEÚDO: ## O Estado Não Deve Honorários em Demanda por Medicamento na Justiça Federal por Força da Súmula Vinculante nº 60

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC, afetado à sistemática de repercussão geral (Tema 1234), que debateu a judicialização de medicamentos. Além disso, aprovou o seguinte enunciado de súmula vinculante:

> **Súmula Vinculante nº 60.** O pedido e a análise administrativos de fármacos na rede pública de saúde, a judicialização do caso, bem ainda seus de...
```

---

## 21. Não Há Indicação Cirúrgica por Médico Especialista do SUS

| Campo | Valor |
|-------|-------|
| **ID** | 28 |
| **Nome** | `mer_cir_sem_esp_sus` |
| **Categoria** | Mérito |
| **Subcategoria** | Cirurgia |
| **Modo Ativação** | deterministic |
| **Ordem** | 0 |

### Condição de Ativação (Legado)

> Quando for pleiteada cirurgia com laudo de médico que não é especialista do SUS.

### Conteúdo

```markdown
## NÃO HÁ INDICAÇÃO CIRÚRGICA POR MÉDICO ESPECIALISTA DO SUS

Um advogado pode atuar em causas de qualquer natureza, assim como um médico pode indicar qualquer tratamento. Não há óbice ao exercício da medicina, ainda que a prescrição de tratamento especializado por profissional não-especialista configure infração disciplinar. No entanto, para realizar o procedimento no SUS, é imprescindível que o paciente seja consultado por especialista da rede pública.

Primeiro porque o médico do SUS conhece as opções terapêuticas da rede pública, que não admite escolha do tratamento de preferência. Por isso, é comum haver contraindicação cirúrgica pelo profissional público diante de prescrição particular.

Segundo porque o encaminhamento para cirurgia por clínico geral (ainda que vinculado ao SUS) caracteriza uma suspeita de que esse seja o tratamento adequado. Contudo, não confere direito subjetivo à realização do procedimento porque precisa ser confirmada por um especialista.

Terceiro porque nenhum médico-cirurgião realizará procedimento em paciente avaliado por outro profissional. Nesse cenário, a indicação cirúrgica de especialista da rede pública é indispensável à existência do direito subjetivo alegado. Ausente a prova, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Não Há Indicação Cirúrgica por Médico Especialista do SUS
CATEGORIA: Mérito > Cirurgia
QUANDO USAR: Quando for pleiteada cirurgia com laudo de médico que não é especialista do SUS.
CONTEÚDO: ## NÃO HÁ INDICAÇÃO CIRÚRGICA POR MÉDICO ESPECIALISTA DO SUS

Um advogado pode atuar em causas de qualquer natureza, assim como um médico pode indicar qualquer tratamento. Não há óbice ao exercício da medicina, ainda que a prescrição de tratamento especializado por profissional não-especialista configure infração disciplinar. No entanto, para realizar o procedimento no SUS, é imprescindível que o paciente seja consultado por especialista da rede pública.

Primeiro porque o médico do SUS conhece ...
```

---

## 22. Não Há Direito à Escolha do Profissional em Face do SUS

| Campo | Valor |
|-------|-------|
| **ID** | 29 |
| **Nome** | `mer_cir_escolha_prof` |
| **Categoria** | Mérito |
| **Subcategoria** | Cirurgia |
| **Modo Ativação** | deterministic |
| **Ordem** | 1 |

### Condição de Ativação (Legado)

> Quando for requerido custeio de procedimento com profissional específico.

### Conteúdo

```markdown
## NÃO HÁ DIREITO À ESCOLHA DO PROFISSIONAL EM FACE DO SUS

A parte autora requer o custeio de procedimento com profissional específico com honorários de R$ {{ cirurgia_valor }}. Ocorre que o tratamento integral é oferecido pelo SUS. Não há direito subjetivo de escolher o profissional, procedimento e local a serem custeados pelo Poder Público, sob a ótica da isonomia e universalidade. Cabe ao paciente respeitar os meios disponíveis e os critérios de classificação de risco. Portanto, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Não Há Direito à Escolha do Profissional em Face do SUS
CATEGORIA: Mérito > Cirurgia
QUANDO USAR: Quando for requerido custeio de procedimento com profissional específico.
CONTEÚDO: ## NÃO HÁ DIREITO À ESCOLHA DO PROFISSIONAL EM FACE DO SUS

A parte autora requer o custeio de procedimento com profissional específico com honorários de R$ {{ cirurgia_valor }}. Ocorre que o tratamento integral é oferecido pelo SUS. Não há direito subjetivo de escolher o profissional, procedimento e local a serem custeados pelo Poder Público, sob a ótica da isonomia e universalidade. Cabe ao paciente respeitar os meios disponíveis e os critérios de classificação de risco. Portanto, o pedido é i...
```

---

## 23. Não Há Dano Moral

| Campo | Valor |
|-------|-------|
| **ID** | 47 |
| **Nome** | `mer_dano_moral` |
| **Categoria** | Mérito |
| **Subcategoria** | Dano Moral |
| **Modo Ativação** | deterministic |
| **Ordem** | 20 |

### Condição de Ativação (Legado)

> Quando for pleiteada indenização por danos morais.

### Conteúdo

```markdown
## NÃO HÁ DANO MORAL

A responsabilidade civil exige, no mínimo, conduta, dano e nexo causal. A parte autora não demonstra agravamento de saúde ou sofrimento excepcional relacionado a conduta estatal. Em se tratando de responsabilidade estatal por omissão, exige-se também a culpa, pela Teoria do Risco Administrativo. No caso, não há demora ou falta de atendimento imputável ao Estado de Mato Grosso do Sul. Assim, o pedido de compensação por dano moral é improcedente.
```

### Texto para Embedding

```
TÍTULO: Não Há Dano Moral
CATEGORIA: Mérito > Dano Moral
QUANDO USAR: Quando for pleiteada indenização por danos morais.
CONTEÚDO: ## NÃO HÁ DANO MORAL

A responsabilidade civil exige, no mínimo, conduta, dano e nexo causal. A parte autora não demonstra agravamento de saúde ou sofrimento excepcional relacionado a conduta estatal. Em se tratando de responsabilidade estatal por omissão, exige-se também a culpa, pela Teoria do Risco Administrativo. No caso, não há demora ou falta de atendimento imputável ao Estado de Mato Grosso do Sul. Assim, o pedido de compensação por dano moral é improcedente.
```

---

## 24. Atendimento de Enfermagem 24 Horas por Dia

| Campo | Valor |
|-------|-------|
| **ID** | 44 |
| **Nome** | `mer_enf24h` |
| **Categoria** | Mérito |
| **Subcategoria** | Enfermagem |
| **Modo Ativação** | deterministic |
| **Ordem** | 2 |

### Condição de Ativação (Legado)

> Quando for pleiteado atendimento de enfermagem 24 horas por dia.

### Conteúdo

```markdown
## ATENDIMENTO DE ENFERMAGEM 24 HORAS POR DIA

O atendimento de enfermagem é disponibilizado no SUS, pelos municípios, embora não pelo período de 24 horas por dia. Isso porque o Poder Público não pode retirar profissionais de hospitais ou locais de atendimento de toda a população para atender apenas um paciente.

Ademais, a pretensão destina-se a cuidados de higiene pessoal, que podem ser realizados pela família (Art. 227 da CRFB), conforme entendimento do TJMS. Em vista disso, o pedido merece ser julgado improcedente.
```

### Texto para Embedding

```
TÍTULO: Atendimento de Enfermagem 24 Horas por Dia
CATEGORIA: Mérito > Enfermagem
QUANDO USAR: Quando for pleiteado atendimento de enfermagem 24 horas por dia.
CONTEÚDO: ## ATENDIMENTO DE ENFERMAGEM 24 HORAS POR DIA

O atendimento de enfermagem é disponibilizado no SUS, pelos municípios, embora não pelo período de 24 horas por dia. Isso porque o Poder Público não pode retirar profissionais de hospitais ou locais de atendimento de toda a população para atender apenas um paciente.

Ademais, a pretensão destina-se a cuidados de higiene pessoal, que podem ser realizados pela família (Art. 227 da CRFB), conforme entendimento do TJMS. Em vista disso, o pedido merece s...
```

---

## 25. Fraldas Descartáveis

| Campo | Valor |
|-------|-------|
| **ID** | 42 |
| **Nome** | `mer_fraldas` |
| **Categoria** | Mérito |
| **Subcategoria** | Fraldas |
| **Modo Ativação** | deterministic |
| **Ordem** | 3 |

### Condição de Ativação (Legado)

> Quando for pleiteado fornecimento de fraldas descartáveis.

### Conteúdo

```markdown
## FRALDAS DESCARTÁVEIS

O fornecimento de fraldas é política da assistência social, cujas medidas são desenvolvidas pelos municípios, nos termos da Lei n° 8.742/93 (LOAS) e da Norma Operacional Básica do Sistema Único de Assistência Social (NOB/SUAS/2102). Só é legítima a imposição de atuação direta dos estados se os custos ou a ausência de demanda municipal a exigirem (Art. 13, inciso V, da LOAS). Contudo, não estão presentes essas circunstâncias.

Além disso, por serem insumos de higiene pessoal, seu custeio não deve ser imposto ao SUS, como recomenda o Enunciado nº 10 do CNJ. Não existe previsão legal do dever de fornecê-las nem parece adequado o Judiciário imiscuir-se em atividade própria do legislador e do gestor público, com base na efetivação do direito à saúde.

Isso porque o princípio da seletividade (Art. 194, parágrafo único, inciso III, da CRFB) norteia a atividade do legislador e do administrador para que selecionem (por lei) as prestações aptas a cobrir as contingências sociais mais relevantes. É preciso considerar a escassez financeira frente às necessidades infindáveis da população.

Portanto, fraldas descartáveis são insumos prescindíveis e o pedido de seu fornecimento deve ser julgado improcedente, na forma do inciso I do Art. 487 do CPC.
```

### Texto para Embedding

```
TÍTULO: Fraldas Descartáveis
CATEGORIA: Mérito > Fraldas
QUANDO USAR: Quando for pleiteado fornecimento de fraldas descartáveis.
CONTEÚDO: ## FRALDAS DESCARTÁVEIS

O fornecimento de fraldas é política da assistência social, cujas medidas são desenvolvidas pelos municípios, nos termos da Lei n° 8.742/93 (LOAS) e da Norma Operacional Básica do Sistema Único de Assistência Social (NOB/SUAS/2102). Só é legítima a imposição de atuação direta dos estados se os custos ou a ausência de demanda municipal a exigirem (Art. 13, inciso V, da LOAS). Contudo, não estão presentes essas circunstâncias.

Além disso, por serem insumos de higiene pess...
```

---

## 26. Atendimento em Regime de Home Care

| Campo | Valor |
|-------|-------|
| **ID** | 43 |
| **Nome** | `mer_homecare` |
| **Categoria** | Mérito |
| **Subcategoria** | Home Care |
| **Modo Ativação** | deterministic |
| **Ordem** | 4 |

### Condição de Ativação (Legado)

> Quando for pleiteado atendimento domiciliar em regime de home care.

### Conteúdo

```markdown
## ATENDIMENTO EM REGIME DE HOME CARE

Não se deve confundir o home care com a atenção domiciliar. Aquele corresponde ao conjunto de procedimentos hospitalares realizados em domicílio por profissionais da saúde. É uma espécie de internação em casa. Já o Serviço de Atenção Domiciliar (SAD) é um conjunto de ações em domicílio para garantir a continuidade de cuidados. São visitas técnicas pré-programadas com profissionais de saúde para capacitar a família a oferecer cuidados ao usuário e ampliar sua autonomia.

Se deferido o regime de home care, o Estado deverá fornecer todos os equipamentos, insumos, medicamentos e recursos humanos necessários ao atendimento das necessidades do paciente, consoante RDC nº 11 da ANVISA. É obrigação muito ampla, de conteúdo incerto e de repercussões financeiras indeterminadas.

Por essa razão, a prescrição médica deve especificar quais cuidados de natureza hospitalar precisam ser realizados em casa por profissionais da saúde (banho no leito, troca de fraldas, mudança de posição a cada 2 horas, aspiração de vias aéreas, administração de água ou dieta por sonda, etc.), ao invés de sugerir a instalação de um "hospital em casa".

Portanto, o pedido de regime de home care merece ser julgado improcedente.
```

### Texto para Embedding

```
TÍTULO: Atendimento em Regime de Home Care
CATEGORIA: Mérito > Home Care
QUANDO USAR: Quando for pleiteado atendimento domiciliar em regime de home care.
CONTEÚDO: ## ATENDIMENTO EM REGIME DE HOME CARE

Não se deve confundir o home care com a atenção domiciliar. Aquele corresponde ao conjunto de procedimentos hospitalares realizados em domicílio por profissionais da saúde. É uma espécie de internação em casa. Já o Serviço de Atenção Domiciliar (SAD) é um conjunto de ações em domicílio para garantir a continuidade de cuidados. São visitas técnicas pré-programadas com profissionais de saúde para capacitar a família a oferecer cuidados ao usuário e ampliar su...
```

---

## 27. Medicamento Sem Registro na ANVISA - Tema 500

| Campo | Valor |
|-------|-------|
| **ID** | 38 |
| **Nome** | `mer_med_sem_anvisa` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 5 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento sem registro na ANVISA.

### Conteúdo

```markdown
## DO MEDICAMENTO SEM REGISTRO NA ANVISA (TEMA 500): {{ nome_sem_anvisa }}

Em 2019, o Supremo Tribunal Federal concluiu o julgamento do Recurso Extraordinário nº 657.718/MG. Ao interpretar o Art. 1º, inciso III; Art. 6º; Art. 23, inciso II; Art. 196; Art. 198, inciso II e § 2º; e Art. 204, todos da CRFB, a Corte fixou em repercussão geral (Tema 500) que:

> 1. O Estado não pode ser obrigado a fornecer medicamentos experimentais.
>
> 2. A ausência de registro na ANVISA impede, como regra geral, o fornecimento de medicamento por decisão judicial.
>
> 3. É possível, excepcionalmente, a concessão judicial de medicamento sem registro sanitário, em caso de mora irrazoável da ANVISA em apreciar o pedido (prazo superior ao previsto na Lei nº 13.411/2016), quando preenchidos três requisitos: (i) a existência de pedido de registro do medicamento no Brasil (salvo no caso de medicamentos órfãos para doenças raras e ultrarraras); (ii) a existência de registro do medicamento em renomadas agências de regulação no exterior; e (iii) a inexistência de substituto terapêutico com registro no Brasil.

Nesta demanda, a parte autora não se desincumbiu do ônus da prova de que:

(1) há pedido de registro do medicamento e mora irrazoável da ANVISA em analisá-lo;
(2) o medicamento é órfão e a sua doença rara ou ultrarrara;
(3) o medicamento está registrado em renomadas agências de regulação no exterior;
(iii) não existe substituto terapêutico no Brasil.

Portanto, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Medicamento Sem Registro na ANVISA - Tema 500
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento sem registro na ANVISA.
CONTEÚDO: ## DO MEDICAMENTO SEM REGISTRO NA ANVISA (TEMA 500): {{ nome_sem_anvisa }}

Em 2019, o Supremo Tribunal Federal concluiu o julgamento do Recurso Extraordinário nº 657.718/MG. Ao interpretar o Art. 1º, inciso III; Art. 6º; Art. 23, inciso II; Art. 196; Art. 198, inciso II e § 2º; e Art. 204, todos da CRFB, a Corte fixou em repercussão geral (Tema 500) que:

> 1. O Estado não pode ser obrigado a fornecer medicamentos experimentais.
>
> 2. A ausência de registro na ANVISA impede, como regra geral, ...
```

---

## 28. O SUS Fornece Insulinas Semelhantes

| Campo | Valor |
|-------|-------|
| **ID** | 40 |
| **Nome** | `mer_insulina` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 6 |

### Condição de Ativação (Legado)

> Quando for pleiteada insulina.

### Conteúdo

```markdown
## O SUS FORNECE INSULINAS SEMELHANTES

O SUS fornece insulinas. No Componente Básico da Assistência Farmacêutica, estão disponíveis a insulina humana regular e a humana NPH, fornecidas nas unidades básicas de saúde, de responsabilidade municipal.

No Componente Especializado da Assistência Farmacêutica, são fornecidas insulinas análogas de ação rápida e prolongada, de aquisição centralizada pelo Ministério de Saúde e distribuição pelas Secretarias Estaduais de Saúde.

As insulinas análogas estão incorporadas por seus gêneros, e não por suas espécies. O gênero de ação rápida é formado pelas insulinas lispro, asparte e glulisina e o de ação prolongada é formado pelas insulinas glargina, detemir e degludeca. Por isso, o NAT explica que as insulinas solicitadas não estão padronizadas na RENAME, especificamente com estes respectivos nomes.

Portanto, apesar da espécie de insulina requerida, o SUS oferece alternativa terapêutica do mesmo gênero e com eficácia similar.
```

### Texto para Embedding

```
TÍTULO: O SUS Fornece Insulinas Semelhantes
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteada insulina.
CONTEÚDO: ## O SUS FORNECE INSULINAS SEMELHANTES

O SUS fornece insulinas. No Componente Básico da Assistência Farmacêutica, estão disponíveis a insulina humana regular e a humana NPH, fornecidas nas unidades básicas de saúde, de responsabilidade municipal.

No Componente Especializado da Assistência Farmacêutica, são fornecidas insulinas análogas de ação rápida e prolongada, de aquisição centralizada pelo Ministério de Saúde e distribuição pelas Secretarias Estaduais de Saúde.

As insulinas análogas estã...
```

---

## 29. Análise de Medicamentos Não Incorporados - Tema 6

| Campo | Valor |
|-------|-------|
| **ID** | 37 |
| **Nome** | `mer_med_nao_inc_tema6` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 7 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento não incorporado ao SUS com registro na ANVISA.

### Conteúdo

```markdown
# orientação para LLM:

Ao elaborar este tópico, a LLM deve analisar cuidadosamente o caso concreto, com especial atenção às informações técnicas constantes dos autos, em particular o parecer do Núcleo de Apoio Técnico do Poder Judiciário (NATJUS), quando existente. A fundamentação não deve ser automática nem meramente abstrata, devendo dialogar com os elementos fáticos e técnicos do processo, inclusive para reconhecer a ausência ou a insuficiência de comprovação dos requisitos exigidos pelo Supremo Tribunal Federal.

---

## ANÁLISE JUDICIAL DE MEDICAMENTOS REGISTRADOS NA ANVISA E NÃO INCORPORADOS AO SUS DE ACORDO COM O TEMA 6 DO STF

Em 2020, o Ministro Gilmar Mendes pediu vista dos autos do RE 566.471/RN (Tema 6), depois de proposta a tese pelo Ministro Relator Marco Aurélio. O julgamento foi retomado em 2024, após a homologação dos acordos no RE 1.366.243/SC (Tema 1234). Em complemento a eles, foram fixadas as seguintes teses.

> 1. A ausência de inclusão de medicamento nas listas de dispensação do Sistema Único de Saúde - SUS (RENAME, RESME, REMUME, entre outras) impede, como regra geral, o fornecimento do fármaco por decisão judicial, independentemente do custo.
>
> 2. É possível, excepcionalmente, a concessão judicial de medicamento registrado na ANVISA, mas não incorporado às listas de dispensação do Sistema Único de Saúde, desde que preenchidos, cumulativamente, os seguintes requisitos, cujo ônus probatório incumbe ao autor da ação:
>
> (a) negativa de fornecimento do medicamento na via administrativa, nos termos do item '4' do Tema 1234 da repercussão geral;
>
> (b) ilegalidade do ato de não incorporação do medicamento pela Conitec, ausência de pedido de incorporação ou da mora na sua apreciação;
>
> (c) impossibilidade de substituição por outro medicamento constante das listas do SUS e dos protocolos clínicos e diretrizes terapêuticas;
>
> (d) comprovação, à luz da medicina baseada em evidências, da eficácia, acurácia, efetividade e segurança do fármaco, necessariamente respaldadas por evidências científicas de alto nível, ou seja, unicamente ensaios clínicos randomizados e revisão sistemática ou meta-análise;
>
> (e) imprescindibilidade clínica do tratamento, comprovada mediante laudo médico fundamentado, descrevendo inclusive qual o tratamento já realizado; e
>
> (f) incapacidade financeira de arcar com o custeio do medicamento.
>
> 3. Sob pena de nulidade da decisão judicial, o Poder Judiciário, ao apreciar pedido de concessão de medicamentos não incorporados, deverá obrigatoriamente:
>
> (a) analisar o ato administrativo comissivo ou omissivo de não incorporação pela Conitec ou da negativa de fornecimento da via administrativa;
>
> (b) aferir a presença dos requisitos de dispensação do medicamento, previstos no item 2, a partir da prévia consulta ao Núcleo de Apoio Técnico do Poder Judiciário (NATJUS), sempre que disponível na respectiva jurisdição, não podendo fundamentar a sua decisão unicamente em prescrição, relatório ou laudo médico juntado aos autos pelo autor da ação; e
>
> (c) no caso de deferimento judicial do fármaco, oficiar aos órgãos competentes para avaliarem a possibilidade de sua incorporação no âmbito do SUS.

Nesta demanda, a parte autora não se desincumbiu do ônus da prova porque:

(1) não apresentou negativa administrativa ilegal;
(2) não demonstrou a impossibilidade de substituição do medicamento por alternativas terapêuticas do SUS;
(3) não provou que o medicamento requerido é eficaz, acurado, efetivo e seguro à luz de ensaio clínico randomizado, revisão sistemática ou meta-análise;
(4) não descreveu os tratamentos realizados.

Portanto, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Análise de Medicamentos Não Incorporados - Tema 6
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento não incorporado ao SUS com registro na ANVISA.
CONTEÚDO: # orientação para LLM:

Ao elaborar este tópico, a LLM deve analisar cuidadosamente o caso concreto, com especial atenção às informações técnicas constantes dos autos, em particular o parecer do Núcleo de Apoio Técnico do Poder Judiciário (NATJUS), quando existente. A fundamentação não deve ser automática nem meramente abstrata, devendo dialogar com os elementos fáticos e técnicos do processo, inclusive para reconhecer a ausência ou a insuficiência de comprovação dos requisitos exigidos pelo Sup...
```

---

## 30. Custo-Efetividade do Pedido

| Campo | Valor |
|-------|-------|
| **ID** | 45 |
| **Nome** | `mer_custo_efetividade` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 8 |

### Condição de Ativação (Legado)

> Quando o valor do tratamento com medicamento não incorporado for superior a R$ 100.000,00.

### Conteúdo

```markdown
## CUSTO-EFETIVIDADE DO PEDIDO

O custo-efetividade é a medida do valor das intervenções em saúde. Ele supre a lacuna entre preferências (subjetividade) e ciência (objetividade). Embora a opção terapêutica seja uma questão técnica guiada pelo conhecimento profissional e o estado de arte, o crescimento da demanda em contraposição à escassez de recursos impõe a análise do custo-efetividade. Nesta demanda, o tratamento pleiteado pode custar R$ {{ valor }}.

A situação sob análise do Judiciário é se o gestor deve arcar com o custo desse tratamento ou se esses recursos seriam melhor aplicados em políticas públicas de saúde universalizáveis. Nesse cenário em que o magistrado atua como gestor, ele deve considerar a desproporção entre a possibilidade de benefício ao paciente em face da certeza de prejuízo aos demais usuários do sistema de saúde.

Além disso, deve-se ponderar que o benefício individual não está previsto em lei, não tem previsão orçamentária ou evidências científicas.

Portanto, o pedido merece ser julgado improcedente.
```

### Texto para Embedding

```
TÍTULO: Custo-Efetividade do Pedido
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando o valor do tratamento com medicamento não incorporado for superior a R$ 100.000,00.
CONTEÚDO: ## CUSTO-EFETIVIDADE DO PEDIDO

O custo-efetividade é a medida do valor das intervenções em saúde. Ele supre a lacuna entre preferências (subjetividade) e ciência (objetividade). Embora a opção terapêutica seja uma questão técnica guiada pelo conhecimento profissional e o estado de arte, o crescimento da demanda em contraposição à escassez de recursos impõe a análise do custo-efetividade. Nesta demanda, o tratamento pleiteado pode custar R$ {{ valor }}.

A situação sob análise do Judiciário é se...
```

---

## 31. Medicamento para Uso Off Label - Tema 106

| Campo | Valor |
|-------|-------|
| **ID** | 39 |
| **Nome** | `mer_med_offlabel` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 9 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento para uso off label (fora da bula).

### Conteúdo

```markdown
## DO USO OFF LABEL DO MEDICAMENTO (TEMA 106): {{ offlabel_nome }}

É proibido fornecer medicamento para uso off label (fora da bula) no SUS (Art. 19-T da Lei nº 8.080/90 e Art. 12 da Lei n.º 6.360/76). Por isso, o Tema 106 do STJ veda o deferimento judicial de medicamento para uso off label. No entanto, a parte autora requer medicamento para uso fora das hipóteses autorizadas na bula aprovada pela ANVISA, motivo pelo qual, o pedido é improcedente.


ATENÇÃO:

O uso off label caracteriza-se exclusivamente pela prescrição do medicamento em desconformidade com a bula aprovada pela ANVISA, seja quanto à indicação terapêutica, posologia, faixa etária ou forma de administração.

Diversa é a hipótese de desconformidade com os critérios de incorporação no SUS. Nessa situação, o medicamento pode até possuir indicação em bula para determinada patologia, mas não foi incorporado ao SUS para aquele uso específico, por decisão técnica e administrativa no âmbito da política pública de saúde. Tal circunstância, por si só, não configura uso off label, mas apenas ausência de incorporação para aquela indicação.
```

### Texto para Embedding

```
TÍTULO: Medicamento para Uso Off Label - Tema 106
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento para uso off label (fora da bula).
CONTEÚDO: ## DO USO OFF LABEL DO MEDICAMENTO (TEMA 106): {{ offlabel_nome }}

É proibido fornecer medicamento para uso off label (fora da bula) no SUS (Art. 19-T da Lei nº 8.080/90 e Art. 12 da Lei n.º 6.360/76). Por isso, o Tema 106 do STJ veda o deferimento judicial de medicamento para uso off label. No entanto, a parte autora requer medicamento para uso fora das hipóteses autorizadas na bula aprovada pela ANVISA, motivo pelo qual, o pedido é improcedente.


ATENÇÃO:

O uso off label caracteriza-se excl...
```

---

## 32. Súmulas Vinculantes nº 60 e 61 sobre Medicamentos

| Campo | Valor |
|-------|-------|
| **ID** | 33 |
| **Nome** | `mer_sv_60_61` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 10 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento.

### Conteúdo

```markdown
## SÚMULAS VINCULANTES Nº 60 E 61 SOBRE MEDICAMENTOS

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC e do RE 566.471/RN, afetados à sistemática de repercussão geral (Temas 1234 e 6), que debateram a judicialização de medicamentos. O Tema 1234 é aplicável a qualquer medicamento e o Tema 6 só a medicamentos com registro na ANVISA, mas não incorporados ao SUS. Em ambos os casos, foram aprovados enunciados de súmula vinculante.

> Súmula Vinculante nº 60. O pedido e a análise administrativos de fármacos na rede pública de saúde, a judicialização do caso, bem ainda seus desdobramentos (administrativos e jurisdicionais) devem observar os termos dos 3 (três) acordos interfederativos (e seus fluxos) homologados pelo Supremo Tribunal Federal, em governança judicial colaborativa, no tema 1.234 da sistemática da repercussão geral (RE 1.366.243)
>
> Súmula Vinculante nº 61. A concessão judicial de medicamento registrado na ANVISA, mas não incorporado às listas de dispensação do Sistema Único de Saúde, deve observar as teses firmadas no julgamento do Tema 6 da Repercussão Geral (RE 566.471).

Nesse cenário, passa-se à análise desta demanda.
```

### Texto para Embedding

```
TÍTULO: Súmulas Vinculantes nº 60 e 61 sobre Medicamentos
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento.
CONTEÚDO: ## SÚMULAS VINCULANTES Nº 60 E 61 SOBRE MEDICAMENTOS

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC e do RE 566.471/RN, afetados à sistemática de repercussão geral (Temas 1234 e 6), que debateram a judicialização de medicamentos. O Tema 1234 é aplicável a qualquer medicamento e o Tema 6 só a medicamentos com registro na ANVISA, mas não incorporados ao SUS. Em ambos os casos, foram aprovados enunciados de súmula vinculante.

> Súmula Vinculante nº 60. O pedido e a análise ad...
```

---

## 33. Medicamento Não Incorporado para Situação Clínica da Parte Autora

| Campo | Valor |
|-------|-------|
| **ID** | 34 |
| **Nome** | `mer_med_pat_div` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 11 |

### Condição de Ativação (Legado)

> Quando o medicamento estiver incorporado ao SUS para patologia, dosagem ou forma de dispensação diversa da situação clínica da parte autora.

### Conteúdo

```markdown
## O MEDICAMENTO {% if pat_div %}{{ nome_pat_div }}{% endif %}{% if dos_div %}{{ nome_dos_div }}{% endif %}{% if for_div %}{{ nome_for_div }}{% endif %} NÃO ESTÁ INCORPORADO AO SUS PARA A SITUAÇÃO CLÍNICA DA PARTE AUTORA

Definir se um medicamento está ou não incorporado ao SUS é relevante para determinar quais os fluxos e critérios aplicáveis ao pedido de medicamento. Segundo conceituação estabelecida pelo STF no Tema 1234, não estão incorporados os medicamentos que se enquadrem na seguinte definição.

> II – Definição de Medicamentos Não Incorporados
>
> 2.1) Consideram-se medicamentos não incorporados aqueles que não constam na política pública do SUS; medicamentos previstos nos PCDTs para outras finalidades; medicamentos sem registro na ANVISA; e medicamentos off label sem PCDT ou que não integrem listas do componente básico.

Diante disso, não basta que o medicamento tenha sido "incorporado" por uma Portaria do Ministério da Saúde ou que tenha sido incluído em listagem oficial de medicamentos, como a Relação Nacional de Medicamentos (RENAME). É preciso averiguar se ele está incluído na política pública do SUS.

{% if pat_div %}Conforme consta da RENAME, o medicamento {{ nome_pat_div }} está incorporado ao SUS para patologia diversa ({{ patologia_div }}) daquela apresentada pela parte autora ({{ patologia }}), ou seja, a incorporação do medicamento contempla indicação clínica específica que não corresponde à condição de saúde do paciente nos autos.{% endif %}

{% if dos_div %}Conforme consta da RENAME, o medicamento {{ nome_dos_div }} está incorporado ao SUS, porém em dosagem diversa daquela pleiteada pela parte autora. A política pública prevê o fornecimento do medicamento em concentração ou posologia diferente da prescrita.{% endif %}

{% if for_div %}Conforme consta da RENAME, o medicamento {{ nome_for_div }} está incorporado ao SUS, porém com forma de dispensação diversa daquela pleiteada pela parte autora. A política pública prevê o fornecimento do medicamento em apresentação farmacêutica diferente da prescrita.{% endif %}

Portanto, o medicamento não está incorporado para a situação da parte autora, segundo definição vinculante adotada pelo STF, e os critérios de análise judicial do pedido são os seguintes.
```

### Texto para Embedding

```
TÍTULO: Medicamento Não Incorporado para Situação Clínica da Parte Autora
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando o medicamento estiver incorporado ao SUS para patologia, dosagem ou forma de dispensação diversa da situação clínica da parte autora.
CONTEÚDO: ## O MEDICAMENTO {% if pat_div %}{{ nome_pat_div }}{% endif %}{% if dos_div %}{{ nome_dos_div }}{% endif %}{% if for_div %}{{ nome_for_div }}{% endif %} NÃO ESTÁ INCORPORADO AO SUS PARA A SITUAÇÃO CLÍNICA DA PARTE AUTORA

Definir se um medicamento está ou não incorporado ao SUS é relevante para determinar quais os fluxos e critérios aplicáveis ao pedido de medicamento. Segundo conceituação estabelecida pelo STF no Tema 1234, não estão incorporados os medicamentos que se enquadrem na seguinte def...
```

---

## 34. Análise de Medicamentos Não Incorporados - Tema 1234

| Campo | Valor |
|-------|-------|
| **ID** | 36 |
| **Nome** | `mer_med_nao_inc_tema1234` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 12 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento não incorporado ao SUS (naoinc, pat_div, dos_div, for_div, onco não incorporado).

### Conteúdo

```markdown
## ANÁLISE JUDICIAL DE MEDICAMENTOS NÃO INCORPORADOS AO SUS DE ACORDO COM O TEMA 1234 DO STF

O Supremo Tribunal Federal definiu critérios para análise judicial de pedidos de medicamentos não incorporados ao SUS no RE 1.366.243/SC (Tema 1234). Diante da força vinculante do precedente (Art. 927, incisos II e III, do CPC), exige-se análise da legalidade do ato administrativo de indeferimento. Nos termos da decisão:

> 4) Sob pena de nulidade do ato jurisdicional (art. 489, § 1º, V e VI, c/c art. 927, III, §1º, ambos do CPC), o Poder Judiciário, ao apreciar pedido de concessão de medicamentos não incorporados, deverá obrigatoriamente analisar o ato administrativo comissivo ou omissivo da não incorporação pela Conitec e da negativa de fornecimento na via administrativa, tal como acordado entre os Entes Federativos em autocomposição no Supremo Tribunal Federal.
>
> 4.1) No exercício do controle de legalidade, o Poder Judiciário não pode substituir a vontade do administrador, mas tão somente verificar se o ato administrativo específico daquele caso concreto está em conformidade com as balizas presentes na Constituição Federal, na legislação de regência e na política pública no SUS.
>
> 4.2) A análise jurisdicional do ato administrativo que indefere o fornecimento de medicamento não incorporado restringe-se ao exame da regularidade do procedimento e da legalidade do ato de não incorporação e do ato administrativo questionado, à luz do controle de legalidade e da teoria dos motivos determinantes, não sendo possível incursão no mérito administrativo.
>
> 4.3) Tratando-se de medicamento não incorporado, é do autor da ação o ônus de demonstrar, com fundamento na Medicina Baseada em Evidências, a segurança e a eficácia do fármaco, bem como a inexistência de substituto terapêutico incorporado pelo SUS.
>
> 4.4) Conforme decisão da STA 175-AgR, não basta a simples alegação de necessidade do medicamento, mesmo que acompanhada de relatório médico, sendo necessária a demonstração de que a opinião do profissional encontra respaldo em evidências científicas de alto nível, ou seja, unicamente ensaios clínicos randomizados, revisão sistemática ou meta-análise.

Nesta demanda, a parte autora não se desincumbiu do ônus da prova de que (IMPORTANTE: APRESENTAR ARGUMENTOS COM BASE NOS RESUMOS EXTRAÍDOS DO PROCESSO)

Portanto, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Análise de Medicamentos Não Incorporados - Tema 1234
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento não incorporado ao SUS (naoinc, pat_div, dos_div, for_div, onco não incorporado).
CONTEÚDO: ## ANÁLISE JUDICIAL DE MEDICAMENTOS NÃO INCORPORADOS AO SUS DE ACORDO COM O TEMA 1234 DO STF

O Supremo Tribunal Federal definiu critérios para análise judicial de pedidos de medicamentos não incorporados ao SUS no RE 1.366.243/SC (Tema 1234). Diante da força vinculante do precedente (Art. 927, incisos II e III, do CPC), exige-se análise da legalidade do ato administrativo de indeferimento. Nos termos da decisão:

> 4) Sob pena de nulidade do ato jurisdicional (art. 489, § 1º, V e VI, c/c art. 9...
```

---

## 35. Análise de Medicamentos Incorporados ao SUS - Tema 1234

| Campo | Valor |
|-------|-------|
| **ID** | 35 |
| **Nome** | `mer_med_inc_tema1234` |
| **Categoria** | Mérito |
| **Subcategoria** | Medicamentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 13 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento incorporado ao SUS ou insulina tipo análoga rápida ou lenta

### Conteúdo

```markdown
## Instrução de uso para a LLM – Tema 1234 do STF

Ao redigir a peça, **utilize exclusivamente o subtópico correspondente ao componente do SUS efetivamente em discussão no caso concreto**.

Não reproduza, mencione ou faça referência a subtópicos relativos a outros componentes que **não guardem relação direta com o medicamento pleiteado**.

Em especial:

- Se o medicamento pertencer ao **CBAF**, utilize **apenas** o subtópico “Medicamentos do CBAF”.
- Se o medicamento pertencer ao **CEAF – Grupo 1A**, utilize **apenas** o subtópico “Medicamentos do CEAF – Grupo 1A”.
- Se o medicamento pertencer ao **CEAF – Grupos 1B e 2**, utilize **apenas** o subtópico “Medicamentos do CEAF – Grupos 1B e 2”.
- Se o medicamento pertencer ao **CESAF**, utilize **apenas** o subtópico “Medicamentos do CESAF”.

Os demais subtópicos devem ser **integralmente ignorados**, como se não existissem para fins de geração do texto.

A análise jurídica, a fundamentação e a conclusão devem se limitar **exclusivamente** ao subtópico aplicável ao caso em discussão.

---

## ANÁLISE JUDICIAL DE MEDICAMENTOS INCORPORADOS AO SUS DE ACORDO COM O TEMA 1234 DO STF

O Supremo Tribunal Federal, no julgamento do Tema 1234, definiu fluxos específicos para a análise judicial de pedidos de medicamentos incorporados ao SUS, conforme o componente ao qual pertencem: Componente Básico da Assistência Farmacêutica (CBAF), Componente Especializado da Assistência Farmacêutica (CEAF) e Componente Estratégico da Assistência Farmacêutica (CESAF).

Quando o medicamento pleiteado integra o Componente Básico da Assistência Farmacêutica (CBAF), o magistrado deve, à luz do controle de legalidade, examinar o ato administrativo em relação à situação apresentada nos autos. Nessa hipótese, o fornecimento deve ser determinado em face do Município ou do Distrito Federal, sendo que eventual responsabilização do Estado depende de prévia pactuação, nos termos dos arts. 39 e 41 da Portaria de Consolidação GM/MS nº 2.

Quando se tratar de medicamento do Grupo 1A do CEAF, o juiz deve analisar qual é a fase do fluxo de distribuição em que se encontra o fármaco, confrontando o ato administrativo com a situação concreta apresentada nos autos. Em regra, o fornecimento é de responsabilidade da União, admitindo-se a atribuição ao Estado apenas nas hipóteses expressamente previstas no próprio fluxo administrativo.

Nos casos de medicamentos pertencentes aos Grupos 1B ou 2 do CEAF, cabe ao magistrado verificar a fase do fluxo de distribuição e a legalidade do ato administrativo praticado. A definição do ente responsável deve observar que a responsabilização do Município somente ocorre se houver pactuação prévia, nos termos do art. 67 da Portaria de Consolidação GM/MS nº 2.

Quando o medicamento integrar o Componente Estratégico da Assistência Farmacêutica (CESAF), o exame judicial deve considerar a fase do fluxo de distribuição e o ato administrativo questionado. Em regra, o fornecimento compete à União, podendo ser direcionado ao Estado ou ao Município apenas nas hipóteses previstas no próprio fluxo administrativo.

No caso concreto, não se verifica ilegalidade em ato administrativo praticado pelo Estado quando, conforme a situação fática demonstrada nos autos, o Estado não é o ente responsável pelo fornecimento do medicamento segundo o componente do SUS aplicável, a parte autora não requereu previamente o cadastro administrativo para acesso a medicamentos do CEAF ou do CESAF, a parte autora não preenche os requisitos previstos nos Protocolos Clínicos e Diretrizes Terapêuticas estabelecidos pelo Ministério da Saúde, ou a eventual indisponibilidade do medicamento decorre de omissão da União, responsável pela compra centralizada de medicamentos do Grupo 1A do CEAF ou do CESAF.

Quando aplicável, o fornecimento de medicamentos do CBAF deve ser direcionado ao Município, enquanto o fornecimento de medicamentos do Grupo 1A do CEAF ou do CESAF deve ser direcionado à União, conforme a repartição de competências definida pelo Supremo Tribunal Federal.

Diante desse cenário, o pedido deve ser julgado improcedente. Subsidiariamente, caso se entenda pelo fornecimento do medicamento, este deve ser direcionado exclusivamente ao ente público competente, de acordo com o componente do SUS e o respectivo fluxo administrativo.
```

### Texto para Embedding

```
TÍTULO: Análise de Medicamentos Incorporados ao SUS - Tema 1234
CATEGORIA: Mérito > Medicamentos
QUANDO USAR: Quando for pleiteado medicamento incorporado ao SUS ou insulina tipo análoga rápida ou lenta
CONTEÚDO: ## Instrução de uso para a LLM – Tema 1234 do STF

Ao redigir a peça, **utilize exclusivamente o subtópico correspondente ao componente do SUS efetivamente em discussão no caso concreto**.

Não reproduza, mencione ou faça referência a subtópicos relativos a outros componentes que **não guardem relação direta com o medicamento pleiteado**.

Em especial:

- Se o medicamento pertencer ao **CBAF**, utilize **apenas** o subtópico “Medicamentos do CBAF”.
- Se o medicamento pertencer ao **CEAF – Grupo ...
```

---

## 36. A Parte Autora Não Buscou o Atendimento Oncológico do SUS

| Campo | Valor |
|-------|-------|
| **ID** | 41 |
| **Nome** | `mer_onco_sem_unacon` |
| **Categoria** | Mérito |
| **Subcategoria** | Oncologia |
| **Modo Ativação** | deterministic |
| **Ordem** | 14 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento oncológico e a parte autora não buscou atendimento em CACON/UNACON (verificar no parecer do NAT)

### Conteúdo

```markdown
## A PARTE AUTORA NÃO BUSCOU O ATENDIMENTO ONCOLÓGICO DO SUS

O SUS oferece assistência integral em oncologia em instituições habilitadas pelo Ministério da Saúde: Centros de Assistência de Alta Complexidade em Oncologia (CACON) e Unidades de Assistência de Alta Complexidade em Oncologia (UNACON). Em Mato Grosso do Sul, existem sete delas. No entanto, a parte autora não buscou atendimento na rede pública.

As normas do Ministério da Saúde estabelecem que medicamentos para tratamento do câncer serão fornecidos pelo estabelecimento habilitado apenas para pacientes atendidos na própria unidade. Isso porque o tratamento do câncer é complexo e não exige apenas fármacos, mas também quimio e radioterapias e até cirurgias.

O esquema terapêutico e o acompanhamento são responsabilidades do estabelecimento habilitado para isso. Por essa razão, o paciente precisa ser inserido no sistema de regulação, como orienta o Enunciado nº 07 do CNJ.

Neste caso, o deferimento judicial de medicamento oncológico atribui ao ente público o ônus financeiro, sem a garantia da integralidade do atendimento para o paciente. Portanto, ainda que se reconhecesse a patologia como incontroversa, a pretensão de obter medicamentos isoladamente não procede porque a parte autora não está desassistida.
```

### Texto para Embedding

```
TÍTULO: A Parte Autora Não Buscou o Atendimento Oncológico do SUS
CATEGORIA: Mérito > Oncologia
QUANDO USAR: Quando for pleiteado medicamento oncológico e a parte autora não buscou atendimento em CACON/UNACON (verificar no parecer do NAT)
CONTEÚDO: ## A PARTE AUTORA NÃO BUSCOU O ATENDIMENTO ONCOLÓGICO DO SUS

O SUS oferece assistência integral em oncologia em instituições habilitadas pelo Ministério da Saúde: Centros de Assistência de Alta Complexidade em Oncologia (CACON) e Unidades de Assistência de Alta Complexidade em Oncologia (UNACON). Em Mato Grosso do Sul, existem sete delas. No entanto, a parte autora não buscou atendimento na rede pública.

As normas do Ministério da Saúde estabelecem que medicamentos para tratamento do câncer se...
```

---

## 37. Não Há Urgência ou Emergência para o Atendimento

| Campo | Valor |
|-------|-------|
| **ID** | 30 |
| **Nome** | `mer_sem_urgencia` |
| **Categoria** | Mérito |
| **Subcategoria** | Procedimentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 15 |

### Condição de Ativação (Legado)

> Quando for pleiteada cirurgia eletiva  ou exame não urgente 

### Conteúdo

```markdown
## NÃO HÁ URGÊNCIA OU EMERGÊNCIA PARA O ATENDIMENTO

O quadro clínico da parte autora não é uma urgência ou emergência porque não exige atendimento imediato, segundo definições da Portaria nº 354, de 10 de março de 2014, do Ministério da Saúde, e da Resolução nº 1.451/1995, do Conselho Federal de Medicina.

Ainda que o fosse, a ordem de atendimento seria orientada pela classificação de risco dos pacientes. Contudo, a alegação de que o atendimento da parte autora mereceria ser preferido não é verossímil porque não há elementos que indiquem grave sofrimento ou risco à vida, motivo pelo qual, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: Não Há Urgência ou Emergência para o Atendimento
CATEGORIA: Mérito > Procedimentos
QUANDO USAR: Quando for pleiteada cirurgia eletiva  ou exame não urgente 
CONTEÚDO: ## NÃO HÁ URGÊNCIA OU EMERGÊNCIA PARA O ATENDIMENTO

O quadro clínico da parte autora não é uma urgência ou emergência porque não exige atendimento imediato, segundo definições da Portaria nº 354, de 10 de março de 2014, do Ministério da Saúde, e da Resolução nº 1.451/1995, do Conselho Federal de Medicina.

Ainda que o fosse, a ordem de atendimento seria orientada pela classificação de risco dos pacientes. Contudo, a alegação de que o atendimento da parte autora mereceria ser preferido não é ver...
```

---

## 38. É Preciso Considerar a Dificuldade Real do Gestor Estadual

| Campo | Valor |
|-------|-------|
| **ID** | 32 |
| **Nome** | `mer_dificuldade_gestor` |
| **Categoria** | Mérito |
| **Subcategoria** | Procedimentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 16 |

### Condição de Ativação (Legado)

> Quando for pleiteada cirurgia, consulta e exame, não houver informação de que o paciente já está inserido no sistema de regulação estadual (CORE)

### Conteúdo

```markdown
## É PRECISO CONSIDERAR A DIFICULDADE REAL DO GESTOR ESTADUAL

Há dois sistemas de regulação: o municipal (SISREG) e o estadual (CORE). O sistema municipal é adotado em todo território estadual para agendamento de procedimentos oferecidos no SUS. Os servidores estaduais não têm meios materiais para agendar consultas, exames, cirurgias ou terapias no SISREG.

Embora possam fazê-lo no CORE, existem dois pontos de atenção. O primeiro é que o CORE não regula todos os atendimentos do SUS. Somente podem ser inseridos no CORE:

(1) urgências e emergências;
(2) transferências hospitalares;
(3) procedimentos oferecidos em hospitais estaduais;
(4) internações psiquiátricas; e
(5) procedimentos contemplados no Programa MS Saúde.

O segundo é que o município de residência da pessoa que deve inserir o pedido no sistema estadual.

Em vista da realidade do gestor estadual, não há omissão ou demora do Estado de Mato Grosso do Sul no atendimento (Art. 20 e Art. 22 da LINDB).
```

### Texto para Embedding

```
TÍTULO: É Preciso Considerar a Dificuldade Real do Gestor Estadual
CATEGORIA: Mérito > Procedimentos
QUANDO USAR: Quando for pleiteada cirurgia, consulta e exame, não houver informação de que o paciente já está inserido no sistema de regulação estadual (CORE)
CONTEÚDO: ## É PRECISO CONSIDERAR A DIFICULDADE REAL DO GESTOR ESTADUAL

Há dois sistemas de regulação: o municipal (SISREG) e o estadual (CORE). O sistema municipal é adotado em todo território estadual para agendamento de procedimentos oferecidos no SUS. Os servidores estaduais não têm meios materiais para agendar consultas, exames, cirurgias ou terapias no SISREG.

Embora possam fazê-lo no CORE, existem dois pontos de atenção. O primeiro é que o CORE não regula todos os atendimentos do SUS. Somente pod...
```

---

## 39. É Preciso Respeitar a Fila de Atendimento Eletivo

| Campo | Valor |
|-------|-------|
| **ID** | 31 |
| **Nome** | `mer_fila_eletivo` |
| **Categoria** | Mérito |
| **Subcategoria** | Procedimentos |
| **Modo Ativação** | deterministic |
| **Ordem** | 17 |

### Condição de Ativação (Legado)

> Quando o procedimento for eletivo e a parte autora não estiver inserida no SISREG ou tiver sido inserida recentemente.

### Conteúdo

```markdown
## É PRECISO RESPEITAR A FILA DE ATENDIMENTO ELETIVO

A providência de saúde pretendida é de atendimento eletivo. Nesses casos, a ordem de atendimento no SUS é orientada pela data de solicitação. Ocorre que a parte autora não está inserida no sistema de regulação e não há omissão ou demora do Estado, consoante Enunciado nº 69 do CNJ e entendimento desse Tribunal. Consequentemente, o pedido é improcedente.

OU

A providência de saúde pretendida é de atendimento eletivo. Nesses casos, a ordem de atendimento no SUS é orientada pela data de solicitação. Ocorre que a parte autora foi inserida recentemente no sistema de regulação e não há omissão ou demora do Estado, consoante Enunciado nº 93 do CNJ e entendimento desse Tribunal. Consequentemente, o pedido é improcedente.
```

### Texto para Embedding

```
TÍTULO: É Preciso Respeitar a Fila de Atendimento Eletivo
CATEGORIA: Mérito > Procedimentos
QUANDO USAR: Quando o procedimento for eletivo e a parte autora não estiver inserida no SISREG ou tiver sido inserida recentemente.
CONTEÚDO: ## É PRECISO RESPEITAR A FILA DE ATENDIMENTO ELETIVO

A providência de saúde pretendida é de atendimento eletivo. Nesses casos, a ordem de atendimento no SUS é orientada pela data de solicitação. Ocorre que a parte autora não está inserida no sistema de regulação e não há omissão ou demora do Estado, consoante Enunciado nº 69 do CNJ e entendimento desse Tribunal. Consequentemente, o pedido é improcedente.

OU

A providência de saúde pretendida é de atendimento eletivo. Nesses casos, a ordem de a...
```

---

## 40. Da Restituição de Eventuais Valores Despendidos

| Campo | Valor |
|-------|-------|
| **ID** | 48 |
| **Nome** | `mer_restituicao` |
| **Categoria** | Mérito |
| **Subcategoria** | Restituição |
| **Modo Ativação** | deterministic |
| **Ordem** | 18 |

### Condição de Ativação (Legado)

> Quando for pleiteada restituição de valores eventualmente despendidos pela parte autora.

### Conteúdo

```markdown
## DA RESTITUIÇÃO DE EVENTUAIS VALORES DESPENDIDOS

A parte autora pleiteia a restituição de valores eventualmente despendidos por ela para a compra do objeto da ação. Ocorre que demandas judiciais de saúde pressupõem que o paciente não possa custear o tratamento. Se consegue (e opta por) custeá-lo, não há direito ao ressarcimento pelo Poder Público.

Isso se mantém ainda que a obrigação de dar a providência de saúde em espécie esteja constituída em título executivo judicial porque o juízo pode determinar todas as medidas indutivas, coercitivas, mandamentais ou substitutivas para assegurar o cumprimento de sua decisão, inclusive o sequestro de recursos públicos. Em vista disso, o pedido de ressarcimento é improcedente.
```

### Texto para Embedding

```
TÍTULO: Da Restituição de Eventuais Valores Despendidos
CATEGORIA: Mérito > Restituição
QUANDO USAR: Quando for pleiteada restituição de valores eventualmente despendidos pela parte autora.
CONTEÚDO: ## DA RESTITUIÇÃO DE EVENTUAIS VALORES DESPENDIDOS

A parte autora pleiteia a restituição de valores eventualmente despendidos por ela para a compra do objeto da ação. Ocorre que demandas judiciais de saúde pressupõem que o paciente não possa custear o tratamento. Se consegue (e opta por) custeá-lo, não há direito ao ressarcimento pelo Poder Público.

Isso se mantém ainda que a obrigação de dar a providência de saúde em espécie esteja constituída em título executivo judicial porque o juízo pode ...
```

---

## 41. Não É Aconselhável a Predefinição de Método Específico - TEA

| Campo | Valor |
|-------|-------|
| **ID** | 46 |
| **Nome** | `mer_autismo` |
| **Categoria** | Mérito |
| **Subcategoria** | TEA |
| **Modo Ativação** | deterministic |
| **Ordem** | 19 |

### Condição de Ativação (Legado)

> Quando for pleiteado tratamento específico para TEA (Transtorno do Espectro Autista).

### Conteúdo

```markdown
## DO MÉTODO ESPECÍFICO E DA POLÍTICA PÚBLICA PARA PACIENTES COM AUTISMO

O SUS oferece uma rede de apoio e assistência a pacientes com autismo em Centros Especializados em Reabilitação (CER) e Centros de Atenção Psicossocial infantil (CAPS IJ). Além disso, existem a Associação de Pais e Amigos dos Excepcionais (APAE) e a Associação de Pais e Amigos do Autista (AMA). Nessa rede, é elaborado e desenvolvido um Projeto Terapêutico Singular (PTS) com ações interdisciplinares para o desenvolvimento e bem-estar do paciente.

Segundo a Sociedade Brasileira de Pediatria (SBP), "o tratamento padrão-ouro para o TEA é a intervenção precoce", não um método específico. Igualmente, o PCDT do Comportamento Agressivo no TEA ensina que "apesar de algumas terapias e técnicas terem sido mais exploradas na literatura científica, revisões sistemáticas reconhecem os benefícios de diversas intervenções, sem sugerir superioridade de qualquer modelo".

Embora a escolha da intervenção seja livre ao paciente na rede privada, não há esse direito em face do SUS. Para exigir do Poder Público determinado tratamento, é preciso demonstrar a ineficácia das opções disponíveis na rede pública. Nesta demanda, não há evidência científica de superioridade do método pleiteado, tampouco houve o esgotamento das alternativas disponíveis no SUS.

Portanto, o pedido de metodologia específica é improcedente.
```

### Texto para Embedding

```
TÍTULO: Não É Aconselhável a Predefinição de Método Específico - TEA
CATEGORIA: Mérito > TEA
QUANDO USAR: Quando for pleiteado tratamento específico para TEA (Transtorno do Espectro Autista).
CONTEÚDO: ## DO MÉTODO ESPECÍFICO E DA POLÍTICA PÚBLICA PARA PACIENTES COM AUTISMO

O SUS oferece uma rede de apoio e assistência a pacientes com autismo em Centros Especializados em Reabilitação (CER) e Centros de Atenção Psicossocial infantil (CAPS IJ). Além disso, existem a Associação de Pais e Amigos dos Excepcionais (APAE) e a Associação de Pais e Amigos do Autista (AMA). Nessa rede, é elaborado e desenvolvido um Projeto Terapêutico Singular (PTS) com ações interdisciplinares para o desenvolvimento e...
```

---

## 42. Do Não Comparecimento à Audiência

| Campo | Valor |
|-------|-------|
| **ID** | 27 |
| **Nome** | `prel_nao_comparecimento` |
| **Categoria** | Preliminar |
| **Subcategoria** | Audiência |
| **Modo Ativação** | deterministic |
| **Ordem** | 0 |

### Condição de Ativação (Legado)

> Quando houver audiência designada no Juizado Especial.

### Conteúdo

```markdown
## DO NÃO COMPARECIMENTO À AUDIÊNCIA

O Estado de Mato Grosso do Sul não comparecerá à audiência de conciliação porque não existe legislação estadual que autorize a Procuradoria-Geral do Estado a conciliar no Juizado Especial (Art. 8º da Lei nº 12.153/09). Ademais, não existe interesse em produzir prova em audiência de instrução. Em vista disso, pede-se o cancelamento da audiência à luz da duração razoável do processo.
```

### Texto para Embedding

```
TÍTULO: Do Não Comparecimento à Audiência
CATEGORIA: Preliminar > Audiência
QUANDO USAR: Quando houver audiência designada no Juizado Especial.
CONTEÚDO: ## DO NÃO COMPARECIMENTO À AUDIÊNCIA

O Estado de Mato Grosso do Sul não comparecerá à audiência de conciliação porque não existe legislação estadual que autorize a Procuradoria-Geral do Estado a conciliar no Juizado Especial (Art. 8º da Lei nº 12.153/09). Ademais, não existe interesse em produzir prova em audiência de instrução. Em vista disso, pede-se o cancelamento da audiência à luz da duração razoável do processo.
```

---

## 43. Competência do Juizado Especial da Fazenda Pública

| Campo | Valor |
|-------|-------|
| **ID** | 14 |
| **Nome** | `prel_jef_estadual` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 1 |

### Condição de Ativação (Legado)

> Quando o juízo for 'Justiça Comum Estadual', o valor da causa for inferior ou igual a 60 salários mínimos (R$ 91.080,00) e existir Juizado Especial da Fazenda Pública instalado na comarca (Aquidauana, Bela Vista, Nioaque, Campo Grande, Dourados, Sonora, Terenos).

### Conteúdo

```markdown
## COMPETÊNCIA DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA

O valor atribuído à causa é inferior a 60 (sessenta) salários mínimos e existe Juizado Especial da Fazenda Pública instalado nesta Comarca. Assim, a competência do Juizado Especial para processar e julgar a demanda é absoluta (Art. 2º da Lei nº 12.153/09), independentemente da complexidade da causa, já que é possível realizar prova pericial nos Juizados (Art. 10 da Lei nº 12.153/09). Portanto, requer a remessa do processo ao juízo competente.
```

### Texto para Embedding

```
TÍTULO: Competência do Juizado Especial da Fazenda Pública
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando o juízo for 'Justiça Comum Estadual', o valor da causa for inferior ou igual a 60 salários mínimos (R$ 91.080,00) e existir Juizado Especial da Fazenda Pública instalado na comarca (Aquidauana, Bela Vista, Nioaque, Campo Grande, Dourados, Sonora, Terenos).
CONTEÚDO: ## COMPETÊNCIA DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA

O valor atribuído à causa é inferior a 60 (sessenta) salários mínimos e existe Juizado Especial da Fazenda Pública instalado nesta Comarca. Assim, a competência do Juizado Especial para processar e julgar a demanda é absoluta (Art. 2º da Lei nº 12.153/09), independentemente da complexidade da causa, já que é possível realizar prova pericial nos Juizados (Art. 10 da Lei nº 12.153/09). Portanto, requer a remessa do processo ao juízo competente...
```

---

## 44. Competência do Juizado Especial Federal

| Campo | Valor |
|-------|-------|
| **ID** | 15 |
| **Nome** | `prel_jef_federal` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 2 |

### Condição de Ativação (Legado)

> Quando o juízo for 'Justiça Comum Federal' e o valor da causa for inferior ou igual a 60 salários mínimos (R$ 91.080,00).

### Conteúdo

```markdown
## COMPETÊNCIA DO JUIZADO ESPECIAL FEDERAL

O valor atribuído à causa é inferior a 60 (sessenta) salários mínimos e existe Juizado Especial Federal instalado nesta Comarca. Assim, a competência do Juizado Especial para processar e julgar a demanda é absoluta (Art. 3º da Lei nº 10.259/01), independentemente da complexidade da causa, já que é possível realizar prova pericial nos Juizados (Art. 12 da Lei nº 10.259/01). Portanto, requer a remessa do processo ao juízo competente.
```

### Texto para Embedding

```
TÍTULO: Competência do Juizado Especial Federal
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando o juízo for 'Justiça Comum Federal' e o valor da causa for inferior ou igual a 60 salários mínimos (R$ 91.080,00).
CONTEÚDO: ## COMPETÊNCIA DO JUIZADO ESPECIAL FEDERAL

O valor atribuído à causa é inferior a 60 (sessenta) salários mínimos e existe Juizado Especial Federal instalado nesta Comarca. Assim, a competência do Juizado Especial para processar e julgar a demanda é absoluta (Art. 3º da Lei nº 10.259/01), independentemente da complexidade da causa, já que é possível realizar prova pericial nos Juizados (Art. 12 da Lei nº 10.259/01). Portanto, requer a remessa do processo ao juízo competente.
```

---

## 45. Competência da Justiça Federal - Produto à Base de Canabidiol

| Campo | Valor |
|-------|-------|
| **ID** | 17 |
| **Nome** | `prel_jf_canabidiol` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 3 |

### Condição de Ativação (Legado)

> Quando for pleiteado produto à base de canabidiol (cannabis).

### Regra Secundária (Fallback)

> parecer do nat avaliou pedido de canabidiol

### Conteúdo

```markdown
## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR PRODUTO À BASE DE CANABIDIOL QUE, APESAR DE TER AUTORIZAÇÃO SANITÁRIA, NÃO POSSUI REGISTRO NA ANVISA

A 1ª Seção do Superior Tribunal de Justiça julgou, em 05/06/2025, o Conflito de Competência nº 209648 - SC e, ao interpretar os Temas 500, 793, 1.161 e 1.234, do STF, entendeu que:

> Com efeito, apesar de ser possível a autorização de importação de produto derivado de Cannabis pela ANVISA, o aludido órgão esclareceu que esses produtos não são por ela registrados, conforme consta da Nota Técnica n. 11/2024/SEI/COCIC/GPCON/DIRE5/ANVISA.
> (...)
> Nesse contexto, a jurisprudência consolidada deste STJ entende, à luz do Tema 500/STF, que as ações, visando ao fornecimento de medicamentos não registrados na ANVISA, como é o caso dos autos, devem ser necessariamente propostas contra a União, atraindo, portanto, a competência da Justiça Federal para processá-las e julgá-las.

Diante disso, o processo deve ser remetido à Justiça federal.
```

### Texto para Embedding

```
TÍTULO: Competência da Justiça Federal - Produto à Base de Canabidiol
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando for pleiteado produto à base de canabidiol (cannabis).
CONTEÚDO: ## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR PRODUTO À BASE DE CANABIDIOL QUE, APESAR DE TER AUTORIZAÇÃO SANITÁRIA, NÃO POSSUI REGISTRO NA ANVISA

A 1ª Seção do Superior Tribunal de Justiça julgou, em 05/06/2025, o Conflito de Competência nº 209648 - SC e, ao interpretar os Temas 500, 793, 1.161 e 1.234, do STF, entendeu que:

> Com efeito, apesar de ser possível a autorização de importação de produto derivado de Cannabis pela ANVISA, o aludido órgão esclareceu que esses produtos não são por el...
```

---

## 46. Competência da Justiça Federal - Medicamentos Grupo 1A CEAF (Tema 1234)

| Campo | Valor |
|-------|-------|
| **ID** | 18 |
| **Nome** | `prel_jf_grupo1a` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 4 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento incorporado ao SUS no Grupo 1A do CEAF. SOMENTE APLICAR ÀS AÇÕES AJUIZADAS APÓS 19/09/2024 (VER A DATA DE AJUIZAMENTO DA DEMANDA)

### Regra Secundária (Fallback)

> o parecer do nat avaliou pedido de medicamento 1a

### Conteúdo

```markdown
## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTOS INCORPORADOS AO SUS NO GRUPO 1A: {{ nome_1a }}

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC (Tema 1234), afetado à sistemática de repercussão geral. Na oportunidade, homologou três acordos entre União, estados, Distrito Federal e municípios a respeito de definição, competência e custeio de medicamentos incorporados e não incorporados ao SUS. Nos termos da decisão:

> VI – Medicamentos incorporados
>
> 6) Em relação aos medicamentos incorporados, conforme conceituação estabelecida no âmbito da Comissão Especial e constante do Anexo I, os Entes concordam em seguir o fluxo administrativo e judicial detalhado no Anexo I, inclusive em relação à competência judicial para apreciação das demandas e forma de ressarcimento entre os Entes, quando devido.

Além disso, aprovou a seguinte súmula vinculante:

> O pedido e a análise administrativos de fármacos na rede pública de saúde, a judicialização do caso, bem ainda seus desdobramentos (administrativos e jurisdicionais), devem observar os termos dos 3 (três) acordos interfederativos (e seus fluxos) homologados pelo Supremo Tribunal Federal, em governança judicial colaborativa, no tema 1.234 da sistemática da repercussão geral (RE 1.366.243).

Nesta demanda, pede-se medicamento incorporado ao SUS no Grupo 1A do Componente Especializado da Assistência Farmacêutica (CEAF). Segundo o fluxo acordado pelos entes públicos e homologado pela Corte:

> a) Grupo 1A do CEAF: Competência da Justiça Federal e responsabilidade de custeio total da União, com posterior ressarcimento integral aos demais entes federativos que tenham suportado o ônus financeiro no processo, salvo se tratar de ato atribuído aos Estados na programação, distribuição ou dispensação;

Na hipótese de cumulação de pedidos: se houver medicamento de competência da Justiça federal e outros da Justiça estadual, todos serão de competência do juízo federal, independentemente do objeto ou valor dos demais, devido à força atrativa do foro federal.

No entanto, a parte autora não observou o precedente porque pediu à Justiça estadual medicamento incluído na competência da Justiça federal. Consequentemente, não há requisito de constituição e desenvolvimento regular do processo. Portanto, a competência é da Justiça federal.
```

### Texto para Embedding

```
TÍTULO: Competência da Justiça Federal - Medicamentos Grupo 1A CEAF (Tema 1234)
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando for pleiteado medicamento incorporado ao SUS no Grupo 1A do CEAF. SOMENTE APLICAR ÀS AÇÕES AJUIZADAS APÓS 19/09/2024 (VER A DATA DE AJUIZAMENTO DA DEMANDA)
CONTEÚDO: ## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTOS INCORPORADOS AO SUS NO GRUPO 1A: {{ nome_1a }}

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC (Tema 1234), afetado à sistemática de repercussão geral. Na oportunidade, homologou três acordos entre União, estados, Distrito Federal e municípios a respeito de definição, competência e custeio de medicamentos incorporados e não incorporados ao SUS. Nos termos da decisão:

> VI – Medicamentos incorporados
>
> 6) Em relaçã...
```

---

## 47. Competência da Justiça Federal - Medicamentos Não Incorporados > 210 SM (Tema 1234)

| Campo | Valor |
|-------|-------|
| **ID** | 19 |
| **Nome** | `prel_jf_nao_inc_210sm` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 5 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento não incorporado ao SUS com valor anual igual ou superior a 210 salários mínimos e a União não estiver no polo passivo. SOMENTE APLICAR ÀS AÇÕES AJUIZADAS APÓS 19/09/2024 (VER A DATA DE AJUIZAMENTO DA DEMANDA)

### Conteúdo

```markdown
## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTOS NÃO INCORPORADOS AO SUS COM VALOR ACIMA DE 210 SALÁRIOS MÍNIMOS

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC (Tema 1234), afetado à sistemática de repercussão geral. Na oportunidade, homologou três acordos entre União, estados, Distrito Federal e municípios a respeito de definição, competência e custeio de medicamentos incorporados e não incorporados ao SUS. Nos termos da decisão:

I – Competência

> 1) Para fins de fixação de competência, as demandas relativas a medicamentos não incorporados na política pública do SUS, mas com registro na ANVISA, tramitarão perante a Justiça Federal, nos termos do art. 109, I, da Constituição Federal, quando o valor do tratamento anual específico do fármaco ou do princípio ativo, com base no Preço Máximo de Venda do Governo (PMVG – situado na alíquota zero), divulgado pela Câmara de Regulação do Mercado de Medicamentos (CMED - Lei 10.742/2003), for igual ou superior ao valor de 210 salários mínimos, na forma do art. 292 do CPC.
>
> (...)
>
> 1.4) No caso de cumulação de pedidos, para fins de competência, será considerado apenas o valor do(s) medicamento(s) não incorporado(s) que deverá(ão) ser somado(s), independentemente da existência de cumulação alternativa de outros pedidos envolvendo obrigação de fazer, pagar ou de entregar coisa certa.

Além disso, aprovou a seguinte súmula vinculante:

> O pedido e a análise administrativos de fármacos na rede pública de saúde, a judicialização do caso, bem ainda seus desdobramentos (administrativos e jurisdicionais), devem observar os termos dos 3 (três) acordos interfederativos (e seus fluxos) homologados pelo Supremo Tribunal Federal, em governança judicial colaborativa, no tema 1.234 da sistemática da repercussão geral (RE 1.366.243).

No entanto, a parte autora não observou o precedente porque pediu à Justiça estadual medicamento incluído na competência da Justiça federal. Consequentemente, não há requisito de constituição e desenvolvimento regular do processo. Portanto, a competência é da Justiça federal.
```

### Texto para Embedding

```
TÍTULO: Competência da Justiça Federal - Medicamentos Não Incorporados > 210 SM (Tema 1234)
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando for pleiteado medicamento não incorporado ao SUS com valor anual igual ou superior a 210 salários mínimos e a União não estiver no polo passivo. SOMENTE APLICAR ÀS AÇÕES AJUIZADAS APÓS 19/09/2024 (VER A DATA DE AJUIZAMENTO DA DEMANDA)
CONTEÚDO: ## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTOS NÃO INCORPORADOS AO SUS COM VALOR ACIMA DE 210 SALÁRIOS MÍNIMOS

O Supremo Tribunal Federal concluiu o julgamento do RE 1.366.243/SC (Tema 1234), afetado à sistemática de repercussão geral. Na oportunidade, homologou três acordos entre União, estados, Distrito Federal e municípios a respeito de definição, competência e custeio de medicamentos incorporados e não incorporados ao SUS. Nos termos da decisão:

I – Competência

> 1) Para fins ...
```

---

## 48. Competência da Justiça Federal - Medicamento sem Registro na ANVISA (Tema 500)

| Campo | Valor |
|-------|-------|
| **ID** | 16 |
| **Nome** | `prel_jf_sem_anvisa` |
| **Categoria** | Preliminar |
| **Subcategoria** | Competência |
| **Modo Ativação** | deterministic |
| **Ordem** | 6 |

### Condição de Ativação (Legado)

> Quando NAT analisar medicamento sem registro na ANVISA.

### Conteúdo

```markdown
## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTO SEM REGISTRO NA ANVISA: {{ nome_sem_anvisa }}

O Supremo Tribunal Federal concluiu o julgamento do RE nº 657.718/MG (Tema 500) e, ao interpretar os arts. 1º, inciso III; 6º; 23, inciso II; 196; 198, inciso II e § 2º; e 204, todos da CRFB, fixou em repercussão geral que:

> (...)
> 4. As ações que demandem fornecimento de medicamentos sem registro na ANVISA deverão necessariamente ser propostas em face da União.

Diante disso, o processo deve ser extinto sem resolução do mérito, ante a incompetência da Justiça estadual para processar e julgar demanda por medicamento sem registro na ANVISA, ou, subsidiariamente, remetido à Justiça federal.
```

### Texto para Embedding

```
TÍTULO: Competência da Justiça Federal - Medicamento sem Registro na ANVISA (Tema 500)
CATEGORIA: Preliminar > Competência
QUANDO USAR: Quando NAT analisar medicamento sem registro na ANVISA.
CONTEÚDO: ## COMPETÊNCIA DA JUSTIÇA FEDERAL PARA JULGAR MEDICAMENTO SEM REGISTRO NA ANVISA: {{ nome_sem_anvisa }}

O Supremo Tribunal Federal concluiu o julgamento do RE nº 657.718/MG (Tema 500) e, ao interpretar os arts. 1º, inciso III; 6º; 23, inciso II; 196; 198, inciso II e § 2º; e 204, todos da CRFB, fixou em repercussão geral que:

> (...)
> 4. As ações que demandem fornecimento de medicamentos sem registro na ANVISA deverão necessariamente ser propostas em face da União.

Diante disso, o processo d...
```

---

## 49. Inépcia da Petição Inicial - Pedido Genérico

| Campo | Valor |
|-------|-------|
| **ID** | 20 |
| **Nome** | `prel_inepcia` |
| **Categoria** | Preliminar |
| **Subcategoria** | Condições da Ação |
| **Modo Ativação** | deterministic |
| **Ordem** | 7 |

### Condição de Ativação (Legado)

> Quando a parte autora fizer pedido genérico e indeterminado (ex: 'tudo mais o que se fizer necessário').

### Conteúdo

```markdown
## INÉPCIA DA PETIÇÃO INICIAL

Conforme se extrai da petição inicial, a parte autora formula **pedidos genéricos e indeterminados**, nos seguintes termos: **{{ peticao_inicial_pedidos_genericos }}**.

A admissão da demanda com esse grau de indeterminação autoriza o indevido alargamento do objeto litigioso, comprometendo a regularidade do andamento processual e conduzindo à duração indefinida das fases de conhecimento e de eventual cumprimento de sentença. Ademais, a formulação de pedidos genéricos inviabiliza o exercício efetivo do contraditório e da ampla defesa, uma vez que apenas os bens da vida claramente delimitados na causa de pedir podem ser validamente contestados e apreciados em cognição exauriente.

Ressalte-se que eventual necessidade futura de outras providências na área da saúde pode ser objeto de nova demanda, devidamente delimitada e instruída. No momento, contudo, inexiste certeza quanto à necessidade ou ao direito aos tratamentos que venham a ser futuramente prescritos de forma genérica e indeterminada.

Diante disso, impõe-se o reconhecimento da inépcia da petição inicial **no ponto em que veicula pedidos genéricos**, com o consequente indeferimento da inicial quanto a tais requerimentos.

```

### Texto para Embedding

```
TÍTULO: Inépcia da Petição Inicial - Pedido Genérico
CATEGORIA: Preliminar > Condições da Ação
QUANDO USAR: Quando a parte autora fizer pedido genérico e indeterminado (ex: 'tudo mais o que se fizer necessário').
CONTEÚDO: ## INÉPCIA DA PETIÇÃO INICIAL

Conforme se extrai da petição inicial, a parte autora formula **pedidos genéricos e indeterminados**, nos seguintes termos: **{{ peticao_inicial_pedidos_genericos }}**.

A admissão da demanda com esse grau de indeterminação autoriza o indevido alargamento do objeto litigioso, comprometendo a regularidade do andamento processual e conduzindo à duração indefinida das fases de conhecimento e de eventual cumprimento de sentença. Ademais, a formulação de pedidos genéric...
```

---

## 50. Falta de Documento Essencial - Prescrição Médica

| Campo | Valor |
|-------|-------|
| **ID** | 21 |
| **Nome** | `prel_doc_essencial` |
| **Categoria** | Preliminar |
| **Subcategoria** | Condições da Ação |
| **Modo Ativação** | deterministic |
| **Ordem** | 8 |

### Condição de Ativação (Legado)

> Quando for pleiteado medicamento e não houver prescrição médica nos autos.

### Conteúdo

```markdown
## FALTA DE DOCUMENTO ESSENCIAL À PROPOSITURA DA AÇÃO

Não há prescrição médica que indique o princípio ativo, a dose e a posologia do medicamento. Essas informações são indispensáveis à análise técnica do pedido e repercutem no custo do tratamento para fins de competência. Questionários e orçamentos não substituem a prescrição ainda que assinados por profissional habilitado. Nesse sentido é o Enunciado nº 15 do CNJ. Em vista disso, a parte autora deve ser intimada para emendar a petição inicial, sob pena de indeferimento (Art. 320 do CPC).
```

### Texto para Embedding

```
TÍTULO: Falta de Documento Essencial - Prescrição Médica
CATEGORIA: Preliminar > Condições da Ação
QUANDO USAR: Quando for pleiteado medicamento e não houver prescrição médica nos autos.
CONTEÚDO: ## FALTA DE DOCUMENTO ESSENCIAL À PROPOSITURA DA AÇÃO

Não há prescrição médica que indique o princípio ativo, a dose e a posologia do medicamento. Essas informações são indispensáveis à análise técnica do pedido e repercutem no custo do tratamento para fins de competência. Questionários e orçamentos não substituem a prescrição ainda que assinados por profissional habilitado. Nesse sentido é o Enunciado nº 15 do CNJ. Em vista disso, a parte autora deve ser intimada para emendar a petição inicial...
```

---

## 51. Ausência de Interesse Processual - Fraldas

| Campo | Valor |
|-------|-------|
| **ID** | 25 |
| **Nome** | `prel_fraldas_interesse` |
| **Categoria** | Preliminar |
| **Subcategoria** | Interesse Processual |
| **Modo Ativação** | deterministic |
| **Ordem** | 9 |

### Condição de Ativação (Legado)

> Quando for pleiteado fornecimento de fraldas sem narrativa de tentativa frustrada de obtenção via administrativa.

### Conteúdo

```markdown
## AUSÊNCIA DE INTERESSE PROCESSUAL EM RELAÇÃO AO PEDIDO DE FRALDAS

O Programa Farmácia Popular do Brasil subsidia até 90% do valor de referência para a compra de fraldas. Para beneficiários do Programa Bolsa Família elas são distribuídas gratuitamente.

Nessa demanda, não há narrativa da tentativa frustrada de obter fraldas pela via administrativa ou negativa de seu fornecimento pelo Estado. Portanto, não há interesse processual (necessidade-adequação), condição para o ajuizamento de ação perante o Poder Judiciário. Consequentemente, impõe-se a extinção do processo sem resolução de mérito em relação ao Estado de Mato Grosso do Sul (Art. 485, inciso VI, do CPC).
```

### Texto para Embedding

```
TÍTULO: Ausência de Interesse Processual - Fraldas
CATEGORIA: Preliminar > Interesse Processual
QUANDO USAR: Quando for pleiteado fornecimento de fraldas sem narrativa de tentativa frustrada de obtenção via administrativa.
CONTEÚDO: ## AUSÊNCIA DE INTERESSE PROCESSUAL EM RELAÇÃO AO PEDIDO DE FRALDAS

O Programa Farmácia Popular do Brasil subsidia até 90% do valor de referência para a compra de fraldas. Para beneficiários do Programa Bolsa Família elas são distribuídas gratuitamente.

Nessa demanda, não há narrativa da tentativa frustrada de obter fraldas pela via administrativa ou negativa de seu fornecimento pelo Estado. Portanto, não há interesse processual (necessidade-adequação), condição para o ajuizamento de ação pera...
```

---

## 52. Ilegitimidade Passiva do Estado - Atendimento Educacional

| Campo | Valor |
|-------|-------|
| **ID** | 23 |
| **Nome** | `prel_ileg_educacional` |
| **Categoria** | Preliminar |
| **Subcategoria** | Legitimidade |
| **Modo Ativação** | deterministic |
| **Ordem** | 10 |

### Condição de Ativação (Legado)

> Quando for pleiteado professor de apoio ou psicopedagogo para educação infantil (ensino básico)

### Conteúdo

```markdown
## ILEGITIMIDADE PASSIVA DO ESTADO EM RELAÇÃO AO PEDIDO DE ATENDIMENTO EDUCACIONAL (É UMA PRELIMINAR)

O Estado de Mato Grosso do Sul é parte ilegítima para ocupar o polo passivo em demandas por professor de apoio ou psicopedagogo. Serviços dessa natureza estão relacionados ao ambiente escolar. Nesse cenário, a Lei de Diretrizes Bases da Educação Nacional - LDB (Lei Federal n.º 9.394/96) atribui a cada ente político a responsabilidade pela gestão do respectivo sistema de ensino.

Pela idade da parte autora, presume-se estar matriculada em instituição de ensino infantil, compreendida no sistema municipal. Assim, os órgãos estaduais não têm competências administrativa e pedagógica para emitir parecer quanto à necessidade do atendimento solicitado, tampouco ingerência sobre o sistema municipal de ensino.

Portanto, não há pertinência subjetiva na inclusão do ente estadual no processo. Consequentemente, impõe-se a extinção do processo sem resolução de mérito em relação ao Estado de Mato Grosso do Sul (Art. 485, inciso VI, do CPC).
```

### Texto para Embedding

```
TÍTULO: Ilegitimidade Passiva do Estado - Atendimento Educacional
CATEGORIA: Preliminar > Legitimidade
QUANDO USAR: Quando for pleiteado professor de apoio ou psicopedagogo para educação infantil (ensino básico)
CONTEÚDO: ## ILEGITIMIDADE PASSIVA DO ESTADO EM RELAÇÃO AO PEDIDO DE ATENDIMENTO EDUCACIONAL (É UMA PRELIMINAR)

O Estado de Mato Grosso do Sul é parte ilegítima para ocupar o polo passivo em demandas por professor de apoio ou psicopedagogo. Serviços dessa natureza estão relacionados ao ambiente escolar. Nesse cenário, a Lei de Diretrizes Bases da Educação Nacional - LDB (Lei Federal n.º 9.394/96) atribui a cada ente político a responsabilidade pela gestão do respectivo sistema de ensino.

Pela idade da p...
```

---

## 53. Ilegitimidade Passiva do Estado - Dano Moral em Transferência Hospitalar

| Campo | Valor |
|-------|-------|
| **ID** | 24 |
| **Nome** | `prel_ileg_dano_moral` |
| **Categoria** | Preliminar |
| **Subcategoria** | Legitimidade |
| **Modo Ativação** | deterministic |
| **Ordem** | 11 |

### Condição de Ativação (Legado)

> Quando for pleiteada transferência hospitalar cumulada com pedido de dano moral.

### Conteúdo

```markdown
## ILEGITIMIDADE PASSIVA DO ESTADO QUANTO AO DANO MORAL

O Estado de Mato Grosso do Sul não tem legitimidade passiva para o pedido de compensação por dano moral porque a solidariedade entre os entes federativos para garantir o direito à saúde não se estende à responsabilidade civil, que exige conduta, dano e nexo causal. Nesse sentido entende o Superior Tribunal de Justiça.

Quando se trata de transferência hospitalar, a central reguladora estadual (CORE) é responsável pela busca de vagas entre unidades hospitalares de referência, mas não escolhe quais pacientes entram ou saem. Essa análise é realizada pelos profissionais de cada unidade hospitalar, conforme classificação de risco e disponibilidade de leitos.

No entanto, a parte autora apenas narra a necessidade da vaga, sem descrever ato ilícito da central reguladora estadual em buscá-la. Assim, não alega conduta, comissiva ou omissiva, imputável ao Estado. Portanto, não há pertinência subjetiva na manutenção do Estado no processo, motivo pelo qual pede-se o reconhecimento de sua ilegitimidade passiva.
```

### Texto para Embedding

```
TÍTULO: Ilegitimidade Passiva do Estado - Dano Moral em Transferência Hospitalar
CATEGORIA: Preliminar > Legitimidade
QUANDO USAR: Quando for pleiteada transferência hospitalar cumulada com pedido de dano moral.
CONTEÚDO: ## ILEGITIMIDADE PASSIVA DO ESTADO QUANTO AO DANO MORAL

O Estado de Mato Grosso do Sul não tem legitimidade passiva para o pedido de compensação por dano moral porque a solidariedade entre os entes federativos para garantir o direito à saúde não se estende à responsabilidade civil, que exige conduta, dano e nexo causal. Nesse sentido entende o Superior Tribunal de Justiça.

Quando se trata de transferência hospitalar, a central reguladora estadual (CORE) é responsável pela busca de vagas entre ...
```

---

## 54. Litisconsórcio Necessário do Município (Tema 793)

| Campo | Valor |
|-------|-------|
| **ID** | 22 |
| **Nome** | `mun_793` |
| **Categoria** | Preliminar |
| **Subcategoria** | Litisconsórcio |
| **Modo Ativação** | deterministic |
| **Ordem** | 12 |

### Condição de Ativação (Legado)

> Quando o município não está no polo passivo e o pedido envolve procedimentos de responsabilidade municipal (dieta, cirurgia, consulta ou exame, TEA, fralda, atendimento educacional no ensino básico, home care, transferencia hospitalar e internação involuntária). NÃO SE APLICA A MEDICAMENTO

### Conteúdo

```markdown
## LITISCONSÓRCIO NECESSÁRIO PARA A EFETIVIDADE DA TUTELA JURISDICIONAL (TEMA 793)

Em 2019, o Supremo Tribunal Federal concluiu o julgamento dos EDcl no RE n° 855.178/SE (Tema 793) e, ao interpretar os arts. 23, inciso II; o 196; e o 198, todos da CRFB, fixou em repercussão geral que:

> Os entes da federação, em decorrência da competência comum, são solidariamente responsáveis nas demandas prestacionais na área da saúde, e diante dos critérios constitucionais de descentralização e hierarquização, compete à autoridade judicial direcionar o cumprimento conforme as regras de repartição de competências e determinar o ressarcimento a quem suportou o ônus financeiro.

A competência pela gestão e a execução dos procedimentos requeridos é dos municípios. Ainda que o município de residência da parte autora não disponha do serviço em seu território, o pedido é inserido no sistema municipal de regulação (SISREG) e direcionado à Central Reguladora do município de referência na especialidade, com o qual aquele deve(ria) estar pactuado no Programa de Pactuação Integrada (PPI).

Nessa relação, o município executor (referência) recebe parcela dos recursos federais que seriam destinados ao município solicitante (residência) para custear o atendimento à população de outro ente público. Noutro cenário, se o município de residência não mantiver pactuação com nenhum ente para realizar atendimentos que não oferece em seu território, então ele receberá os recursos federais e os aplicará em outras finalidades.

Em qualquer situação, só o município de residência tem acesso à funcionalidade de solicitar atendimento no SISREG para seus administrados. Por seu turno, só o município de referência tem acesso à funcionalidade de agendar o atendimento e possui pessoal capacitado para executar os serviços regulados.

Consequentemente, a eficácia da decisão judicial dependerá do direcionamento da obrigação ao ente municipal responsável pela etapa do atendimento em que se verificar a omissão administrativa. Igualmente, a validade do direito de ressarcimento assegurado ao Estado exige que o município-devedor participe da relação processual.

Em vista disso, o Estado não questiona sua legitimidade passiva, mas pede a inclusão do Município de {{ municipio }} no polo passivo, em observância à regra de repartição de responsabilidades que passa a expor.
```

### Texto para Embedding

```
TÍTULO: Litisconsórcio Necessário do Município (Tema 793)
CATEGORIA: Preliminar > Litisconsórcio
QUANDO USAR: Quando o município não está no polo passivo e o pedido envolve procedimentos de responsabilidade municipal (dieta, cirurgia, consulta ou exame, TEA, fralda, atendimento educacional no ensino básico, home care, transferencia hospitalar e internação involuntária). NÃO SE APLICA A MEDICAMENTO
CONTEÚDO: ## LITISCONSÓRCIO NECESSÁRIO PARA A EFETIVIDADE DA TUTELA JURISDICIONAL (TEMA 793)

Em 2019, o Supremo Tribunal Federal concluiu o julgamento dos EDcl no RE n° 855.178/SE (Tema 793) e, ao interpretar os arts. 23, inciso II; o 196; e o 198, todos da CRFB, fixou em repercussão geral que:

> Os entes da federação, em decorrência da competência comum, são solidariamente responsáveis nas demandas prestacionais na área da saúde, e diante dos critérios constitucionais de descentralização e hierarquizaç...
```

---

## 55. Perda do Objeto - Transferência Hospitalar Realizada

| Campo | Valor |
|-------|-------|
| **ID** | 26 |
| **Nome** | `prel_transf_realizada` |
| **Categoria** | Preliminar |
| **Subcategoria** | Perda do Objeto |
| **Modo Ativação** | deterministic |
| **Ordem** | 13 |

### Condição de Ativação (Legado)

> Quando for pleiteada transferência hospitalar e a transferência já tiver sido realizada.

### Conteúdo

```markdown
## PERDA DO OBJETO: TRANSFERÊNCIA HOSPITALAR

A transferência hospitalar ocorreu em {{ transferido_data }} {{ transferido_hora }} para unidade de referência na especialidade. Não houve omissão nem demora no atendimento e a parte autora está assistida pelo Poder Público. Em vista disso, não se justifica a continuidade deste processo e impõe-se sua extinção sem resolução de mérito.
```

### Texto para Embedding

```
TÍTULO: Perda do Objeto - Transferência Hospitalar Realizada
CATEGORIA: Preliminar > Perda do Objeto
QUANDO USAR: Quando for pleiteada transferência hospitalar e a transferência já tiver sido realizada.
CONTEÚDO: ## PERDA DO OBJETO: TRANSFERÊNCIA HOSPITALAR

A transferência hospitalar ocorreu em {{ transferido_data }} {{ transferido_hora }} para unidade de referência na especialidade. Não houve omissão nem demora no atendimento e a parte autora está assistida pelo Poder Público. Em vista disso, não se justifica a continuidade deste processo e impõe-se sua extinção sem resolução de mérito.
```

---
