# ADR-0010: Sistema de Recuperação de Execuções Travadas

**Data**: 2026-01-30
**Status**: Aceito
**Autores**: LAB/PGE-MS

## Contexto

O sistema de classificação de documentos processa lotes de até 2.000 arquivos usando IA (OpenRouter). Durante o processamento:

1. **Problema identificado**: Execuções podem travar sem feedback (ex: parar em 80/2000 sem avançar)
2. **Causas possíveis**:
   - Timeout na API OpenRouter
   - Erro não tratado em documento específico
   - Desconexão SSE do cliente
   - PDF corrompido causando crash no PyMuPDF
   - Rate limiting excessivo

3. **Impacto atual**:
   - UI fica indefinidamente em "Classificação em andamento"
   - Usuário não sabe se deve aguardar ou reiniciar
   - Ao reiniciar, perde todo o progresso
   - Não há registro do erro específico que causou o travamento

## Decisão

Implementar sistema robusto de detecção de travamento e recuperação com:

### 1. Detecção de Travamento (Watchdog)

**Timeouts definidos**:
| Componente | Timeout | Justificativa |
|------------|---------|---------------|
| Heartbeat da execução | 5 minutos | Se não houver progresso em 5 min, considerar travado |
| Processamento por documento | 2 minutos | Documento individual não deve demorar mais |
| Conexão SSE | 30 segundos keepalive | Detectar desconexão do cliente |

**Implementação**:
- Campo `ultimo_heartbeat` atualizado a cada documento processado
- Campo `ultimo_codigo_processado` para identificar onde parou
- Watchdog verifica execuções `EM_ANDAMENTO` com heartbeat > 5 min

### 2. Máquina de Estados

```
PENDENTE → EM_ANDAMENTO → CONCLUIDO
              ↓              ↑
           TRAVADO ──────────┘
              ↓         (retomar)
            ERRO
```

**Novos estados**:
- `TRAVADO`: Detectado automaticamente pelo watchdog
- Transições permitidas:
  - `TRAVADO → EM_ANDAMENTO`: Via endpoint de retomada
  - `TRAVADO → ERRO`: Após max_retries

### 3. Política de Retry

| Parâmetro | Valor | Configurável |
|-----------|-------|--------------|
| max_retries_execucao | 3 | Sim, via projeto |
| max_retries_documento | 2 | Sim, via projeto |
| backoff_inicial | 5 segundos | Não |
| backoff_multiplicador | 2 | Não |

**Regras**:
1. Documento com erro pode ser retentado até `max_retries_documento` vezes
2. Execução travada pode ser retomada até `max_retries_execucao` vezes
3. Após limites, marcar como ERRO definitivo

### 4. Persistência de Estado por Documento

Cada `ResultadoClassificacao` terá:
- `status`: PENDENTE, PROCESSANDO, CONCLUIDO, ERRO, PULADO
- `tentativas`: Contador de tentativas
- `erro_mensagem`: Detalhes do erro
- `erro_stack`: Stack trace (debug)
- `ultimo_erro_em`: Timestamp do último erro

### 5. Endpoints de Recuperação

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/execucoes/{id}/status-detalhado` | GET | Status com heartbeat, erros, rota origem |
| `/execucoes/{id}/erros` | GET | Lista documentos com erro e detalhes |
| `/execucoes/{id}/retomar` | POST | Retoma de onde parou (idempotente) |
| `/execucoes/{id}/reprocessar-erros` | POST | Reprocessa apenas itens com erro |

### 6. Frontend

- Timeout no EventSource: 60s sem eventos → mostrar aviso
- Se `status == TRAVADO`: exibir mensagem clara
- Botões: "Continuar de onde parou", "Reprocessar apenas erros"
- Exibir rota afetada: `/classificador/`

## Consequências

### Positivas
- Usuário nunca fica indefinidamente esperando
- Progresso nunca é perdido completamente
- Erros são registrados para análise
- Retomada é idempotente (seguro chamar múltiplas vezes)

### Negativas
- Complexidade adicional no código
- Mais campos no banco de dados
- Watchdog precisa ser executado periodicamente

### Riscos
- Watchdog pode marcar execução como travada durante processamento lento legítimo
  - Mitigação: timeout de 5 min é generoso
- Múltiplas retomadas simultâneas
  - Mitigação: Lock otimista via status + transação

## Alternativas Consideradas

1. **Timeout simples no frontend**: Descartado - não resolve o problema server-side
2. **Fila de mensagens (RabbitMQ)**: Descartado - over-engineering para o volume atual
3. **Checkpoint em arquivo**: Descartado - banco já persiste estado

## Implementação

### Arquivos a modificar/criar:
1. `sistemas/classificador_documentos/models.py` - Novos campos
2. `sistemas/classificador_documentos/watchdog.py` - Novo arquivo
3. `sistemas/classificador_documentos/router.py` - Novos endpoints
4. `sistemas/classificador_documentos/services.py` - Lógica de retomada
5. `sistemas/classificador_documentos/templates/index.html` - UI
6. `tests/classificador_documentos/test_watchdog.py` - Testes

### Migration necessária:
```sql
ALTER TABLE execucoes_classificacao ADD COLUMN ultimo_heartbeat TIMESTAMP;
ALTER TABLE execucoes_classificacao ADD COLUMN ultimo_codigo_processado VARCHAR(100);
ALTER TABLE execucoes_classificacao ADD COLUMN tentativas_retry INTEGER DEFAULT 0;
ALTER TABLE execucoes_classificacao ADD COLUMN max_retries INTEGER DEFAULT 3;

ALTER TABLE resultados_classificacao ADD COLUMN tentativas INTEGER DEFAULT 0;
ALTER TABLE resultados_classificacao ADD COLUMN erro_stack TEXT;
ALTER TABLE resultados_classificacao ADD COLUMN ultimo_erro_em TIMESTAMP;
```

## Referências

- CLAUDE.md: Regras de negócio do classificador
- docs/sistemas/classificador_documentos.md: Documentação do sistema
- sistemas/bert_training/watchdog.py: Implementação de referência do watchdog BERT
