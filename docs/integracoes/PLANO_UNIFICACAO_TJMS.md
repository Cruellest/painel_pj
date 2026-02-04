# Plano de Unificação do Serviço TJMS

> ✅ **STATUS: MIGRAÇÃO CONCLUÍDA EM 24/01/2026**
>
> Todos os 6 sistemas foram migrados para usar `services/tjms/` como cliente unificado.

---

## ⚠️ REGRA CRÍTICA: Sincronização Backend/Frontend

**Ao alterar qualquer arquivo em `services/tjms/`, DEVE-SE:**

1. Verificar impacto nos templates dos sistemas que consomem TJMS
2. Atualizar a página de documentação em `/admin/tjms-docs`
3. Atualizar este documento se houver mudança arquitetural
4. Notificar a equipe de frontend se houver mudança na estrutura de dados

**Arquivos críticos que afetam TODOS os sistemas:**
- `services/tjms/config.py` - Configuração centralizada
- `services/tjms/client.py` - Cliente principal
- `services/tjms/models.py` - Modelos de dados
- `services/tjms/adapters.py` - Wrappers de compatibilidade

---

## Resumo da Migração Concluída

| Sistema | Status | Import Atual |
|---------|--------|--------------|
| Assistência Judiciária | ✅ Migrado | `from services.tjms import TJMSClient` |
| Classificador de Documentos | ✅ Migrado | `from services.tjms import TJMSClient` |
| Relatório Cumprimento | ✅ Migrado | `from services.tjms import DocumentDownloader` |
| Prestação de Contas | ✅ Migrado | `from services.tjms import consultar_processo_async` |
| Pedido de Cálculo | ✅ Migrado | `from services.tjms import DocumentDownloader` |
| Gerador de Peças | ✅ Migrado | `from services.tjms import get_config` |

---

## Documentação Original (Histórico)

## 1. Diagnóstico Atual

### 1.1 Mapeamento de Implementações SOAP

Atualmente existem **4 implementações diferentes** para comunicação com o TJ-MS:

| Implementação | Localização | Tipo | Usada por |
|--------------|-------------|------|-----------|
| **DocumentDownloader** | `sistemas/pedido_calculo/document_downloader.py` | async (aiohttp) | Pedido Cálculo, Prestação de Contas, Relatório Cumprimento, Classificador de Documentos |
| **AgenteTJMS** | `sistemas/gerador_pecas/agente_tjms.py` | async (aiohttp) | Gerador de Peças (sistema principal) |
| **soap_consultar_processo** | `sistemas/assistencia_judiciaria/core/logic.py` | sync (requests) | Assistência Judiciária |
| **tjms_client** | `services/tjms_client.py` | async (httpx) | **NÃO UTILIZADO** (existe mas não foi adotado) |

### 1.2 Uso por Sistema

| Sistema | Consulta XML | Download PDFs | Extração Texto | Processamento Especial |
|---------|--------------|---------------|----------------|------------------------|
| **Gerador de Peças** | ✅ Completo | ✅ Batch paralelo | ✅ PyMuPDF | NAT origin search, filtro por categorias |
| **Pedido Cálculo** | ✅ Completo | ✅ Batch de 3 | ✅ PyMuPDF | Identificação de planilha, petição |
| **Prestação de Contas** | ✅ Completo | ✅ Via pedido_calculo | ✅ Via pedido_calculo | Subconta (Playwright), fallback alvarás |
| **Relatório Cumprimento** | ✅ Completo | ✅ Via pedido_calculo | ✅ Via pedido_calculo | Detecção de agravo de instrumento |
| **Classificador de Documentos** | ✅ Completo | ✅ Via pedido_calculo | ✅ Via pedido_calculo | Conversão RTF→PDF |
| **Assistência Judiciária** | ✅ Só movimentos | ❌ Não baixa | ❌ Não extrai | Análise de gratuidade |

### 1.3 Problemas Identificados

