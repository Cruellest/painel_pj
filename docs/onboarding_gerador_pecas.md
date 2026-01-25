# Onboarding: Sistema Gerador de Pecas

> Guia pratico para desenvolvedores iniciando no sistema de geracao de pecas juridicas.

## Visao Geral Rapida

O Gerador de Pecas e um sistema que **automatiza a criacao de pecas juridicas** (contestacoes, recursos, etc.) usando:
- Integracao com TJ-MS para baixar documentos do processo
- IA (Gemini) para extrair informacoes e gerar texto
- Regras deterministicas para selecao de prompts
- Conversao para DOCX formatado

## Arquitetura em 3 Agentes

```
[Usuario] -> [Router] -> [Agente 1: Coletor] -> [Agente 2: Detector] -> [Agente 3: Gerador] -> [DOCX]
```

### Agente 1 - Coletor (agente_tjms_integrado.py)
- Consulta processo no TJ-MS via SOAP
- Baixa e processa documentos (PDF -> texto)
- Gera resumos em JSON de cada documento
- Consolida dados de extracao

### Agente 2 - Detector (detector_modulos.py)
- Analisa resumos e ativa modulos de conteudo
- **Fast Path**: Se todas as regras sao deterministicas, pula a IA
- **Modo Misto**: Avalia regras deterministicas + chama IA para o resto
- Retorna lista de IDs dos modulos a usar

### Agente 3 - Gerador (orquestrador_agentes.py)
- Monta prompt combinando: sistema + peca + conteudos ativados
- Chama Gemini Pro para gerar o texto
- Retorna markdown da peca

## Estrutura de Arquivos

```
sistemas/gerador_pecas/
├── router.py                 # Endpoints da API (principal)
├── services.py               # GeradorPecasService (orquestracao)
├── orquestrador_agentes.py   # Coordena os 3 agentes
├── agente_tjms.py            # Logica de download TJ-MS
├── agente_tjms_integrado.py  # Wrapper do agente TJ-MS
├── detector_modulos.py       # Deteccao de modulos por IA/regras
├── services_deterministic.py # Motor de regras deterministicas
├── services_process_variables.py # Variaveis derivadas do XML
├── docx_converter.py         # Markdown -> DOCX
├── constants.py              # Constantes centralizadas (NOVO)
├── exceptions.py             # Excecoes customizadas (NOVO)
├── models.py                 # Modelos SQLAlchemy
└── temp_docs/                # Diretorio de arquivos temporarios
```

## Como Rodar Localmente

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com credenciais do TJ-MS e Gemini

# 3. Rodar servidor
uvicorn main:app --reload

# 4. Acessar API
# http://localhost:8000/docs
```

## Fluxo Principal: processar-stream

Endpoint mais usado: `POST /gerador-pecas/processar-stream`

```python
# Request
{
    "numero_cnj": "0800001-00.2024.8.12.0001",
    "tipo_peca": "contestacao",  # opcional
    "group_id": 1,
    "subcategoria_ids": [1, 2]
}

# Response: SSE stream com eventos
data: {"tipo": "status", "mensagem": "Consultando processo..."}
data: {"tipo": "documento", "nome": "Peticao Inicial"}
data: {"tipo": "resumo_disponivel", "total": 5}
data: {"tipo": "modulos_detectados", "ids": [1, 5, 12]}
data: {"tipo": "geracao_iniciada"}
data: {"tipo": "chunk", "conteudo": "## CONTESTACAO\n\n"}
data: {"tipo": "concluido", "geracao_id": 123}
```

## Sistema de Prompts Modulares

### Tipos de Modulos

| Tipo | Descricao | Exemplo |
|------|-----------|---------|
| `sistema` | Instrucoes base para a IA | "Voce e um advogado publico..." |
| `peca` | Template da peca | "## CONTESTACAO\n\n{conteudo}" |
| `conteudo` | Argumentos especificos | "Tema 106 - Medicamentos" |

### Regras de Ativacao

Modulos de conteudo podem ter **regras deterministicas**:

```json
{
  "op": "and",
  "conditions": [
    {"var": "tipo_acao", "op": "eq", "value": "obrigacao_fazer"},
    {"var": "valor_causa", "op": "gt", "value": 60000}
  ]
}
```

**Operadores disponiveis:**
- `eq`, `neq` - Igualdade
- `gt`, `gte`, `lt`, `lte` - Comparacao numerica
- `contains` - Contem substring
- `is_empty`, `exists` - Verificacao de existencia
- `and`, `or`, `not` - Logicos

## Debugando Selecao Deterministicas

### 1. Ver logs de ativacao
```python
# No terminal, procure por:
[AGENTE2] modo_ativacao=fast_path
[AGENTE2] Modulos determinísticos ativados: [1, 5, 12]
```

### 2. Testar regra isoladamente
```python
from sistemas.gerador_pecas.services_deterministic import avaliar_ativacao_prompt

