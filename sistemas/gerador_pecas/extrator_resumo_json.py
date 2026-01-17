# sistemas/gerador_pecas/extrator_resumo_json.py
"""
Extrator de resumos em formato JSON baseado em categorias de documento.

Este módulo é responsável por:
1. Identificar a categoria do documento pelo código TJ-MS
2. Buscar o formato JSON e instruções correspondentes
3. Gerar o prompt adequado para extração estruturada
4. Validar e parsear a resposta da IA
"""

import json
import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session


# Prompt padrão de critérios de relevância (fallback)
CRITERIOS_RELEVANCIA_PADRAO = """Se o documento for meramente administrativo (procuração, AR de citação, comprovante de pagamento,
documento pessoal, certidão de publicação, protocolo, etc), retorne apenas:
```json
{{"irrelevante": true, "motivo": "breve descrição do motivo"}}
```

IMPORTANTE: Os seguintes tipos de documento SÃO RELEVANTES e devem ser resumidos normalmente:
- Emails, ofícios e comunicações que contenham informações sobre o caso
- Documentos sobre transferência hospitalar, notificações médicas, comunicados sobre tratamento
- Relatórios, laudos, pareceres técnicos
- Qualquer documento que contenha informações factuais sobre o processo"""


def obter_criterios_relevancia(db: Optional[Session] = None) -> str:
    """
    Obtém os critérios de relevância do banco de dados.

    Busca na tabela ConfiguracaoIA com sistema='gerador_pecas' e chave='prompt_criterios_relevancia'.
    Se não encontrar, retorna o prompt padrão.

    Args:
        db: Sessão do banco de dados (opcional)

    Returns:
        String com os critérios de relevância para o prompt (com chaves escapadas para .format())
    """
    if not db:
        return CRITERIOS_RELEVANCIA_PADRAO

    try:
        from admin.models import ConfiguracaoIA

        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "gerador_pecas",
            ConfiguracaoIA.chave == "prompt_criterios_relevancia"
        ).first()

        if config and config.valor and config.valor.strip():
            # IMPORTANTE: Escapa chaves para não conflitar com .format()
            return config.valor.replace("{", "{{").replace("}", "}}")
    except Exception as e:
        print(f"[WARN] Erro ao carregar critérios de relevância do banco: {e}")

    return CRITERIOS_RELEVANCIA_PADRAO


@dataclass
class FormatoResumo:
    """Representa o formato de resumo a ser usado"""
    categoria_id: int
    categoria_nome: str
    formato_json: str  # JSON string com estrutura esperada
    instrucoes_extracao: Optional[str]
    is_residual: bool


def obter_formato_para_documento(db: Session, codigo_documento: int) -> Optional[FormatoResumo]:
    """
    Busca o formato de resumo JSON para um código de documento.
    
    Args:
        db: Sessão do banco de dados
        codigo_documento: Código do tipo de documento do TJ-MS
        
    Returns:
        FormatoResumo com o formato a ser usado, ou None se não encontrar
    """
    from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
    
    # Primeiro tenta encontrar categoria específica
    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True,
        CategoriaResumoJSON.is_residual == False
    ).all()
    
    for cat in categorias:
        if codigo_documento in (cat.codigos_documento or []):
            return FormatoResumo(
                categoria_id=cat.id,
                categoria_nome=cat.nome,
                formato_json=cat.formato_json,
                instrucoes_extracao=cat.instrucoes_extracao,
                is_residual=False
            )
    
    # Se não encontrou específica, usa residual
    residual = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True,
        CategoriaResumoJSON.is_residual == True
    ).first()
    
    if residual:
        return FormatoResumo(
            categoria_id=residual.id,
            categoria_nome=residual.nome,
            formato_json=residual.formato_json,
            instrucoes_extracao=residual.instrucoes_extracao,
            is_residual=True
        )
    
    return None