| Problema | Impacto | Sistemas Afetados |
|----------|---------|-------------------|
| **Duplicação de código** | Manutenção difícil | Todos |
| **Timeouts inconsistentes** | 60s / 90s / 180s | Todos |
| **Retry logic diferente** | Resiliência variável | Todos |
| **Cliente centralizado não usado** | Esforço perdido | services/tjms_client.py |
| **Mistura sync/async** | Complexidade | Assistência Judiciária |
| **Configuração dispersa** | Risco de inconsistência | Todos |

### 1.4 Especificidades por Sistema

#### Gerador de Peças (mais complexo)
```python
# Funcionalidades específicas:
- Filtro por códigos_permitidos (por tipo de peça)
- CATEGORIAS_EXCLUIDAS hardcoded
- NAT origin search (busca em processo de origem)
- Agrupamento de documentos por janela de 2 horas
- Seleção determinística para 2º grau
- Processamento de pareceres NAT com JSON específico
- Batch paralelo: 4 conexões, batches de 5 docs
- Timeout: 180s para downloads
```

#### Pedido Cálculo (implementação base)
```python
# Funcionalidades:
- Batch de 3 documentos por vez
- Identificação inteligente de planilha vs petição
- Detecção de tipo 286 (Pedido de Cumprimento)
- Análise de complemento do movimento
- Suporte a IA para identificar planilha correta
- Timeout: 180s para downloads
```

#### Prestação de Contas
```python
# Funcionalidades específicas:
- Extração de subconta via Playwright (proxy local)
- Busca de alvarás como fallback
- Classificação de documentos via LLM
- Conversão PDF→imagens para IA multimodal
- Timeout: usa pedido_calculo
```

#### Relatório Cumprimento
```python
# Funcionalidades específicas:
- Detecção de Agravo de Instrumento
- Validação de agravos por partes do processo
- Busca em processo de origem
- Localização de trânsito em julgado
- Timeout: usa pedido_calculo
```

#### Classificador de Documentos
```python
# Funcionalidades específicas:
- Conversão RTF→PDF
- Listagem de documentos disponíveis
- Download individual ou em lote
- Timeout: usa pedido_calculo
```

#### Assistência Judiciária (mais simples)
```python
# Funcionalidades específicas:
- Apenas consulta XML (sem download de documentos)
- Extração de partes e assistência judiciária
- Detecção de apensos
- Análise de movimentos/complementos
- Sync (requests) com retry
- Timeout: 90s
```

---

## 2. Arquitetura Proposta

### 2.1 Visão Geral

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAMADA DE APLICAÇÃO                                │
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Gerador    │  │    Pedido    │  │  Prestação   │  │  Relatório   │     │
│  │    Peças     │  │   Cálculo    │  │   Contas     │  │ Cumprimento  │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │                 │              │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐     │
│  │Classificador │  │ Assistência  │  │              │  │              │     │
│  │  Documentos  │  │  Judiciária  │  │              │  │              │     │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  └──────────────┘     │
│         │                 │                                                  │
└─────────┼─────────────────┼──────────────────────────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CAMADA DE SERVIÇO UNIFICADO                              │
│                                                                              │
│  services/tjms/                                                              │
│  ├── __init__.py          # Exports públicos                                │
│  ├── client.py            # TJMSClient (classe principal)                   │
│  ├── config.py            # TJMSConfig (configuração centralizada)          │
│  ├── models.py            # ProcessoTJMS, DocumentoTJMS, etc.               │
│  ├── parsers.py           # XMLParser, extrair_documentos_xml              │
│  ├── downloaders.py       # BatchDownloader, download paralelo              │
│  └── extractors.py        # PDF→texto, RTF→PDF, PDF→imagens                │
│                                                                              │
│  Interface Principal:                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ class TJMSClient:                                                    │    │
│  │   async def consultar_processo(cnj, opts) -> ProcessoTJMS           │    │
│  │   async def baixar_documento(cnj, doc_id) -> bytes                  │    │
│  │   async def baixar_documentos(cnj, ids, opts) -> Dict[str, bytes]   │    │
│  │   async def extrair_subconta(cnj) -> ResultadoSubconta              │    │
│  │   async def listar_documentos(cnj) -> List[DocMetadata]             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CAMADA DE TRANSPORTE                                  │
│                                                                              │
│  ┌─────────────────────┐        ┌─────────────────────┐                     │
│  │    Proxy Fly.io     │        │    Proxy Local      │                     │
│  │   (SOAP - rápido)   │        │  (Playwright/ngrok) │                     │
│  │   tjms-proxy.fly.dev│        │  subconta, fallback │                     │
│  └──────────┬──────────┘        └──────────┬──────────┘                     │
│             │                              │                                 │
│             └──────────────┬───────────────┘                                 │
│                            │                                                 │
│                            ▼                                                 │
│                   ┌─────────────────┐                                        │
│                   │     TJ-MS       │                                        │
│                   │  (e-SAJ / MNI)  │                                        │
│                   └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Interface do Serviço Unificado

