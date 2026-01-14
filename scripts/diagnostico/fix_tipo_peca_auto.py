# Script para corrigir registros com tipo_peca NULL ou inválido (AUTOMÁTICO)
# Execute com: railway run python scripts/diagnostico/fix_tipo_peca_auto.py
#
# ATENÇÃO: Este script aplica as correções automaticamente sem confirmação!

import sys
sys.path.insert(0, '.')

from database.connection import get_db
from sistemas.gerador_pecas.models import GeracaoPeca
import re

def inferir_tipo_peca(conteudo: str, prompt: str) -> str:
    """
    Infere o tipo de peça a partir do conteúdo ou prompt.
    Retorna o tipo identificado ou 'contestacao' como fallback.
    """
    texto = (conteudo or '') + (prompt or '')
    texto_lower = texto.lower()

    # Padrões para identificar cada tipo de peça
    padroes = {
        'recurso_apelacao': [
            r'recurso de apelação',
            r'apelação cível',
            r'apelante.*estado',
            r'razões de apelação',
            r'apelo',
            r'reforma.*sentença',
        ],
        'contrarrazoes': [
            r'contrarrazões',
            r'contra-razões',
            r'contraminuta',
            r'apelado.*estado',
            r'manutenção.*sentença',
            r'improvimento.*recurso',
        ],
        'parecer': [
            r'parecer jurídico',
            r'parecer.*n[º°]',
            r'opinativo',
            r'consulta jurídica',
        ],
        'contestacao': [
            r'contestação',
            r'contesta.*ação',
            r'réu.*estado',
            r'improcedência.*pedido',
            r'preliminar.*mérito',
        ],
    }

    # Conta matches para cada tipo
    scores = {}
    for tipo, patterns in padroes.items():
        score = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, texto_lower))
            score += matches
        scores[tipo] = score

    # Retorna o tipo com maior score
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)

    # Fallback
    return 'contestacao'


def main():
    db = next(get_db())

    print("=" * 60)
    print("CORREÇÃO AUTOMÁTICA DE tipo_peca NULL/INVÁLIDO")
    print("=" * 60)

    # Busca registros problemáticos
    registros = db.query(GeracaoPeca).filter(
        (GeracaoPeca.tipo_peca == None) |
        (GeracaoPeca.tipo_peca == '') |
        (GeracaoPeca.tipo_peca == 'null') |
        (GeracaoPeca.tipo_peca == 'undefined')
    ).all()

    print(f"\nRegistros com tipo_peca inválido: {len(registros)}")

    if not registros:
        print("Nenhum registro para corrigir!")
        return

    print("\nCorrigindo...")
    print("-" * 60)

    corrigidos = 0
    for g in registros:
        tipo_antigo = repr(g.tipo_peca)
        tipo_inferido = inferir_tipo_peca(g.conteudo_gerado, g.prompt_enviado)

        print(f"ID={g.id} | CNJ={g.numero_cnj}")
        print(f"  {tipo_antigo} -> {tipo_inferido}")

        g.tipo_peca = tipo_inferido
        corrigidos += 1

    # Salva as alterações
    db.commit()
    print("-" * 60)
    print(f"\n✅ {corrigidos} registros corrigidos com sucesso!")


if __name__ == "__main__":
    main()
