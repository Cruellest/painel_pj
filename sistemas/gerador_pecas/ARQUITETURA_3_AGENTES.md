# Arquitetura de 3 Agentes - Gerador de Peças Jurídicas

## Visão Geral

O sistema de geração de peças jurídicas utiliza uma arquitetura de 3 agentes de IA que trabalham em sequência para produzir documentos jurídicos de alta qualidade.

## Fluxo de Execução

```
┌─────────────────────────────────────────────────────────────────────┐
│                           USUÁRIO                                    │
│                    (digita número do processo)                       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENTE 1 - COLETOR TJ-MS                                           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━                                          │
│  Modelo: google/gemini-2.5-flash-lite                               │
│                                                                      │
│  Responsabilidades:                                                  │
│  • Consultar processo via API SOAP do TJ-MS                         │
│  • Baixar documentos relevantes (petições, decisões, sentenças)     │
│  • Extrair texto de PDFs (inclusive digitalizados via OCR)          │
│  • Gerar resumo individual de cada documento                        │
│  • Produzir RESUMO CONSOLIDADO do processo                          │
│                                                                      │
│  Saída: resumo_consolidado (markdown estruturado)                   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENTE 2 - DETECTOR DE MÓDULOS                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                                     │
│  Modelo: google/gemini-2.0-flash-lite                               │
│                                                                      │
│  Responsabilidades:                                                  │
│  • Analisar o resumo consolidado                                    │
│  • Identificar situações jurídicas presentes no caso                │
│  • Ativar módulos de CONTEÚDO relevantes (teses e argumentos)       │
│  • Montar prompt combinando: BASE + PEÇA + CONTEÚDO                 │
│                                                                      │
│  Saída: prompts_modulares (sistema, peça, conteúdo)                 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AGENTE 3 - GERADOR DE PEÇA                                         │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━                                        │
│  Modelo: google/gemini-2.5-pro-preview-05-06                        │
│                                                                      │
│  Recebe:                                                             │
│  • Resumo consolidado (do Agente 1)                                 │
│  • Prompt do sistema (BASE)                                         │
│  • Prompt da peça (estrutura específica)                            │
│  • Prompt de conteúdo (teses e argumentos)                          │
│                                                                      │
│  Responsabilidades:                                                  │
│  • Gerar peça jurídica completa e fundamentada                      │
│  • Seguir estrutura formal da peça                                  │
│  • Aplicar argumentos e teses dos módulos ativados                  │
│  • Citar jurisprudência e legislação pertinentes                    │
│                                                                      │
│  Saída: conteudo_json (estrutura para DOCX)                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DOCUMENTO WORD                               │
│                      (download pelo usuário)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Arquivos do Sistema

```
sistemas/gerador_pecas/
├── agente_tjms.py              # Agente TJ-MS original (copiado)
├── agente_tjms_integrado.py    # Wrapper para integração
├── detector_modulos.py         # Agente 2 - Detector de módulos
├── orquestrador_agentes.py     # Coordena os 3 agentes
├── services.py                 # Serviço principal (usa orquestrador)
├── router.py                   # Endpoints da API
├── models.py                   # Modelos do banco
└── templates/
    ├── index.html              # Interface do usuário
    └── app.js                  # JavaScript (mostra progresso dos agentes)
```

## Prompts Modulares

O sistema utiliza 3 tipos de prompts armazenados no banco:

### 1. BASE (sempre ativo)
- Instruções gerais para a IA
- Diretrizes de formatação
- Padrões de linguagem jurídica

### 2. PEÇA (por tipo)
- Estrutura específica de cada peça
- Contestação, Recurso, Contrarrazões, Parecer
- Ativado com base na escolha do usuário

### 3. CONTEÚDO (detectado por IA)
- Teses e argumentos específicos
- Medicamentos não incorporados ao SUS
- Procedimentos cirúrgicos
- Laudos médicos
- Etc.

## Exemplo de Uso

```python
from sistemas.gerador_pecas.orquestrador_agentes import OrquestradorAgentes

# Inicializa com sessão do banco
orquestrador = OrquestradorAgentes(db=db_session)

# Processa um processo
resultado = await orquestrador.processar_processo(
    numero_processo="0000000-00.2024.8.12.0001",
    tipo_peca="contestacao"
)

if resultado.status == "sucesso":
    print(f"Peça gerada em {resultado.tempo_total:.1f}s")
    print(f"Documentos analisados: {resultado.agente1.documentos_analisados}")
```

## Variáveis de Ambiente Necessárias

```env
# API TJ-MS
URL_WSDL=https://esaj.tjms.jus.br/...
WS_USER=usuario
WS_PASS=senha

# OpenRouter (para os 3 agentes)
OPENROUTER_API_KEY=sk-or-...
```

## Tempos Estimados

| Agente | Tempo Médio | Descrição |
|--------|-------------|-----------|
| Agente 1 | 30-60s | Depende da quantidade de documentos |
| Agente 2 | 5-10s | Detecção rápida de módulos |
| Agente 3 | 20-40s | Geração da peça completa |
| **Total** | **60-120s** | Processo completo |

## Próximos Passos

1. [ ] Implementar cache de resumos consolidados
2. [ ] Adicionar mais módulos de conteúdo
3. [ ] Criar testes automatizados
4. [ ] Otimizar prompts com feedback dos usuários