```python
# services/tjms/models.py

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class TipoConsulta(Enum):
    """Tipo de consulta para otimização."""
    COMPLETA = "completa"           # XML + movimentos + documentos
    METADATA_ONLY = "metadata"       # Apenas dados básicos
    MOVIMENTOS_ONLY = "movimentos"   # Dados + movimentos (sem docs)

@dataclass
class ConsultaOptions:
    """Opções de consulta customizáveis por sistema."""
    tipo: TipoConsulta = TipoConsulta.COMPLETA
    incluir_movimentos: bool = True
    incluir_documentos: bool = True
    timeout: float = 60.0

@dataclass
class DownloadOptions:
    """Opções de download customizáveis."""
    batch_size: int = 5
    max_paralelo: int = 4
    timeout: float = 180.0
    extrair_texto: bool = False
    converter_rtf: bool = True
    codigos_permitidos: Optional[List[int]] = None
    codigos_excluidos: Optional[List[int]] = None

@dataclass
class Parte:
    """Parte processual."""
    nome: str
    tipo_pessoa: Optional[str] = None  # fisica/juridica
    documento: Optional[str] = None     # CPF/CNPJ
    assistencia_judiciaria: bool = False
    tipo_representante: Optional[str] = None

@dataclass
class Movimento:
    """Movimento processual."""
    codigo_nacional: Optional[int] = None
    codigo_local: Optional[str] = None
    descricao: str = ""
    data_hora: Optional[datetime] = None
    complemento: Optional[str] = None

@dataclass
class DocumentoMetadata:
    """Metadados de documento."""
    id: str
    tipo_codigo: Optional[int] = None
    tipo_descricao: Optional[str] = None
    data_juntada: Optional[datetime] = None
    mimetype: Optional[str] = None

@dataclass
class ProcessoTJMS:
    """Processo completo do TJ-MS."""
    numero: str
    numero_formatado: str

    # Dados básicos
    classe_processual: Optional[str] = None
    data_ajuizamento: Optional[datetime] = None
    valor_causa: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    competencia: Optional[str] = None

    # Partes
    polo_ativo: List[Parte] = field(default_factory=list)
    polo_passivo: List[Parte] = field(default_factory=list)

    # Movimentos
    movimentos: List[Movimento] = field(default_factory=list)

    # Documentos (metadados)
    documentos: List[DocumentoMetadata] = field(default_factory=list)

    # Processo de origem (para cumprimentos autônomos)
    processo_origem: Optional[str] = None

    # XML original (para casos especiais)
    xml_raw: Optional[str] = None

@dataclass
class DocumentoTJMS:
    """Documento baixado."""
    id: str
    numero_processo: str
    conteudo_bytes: Optional[bytes] = None
    texto_extraido: Optional[str] = None
    formato: str = "pdf"  # pdf, rtf
    erro: Optional[str] = None
```

