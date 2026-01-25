# Integracoes Externas

Documentacao de integracoes com sistemas e servicos externos.

## Conteudo

| Documento | Descricao |
|-----------|-----------|
| [PLANO_UNIFICACAO_TJMS.md](PLANO_UNIFICACAO_TJMS.md) | **TJ-MS** - Cliente SOAP unificado em `services/tjms/` |
| [banco_vetorial.md](banco_vetorial.md) | Embeddings e busca vetorial |

## TJ-MS (Tribunal de Justica de MS)

> **IMPORTANTE**: Ao alterar `services/tjms/`, atualize `/admin/tjms-docs` e notifique frontend.

Cliente unificado em `services/tjms/`:
- `config.py` - Configuracao centralizada
- `client.py` - TJMSClient principal
- `models.py` - Modelos de dados
- `adapters.py` - Wrappers de compatibilidade

Todos os 6 sistemas usam este cliente unificado.

## Banco Vetorial

Integracao com embeddings para busca semantica em prompts e documentos.