def gerar_prompt_extracao_json(
    formato: FormatoResumo,
    descricao_documento: str = "",
    db: Optional[Session] = None
) -> str:
    """
    Gera o prompt para extração de resumo em formato JSON.

    Args:
        formato: FormatoResumo com a estrutura esperada
        descricao_documento: Descrição do documento (se conhecida)
        db: Sessão do banco para carregar critérios de relevância configuráveis

    Returns:
        Prompt completo para a IA
    """
    # Escapa chaves do JSON para não conflitar com .format()
    formato_json_escaped = formato.formato_json.replace("{", "{{").replace("}", "}}")
    instrucoes_escaped = (formato.instrucoes_extracao or "").replace("{", "{{").replace("}", "}}")
    descricao_escaped = descricao_documento.replace("{", "{{").replace("}", "}}")

    # Obtém critérios de relevância configuráveis
    criterios_relevancia = obter_criterios_relevancia(db)

    prompt = """Analise o documento judicial e extraia as informações no formato JSON especificado abaixo.

## FORMATO JSON ESPERADO:
```json
""" + formato_json_escaped + """
```

## REGRAS DE PREENCHIMENTO:
1. Retorne APENAS o JSON válido, sem texto adicional antes ou depois
2. Use `null` para campos não encontrados no documento
3. Use `[]` (array vazio) para listas sem conteúdo
4. Use `false` para campos booleanos quando não aplicável
5. Seja fiel ao documento - NÃO invente informações
6. Para datas, use formato "DD/MM/YYYY" quando possível

## DOCUMENTOS IRRELEVANTES:
""" + criterios_relevancia + """
"""

    if instrucoes_escaped:
        prompt += """
## INSTRUÇÕES ESPECÍFICAS PARA ESTA CATEGORIA:
""" + instrucoes_escaped + """
"""

    if descricao_escaped:
        prompt += """
## TIPO DE DOCUMENTO INFORMADO:
""" + descricao_escaped + """
"""

    prompt += """
## DOCUMENTO A ANALISAR:
{texto_documento}"""

    return prompt


def gerar_prompt_extracao_json_imagem(
    formato: FormatoResumo,
    db: Optional[Session] = None
) -> str:
    """
    Gera o prompt para extração de resumo JSON a partir de imagens (PDFs digitalizados).

    Args:
        formato: FormatoResumo com a estrutura esperada
        db: Sessão do banco para carregar critérios de relevância configuráveis
    """
    # Escapa chaves do JSON para não conflitar com .format()
    formato_json_escaped = formato.formato_json.replace("{", "{{").replace("}", "}}")
    instrucoes_escaped = (formato.instrucoes_extracao or "").replace("{", "{{").replace("}", "}}")

    # Obtém critérios de relevância configuráveis
    criterios_relevancia = obter_criterios_relevancia(db)

    prompt = """Analise as imagens deste documento judicial e extraia as informações no formato JSON.

## FORMATO JSON ESPERADO:
```json
""" + formato_json_escaped + """
```

## REGRAS:
1. Retorne APENAS o JSON válido
2. Use `null` para campos não identificáveis
3. Seja fiel ao documento - NÃO invente informações

## DOCUMENTOS IRRELEVANTES:
""" + criterios_relevancia + """
"""

    if instrucoes_escaped:
        prompt += """
## INSTRUÇÕES ESPECÍFICAS:
""" + instrucoes_escaped + """
"""

    return prompt


