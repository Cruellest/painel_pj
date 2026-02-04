# Sistema de Classificacao de Documentos PDF

## Visao Geral

Este sistema implementa a classificacao automatica de documentos PDF anexados no Gerador de Pecas, permitindo:

1. **Classificacao por categoria**: Cada PDF e classificado em uma das categorias existentes no `/admin/categorias-resumo-json`
2. **Extracao de JSON estruturado**: Apos classificado, o JSON e extraido conforme o formato da categoria
3. **Selecao inteligente**: Documentos sao priorizados como primarios ou secundarios conforme o tipo de peca

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLUXO DE PDFs ANEXADOS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌────────────────────┐    ┌────────────────────────┐   │
│  │  PDFs        │───>│ DocumentClassifier │───>│   Classificacoes       │   │
│  │  Anexados    │    │ (por arquivo)      │    │   com categoria_id     │   │
│  └──────────────┘    └────────────────────┘    └────────────┬───────────┘   │
│                                                              │               │
│                                                              ▼               │
│                      ┌────────────────────┐    ┌────────────────────────┐   │
│                      │ DocumentSelector   │<───│   Tipo de Peca         │   │
│                      │ (primario/secund.) │    │   (user ou detectado)  │   │
│                      └─────────┬──────────┘    └────────────────────────┘   │
│                                │                                             │
│                                ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │              EXTRACAO DE JSON POR CATEGORIA                            │ │
│  │  - Cada documento classificado -> formato JSON da categoria            │ │
│  │  - Consolida dados de extracao para regras deterministicas             │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                │                                             │
│                                ▼                                             │
│  ┌──────────────┐    ┌────────────────────┐    ┌────────────────────────┐   │
│  │  Agente 2    │───>│    Agente 3        │───>│   Peca Gerada          │   │
│  │  (Modulos)   │    │    (Geracao)       │    │                        │   │
│  └──────────────┘    └────────────────────┘    └────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. DocumentClassifier (`document_classifier.py`)

Classifica cada PDF individualmente em uma categoria.

#### Heuristica de Conteudo

| Condicao | Acao | Source |
|----------|------|--------|
| PDF com texto extraivel de boa qualidade | Envia primeiros 1000 + ultimos 1000 tokens | `text` |
| PDF com texto de ma qualidade | Converte para imagens | `full_image` |
| PDF e imagem nativa | Envia imagens das paginas | `full_image` |
| OCR falha | Envia imagens das paginas | `full_image` |

#### Prompt de Classificacao

O prompt e montado dinamicamente com:
- Lista de categorias do banco (id, nome, titulo, descricao)
- Conteudo do documento (texto truncado OU imagens)

Exemplo de prompt:
```
Voce e um classificador de documentos juridicos. Analise o documento
e classifique-o em UMA das categorias:

## CATEGORIAS DISPONIVEIS
- ID: 1 | peticoes (Peticoes Iniciais) - Peticoes iniciais e acoes judiciais
- ID: 2 | decisoes (Decisoes Judiciais) - Sentencas, despachos e decisoes
...

## DOCUMENTO A CLASSIFICAR
[Texto ou imagens]

## FORMATO DE RESPOSTA (JSON)
{
  "categoria_id": <ID_NUMERICO>,
  "confianca": <0.0_A_1.0>,
  "justificativa_curta": "<ate 140 caracteres>"
}
```

#### Fallback

Aplicado quando:
- IA retorna `categoria_id` inexistente
- IA retorna JSON malformado
- Confianca abaixo do threshold (padrao: 0.5)
- Erro de comunicacao com a IA

**Acao de fallback**: Usa categoria residual (is_residual=True) ou primeira categoria disponivel.

### 2. DocumentSelector (`document_selector.py`)

Seleciona documentos primarios e secundarios para cada tipo de peca.

#### Configuracao de Prioridades

Configuracao padrao (em `DEFAULT_PRIORITY_CONFIG`):

```python
{
    "contestacao": {
        "primarias": ["peticoes", "peticao_inicial"],
        "secundarias": ["decisoes", "sentencas", "pareceres"]
    },
    "contrarrazoes": {
        "primarias": ["recursos", "apelacao", "agravo"],
        "secundarias": ["sentencas", "decisoes", "peticoes"]
    },
    "recurso_apelacao": {
        "primarias": ["sentencas", "decisoes"],
        "secundarias": ["peticoes", "contestacao"]
    },
    ...
}
```

