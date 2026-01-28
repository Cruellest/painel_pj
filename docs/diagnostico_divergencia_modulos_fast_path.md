# Diagnóstico: Divergência de Módulos no Fast Path

## Resumo Executivo

**Problema**: Para o mesmo processo (`08021483520258120043`), diferentes execuções mostram quantidades variadas de módulos ativados no Fast Path (1, 2 ou 4 módulos).

**Causa Raiz**: A extração de variáveis por IA (Agente 1) é **NÃO-DETERMINÍSTICA**, produzindo valores diferentes para a mesma variável em diferentes execuções.

**Severidade**: Média - Não é um bug no detector de módulos, mas uma inconsistência na extração de variáveis.

---

## 1. Linha do Tempo das Execuções

| ID | Timestamp | Modo | Módulos Det | Variável Crítica |
|----|-----------|------|-------------|------------------|
| 212 | 2026-01-27 20:59:59 | fast_path | 2 | `equipamentos_materiais=False` |
| 215 | 2026-01-27 22:14:15 | fast_path | 1 | `equipamentos_materiais=False` |
| 216 | 2026-01-27 22:30:36 | fast_path | 1 | `equipamentos_materiais=False` |
| 217 | 2026-01-28 00:17:44 | fast_path | 4 | `equipamentos_materiais=True` |

Todas as execuções usaram:
- Modelo: `gemini-3-flash-preview`
- Tipo de peça: `contestacao`
- Modo: `fast_path` (100% determinístico)

---

## 2. Evidências

### 2.1. Dados de Entrada Diferentes

```
Hashes dados_processo:
- Geração 212: e8466a66 (172 chaves)
- Geração 215: 7b443ea4 (173 chaves)
- Geração 216: 4b660d90 (173 chaves)
- Geração 217: bc7f6db1 (173 chaves)

Todos diferentes!
```

### 2.2. Variável Crítica: `peticao_inicial_equipamentos_materiais`

```python
# Geração 216 (1 módulo)
peticao_inicial_equipamentos_materiais = False

# Geração 217 (4 módulos)
peticao_inicial_equipamentos_materiais = True
```

A petição menciona "Sondas Botton de Gastrostomia Mic-Key" - claramente equipamentos médicos. O valor correto deveria ser `True`, mas a IA extraiu `False` em 3 de 4 execuções.

### 2.3. Impacto nos Módulos

A variável `peticao_inicial_equipamentos_materiais` afeta diretamente:

1. **Módulo 54** (`evt_mun_insumos`):
   - Regra: `peticao_inicial_equipamentos_materiais == True`
   - Com `False`: não ativado
   - Com `True`: ATIVADO

2. **Módulo 62** (`evt_tres_orcamentos`):
   - Regra OR incluindo `peticao_inicial_equipamentos_materiais`
   - Com `False`: depende de outras variáveis
   - Com `True`: ATIVADO

---

## 3. Análise da Causa Raiz

### 3.1. Fluxo de Extração de Variáveis

```
Documentos PDF
     ↓
Agente 1 (IA) → Gera resumos JSON com variáveis
     ↓
consolidar_dados_extracao() → Extrai variáveis
     ↓
Detector de Módulos → Avalia regras determinísticas
     ↓
Módulos ativados
```

### 3.2. Fonte da Inconsistência

1. **Temperatura padrão**: 0.3 (em `services/ia_params_resolver.py:71`)
2. **Sem cache**: Cada execução faz nova extração
3. **Sem validação cruzada**: Não há verificação de consistência

### 3.3. Query de Confirmação

```sql
-- Diferenças entre gerações 216 e 217
SELECT
    '216' as geracao,
    dados_processo->>'peticao_inicial_equipamentos_materiais' as equipamentos
FROM geracoes_pecas WHERE id = 216
UNION ALL
SELECT
    '217' as geracao,
    dados_processo->>'peticao_inicial_equipamentos_materiais' as equipamentos
FROM geracoes_pecas WHERE id = 217;

-- Resultado:
-- 216: false
-- 217: true
```

