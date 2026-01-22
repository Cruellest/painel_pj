# Agentes de Análise de Documentos

Este documento descreve os agentes de análise de documentos do TJ-MS e suas funcionalidades especiais.

## AgenteTJMS

O `AgenteTJMS` é responsável por:

1. Consultar processos via API SOAP do TJ-MS
2. Baixar documentos relevantes para análise
3. Processar documentos em paralelo com IA
4. Gerar resumos e relatórios

### Localização

- Arquivo: `sistemas/gerador_pecas/agente_tjms.py`
- Classe: `AgenteTJMS`

---

## Modo 2º Grau (competencia=999)

### Visão Geral

Processos de 2º grau (identificados por `competencia="999"` no XML do TJ-MS) tipicamente possuem centenas de documentos. Para otimizar o tempo de análise e reduzir custos, o sistema implementa uma **seleção determinística** que escolhe apenas os documentos mais relevantes.

### Ativação

O modo é ativado automaticamente quando:

- `dados_processo.competencia == "999"`
- `db_session` está disponível no agente

### Regras de Seleção

| Categoria | Regra | Configurável |
|-----------|-------|--------------|
| Parecer (NAT) | Último documento apenas | Não |
| Petição | Últimas N | Sim (default: 10) |
| Recurso | Últimas N | Sim (default: 10) |
| Despacho | Últimos 3 | Não (fixo) |
| Acórdão | TODOS | Não |
| Sentença | TODOS | Não |
| Decisão | TODOS | Não |
| Petição Inicial | Primeiro documento | Não |

### Configurações

As configurações podem ser alteradas no painel de administração (`/admin/config-ia?sistema=gerador_pecas`):

| Chave | Default | Descrição |
|-------|---------|-----------|
| `competencia_999_last_peticoes_limit` | 10 | Limite de petições recentes (1-50) |
| `competencia_999_last_recursos_limit` | 10 | Limite de recursos recentes (1-50) |

### Fluxo de Integração

```
analisar_processo()
    │
    ├─ [1] consultar_processo_async() → XML
    │
    ├─ [2] extrair_dados_processo_xml() → DadosProcesso (com competencia)
    │
    ├─ [3] extrair_documentos_xml() → List[DocumentoTJMS]
    │
    ├─ [4] Filtragem por códigos permitidos
    │
    ├─ [5] if is_modo_segundo_grau(competencia):
    │      └─ selecionar_documentos_segundo_grau()
    │
    ├─ [6] Agrupamento de documentos
    │
    └─ [7] Download e processamento
```

### Logs Estruturados

Quando o modo 2º grau está ativo, o sistema emite logs detalhados:

```
[2º-GRAU] Modo determinístico ativado (competencia=999)
[2º-GRAU] Limites configurados: petições=10, recursos=10
[2º-GRAU] Seleção por categoria: acórdão=2, decisão=3, despacho=3, parecer=1, petição=10, petição_inicial=1, recurso=5, sentença=1
[2º-GRAU] Documentos excluídos por limite: 35
[2º-GRAU] Total selecionados: 26 de 61
```

### Arquivos Relacionados

| Arquivo | Descrição |
|---------|-----------|
| `sistemas/gerador_pecas/services_segundo_grau.py` | Serviço de seleção determinística |
| `sistemas/gerador_pecas/agente_tjms.py` | Integração no fluxo principal |
| `admin/seed_prompts.py` | Configurações default |
| `tests/test_modo_segundo_grau.py` | Testes unitários |

### Verificação

1. **Teste unitário**:
   ```bash
   pytest tests/test_modo_segundo_grau.py -v
   ```

2. **Verificar configs**:
   Acesse `/admin/config-ia?sistema=gerador_pecas` e confirme as novas configurações.

3. **Teste manual**:
   Processe um processo com `competencia=999` e verifique os logs `[2º-GRAU]`.

4. **Teste de regressão**:
   Processe um processo com competencia diferente de "999" e verifique que o fluxo normal não foi afetado.

---

## Detecção Automática de Tipo de Peça

### Visão Geral

O sistema possui uma funcionalidade onde a IA pode detectar automaticamente qual tipo de peça jurídica gerar (contestação, recurso, contrarrazões, etc.) baseado na análise dos documentos do processo.

**Esta funcionalidade está DESABILITADA por padrão** para garantir previsibilidade e controle do fluxo de geração em produção.

### Feature Flag