```python
# services/tjms/client.py

import asyncio
from typing import Optional, List, Dict
import httpx

from .config import TJMSConfig, get_config
from .models import (
    ProcessoTJMS, DocumentoTJMS, DocumentoMetadata,
    ConsultaOptions, DownloadOptions, TipoConsulta,
    ResultadoSubconta
)
from .parsers import XMLParserTJMS
from .extractors import extrair_texto_pdf, converter_rtf_para_pdf

class TJMSClient:
    """
    Cliente unificado para comunicação com TJ-MS.

    Centraliza todas as operações SOAP e download de documentos,
    permitindo customização por sistema via options.

    Exemplo de uso:

        # Uso simples (defaults)
        client = TJMSClient()
        processo = await client.consultar_processo("0800001-00.2024.8.12.0001")

        # Uso com opções customizadas
        opts = ConsultaOptions(tipo=TipoConsulta.MOVIMENTOS_ONLY, timeout=90)
        processo = await client.consultar_processo(cnj, opts)

        # Download de documentos
        download_opts = DownloadOptions(batch_size=3, extrair_texto=True)
        docs = await client.baixar_documentos(cnj, ids, download_opts)
    """

    def __init__(self, config: Optional[TJMSConfig] = None):
        self.config = config or get_config()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.config.soap_timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def consultar_processo(
        self,
        numero_cnj: str,
        options: Optional[ConsultaOptions] = None
    ) -> ProcessoTJMS:
        """
        Consulta processo no TJ-MS.

        Args:
            numero_cnj: Número CNJ (com ou sem formatação)
            options: Opções de consulta (opcional)

        Returns:
            ProcessoTJMS com dados estruturados

        Raises:
            TJMSError: Em caso de erro de comunicação
        """
        opts = options or ConsultaOptions()

        # Monta flags baseado no tipo de consulta
        incluir_movimentos = opts.incluir_movimentos
        incluir_documentos = opts.incluir_documentos

        if opts.tipo == TipoConsulta.METADATA_ONLY:
            incluir_movimentos = False
            incluir_documentos = False
        elif opts.tipo == TipoConsulta.MOVIMENTOS_ONLY:
            incluir_documentos = False

        # Executa consulta SOAP
        xml_response = await self._soap_consultar(
            numero_cnj,
            movimentos=incluir_movimentos,
            incluir_documentos=incluir_documentos,
            timeout=opts.timeout
        )

        # Parseia XML
        parser = XMLParserTJMS(xml_response)
        return parser.parse()

    async def baixar_documento(
        self,
        numero_cnj: str,
        doc_id: str,
        options: Optional[DownloadOptions] = None
    ) -> DocumentoTJMS:
        """Baixa um documento específico."""
        opts = options or DownloadOptions()
        docs = await self.baixar_documentos(numero_cnj, [doc_id], opts)
        return docs.get(doc_id, DocumentoTJMS(id=doc_id, numero_processo=numero_cnj, erro="Não encontrado"))

    async def baixar_documentos(
        self,
        numero_cnj: str,
        ids_documentos: List[str],
        options: Optional[DownloadOptions] = None
    ) -> Dict[str, DocumentoTJMS]:
        """
        Baixa múltiplos documentos em paralelo.

        Args:
            numero_cnj: Número CNJ do processo
            ids_documentos: Lista de IDs de documentos
            options: Opções de download

        Returns:
            Dict[doc_id -> DocumentoTJMS]
        """
        opts = options or DownloadOptions()
        resultado = {}

        # Processa em batches
        for i in range(0, len(ids_documentos), opts.batch_size):
            batch = ids_documentos[i:i + opts.batch_size]

            # Executa batch em paralelo (limitado por max_paralelo)
            tasks = [
                self._baixar_batch(numero_cnj, batch, opts)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for batch_result in batch_results:
                if isinstance(batch_result, dict):
                    resultado.update(batch_result)

        return resultado

    async def listar_documentos(
        self,
        numero_cnj: str
    ) -> List[DocumentoMetadata]:
        """Lista documentos disponíveis sem baixar conteúdo."""
        processo = await self.consultar_processo(
            numero_cnj,
            ConsultaOptions(tipo=TipoConsulta.COMPLETA)
        )
        return processo.documentos

    async def extrair_subconta(
        self,
        numero_cnj: str
    ) -> ResultadoSubconta:
        """Extrai extrato de subconta via proxy local (Playwright)."""
        from .subconta import extrair_subconta
        return await extrair_subconta(numero_cnj, self.config)

    # ========== Métodos privados ==========

    async def _soap_consultar(
        self,
        numero_cnj: str,
        movimentos: bool,
        incluir_documentos: bool,
        timeout: float
    ) -> str:
        """Executa consulta SOAP."""
        # Implementação similar ao atual soap_consultar_processo
        ...

    async def _baixar_batch(
        self,
        numero_cnj: str,
        ids: List[str],
        opts: DownloadOptions
    ) -> Dict[str, DocumentoTJMS]:
        """Baixa um batch de documentos."""
        ...


# Instância singleton para uso conveniente
_client: Optional[TJMSClient] = None

def get_client() -> TJMSClient:
    """Retorna instância singleton do cliente."""
    global _client
    if _client is None:
        _client = TJMSClient()
    return _client
```