def _corrigir_json_malformado(json_str: str) -> str:
    """
    Tenta corrigir problemas comuns de JSON malformado retornado pela LLM.

    Corrige:
    - Trailing commas (vírgulas antes de } ou ])
    - Vírgulas faltando entre elementos
    - Quebras de linha dentro de strings
    - Comentários // e /* */
    - Aspas "inteligentes" (curly quotes)
    - Caracteres de controle inválidos
    - JSON truncado (strings/chaves não fechadas)
    """
    import logging
    logger = logging.getLogger(__name__)

    original = json_str

    # 0. Normaliza aspas "inteligentes" para aspas normais
    json_str = json_str.replace('"', '"').replace('"', '"')
    json_str = json_str.replace(''', "'").replace(''', "'")

    # 1. Remove caracteres de controle inválidos (exceto \n, \r, \t)
    # Esses caracteres causam erro de parse mesmo dentro de strings
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)

    # 2. Remove comentários multilinha /* ... */
    # Usa abordagem não-gulosa para pegar cada bloco
    json_str = re.sub(r'/\*[\s\S]*?\*/', '', json_str)

    # 3. Remove comentários de linha única (// ...)
    # Cuidado para não remover // dentro de strings
    lines = json_str.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        # Remove comentário no final da linha (fora de strings)
        # Heurística simples: se tem // e não está dentro de aspas
        if '//' in line:
            # Conta aspas antes do //
            pos = line.find('//')
            aspas_antes = line[:pos].count('"') - line[:pos].count('\\"')
            if aspas_antes % 2 == 0:  # Número par = fora de string
                line = line[:pos]
        cleaned_lines.append(line)
    json_str = '\n'.join(cleaned_lines)

    # Remove trailing commas antes de } ou ]
    # Padrão: vírgula seguida de espaços/quebras e então } ou ]
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Adiciona vírgulas faltando entre elementos JSON
    # Aplica em loop até não haver mais mudanças (para pegar múltiplas ocorrências)
    padroes_virgula = [
        # === Padrões com quebra de linha ===
        # Padrão 1: string seguida de nova chave
        (r'(")\s*\n(\s*"[^"]+"\s*:)', r'\1,\n\2', 0),
        # Padrão 2: número seguido de nova chave
        (r'(\d)\s*\n(\s*"[^"]+"\s*:)', r'\1,\n\2', 0),
        # Padrão 3: true/false/null seguido de nova chave
        (r'(true|false|null)\s*\n(\s*"[^"]+"\s*:)', r'\1,\n\2', re.IGNORECASE),
        # Padrão 4: } ou ] seguido de nova chave
        (r'([}\]])\s*\n(\s*"[^"]+"\s*:)', r'\1,\n\2', 0),
        # Padrão 5: string seguida de { ou [
        (r'(")\s*\n(\s*[{\[])', r'\1,\n\2', 0),
        # Padrão 6: } ou ] seguido de { ou [
        (r'([}\]])\s*\n(\s*[{\[])', r'\1,\n\2', 0),
        # Padrão 7: string seguida de string
        (r'(")\s*\n(\s*")', r'\1,\n\2', 0),
        # Padrão 8: número seguido de número
        (r'(\d)\s*\n(\s*\d)', r'\1,\n\2', 0),
        # Padrão 9: número seguido de string
        (r'(\d)\s*\n(\s*")', r'\1,\n\2', 0),
        # Padrão 10: string seguida de número
        (r'(")\s*\n(\s*\d)', r'\1,\n\2', 0),
        # Padrão 11: true/false/null seguido de valor
        (r'(true|false|null)\s*\n(\s*["\d\[{tfn])', r'\1,\n\2', re.IGNORECASE),
        # Padrão 12: valor seguido de true/false/null
        (r'(["\d}\]])\s*\n(\s*(?:true|false|null))', r'\1,\n\2', re.IGNORECASE),

        # === Padrões na mesma linha (sem quebra) ===
        # Padrão 13: string seguida de chave na mesma linha (ex: "valor" "chave":)
        (r'(")\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', 0),
        # Padrão 14: número seguido de chave na mesma linha
        (r'(\d)\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', 0),
        # Padrão 15: } seguido de chave na mesma linha
        (r'(\})\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', 0),
        # Padrão 16: ] seguido de chave na mesma linha
        (r'(\])\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', 0),
        # Padrão 17: true/false/null seguido de chave na mesma linha
        (r'(true|false|null)\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', re.IGNORECASE),
    ]

    # Aplica padrões em loop até estabilizar
    max_iteracoes = 10
    for _ in range(max_iteracoes):
        json_anterior = json_str
        for padrao, substituicao, flags in padroes_virgula:
            json_str = re.sub(padrao, substituicao, json_str, flags=flags)
        if json_str == json_anterior:
            break

    # Corrige quebras de linha dentro de strings
    # Isso é mais complexo - vamos tentar uma abordagem conservadora
    # Substitui quebras de linha por \n quando parecem estar dentro de strings

    # Primeiro, vamos tentar parsear e ver se funciona
    try:
        json.loads(json_str)
        return json_str  # Já está ok após correções básicas
    except json.JSONDecodeError:
        pass

    # Se ainda falhou, tenta corrigir strings multilinha
    # Abordagem: encontra strings e escapa quebras de linha dentro delas
    resultado = []
    i = 0
    dentro_string = False

    while i < len(json_str):
        char = json_str[i]

        if char == '"' and (i == 0 or json_str[i-1] != '\\'):
            dentro_string = not dentro_string
            resultado.append(char)
        elif dentro_string and char == '\n':
            resultado.append('\\n')
        elif dentro_string and char == '\r':
            pass  # Ignora \r
        elif dentro_string and char == '\t':
            resultado.append('\\t')
        else:
            resultado.append(char)

        i += 1

    json_str = ''.join(resultado)

    # Tenta novamente remover trailing commas (pode ter surgido novos casos)
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    if json_str != original:
        logger.debug(f"JSON corrigido de {len(original)} para {len(json_str)} chars")

    return json_str


