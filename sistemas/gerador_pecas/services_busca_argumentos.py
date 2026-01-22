# sistemas/gerador_pecas/services_busca_argumentos.py
"""
Serviço de busca de argumentos jurídicos no banco de dados.

Permite ao chatbot de edição encontrar módulos de conteúdo relevantes
baseado na mensagem do usuário, usando busca full-text no Postgres.
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, text

from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca


def buscar_argumentos_relevantes(
    db: Session,
    query: str,
    tipo_peca: Optional[str] = None,
    limit: int = 5
) -> List[Dict]:
    """
    Busca módulos de conteúdo relevantes para a query do usuário.

    Busca em:
    - titulo
    - condicao_ativacao
    - regra_texto_original
    - regra_secundaria_texto_original
    - categoria/subcategoria

    Args:
        db: Sessão do banco de dados
        query: Texto de busca do usuário
        tipo_peca: Tipo de peça atual (para filtrar regras específicas)
        limit: Número máximo de resultados

    Returns:
        Lista de módulos relevantes com suas condições de ativação
    """
    print(f"\n[BUSCA-ARGUMENTOS] 🔍 Query: '{query}'")
    print(f"[BUSCA-ARGUMENTOS] 📋 Tipo de peça: {tipo_peca or 'não especificado'}")

    # Normaliza a query para busca
    query_normalizada = query.lower().strip()

    # Extrai palavras-chave da query (remove stopwords comuns)
    stopwords = {'adicione', 'adicionar', 'insira', 'inserir', 'coloque', 'colocar',
                 'argumento', 'argumentos', 'sobre', 'com', 'para', 'de', 'da', 'do',
                 'que', 'um', 'uma', 'o', 'a', 'os', 'as', 'e', 'ou', 'na', 'no',
                 'tese', 'teses', 'incluir', 'inclua', 'mencione', 'mencionar'}

    palavras = [p for p in query_normalizada.split() if p not in stopwords and len(p) > 2]
    print(f"[BUSCA-ARGUMENTOS] 🏷️  Palavras-chave extraídas: {palavras}")

    if not palavras:
        print(f"[BUSCA-ARGUMENTOS] ⚠️  Nenhuma palavra-chave válida encontrada")
        return []

    # Monta filtro de busca com ILIKE para cada palavra
    filtros = []
    for palavra in palavras:
        termo = f"%{palavra}%"
        filtros.append(
            or_(
                func.lower(PromptModulo.titulo).like(termo),
                func.lower(PromptModulo.condicao_ativacao).like(termo),
                func.lower(PromptModulo.regra_texto_original).like(termo),
                func.lower(PromptModulo.regra_secundaria_texto_original).like(termo),
                func.lower(PromptModulo.categoria).like(termo),
                func.lower(PromptModulo.subcategoria).like(termo)
            )
        )

    # Busca módulos de conteúdo ativos que correspondem aos filtros
    modulos = db.query(PromptModulo).filter(
        PromptModulo.tipo == 'conteudo',
        PromptModulo.ativo == True,
        or_(*filtros)  # Qualquer palavra encontrada
    ).order_by(PromptModulo.ordem).limit(limit * 2).all()  # Pega mais para rankear

    print(f"[BUSCA-ARGUMENTOS] 📦 Módulos encontrados: {len(modulos)}")

    # Rankeia por relevância (número de palavras encontradas)
    resultados_rankeados = []
    for modulo in modulos:
        score = 0
        campos_match = []

        texto_busca = " ".join([
            modulo.titulo or "",
            modulo.condicao_ativacao or "",
            modulo.regra_texto_original or "",
            modulo.categoria or "",
            modulo.subcategoria or ""
        ]).lower()

        for palavra in palavras:
            if palavra in texto_busca:
                score += 1
                if palavra in (modulo.titulo or "").lower():
                    score += 2  # Bonus para match no título
                    campos_match.append(f"titulo:'{palavra}'")
                elif palavra in (modulo.condicao_ativacao or "").lower():
                    campos_match.append(f"condicao:'{palavra}'")
                elif palavra in (modulo.regra_texto_original or "").lower():
                    campos_match.append(f"regra:'{palavra}'")

        if score > 0:
            resultados_rankeados.append((modulo, score, campos_match))

    # Ordena por score decrescente
    resultados_rankeados.sort(key=lambda x: x[1], reverse=True)

    # Busca regras específicas por tipo de peça
    regras_por_modulo = {}
    if tipo_peca:
        modulo_ids = [m.id for m, _, _ in resultados_rankeados[:limit]]
        if modulo_ids:
            regras = db.query(RegraDeterministicaTipoPeca).filter(
                RegraDeterministicaTipoPeca.modulo_id.in_(modulo_ids),
                RegraDeterministicaTipoPeca.tipo_peca == tipo_peca,
                RegraDeterministicaTipoPeca.ativo == True
            ).all()

            for regra in regras:
                if regra.modulo_id not in regras_por_modulo:
                    regras_por_modulo[regra.modulo_id] = []
                regras_por_modulo[regra.modulo_id].append(regra.regra_texto_original)

    # Monta resultado final
    resultados = []
    for modulo, score, campos in resultados_rankeados[:limit]:
        resultado = {
            "id": modulo.id,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
            "condicao_ativacao": modulo.condicao_ativacao,
            "regra_texto_original": modulo.regra_texto_original,
            "regra_secundaria": modulo.regra_secundaria_texto_original,
            "conteudo": modulo.conteudo,
            "score": score,
            "campos_match": campos
        }

        # Adiciona regras específicas do tipo de peça
        if modulo.id in regras_por_modulo:
            resultado["regras_tipo_peca"] = regras_por_modulo[modulo.id]

        resultados.append(resultado)
        print(f"[BUSCA-ARGUMENTOS]   ✓ [{score}] {modulo.titulo} (match: {', '.join(campos)})")

    return resultados


def formatar_contexto_argumentos(argumentos: List[Dict], max_chars: int = 8000) -> str:
    """
    Formata os argumentos encontrados como contexto para o prompt da IA.

    Args:
        argumentos: Lista de argumentos da busca
        max_chars: Limite de caracteres para não estourar contexto

    Returns:
        Texto formatado com os argumentos disponíveis
    """
    if not argumentos:
        return ""

    partes = [
        "### ARGUMENTOS DISPONÍVEIS NA BASE DE CONHECIMENTO:",
        "",
        "Os seguintes argumentos jurídicos estão disponíveis e podem ser utilizados:",
        ""
    ]

    chars_usados = len("\n".join(partes))

    for i, arg in enumerate(argumentos, 1):
        bloco = f"""**{i}. {arg['titulo']}**