---

## 4. Hipóteses Testadas

| Hipótese | Resultado | Evidência |
|----------|-----------|-----------|
| Bug no detector de módulos | ❌ Descartada | Detector funciona corretamente com as variáveis recebidas |
| Mudança em regras entre execuções | ❌ Descartada | Regras não mudaram no período |
| Cache invalidado | ❌ Descartada | Não há cache de extração |
| Variáveis derivadas do XML incorretas | ❌ Descartada | `municipio_polo_passivo` é calculada corretamente |
| **Extração por IA não-determinística** | ✅ Confirmada | Mesmos documentos → variáveis diferentes |

---

## 5. Correção Proposta

### 5.1. Correção Imediata: Reduzir Temperatura da Extração

**Arquivo**: `services/ia_params_resolver.py`

```python
# Antes (linha 71)
DEFAULTS = {
    "modelo": "gemini-3-flash-preview",
    "temperatura": 0.3,  # Permite variação
    ...
}

# Depois
DEFAULTS = {
    "modelo": "gemini-3-flash-preview",
    "temperatura": 0.1,  # Reduz variação significativamente
    ...
}
```

### 5.2. Correção de Médio Prazo: Cache de Extração

Implementar cache baseado em hash dos documentos:

```python
# sistemas/gerador_pecas/services_extraction_cache.py
import hashlib
from typing import Dict, Any, Optional

class ExtractionCache:
    """Cache de extração de variáveis por hash de documentos."""

    def __init__(self, ttl_hours: int = 24):
        self.ttl_hours = ttl_hours

    def get_cache_key(self, numero_processo: str, docs_hash: str) -> str:
        return f"extraction:{numero_processo}:{docs_hash}"

    def compute_docs_hash(self, documentos: list) -> str:
        """Computa hash dos conteúdos dos documentos."""
        content = "".join(sorted([d.conteudo_texto for d in documentos if d.conteudo_texto]))
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def get_cached_extraction(
        self,
        numero_processo: str,
        documentos: list
    ) -> Optional[Dict[str, Any]]:
        """Retorna extração cacheada se existir."""
        # Implementação com Redis ou banco
        pass

    async def cache_extraction(
        self,
        numero_processo: str,
        documentos: list,
        dados_extracao: Dict[str, Any]
    ) -> None:
        """Cacheia resultado da extração."""
        pass
```

### 5.3. Correção de Longo Prazo: Validação de Consistência

Implementar validação semântica para variáveis críticas:

```python
def validar_extracao(dados: Dict[str, Any], texto_pedidos: str) -> Dict[str, Any]:
    """Valida e corrige inconsistências óbvias na extração."""

    # Se menciona termos de equipamentos mas variável é False, corrigir
    termos_equipamentos = [
        'sonda', 'cateter', 'bomba', 'cpap', 'bipap',
        'cadeira de rodas', 'muleta', 'andador', 'prótese',
        'órtese', 'aparelho', 'equipamento', 'material'
    ]

    texto_lower = texto_pedidos.lower() if texto_pedidos else ""
    tem_termo = any(termo in texto_lower for termo in termos_equipamentos)

    if tem_termo and not dados.get('peticao_inicial_equipamentos_materiais'):
        logger.warning(
            f"[VALIDAÇÃO] Corrigindo equipamentos_materiais: False -> True "
            f"(texto menciona termos de equipamentos)"
        )
        dados['peticao_inicial_equipamentos_materiais'] = True

    return dados
```

---

## 6. Testes Propostos

### 6.1. Teste de Consistência de Extração