def _reparar_json_truncado(json_str: str) -> str:
    """
    Tenta reparar JSON truncado (strings não terminadas, chaves não fechadas).

    Problemas comuns de truncamento:
    - Strings não terminadas (falta aspas de fechamento)
    - Chaves/colchetes não fechados
    - JSON cortado no meio de um valor
    """
    import logging
    logger = logging.getLogger(__name__)

    texto = json_str.strip()

    # 1. Repara strings não terminadas
    # Reconstrói linha por linha, fechando strings abertas
    linhas = texto.split('\n')
    texto_reconstruido = []

    for linha in linhas:
        linha_stripped = linha.rstrip()
        if not linha_stripped:
            continue

        # Conta aspas na linha (excluindo aspas escapadas)
        aspas_na_linha = linha_stripped.count('"') - linha_stripped.count('\\"')

        if aspas_na_linha % 2 == 0:
            # Número par de aspas = linha completa
            texto_reconstruido.append(linha_stripped)
        else:
            # Linha com string não terminada - tenta fechar
            # Padrão: "chave": "valor_incompleto
            match = re.search(r'^(.*"[^"]*:\s*")([^"]*?)$', linha_stripped)
            if match:
                texto_reconstruido.append(match.group(1) + '[TRUNCADO]"')
            else:
                # Pode ser item de array: "valor_incompleto
                match2 = re.search(r'^(\s*")([^"]*?)$', linha_stripped)
                if match2:
                    texto_reconstruido.append(match2.group(1) + '[TRUNCADO]"')
                else:
                    # Ignora linha problemática
                    pass

    texto = '\n'.join(texto_reconstruido)

    # 2. Fecha estruturas abertas (chaves e colchetes)
    abre_chaves = texto.count('{')
    fecha_chaves = texto.count('}')
    abre_colchetes = texto.count('[')
    fecha_colchetes = texto.count(']')

    # Adiciona fechamentos faltando
    # (ordem importa: fecha arrays antes de objetos se estiverem aninhados)
    faltam_colchetes = abre_colchetes - fecha_colchetes
    faltam_chaves = abre_chaves - fecha_chaves

    if faltam_colchetes > 0 or faltam_chaves > 0:
        # Remove trailing comma antes de fechar
        texto = texto.rstrip()
        if texto.endswith(','):
            texto = texto[:-1]

        # Fecha estruturas (assume ordem: colchetes internos, depois chaves)
        texto += ']' * faltam_colchetes
        texto += '}' * faltam_chaves

        logger.debug(f"JSON truncado reparado: +{faltam_colchetes} colchetes, +{faltam_chaves} chaves")

    return texto


