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
    descricao_documento: str = ""
) -> str:
    """
    Gera o prompt para extração de resumo em formato JSON.
    
    Args:
        formato: FormatoResumo com a estrutura esperada
        descricao_documento: Descrição do documento (se conhecida)
        
    Returns:
        Prompt completo para a IA
    """
    # Escapa chaves do JSON para não conflitar com .format()
    formato_json_escaped = formato.formato_json.replace("{", "{{").replace("}", "}}")
    instrucoes_escaped = (formato.instrucoes_extracao or "").replace("{", "{{").replace("}", "}}")
    descricao_escaped = descricao_documento.replace("{", "{{").replace("}", "}}")
    
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
Se o documento for meramente administrativo (procuração, AR de citação, comprovante de pagamento, 
documento pessoal, certidão de publicação, protocolo, etc), retorne apenas:
```json
{{"irrelevante": true, "motivo": "breve descrição do motivo"}}
```
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
    formato: FormatoResumo
) -> str:
    """
    Gera o prompt para extração de resumo JSON a partir de imagens (PDFs digitalizados).
    """
    # Escapa chaves do JSON para não conflitar com .format()
    formato_json_escaped = formato.formato_json.replace("{", "{{").replace("}", "}}")
    instrucoes_escaped = (formato.instrucoes_extracao or "").replace("{", "{{").replace("}", "}}")
    
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
Se for documento administrativo (procuração, RG, CPF, comprovante, AR, etc), retorne:
```json
{{"irrelevante": true, "motivo": "breve descrição"}}
```
"""

    if instrucoes_escaped:
        prompt += """
## INSTRUÇÕES ESPECÍFICAS:
""" + instrucoes_escaped + """
"""

    return prompt


def parsear_resposta_json(resposta: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parseia a resposta da IA e extrai o JSON.
    
    Args:
        resposta: Texto de resposta da IA
        
    Returns:
        Tupla (json_dict, erro) - erro é None se parse bem-sucedido
    """
    if not resposta:
        return {}, "Resposta vazia"
    
    resposta = resposta.strip()
    
    # Tenta extrair JSON de bloco de código markdown
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', resposta)
    if match:
        json_str = match.group(1).strip()
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
    
    try:
        resultado = json.loads(json_str)
        return resultado, None
    except json.JSONDecodeError as e:
        return {}, f"Erro ao parsear JSON: {e}"


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
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[int, FormatoResumo] = {}
        self._residual: Optional[FormatoResumo] = None
        self._carregado = False
    
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
            else:
                for codigo in (cat.codigos_documento or []):
                    self._cache[codigo] = formato
        
        self._carregado = True
    
    def obter_formato(self, codigo_documento: int) -> Optional[FormatoResumo]:
        """Obtém o formato para um código de documento (usa cache)"""
        self._carregar_formatos()
        
        # Tenta cache específico
        if codigo_documento in self._cache:
            return self._cache[codigo_documento]
        
        # Retorna residual
        return self._residual
    
    def tem_formatos_configurados(self) -> bool:
        """Verifica se há formatos JSON configurados no banco"""
        self._carregar_formatos()
        return self._residual is not None or len(self._cache) > 0