| Chave | Valor | Descrição |
|-------|-------|-----------|
| `enable_auto_piece_detection` | `"false"` | Habilita/desabilita detecção automática do tipo de peça pela IA |

### Comportamento por Valor

| Valor | Frontend | Backend |
|-------|----------|---------|
| `"false"` (padrão) | Mostra placeholder "-- Selecione o tipo de peça --" (obrigatório) | Rejeita requisições sem tipo_peca (HTTP 400) |
| `"true"` | Mostra opção "🤖 Detectar automaticamente (IA decide)" | Permite tipo_peca vazio, Agente 2 detecta via IA |

### Implementação

#### Backend

**Endpoint `/api/gerador-pecas/tipos-peca`**:
- Retorna `permite_auto: true/false` baseado na flag
- Frontend usa esse valor para renderizar opções

**Endpoints de geração**:
- `/api/gerador-pecas/processar-stream`
- `/api/gerador-pecas/processar-pdfs-stream`

Ambos validam:
```python
if not permite_auto and not tipo_peca:
    raise HTTPException(400, "Tipo de peça é obrigatório...")
```

#### Frontend (`app.js`)

```javascript
// Propriedade da classe
this.permiteAutoDetection = false; // fail-safe

// Em carregarTiposPeca():
this.permiteAutoDetection = data.permite_auto === true;

// Em iniciarProcessamento():
if (!this.permiteAutoDetection && !this.tipoPeca) {
    this.mostrarErro('Selecione obrigatoriamente o tipo de peça.');
    return;
}
```

### Reativar a Funcionalidade

Para habilitar a detecção automática no futuro:

**Via SQL:**
```sql
UPDATE configuracoes_ia
SET valor = 'true'
WHERE sistema = 'gerador_pecas'
AND chave = 'enable_auto_piece_detection';
```

**Via Admin Panel:**
Acesse `/admin/config-ia?sistema=gerador_pecas` e altere o valor de `enable_auto_piece_detection` para `true`.

### Fluxo de Detecção (quando habilitado)

```
Usuario seleciona "Detectar automaticamente"
    │
    ├─ [1] Agente 1: Coleta e resume documentos
    │
    ├─ [2] Agente 2: detectar_tipo_peca(resumo_consolidado)
    │      ├─ Consulta módulos tipo="peca" ativos
    │      ├─ Monta prompt com tipos disponíveis
    │      ├─ Gemini classifica baseado em regras:
    │      │   - Estado CITADO sem contestar → CONTESTAÇÃO
    │      │   - Sentença desfavorável → RECURSO DE APELAÇÃO
    │      │   - Adversário apelou → CONTRARRAZÕES
    │      │   - Consulta interna → PARECER
    │      └─ Retorna {tipo_peca, justificativa, confianca}
    │
    ├─ [3] Filtra documentos pelo tipo detectado
    │
    └─ [4] Agente 3: Gera a peça
```

### Arquivos Relacionados

| Arquivo | Descrição |
|---------|-----------|
| `sistemas/gerador_pecas/router.py` | Endpoints com validação |
| `sistemas/gerador_pecas/detector_modulos.py` | Método `detectar_tipo_peca()` |
| `sistemas/gerador_pecas/templates/app.js` | Lógica frontend |
| `database/init_db.py` | Seed da configuração |

---

## DadosProcesso

Estrutura de dados extraídos do XML do processo:

```python
@dataclass
class DadosProcesso:
    numero_processo: str
    polo_ativo: List[ParteProcesso]
    polo_passivo: List[ParteProcesso]
    valor_causa: Optional[str]
    classe_processual: Optional[str]
    data_ajuizamento: Optional[datetime]
    orgao_julgador: Optional[str]
    competencia: Optional[str]  # Código de competência (999 = 2º grau)
```

### Campo competencia

- **Tipo**: `Optional[str]`
- **Origem**: Atributo `competencia` do elemento `<dadosBasicos>` no XML do TJ-MS
- **Uso**: Identificar processos de 2º grau (`"999"`) para aplicar seleção determinística

---

## Categorias de Documentos

Os códigos de documento são obtidos da tabela `categorias_documento` no banco de dados. As categorias são configuradas via:

- Arquivo de seed: `categorias_documentos.json`
- Interface admin: `/admin/categorias-documento`
- Modelo: `CategoriaDocumento` em `sistemas/gerador_pecas/models_config_pecas.py`
