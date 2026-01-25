# ADR-0001: FastAPI como Framework Web

**Status:** Aceito

**Data:** 2024-01-01

**Autores:** Equipe LAB/PGE-MS

---

## Contexto

O Portal PGE-MS precisa de um framework web Python moderno para:
- Construir APIs RESTful
- Integrar com servicos de IA (streaming)
- Suportar alta concorrencia com I/O assincrono
- Gerar documentacao automatica (OpenAPI)
- Ter boa experiencia de desenvolvimento

Frameworks considerados: Flask, Django, FastAPI, Starlette.

## Decisao

> Decidimos usar **FastAPI** como framework web principal porque oferece o melhor equilibrio entre performance, DX e recursos modernos de Python.

## Opcoes Consideradas

### Opcao 1: Flask
- **Pros:** Simples, maduro, grande ecossistema
- **Contras:** Sincrono por padrao, documentacao manual

### Opcao 2: Django
- **Pros:** Baterias incluidas, admin pronto
- **Contras:** Pesado para APIs, curva de aprendizado

### Opcao 3: FastAPI (Escolhida)
- **Pros:**
  - Async nativo
  - Validacao automatica com Pydantic
  - Documentacao OpenAPI automatica
  - Type hints
  - Performance (comparavel a Node/Go)
- **Contras:**
  - Ecossistema menor que Flask/Django
  - Comunidade em crescimento

## Consequencias

### Positivas
- APIs bem documentadas automaticamente
- Validacao de entrada robusta
- Suporte nativo a async/await
- Facil integracao com SQLAlchemy 2.0

### Negativas
- Time precisa aprender async Python
- Alguns pacotes Flask nao funcionam diretamente

### Neutras
- Deploy similar a outras apps Python (Uvicorn)

## Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Comparativo de Performance](https://www.techempower.com/benchmarks/)