```python
# tests/test_extraction_consistency.py
import pytest
from sistemas.gerador_pecas.orquestrador_agentes import consolidar_dados_extracao

class TestExtractionConsistency:
    """Testes de consistência na extração de variáveis."""

    @pytest.mark.asyncio
    async def test_mesmos_documentos_mesmas_variaveis(self, db_session, mock_gemini):
        """
        GIVEN mesmos documentos de entrada
        WHEN extração é executada múltiplas vezes
        THEN variáveis críticas devem ser consistentes
        """
        # Configura mock com temperatura 0
        mock_gemini.temperature = 0

        documentos = load_fixture("processo_08021483520258120043")

        # Executa extração 3 vezes
        resultados = []
        for _ in range(3):
            resultado = await executar_agente1(documentos)
            dados = consolidar_dados_extracao(resultado)
            resultados.append(dados)

        # Verifica consistência de variáveis críticas
        variaveis_criticas = [
            'peticao_inicial_equipamentos_materiais',
            'peticao_inicial_pedido_medicamento',
            'peticao_inicial_pedido_cirurgia',
        ]

        for var in variaveis_criticas:
            valores = [r.get(var) for r in resultados]
            assert len(set(valores)) == 1, \
                f"Variável {var} inconsistente: {valores}"

    @pytest.mark.asyncio
    async def test_validacao_corrige_inconsistencias(self):
        """
        GIVEN extração com valor claramente errado
        WHEN validação é aplicada
        THEN valor deve ser corrigido
        """
        dados = {
            'peticao_inicial_equipamentos_materiais': False,
            'peticao_inicial_pedidos': 'Fornecimento de Sonda de Gastrostomia'
        }

        dados_corrigidos = validar_extracao(
            dados,
            dados['peticao_inicial_pedidos']
        )

        assert dados_corrigidos['peticao_inicial_equipamentos_materiais'] == True
```

### 6.2. Teste de Integração do Fast Path

```python
# tests/test_fast_path_determinism.py
@pytest.mark.asyncio
async def test_fast_path_deterministico(self, db_session):
    """
    GIVEN processo com variáveis conhecidas
    WHEN Fast Path é executado múltiplas vezes
    THEN mesmos módulos devem ser ativados
    """
    # Fixa variáveis de entrada (bypass extração IA)
    dados_fixos = {
        'peticao_inicial_equipamentos_materiais': True,
        'peticao_inicial_municipio_polo_passivo': True,
        # ... outras variáveis
    }

    resultados = []
    for _ in range(3):
        detector = DetectorModulosIA(db_session)
        modulos = await detector.detectar_modulos_relevantes(
            documentos_resumo="...",
            tipo_peca="contestacao",
            dados_extracao=dados_fixos
        )
        resultados.append(sorted(modulos))

    # Todos devem ser idênticos
    assert all(r == resultados[0] for r in resultados), \
        f"Fast Path não-determinístico: {resultados}"
```

---

## 7. Checklist de Validação em Produção

### 7.1. Antes do Deploy

- [ ] Alterar temperatura padrão para 0.1
- [ ] Adicionar logs de variáveis críticas na extração
- [ ] Executar testes de consistência localmente

### 7.2. Após Deploy (Monitoramento)

- [ ] Verificar logs: `grep "equipamentos_materiais" /var/log/app.log`
- [ ] Comparar 10 execuções do mesmo processo
- [ ] Confirmar que variações reduziram

### 7.3. Validação Manual

```bash
# Executar mesma geração 3x e comparar
curl -X POST /api/gerador-pecas/gerar -d '{"processo": "08021483520258120043"}'
# Repetir 3x e comparar modulos_ativados_det
```

---

## 8. Conclusão

O problema reportado **não é um bug no detector de módulos**, mas sim uma **característica inerente da extração por IA** com temperatura > 0.

A correção mais efetiva é:
1. **Imediato**: Reduzir temperatura de extração para 0.1
2. **Curto prazo**: Implementar cache de extração por hash
3. **Médio prazo**: Adicionar validação semântica de variáveis críticas

O comportamento "4 módulos" da geração 217 era o **correto**, pois a petição menciona explicitamente equipamentos médicos (sondas de gastrostomia). As gerações 215/216 com "1 módulo" estavam **incorretas** devido à extração falha.

---

*Diagnóstico realizado em 2026-01-27 por Claude Code*