#### Regras de Desempate

Quando ha multiplos documentos da mesma categoria:
1. Maior confianca de classificacao
2. Presenca de palavras-chave indicativas ("DOS FATOS", "DOS PEDIDOS", etc.)
3. Ordem de envio (primeiro documento)

### 3. Integracao no Pipeline (`router.py`)

O endpoint `/gerador-pecas/processar-pdfs-stream` agora executa:

1. **Estagio 1**: Le bytes de cada PDF
2. **Estagio 2**: Classifica cada PDF via `DocumentClassifier`
3. **Estagio 3**: Seleciona primarios/secundarios via `DocumentSelector`
4. **Estagio 4**: Extrai JSON de cada documento usando formato da categoria
5. **Estagio 5**: Monta resumo consolidado com dados estruturados
6. **Estagio 6**: Executa Agente 2 (com dados de extracao!) e Agente 3

## Configuracao no Admin

Acesse `/admin/prompts-config` > Aba "Sistemas Acessorios":

### Classificador de Documentos PDF

| Campo | Descricao | Padrao |
|-------|-----------|--------|
| **Modelo** | Modelo de IA para classificacao | `gemini-2.5-flash-lite` |
| **Temperatura** | Temperatura de geracao | `0.1` |
| **Threshold de Confianca** | Confianca minima para aceitar | `0.5` |

> **Recomendacao**: Use `gemini-2.5-flash-lite` para classificacao - e rapido e barato.

## Auditoria

Cada classificacao registra:

```json
{
  "arquivo_nome": "peticao.pdf",
  "arquivo_id": "pdf_1",
  "categoria_id": 1,
  "categoria_nome": "peticoes",
  "confianca": 0.95,
  "justificativa": "Documento com DOS FATOS e DOS PEDIDOS",
  "source": "text",
  "fallback_aplicado": false,
  "fallback_motivo": null,
  "timestamp": "2024-03-15T10:30:00Z"
}
```

## Impacto de Custo

### Classificacao

- **Texto**: ~2000 tokens de entrada (texto truncado) + ~100 tokens de saida
- **Imagem**: 1-10 imagens (~500-5000 tokens por imagem, dependendo da resolucao)

**Custo estimado por documento**:
- Com texto: ~$0.0001 a $0.0003
- Com imagens: ~$0.001 a $0.005

### Extracao de JSON

Similar ao custo do Agente 1, mas apenas para documentos selecionados.

## Testes

Execute os testes com:

```bash
cd E:\Projetos\PGE\portal-pge
pytest tests/test_document_classifier.py -v
```

Cobertura:
1. PDF com texto - usa heuristica de texto parcial
2. PDF imagem - envia imagem inteira
3. OCR falha - envia imagem inteira
4. IA retorna categoria invalida - fallback
5. IA retorna JSON malformado - fallback
6. Confianca baixa - fallback
7. Categorias dinamicas do banco
8. Regressao: fluxo com metadado continua intacto

## Troubleshooting

### "Nenhum texto foi extraido dos PDFs"

**Causa**: PDFs sao imagens e a conversao para imagem falhou.

**Solucao**: Verifique se o PyMuPDF (fitz) esta instalado corretamente.

### "Classificador retornando sempre fallback"

**Causa**: Possiveis causas:
1. API Key nao configurada
2. Categorias nao cadastradas no banco
3. Threshold muito alto

**Solucao**:
1. Verifique API Key em `/admin/prompts-config`
2. Verifique categorias em `/admin/categorias-resumo-json`
3. Reduza o threshold de confianca

### "Categoria inexistente"

**Causa**: A IA retornou um ID que nao existe no banco.

**Solucao**: O sistema aplica fallback automaticamente. Se persistir, revise o prompt ou aumente a temperatura.

## Arquivos Relacionados

- `sistemas/gerador_pecas/document_classifier.py` - Classificador
- `sistemas/gerador_pecas/document_selector.py` - Seletor
- `sistemas/gerador_pecas/router.py` - Integracao no pipeline
- `frontend/templates/admin_prompts.html` - Configuracao no admin
- `tests/test_document_classifier.py` - Testes automatizados