- Categoria: {arg.get('categoria', 'N/A')} / {arg.get('subcategoria', 'N/A')}
- Condição de uso: {arg.get('condicao_ativacao') or arg.get('regra_texto_original') or 'Sem condição específica'}

Conteúdo:
{arg['conteudo'][:2000]}{'...' if len(arg['conteudo']) > 2000 else ''}

---
"""
        # Verifica se ainda cabe
        if chars_usados + len(bloco) > max_chars:
            partes.append(f"\n*({len(argumentos) - i + 1} argumentos adicionais omitidos por limite de contexto)*")
            break

        partes.append(bloco)
        chars_usados += len(bloco)

    partes.append("""
**INSTRUÇÕES PARA USO DOS ARGUMENTOS:**
1. Use o conteúdo acima como BASE, mas adapte ao caso concreto da minuta
2. Mantenha a estrutura e os fundamentos jurídicos apresentados
3. Se houver variáveis como {{ nome }} ou {{ valor }}, substitua pelos dados do caso
4. Integre o argumento de forma fluida na seção apropriada da minuta
""")

    return "\n".join(partes)


def detectar_intencao_busca(mensagem: str) -> bool:
    """
    Detecta se a mensagem do usuário indica intenção de adicionar/buscar argumentos.

    Args:
        mensagem: Mensagem do usuário

    Returns:
        True se parece ser pedido de argumento/tese
    """
    indicadores = [
        'adicione', 'adicionar', 'insira', 'inserir', 'inclua', 'incluir',
        'argumento', 'argumentos', 'tese', 'teses',
        'preliminar', 'mérito', 'eventualidade',
        'prescrição', 'decadência', 'ilegitimidade', 'incompetência',
        'legitimidade', 'competência', 'nulidade',
        'incorporado', 'não incorporado', 'sus', 'medicamento',
        'tema 106', 'tema 1234', 'tema 6', 'stf', 'stj',
        'fundamento', 'fundamentação'
    ]

    mensagem_lower = mensagem.lower()

    for indicador in indicadores:
        if indicador in mensagem_lower:
            return True

    return False
