# Detecção Inteligente de Módulos de Conteúdo

## Visão Geral

O sistema de geração de peças jurídicas agora utiliza **Inteligência Artificial** para detectar automaticamente quais módulos de CONTEÚDO (argumentos e teses) são relevantes para cada caso específico.

### Modelo Utilizado

- **Modelo padrão**: `google/gemini-2.0-flash-lite`
- **Características**: Rápido, econômico e eficiente para análise de documentos
- **Temperatura**: 0.1 (respostas determinísticas)
- **Max tokens**: 1000 (resposta curta e objetiva)

---

## Como Funciona

### 1. Fluxo de Detecção

```
USUÁRIO ENVIA DOCUMENTOS
         ↓
┌────────────────────────────────────────┐
│  DetectorModulosIA                     │
│  ├─ Recebe resumo dos documentos       │
│  ├─ Carrega módulos disponíveis        │
│  ├─ Monta prompt de análise            │
│  ├─ Envia para Gemini Flash Lite       │
│  └─ Processa resposta JSON              │
└────────────────────────────────────────┘
         ↓
   MÓDULOS RELEVANTES DETECTADOS
   [ID1, ID2, ID3, ...]
         ↓
┌────────────────────────────────────────┐
│  GeradorPecasService                   │
│  ├─ Recebe IDs dos módulos             │
│  ├─ Carrega módulos do banco           │
│  ├─ Monta prompt final                 │
│  └─ Gera peça jurídica                 │
└────────────────────────────────────────┘
```

### 2. Exemplo de Uso

```python
from sistemas.gerador_pecas.services import GeradorPecasService

# Resumo dos documentos do processo
documentos_resumo = """
Processo: Ação de obrigação de fazer contra o Estado de MS
Pedido: Fornecimento de medicamento ADALIMUMABE
Contexto: Paciente com artrite reumatóide, medicamento não incorporado ao SUS
Documentos: Prescrição médica, laudo médico atestando necessidade
CONITEC: Medicamento não recomendado para incorporação
"""

# Inicializar serviço
service = GeradorPecasService(db=db_session)

# Processar processo com detecção automática
resultado = await service.processar_processo(
    numero_cnj="0001234-56.2024.8.12.0001",
    numero_cnj_formatado="0001234-56.2024.8.12.0001",
    tipo_peca="contestacao",
    usuario_id=1,
    documentos_resumo=documentos_resumo,  # ← IA analisa isso
    documentos_completos=None  # Opcional: texto completo
)

# Resultado
print(resultado["status"])  # "sucesso"
print(resultado["url_download"])  # Link para download do DOCX
```

### 3. Resposta da IA

A IA retorna um JSON estruturado:

```json
{
  "modulos_relevantes": [3, 7, 12],
  "justificativa": "Processo envolve fornecimento de medicamento não incorporado ao SUS (módulo 3), laudo médico como prova (módulo 7) e decisão CONITEC (módulo 12).",
  "confianca": "alta"
}
```

**Campos**:
- `modulos_relevantes`: IDs dos módulos detectados
- `justificativa`: Explicação da seleção (útil para auditoria)
- `confianca`: Nível de confiança (`alta`, `media`, `baixa`)

---

## Configurações

As configurações ficam armazenadas no banco de dados (tabela `configuracao_ia`):

| Chave | Valor Padrão | Descrição |
|-------|--------------|-----------|
| `modelo_deteccao` | `google/gemini-2.0-flash-lite` | Modelo de IA para detecção |
| `temperatura_deteccao` | `0.1` | Temperatura (0.0-1.0) |
| `max_tokens_deteccao` | `1000` | Máximo de tokens na resposta |
| `cache_ttl_minutos` | `60` | Tempo de vida do cache (minutos) |

### Alterar Configurações

```python
from admin.models import ConfiguracaoIA

# Exemplo: Trocar para modelo maior
config = db.query(ConfiguracaoIA).filter(
    ConfiguracaoIA.sistema == "gerador_pecas",
    ConfiguracaoIA.chave == "modelo_deteccao"
).first()

config.valor = "google/gemini-3-pro-preview"
db.commit()
```

---

## Cache de Detecções

Para otimizar custos e performance, o sistema implementa **cache inteligente**:

### Como Funciona

1. **Hash dos documentos**: Gera MD5 do texto dos documentos
2. **Verifica cache**: Se já analisou documentos idênticos recentemente
3. **Retorna do cache**: Se encontrado e não expirado (< 60min padrão)
4. **Caso contrário**: Faz nova detecção e salva no cache

### Exemplo de Log

```
✅ Cache hit - módulos detectados anteriormente
```

ou

```
🤖 Usando IA para detectar módulos relevantes...
📊 Detecção IA - Confiança: alta
💡 Justificativa: Processo envolve medicamento não incorporado...
   ✓ Medicamento Não Incorporado ao SUS
   ✓ Laudo Médico como Prova Pericial
🎯 Detectados 2 módulos relevantes
```

### Limpar Cache Manualmente

```python
from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA

detector = DetectorModulosIA(db=db_session)
detector.limpar_cache()
# 🗑️ Cache de detecções limpo
```