### 2.3 Adaptadores por Sistema

Cada sistema que precisa de lógica específica terá um adaptador:

```python
# sistemas/gerador_pecas/tjms_adapter.py

from services.tjms import TJMSClient, DownloadOptions, ProcessoTJMS
from typing import List, Optional

class GeradorPecasTJMSAdapter:
    """
    Adaptador TJMS específico para Gerador de Peças.

    Encapsula:
    - Filtro por códigos permitidos/excluídos
    - NAT origin search
    - Agrupamento por janela de 2h
    """

    CATEGORIAS_EXCLUIDAS = [2, 5, 7, 8, 9, 10, 13, 53, 192, 8433, 8449, 8450, 9508, 9558, 9614, 9999, 8500]

    def __init__(self, client: Optional[TJMSClient] = None):
        self.client = client or TJMSClient()

    async def coletar_documentos(
        self,
        numero_cnj: str,
        codigos_permitidos: Optional[List[int]] = None
    ) -> dict:
        """
        Coleta documentos para geração de peça.

        Aplica filtros específicos do Gerador de Peças.
        """
        async with self.client:
            processo = await self.client.consultar_processo(numero_cnj)

            # Filtra documentos
            docs_para_baixar = self._filtrar_documentos(
                processo.documentos,
                codigos_permitidos
            )

            # Baixa com opções específicas
            opts = DownloadOptions(
                batch_size=5,
                max_paralelo=4,
                timeout=180.0,
                extrair_texto=True
            )

            documentos = await self.client.baixar_documentos(
                numero_cnj,
                [d.id for d in docs_para_baixar],
                opts
            )

            return {
                "processo": processo,
                "documentos": documentos
            }

    async def buscar_nat_origem(
        self,
        numero_origem: str,
        codigos_nat: List[int]
    ) -> Optional[dict]:
        """Busca NAT no processo de origem."""
        # Lógica específica do NAT origin search
        ...

    def _filtrar_documentos(
        self,
        documentos: List,
        codigos_permitidos: Optional[List[int]]
    ) -> List:
        """Aplica filtros de categoria."""
        if codigos_permitidos:
            return [d for d in documentos if d.tipo_codigo in codigos_permitidos]
        return [d for d in documentos if d.tipo_codigo not in self.CATEGORIAS_EXCLUIDAS]
```

---

## 3. Plano de Migração

### 3.1 Fases

```
Fase 0: Preparação (1 semana)
├── Criar estrutura services/tjms/
├── Migrar services/tjms_client.py para novo formato
├── Adicionar testes unitários básicos
└── Documentar interface

Fase 1: Migrar sistemas simples (1-2 semanas)
├── Assistência Judiciária (mais simples, sync→async)
├── Classificador de Documentos (já usa pedido_calculo)
└── Validar com testes de integração

Fase 2: Migrar sistemas médios (2 semanas)
├── Relatório Cumprimento
├── Prestação de Contas
└── Adaptar lógica de subconta

Fase 3: Migrar sistemas complexos (2-3 semanas)
├── Pedido Cálculo (base atual)
├── Gerador de Peças (mais complexo)
└── Criar adaptadores específicos

Fase 4: Cleanup (1 semana)
├── Remover implementações antigas
├── Atualizar documentação
└── Deploy gradual
```

### 3.2 Estratégia de Migração Segura