def parsear_resposta_json(resposta: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parseia a resposta da IA e extrai o JSON.

    Args:
        resposta: Texto de resposta da IA

    Returns:
        Tupla (json_dict, erro) - erro é None se parse bem-sucedido
    """
    import logging
    logger = logging.getLogger(__name__)

    if not resposta:
        logger.error("[JSON_PARSE] Resposta vazia recebida")
        return {}, "Resposta vazia"

    # Log de diagnóstico - tamanho original
    tamanho_original = len(resposta)
    logger.info(f"[JSON_PARSE] Resposta recebida: {tamanho_original} caracteres")

    resposta = resposta.strip()

    # Tenta extrair JSON de bloco de código markdown
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', resposta)
    if match:
        json_str = match.group(1).strip()
        logger.debug(f"[JSON_PARSE] JSON extraído de bloco markdown: {len(json_str)} chars")
    else:
        # Tenta usar resposta direta (pode começar com { ou [)
        json_str = resposta

        # Remove texto antes do primeiro { ou [
        first_brace = json_str.find('{')
        first_bracket = json_str.find('[')

        if first_brace >= 0 and (first_bracket < 0 or first_brace < first_bracket):
            json_str = json_str[first_brace:]
        elif first_bracket >= 0:
            json_str = json_str[first_bracket:]

    # Remove texto após o último } ou ]
    last_brace = json_str.rfind('}')
    last_bracket = json_str.rfind(']')

    if last_brace >= 0 and (last_bracket < 0 or last_brace > last_bracket):
        json_str = json_str[:last_brace + 1]
    elif last_bracket >= 0:
        json_str = json_str[:last_bracket + 1]

    tamanho_extraido = len(json_str)
    if tamanho_original - tamanho_extraido > 50:
        logger.debug(f"[JSON_PARSE] Após extração: {tamanho_extraido} chars (removido {tamanho_original - tamanho_extraido})")

    # VALIDAÇÃO DE COMPLETUDE: Verifica balanceamento antes de parsear
    abre_chaves = json_str.count('{')
    fecha_chaves = json_str.count('}')
    abre_colchetes = json_str.count('[')
    fecha_colchetes = json_str.count(']')

    if abre_chaves != fecha_chaves or abre_colchetes != fecha_colchetes:
        logger.warning(
            f"[JSON_PARSE] POSSÍVEL TRUNCAMENTO - Estruturas desbalanceadas: "
            f"{{ {abre_chaves}/{fecha_chaves} }}, [ {abre_colchetes}/{fecha_colchetes} ]"
        )
        # Log dos últimos 200 chars para diagnóstico
        if len(json_str) > 200:
            logger.warning(f"[JSON_PARSE] Últimos 200 chars: ...{json_str[-200:]}")

    # Primeira tentativa: parse direto
    try:
        resultado = json.loads(json_str)
        logger.info(f"[JSON_PARSE] Parse direto bem-sucedido: {len(resultado)} campos")
        return resultado, None
    except json.JSONDecodeError as e1:
        logger.debug(f"[JSON_PARSE] Parse direto falhou na posição {e1.pos}: {e1.msg}")

    # Segunda tentativa: corrige JSON malformado
    json_str_corrigido = _corrigir_json_malformado(json_str)

    try:
        resultado = json.loads(json_str_corrigido)
        logger.debug("Parse bem-sucedido após correção de JSON malformado")
        return resultado, None
    except json.JSONDecodeError as e2:
        logger.debug(f"Parse após correção falhou: {e2}")

    # Terceira tentativa: repara JSON truncado
    json_str_reparado = _reparar_json_truncado(json_str_corrigido)

    try:
        resultado = json.loads(json_str_reparado)
        logger.info("Parse bem-sucedido após reparo de JSON truncado")
        return resultado, None
    except json.JSONDecodeError as e3:
        # Log detalhado do JSON problemático para debug
        logger.warning(
            f"JSON não parseável após todas as tentativas.\n"
            f"Erro final: {e3}\n"
            f"Tamanho original: {len(json_str)} chars\n"
            f"JSON (primeiros 1000 chars):\n{json_str_reparado[:1000]}"
        )
        return {}, f"Erro ao parsear JSON: {e3}"


def verificar_irrelevante_json(json_dict: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verifica se o JSON indica documento irrelevante.

    Returns:
        Tupla (is_irrelevante, motivo_ou_json_string)
    """
    if not json_dict:
        return False, "{}"

    is_irrelevante = json_dict.get("irrelevante", False)

    if is_irrelevante:
        motivo = json_dict.get("motivo", "Documento irrelevante")
        return True, motivo

    return False, json.dumps(json_dict, ensure_ascii=False, indent=2)


def _obter_valor_default_por_tipo(tipo: str) -> Any:
    """
    Retorna o valor default para um campo baseado no seu tipo.

    Args:
        tipo: Tipo do campo (boolean, list, text, number, date, choice, etc.)

    Returns:
        Valor default apropriado para o tipo
    """
    tipo_lower = (tipo or "").lower()

    if tipo_lower == "boolean":
        return False
    elif tipo_lower == "list":
        return []
    else:
        # text, number, date, choice, etc.
        return None


def normalizar_json_com_schema(
    json_resposta: Dict[str, Any],
    schema_str: str
) -> Dict[str, Any]:
    """
    Normaliza a resposta JSON da IA garantindo que TODAS as chaves do schema
    estejam presentes no resultado final.

    Esta função resolve o problema onde a IA retorna apenas campos "aplicáveis",
    omitindo campos que deveriam estar presentes com valores default.

    Args:
        json_resposta: Dicionário JSON retornado pela IA
        schema_str: String JSON do schema cadastrado na categoria

    Returns:
        Dicionário JSON com todas as chaves do schema preenchidas:
        - Campos presentes na resposta: mantém o valor da IA
        - Campos ausentes: preenche com valor default baseado no tipo:
            - boolean: False
            - list: []
            - outros (text, number, date, choice): None

    Exemplo:
        >>> schema = '{"ativo": {"type": "boolean"}, "itens": {"type": "list"}, "nome": {"type": "text"}}'
        >>> resposta = {"ativo": True}
        >>> normalizar_json_com_schema(resposta, schema)
        {"ativo": True, "itens": [], "nome": None}
    """
    import logging
    logger = logging.getLogger(__name__)

    # Caso especial: documento irrelevante - retorna sem modificações
    if json_resposta.get("irrelevante", False):
        return json_resposta

    # Parseia o schema
    try:
        schema = json.loads(schema_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Erro ao parsear schema para normalização: {e}")
        return json_resposta

    if not isinstance(schema, dict):
        logger.warning("Schema não é um dicionário, retornando resposta sem normalização")
        return json_resposta

    # Cria resultado com todas as chaves do schema
    resultado = {}
    chaves_adicionadas = []

    for chave, config in schema.items():
        if chave in json_resposta:
            # Campo presente na resposta da IA - usa o valor retornado
            resultado[chave] = json_resposta[chave]
        else:
            # Campo ausente - adiciona com valor default
            if isinstance(config, dict):
                tipo = config.get("type", "text")
            else:
                # Config simples (apenas tipo)
                tipo = str(config) if config else "text"

            valor_default = _obter_valor_default_por_tipo(tipo)
            resultado[chave] = valor_default
            chaves_adicionadas.append(chave)

    if chaves_adicionadas:
        logger.info(
            f"Normalização JSON: {len(chaves_adicionadas)} campos adicionados com defaults: "
            f"{chaves_adicionadas[:10]}{'...' if len(chaves_adicionadas) > 10 else ''}"
        )

    return resultado


def extrair_tipo_documento_json(json_dict: Dict[str, Any]) -> Optional[str]:
    """
    Extrai o tipo de documento identificado pela IA do JSON.
    """
    if not json_dict:
        return None
    
    # Tenta vários campos comuns
    tipo = json_dict.get("tipo_documento")
    if tipo:
        return tipo
    
    tipo = json_dict.get("tipo")
    if tipo:
        return tipo
    
    return None


def extrair_processo_origem_json(json_dict: Dict[str, Any]) -> Optional[str]:
    """
    Extrai o número do processo de origem do JSON (para Agravos de Instrumento).
    """
    if not json_dict:
        return None
    
    processo = json_dict.get("processo_origem")
    if processo and isinstance(processo, str) and processo != "null":
        # Valida formato CNJ
        padrao_cnj = r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}'
        if re.match(padrao_cnj, processo):
            return processo
    
    return None


def json_para_markdown(json_dict: Dict[str, Any], nivel: int = 0) -> str:
    """
    Converte um dicionário JSON para formato Markdown legível.
    Útil para exibição e para manter compatibilidade com fluxos existentes.
    """
    if not json_dict:
        return ""
    
    linhas = []
    indent = "  " * nivel
    
    for chave, valor in json_dict.items():
        if chave in ("irrelevante", "motivo") and nivel == 0:
            continue  # Pula campos de controle no nível raiz
            
        # Formata a chave
        chave_formatada = chave.replace("_", " ").title()
        
        if valor is None or valor == "null":
            continue
        elif isinstance(valor, bool):
            linhas.append(f"{indent}**{chave_formatada}**: {'Sim' if valor else 'Não'}")
        elif isinstance(valor, str):
            if valor.strip():
                linhas.append(f"{indent}**{chave_formatada}**: {valor}")
        elif isinstance(valor, list):
            if valor:
                linhas.append(f"{indent}**{chave_formatada}**:")
                for item in valor:
                    if isinstance(item, dict):
                        linhas.append(json_para_markdown(item, nivel + 1))
                    else:
                        linhas.append(f"{indent}  - {item}")
        elif isinstance(valor, dict):
            # Verifica se o dict tem algum valor não-null
            tem_valor = any(v is not None and v != "null" and v != "" for v in valor.values())
            if tem_valor:
                linhas.append(f"{indent}**{chave_formatada}**:")
                linhas.append(json_para_markdown(valor, nivel + 1))
    
    return "\n".join(linhas)


class GerenciadorFormatosJSON:
    """
    Gerenciador que mantém cache dos formatos JSON para evitar
    consultas repetidas ao banco durante processamento de múltiplos documentos.

    Suporta:
    - Categorias por código de documento (comportamento padrão)
    - Categorias com fonte especial (ex: "peticao_inicial" = primeiro doc com código 9500/500)
    - Exclusão automática de documentos de fontes especiais das categorias por código
    """

    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[int, FormatoResumo] = {}  # código -> formato
        self._residual: Optional[FormatoResumo] = None
        self._carregado = False

        # Fontes especiais
        self._fontes_especiais: Dict[str, Tuple[FormatoResumo, List[int]]] = {}  # key -> (formato, códigos)
        self._doc_fonte_especial: Dict[str, FormatoResumo] = {}  # doc_id -> formato (para docs de fonte especial)
        self._docs_excluir_codigo: set = set()  # doc_ids que devem ser excluídos de categorias por código
        self._lote_preparado = False

    def _carregar_formatos(self):
        """Carrega todos os formatos do banco para cache"""
        if self._carregado:
            return

        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

        categorias = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.ativo == True
        ).all()

        for cat in categorias:
            formato = FormatoResumo(
                categoria_id=cat.id,
                categoria_nome=cat.nome,
                formato_json=cat.formato_json,
                instrucoes_extracao=cat.instrucoes_extracao,
                is_residual=cat.is_residual
            )

            if cat.is_residual:
                self._residual = formato
            elif cat.usa_fonte_especial:
                # Categoria com fonte especial - armazena separadamente
                from sistemas.gerador_pecas.services_source_resolver import get_source_resolver
                resolver = get_source_resolver()
                source_info = resolver.get_source_info(cat.source_special_type)
                codigos = source_info["codigos_validos"] if source_info else []
                self._fontes_especiais[cat.source_special_type] = (formato, codigos)
            else:
                # Categoria por código normal
                for codigo in (cat.codigos_documento or []):
                    self._cache[codigo] = formato

        self._carregado = True

    def preparar_lote(self, documentos: List[Any]) -> None:
        """
        Prepara o gerenciador para processar um lote de documentos.

        Identifica quais documentos pertencem a fontes especiais e marca-os
        para exclusão das categorias por código.

        IMPORTANTE: Chamar este método ANTES de iterar os documentos chamando obter_formato().

        Args:
            documentos: Lista de documentos (deve ter atributos 'id' e 'tipo_documento')
        """
        self._carregar_formatos()

        # Limpa estado anterior
        self._doc_fonte_especial.clear()
        self._docs_excluir_codigo.clear()
        self._lote_preparado = True

        if not self._fontes_especiais:
            return  # Sem fontes especiais configuradas

        from sistemas.gerador_pecas.services_source_resolver import (
            get_source_resolver, DocumentoInfo
        )

        # Converte documentos para formato do resolver
        docs_info = []
        for i, doc in enumerate(documentos):
            doc_id = str(getattr(doc, 'id', i))
            codigo_raw = getattr(doc, 'tipo_documento', None)
            data = getattr(doc, 'data', None)

            try:
                codigo = int(codigo_raw) if codigo_raw else 0
            except (ValueError, TypeError):
                codigo = 0

            docs_info.append(DocumentoInfo(
                id=doc_id,
                codigo=codigo,
                data=data,
                ordem=i
            ))

        # Resolve cada fonte especial
        resolver = get_source_resolver()
        for source_type, (formato, codigos) in self._fontes_especiais.items():
            result = resolver.resolve(source_type, docs_info)

            if result.sucesso and result.documento_id:
                # Documento encontrado para fonte especial
                self._doc_fonte_especial[result.documento_id] = formato
                self._docs_excluir_codigo.add(result.documento_id)
                print(f"[FONTE ESPECIAL] {source_type}: doc_id={result.documento_id} (categoria: {formato.categoria_nome})")

    def obter_formato(self, codigo_documento: int, doc_id: str = None) -> Optional[FormatoResumo]:
        """
        Obtém o formato para um documento.

        Args:
            codigo_documento: Código do tipo de documento
            doc_id: ID do documento (opcional, mas necessário para fontes especiais)

        Returns:
            FormatoResumo ou None
        """
        self._carregar_formatos()

        # Se doc_id fornecido e lote preparado, verifica fonte especial
        if doc_id and self._lote_preparado:
            doc_id_str = str(doc_id)

            # Verifica se é documento de fonte especial
            if doc_id_str in self._doc_fonte_especial:
                return self._doc_fonte_especial[doc_id_str]

            # Verifica se deve excluir de categoria por código
            # (documento foi identificado como fonte especial de outra categoria)
            if doc_id_str in self._docs_excluir_codigo:
                # Já retornou acima se era deste doc, então não deve processar
                # por categoria de código
                return self._residual  # Usa residual como fallback

        # Tenta cache específico por código
        if codigo_documento in self._cache:
            return self._cache[codigo_documento]

        # Retorna residual
        return self._residual

    def tem_formatos_configurados(self) -> bool:
        """Verifica se há formatos JSON configurados no banco"""
        self._carregar_formatos()
        return self._residual is not None or len(self._cache) > 0 or len(self._fontes_especiais) > 0
