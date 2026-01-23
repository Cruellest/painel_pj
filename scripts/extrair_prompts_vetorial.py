#!/usr/bin/env python
"""
Script para extrair prompts de conteúdo do banco de dados
e gerar arquivo formatado para inserção em banco vetorial.

Usa SQL puro para evitar problemas com relacionamentos do SQLAlchemy.
"""

import os
import sys
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

# Conecta ao banco
DATABASE_URL = os.environ.get('DATABASE_URL_PROD') or os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERRO: DATABASE_URL não encontrada")
    sys.exit(1)

print(f"Conectando ao banco...")
engine = create_engine(DATABASE_URL)

# Busca módulos usando SQL puro
with engine.connect() as conn:
    # Busca todos os módulos de conteúdo ativos
    result = conn.execute(text("""
        SELECT
            id, nome, titulo, categoria, subcategoria,
            condicao_ativacao, regra_texto_original, regra_secundaria_texto_original,
            modo_ativacao, ordem, conteudo
        FROM prompt_modulos
        WHERE tipo = 'conteudo' AND ativo = true
        ORDER BY categoria, subcategoria, ordem
    """))
    modulos = [dict(row._mapping) for row in result]

    print(f"Total de módulos de conteúdo: {len(modulos)}")

    # Busca regras por tipo de peça
    result = conn.execute(text("""
        SELECT modulo_id, tipo_peca, regra_texto_original
        FROM regra_deterministica_tipo_peca
        WHERE ativo = true
    """))
    regras_raw = [dict(row._mapping) for row in result]

# Organiza regras por modulo_id
regras_por_modulo = {}
for r in regras_raw:
    modulo_id = r['modulo_id']
    if modulo_id not in regras_por_modulo:
        regras_por_modulo[modulo_id] = []
    regras_por_modulo[modulo_id].append({
        'tipo_peca': r['tipo_peca'],
        'regra': r['regra_texto_original']
    })

print(f"Regras por tipo de peça: {len(regras_raw)}")

# Gera o arquivo MD
output = []
output.append("# Prompts de Conteúdo - Base de Conhecimento Jurídico PGE-MS")
output.append("")
output.append(f"Extraído em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
output.append(f"Total de módulos: {len(modulos)}")
output.append("")
output.append("---")
output.append("")
output.append("## Formato para Embedding Vetorial")
output.append("")
output.append("Cada módulo abaixo contém:")
output.append("- **ID**: Identificador único no banco")
output.append("- **Nome**: Slug identificador")
output.append("- **Título**: Nome legível do argumento")
output.append("- **Categoria/Subcategoria**: Classificação hierárquica")
output.append("- **Condição de Ativação**: Quando usar este argumento (texto legado)")
output.append("- **Regra Determinística**: Condição em linguagem natural (nova)")
output.append("- **Regras por Tipo de Peça**: Condições específicas por tipo")
output.append("- **Conteúdo**: O texto do argumento jurídico")
output.append("")
output.append("### Sugestão de Texto para Embedding:")
output.append("```")
output.append("TÍTULO: {titulo}")
output.append("CATEGORIA: {categoria} > {subcategoria}")
output.append("QUANDO USAR: {condicao_ativacao ou regra_texto_original}")
output.append("CONTEÚDO: {conteudo}")
output.append("```")
output.append("")
output.append("---")
output.append("")

for i, m in enumerate(modulos, 1):
    output.append(f"## {i}. {m['titulo']}")
    output.append("")
    output.append("| Campo | Valor |")
    output.append("|-------|-------|")
    output.append(f"| **ID** | {m['id']} |")
    output.append(f"| **Nome** | `{m['nome']}` |")
    output.append(f"| **Categoria** | {m['categoria'] or 'N/A'} |")
    output.append(f"| **Subcategoria** | {m['subcategoria'] or 'N/A'} |")
    output.append(f"| **Modo Ativação** | {m['modo_ativacao'] or 'llm'} |")
    output.append(f"| **Ordem** | {m['ordem']} |")
    output.append("")

    # Condição de ativação
    if m['condicao_ativacao']:
        output.append("### Condição de Ativação (Legado)")
        output.append("")
        output.append(f"> {m['condicao_ativacao']}")
        output.append("")

    # Regra determinística primária
    if m['regra_texto_original']:
        output.append("### Regra Determinística Primária")
        output.append("")
        output.append(f"> {m['regra_texto_original']}")
        output.append("")

    # Regra secundária (fallback)
    if m['regra_secundaria_texto_original']:
        output.append("### Regra Secundária (Fallback)")
        output.append("")
        output.append(f"> {m['regra_secundaria_texto_original']}")
        output.append("")

    # Regras por tipo de peça
    if m['id'] in regras_por_modulo:
        output.append("### Regras por Tipo de Peça")
        output.append("")
        for rtp in regras_por_modulo[m['id']]:
            output.append(f"- **{rtp['tipo_peca']}**: {rtp['regra']}")
        output.append("")

    # Conteúdo
    output.append("### Conteúdo")
    output.append("")
    output.append("```markdown")
    output.append(m['conteudo'])
    output.append("```")
    output.append("")

    # Texto sugerido para embedding
    texto_embedding_parts = [
        f"TÍTULO: {m['titulo']}",
        f"CATEGORIA: {m['categoria'] or 'Geral'} > {m['subcategoria'] or 'Geral'}"
    ]

    condicao = m['regra_texto_original'] or m['condicao_ativacao']
    if condicao:
        texto_embedding_parts.append(f"QUANDO USAR: {condicao}")

    # Adiciona regras por tipo de peça
    if m['id'] in regras_por_modulo:
        for rtp in regras_por_modulo[m['id']]:
            texto_embedding_parts.append(f"EM {rtp['tipo_peca'].upper()}: {rtp['regra']}")

    conteudo_preview = m['conteudo'][:500] + "..." if len(m['conteudo']) > 500 else m['conteudo']
    texto_embedding_parts.append(f"CONTEÚDO: {conteudo_preview}")

    output.append("### Texto para Embedding")
    output.append("")
    output.append("```")
    output.append("\n".join(texto_embedding_parts))
    output.append("```")
    output.append("")
    output.append("---")
    output.append("")

# Salva o arquivo
output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "prompts_conteudo_vetorial.md")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(output))

print(f"Arquivo salvo: {output_path}")
print(f"Tamanho: {len(chr(10).join(output)):,} caracteres")
print("Concluído!")