dados = {
    "tipo_acao": "obrigacao_fazer",
    "valor_causa": 100000
}

ativado, confianca, motivo = avaliar_ativacao_prompt(regra_json, dados, db)
print(f"Ativado: {ativado}, Motivo: {motivo}")
```

### 3. Endpoint de teste
```
POST /admin/teste-ativacao/avaliar
{
    "modulo_id": 123,
    "dados": {"tipo_acao": "obrigacao_fazer"}
}
```

## Testando Geracao DOCX

### 1. Testar conversao isolada
```python
from sistemas.gerador_pecas.docx_converter import markdown_to_docx

markdown = """
# CONTESTACAO

## 1. DOS FATOS

O autor alega que...

## 2. DO DIREITO

a) Primeiro argumento
b) Segundo argumento
"""

docx_bytes = markdown_to_docx(markdown)
with open("teste.docx", "wb") as f:
    f.write(docx_bytes)
```

### 2. Verificar numeracao de listas
- Listas `a)`, `b)`, `c)` devem usar numeracao Word nativa
- Listas `1.`, `2.`, `3.` devem usar numeracao Word nativa
- Bullets `-` ou `*` devem aparecer como bullets

### 3. Teste automatizado
```bash
pytest tests/test_docx_list_numbering.py -v
```

## Armadilhas Comuns

### 1. Cache de modulos
O detector tem cache em memoria. Se alterar regras no banco, reinicie o servidor.

### 2. Timeout de agentes
Agentes tem timeout. Se o processo tiver muitos documentos, pode timeout.
```python
# Em constants.py
TIMEOUT_AG2_DETECCAO = 60  # segundos
```

### 3. Ordem dos modulos
A ordem no prompt final depende de:
1. Ordem da categoria (`CategoriaOrdem`)
2. Ordem do modulo (`PromptModulo.ordem`)

### 4. Variaveis derivadas
Algumas variaveis vem do XML do processo, nao da extracao IA:
- `processo_ajuizado_apos_2024_09_19`
- `estado_polo_passivo`
- `municipio_polo_passivo`

Ver: `services_process_variables.py`

## Checklist de PR

Antes de abrir PR no gerador_pecas:

- [ ] Testes passando: `pytest tests/test_deterministic_rules.py`
- [ ] Testes DOCX passando: `pytest tests/test_docx_list_numbering.py`
- [ ] Sem print() - usar logger
- [ ] Sem magic numbers - usar constants.py
- [ ] Endpoints documentados com docstring
- [ ] Regras deterministicas testadas com dados reais
- [ ] Verificar se mudanca afeta Fast Path

## Recursos Uteis

- **Docs do sistema**: `docs/sistemas/gerador_pecas.md`
- **Arquitetura geral**: `docs/arquitetura/ARQUITETURA_GERAL.md`
- **Cliente TJ-MS**: `services/tjms/` (modulo unificado)
- **Configuracao prompts**: `/admin/prompts-config` (interface web)

## Contato

- **Slack**: #pge-dev
- **Issues**: GitHub Issues do repositorio