---

## Fallback Automático

Se a IA falhar por qualquer motivo, o sistema usa **detecção por palavras-chave**:

```python
# Se IA falhar
if erro_na_deteccao:
    # Usa método antigo: palavras-chave
    modulos = detectar_por_palavras_chave(
        texto=documentos_resumo,
        modulos=todos_modulos
    )
```

### Mensagens de Fallback

```
⚠️ Erro na detecção por IA: Timeout
⚠️ Usando detecção fallback por palavras-chave
   ✓ Medicamento Não Incorporado (palavra: medicamento)
```

---

## Monitoramento e Logs

### Logs do Sistema

O sistema emite logs detalhados:

```python
# Inicialização
print("⚠️ Erro ao inicializar detector de módulos: {erro}")

# Detecção
print("🤖 Usando IA para detectar módulos relevantes...")
print("📊 Detecção IA - Confiança: alta")
print("💡 Justificativa: {justificativa}")
print("   ✓ {nome_modulo}")
print("🎯 Detectados {n} módulos relevantes")

# Cache
print("✅ Cache hit - módulos detectados anteriormente")
print("🗑️ Cache de detecções limpo")

# Fallback
print("⚠️ Usando detecção fallback por palavras-chave")
```

### Auditoria

A justificativa retornada pela IA permite rastrear **por que** determinados módulos foram selecionados, útil para:
- Validação da qualidade da detecção
- Treinamento de novos módulos
- Ajustes finos no prompt

---

## Integração com API REST

### Endpoint Atualizado

```http
POST /gerador-pecas/api/processar
Content-Type: application/json

{
  "numero_cnj": "0001234-56.2024.8.12.0001",
  "tipo_peca": "contestacao",
  "documentos_resumo": "Processo sobre medicamento não incorporado...",
  "documentos_completos": null
}
```

### Campos Novos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `documentos_resumo` | string | Não | Resumo dos documentos (para detecção IA) |
| `documentos_completos` | string | Não | Texto completo (opcional, melhora precisão) |
| `palavras_detectadas` | array | Não | Fallback manual de palavras-chave |

---

## Performance e Custos

### Custos Estimados

Com `google/gemini-2.0-flash-lite`:
- **Input**: ~$0.075 por 1M tokens
- **Output**: ~$0.30 por 1M tokens
- **Custo médio por detecção**: ~$0.0005 (0.05 centavos)

**Com cache de 60min**: Economia de até 90% em casos repetidos

### Performance

- **Latência média**: 1-3 segundos
- **Timeout**: 60 segundos
- **Taxa de acerto** (estimada): >85% com bons prompts de módulos

---

## Criando Módulos Otimizados para IA

Para melhorar a detecção, os módulos de CONTEÚDO devem ter:

### 1. Título Claro e Específico

```python
# ✅ BOM
titulo = "Medicamento Não Incorporado ao SUS - Obrigação de Fornecimento"

# ❌ RUIM
titulo = "Módulo 1"
```

### 2. Descrição Detalhada no Conteúdo

```markdown
# ✅ BOM
## Medicamento Não Incorporado ao SUS

Este módulo trata de casos em que o medicamento solicitado NÃO foi incorporado
ao SUS pela CONITEC. Aplica-se quando há:
- Decisão CONITEC de não incorporação
- Medicamento experimental ou off-label
- Ausência de alternativa terapêutica no SUS
...

# ❌ RUIM
## Medicamento

Argumentos sobre medicamento.
```

### 3. Palavras-chave Relevantes (Fallback)

```json
palavras_chave: [
  "não incorporado",
  "conitec",
  "experimental",
  "off-label",
  "anvisa"
]
```

---

## Troubleshooting

### Problema: IA não detecta módulos relevantes

**Possíveis causas**:
1. Resumo dos documentos muito genérico
2. Módulos mal descritos no banco
3. Modelo com temperatura muito baixa

**Solução**:
- Forneça resumo mais detalhado
- Melhore descrições dos módulos
- Ajuste temperatura para 0.2-0.3

### Problema: IA detecta módulos demais

**Possíveis causas**:
1. Temperatura muito alta
2. Prompt de detecção muito permissivo

**Solução**:
- Reduza temperatura para 0.05
- Ajuste o prompt em `detector_modulos.py`

### Problema: Timeout na API

**Possíveis causas**:
1. Documentos muito longos
2. Modelo sobrecarregado

**Solução**:
- Limite documentos a 5000 caracteres
- Use apenas resumo, não texto completo
- Troque para modelo mais leve

---

## Próximos Passos

1. **Integração com TJ-MS**: Extração automática de documentos
2. **Machine Learning**: Treinar modelo específico para PGE-MS
3. **Feedback Loop**: Usuários avaliarem qualidade da detecção
4. **Dashboard**: Visualizar estatísticas de detecção

---

## Créditos

- **Desenvolvido por**: Equipe de Tecnologia PGE-MS
- **Modelo de IA**: Google Gemini 2.0 Flash Lite
- **Versão**: 1.0.0
- **Data**: Dezembro 2024