```python
# Durante a migração, usar feature flag:

# config.py
USE_UNIFIED_TJMS = os.getenv("USE_UNIFIED_TJMS", "false").lower() == "true"

# sistemas/assistencia_judiciaria/core/logic.py
async def consultar_processo_tj(numero_cnj: str):
    if USE_UNIFIED_TJMS:
        from services.tjms import get_client
        client = get_client()
        return await client.consultar_processo(numero_cnj)
    else:
        # Código antigo
        session = make_session()
        return soap_consultar_processo(session, numero_cnj)
```

### 3.3 Checklist por Sistema

#### Assistência Judiciária ✅
- [x] Migrar para async
- [x] Usar TJMSClient.consultar_processo()
- [x] Remover implementação SOAP local
- [ ] Testar análise de gratuidade

#### Classificador de Documentos ✅
- [x] Trocar import de pedido_calculo para services.tjms
- [x] Validar conversão RTF→PDF
- [ ] Testar listagem de documentos

#### Relatório Cumprimento ✅
- [x] Trocar import de pedido_calculo para services.tjms
- [x] Manter lógica de detecção de agravo no adapter
- [ ] Testar com cumprimentos autônomos

#### Prestação de Contas ✅
- [x] Trocar import de pedido_calculo para services.tjms
- [ ] Validar extração de subconta
- [ ] Testar fallback de alvarás

#### Pedido Cálculo ✅
- [x] Criar PedidoCalculoTJMSAdapter (via adapters.py)
- [x] Mover lógica de identificação de planilha para adapter
- [ ] Remover document_downloader.py após migração completa (mantido para extrair_texto_pdf)

#### Gerador de Peças ✅
- [x] Usar configuração centralizada (get_config)
- [x] Migrar NAT origin search para adapter
- [x] Migrar filtros de categoria para adapter
- [ ] Testar com todos os tipos de peça

---

## 4. Benefícios da Unificação

| Aspecto | Antes | Depois |
|---------|-------|--------|
| **Implementações SOAP** | 4 diferentes | 1 unificada |
| **Linhas de código TJMS** | ~2500 | ~800 + adapters |
| **Timeouts** | 60s/90s/180s (inconsistente) | Configurável |
| **Retry/Circuit Breaker** | Parcial | Padronizado |
| **Testes** | Dispersos | Centralizados |
| **Manutenção** | 4 arquivos | 1 módulo |
| **Novos sistemas** | Copiar código | Usar cliente |
| **Observabilidade** | Logs dispersos | Centralizado |

---

## 5. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Regressão em sistema existente | Média | Alto | Feature flags, testes E2E |
| Perda de performance | Baixa | Médio | Benchmark antes/depois |
| Timeout inadequado | Média | Médio | Configuração por sistema |
| Subconta quebrar | Média | Alto | Manter fallback antigo |

---

## 6. Métricas de Sucesso

- [ ] Zero regressões em produção
- [ ] Cobertura de testes > 80% no módulo tjms
- [ ] Tempo de resposta igual ou melhor
- [x] Todos os 6 sistemas migrados ✅ (24/01/2026)
- [ ] Código legado removido (document_downloader.py mantido para extrair_texto_pdf)

---

## 7. Cronograma Estimado

| Fase | Duração | Entregável |
|------|---------|------------|
| Fase 0 | 1 semana | services/tjms/ estruturado |
| Fase 1 | 2 semanas | 2 sistemas migrados |
| Fase 2 | 2 semanas | 4 sistemas migrados |
| Fase 3 | 3 semanas | 6 sistemas migrados |
| Fase 4 | 1 semana | Cleanup completo |
| **Total** | **9 semanas** | Unificação completa |

---

## 8. Decisão Arquitetural

**Recomendação**: Implementar a unificação conforme este plano.

**Justificativa**:
1. O código atual tem 4 implementações SOAP que fazem a mesma coisa
2. Já existe `services/tjms_client.py` que não foi adotado - hora de usar
3. Cada sistema tem especificidades que serão encapsuladas em adapters
4. A manutenção ficará muito mais simples
5. Novos sistemas poderão integrar TJMS facilmente

**Próximo passo**: Aprovar este plano e iniciar Fase 0.
