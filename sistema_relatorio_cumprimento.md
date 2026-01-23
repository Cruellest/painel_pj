# Sistema de Geração de Relatórios Iniciais no Cumprimento de Sentença

## 1. Objetivo Geral

Este sistema tem por objetivo gerar **relatórios iniciais no cumprimento de sentença**, a partir de uma **entrevista guiada com o usuário**, utilizando como base **todos os documentos relevantes do processo**, especialmente:

- Petição inicial do cumprimento de sentença;
- Sentenças e acórdãos do processo de conhecimento (processo principal);
- Informação sobre trânsito em julgado, quando existente.

O sistema deve reaproveitar, sempre que possível, **os mesmos mecanismos técnicos já existentes** nos sistemas de **geração de peças** e de **pedido de cálculo**, evitando duplicação de lógica e garantindo consistência entre os módulos.

---

## 2. Entrada Inicial do Usuário

O fluxo se inicia com a seguinte entrada obrigatória:

- **Número do processo de cumprimento de sentença**, que normalmente é um processo apartado em relação ao processo de conhecimento.

Esse número será o gatilho para toda a cadeia de busca, download, organização e análise documental.

---

## 3. Obtenção dos Documentos do Processo

### 3.1 Mecanismo de API

Para obtenção dos documentos processuais, o sistema **deve utilizar exatamente o mesmo mecanismo de API** já empregado no sistema de **pedido de cálculo**, garantindo compatibilidade com:

- Autenticação;
- Estrutura de requisições;
- Tratamento de erros;
- Padronização de respostas.

Não deve ser criada uma nova integração se já houver uma funcional funcional equivalente.

---

### 3.2 Petição Inicial do Cumprimento de Sentença

O sistema deve:

- Localizar e baixar a **petição inicial do cumprimento de sentença**;
- Utilizar **a mesma lógica já existente no sistema de pedido de cálculo** para identificação e obtenção da petição inicial.

Essa petição será considerada o documento-base do cumprimento de sentença.

---

## 4. Identificação do Processo Principal

Como o cumprimento de sentença costuma ser apartado, o sistema deverá:

- Identificar o **número do processo principal (processo de conhecimento)**;
- Utilizar **a mesma ferramenta e lógica já existentes no sistema de pedido de cálculo** para essa identificação.

Não deve haver tentativa de inferência por LLM nesse ponto.  
A identificação deve seguir o método determinístico já implementado no sistema de pedido de cálculo.

---

## 5. Download de Sentenças, Acórdãos e Trânsito em Julgado

Uma vez identificado o processo principal, o sistema deverá:

### 5.1 Sentenças e Acórdãos

- Localizar todas as **sentenças e acórdãos** disponíveis no processo principal;
- Realizar o download desses documentos utilizando **exatamente o mesmo mecanismo do sistema de pedido de cálculo**, que já executa essa tarefa;
- Garantir que todos os documentos sejam armazenados localmente para posterior processamento.

### 5.2 Trânsito em Julgado

- Tentar localizar a informação de **trânsito em julgado**, utilizando:
  - A mesma lógica;
  - Os mesmos critérios;
  - As mesmas fontes
  já adotados pelo sistema de pedido de cálculo.

O sistema deve registrar claramente se:
- O trânsito em julgado foi localizado; ou
- Não foi possível identificar essa informação.

---

## 6. Organização e Classificação dos Documentos

Após o download, todos os documentos devem ser:

- Organizados internamente por categoria, por exemplo:
  - Petição inicial do cumprimento de sentença;
  - Sentença;
  - Acórdão;
  - Certidão ou informação de trânsito em julgado.
- Renomeados de forma padronizada, clara e previsível, para facilitar:
  - Auditoria;
  - Visualização pelo usuário;
  - Debug e logs.

---

## 7. Envio dos Documentos para o Modelo de IA

### 7.1 Modelo Utilizado

Todos os documentos coletados devem ser enviados **integralmente** para o modelo:

- **Gemini 3 Flash Preview**

Configuração inicial esperada:
- Thinking level: `low`

### 7.2 Configuração Dinâmica via Admin

Nenhuma das seguintes configurações deve ser hardcoded no código:

- Modelo;
- Temperatura;
- Thinking level;
- Prompt de sistema ou prompt de usuário.

Essas configurações devem ser **100% controladas** pelo painel administrativo em:

- `/admin/prompts-config`

### 7.3 Nova Aba de Sistema

Deve ser criada **uma nova aba de configuração de sistema** dentro do `/admin/prompts-config`, específica para este módulo de:

- Relatórios iniciais no cumprimento de sentença.

Essa aba será responsável por definir:
- Prompt utilizado pelo Gemini;
- Demais parâmetros do modelo.

---

## 8. Geração e Visualização do Resultado

### 8.1 Visualização no Front-end

O sistema deve gerar uma visualização do resultado **semelhante à existente no sistema de pedido de cálculo**, permitindo ao usuário:

- Visualizar o relatório gerado;
- Acessar todos os documentos utilizados no processamento;
- Abrir cada documento individualmente, já classificado e renomeado.

---

## 9. Exportação do Resultado

### 9.1 Formatos Disponíveis

O usuário poderá baixar o resultado final em:

- **DOCX**
- **PDF**

### 9.2 Geração do DOCX

- O DOCX deve ser gerado utilizando **o mesmo `docxconverter` já existente no sistema de geração de peças**;
- Nenhuma conversão alternativa deve ser criada neste momento.

Eventuais ajustes no `docxconverter` serão tratados posteriormente.

### 9.3 Geração do PDF

- O PDF **não deve ser gerado diretamente a partir do Markdown**;
- O fluxo correto deve ser:
  - Markdown → DOCX → PDF
- O PDF deve ser uma conversão direta do DOCX gerado, garantindo consistência visual.

---

## 10. Extração de Dados Básicos do Processo

Além do relatório textual, o sistema deve extrair os **dados básicos do processo**, tais como:

- Partes;
- Polo ativo e passivo;
- Valor da causa;
- Outras informações essenciais já utilizadas pelos sistemas existentes.

Essa extração deve reutilizar:
- A mesma lógica já existente no sistema de geração de peças;
- Ou, se aplicável, lógica equivalente utilizada em outros módulos do sistema.

Caso haja divergência entre sistemas, a prioridade é manter **consistência com o sistema de geração de peças**.

---

## 11. Princípios Gerais de Implementação

- Reutilizar código sempre que possível;
- Evitar duplicação de lógica já existente;
- Manter o sistema altamente configurável via painel administrativo;
- Garantir rastreabilidade completa dos documentos utilizados;
- Facilitar debug por meio de logs claros e organização previsível dos arquivos.

---

## 12. Resultado Esperado

Ao final do fluxo, o usuário terá:

- Um relatório inicial estruturado para o cumprimento de sentença;
- Total transparência sobre os documentos analisados;
- Capacidade de exportação em DOCX e PDF;
- Um sistema consistente com os demais módulos já existentes na plataforma.
