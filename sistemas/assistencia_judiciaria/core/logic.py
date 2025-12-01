# sistemas/assistencia_judiciaria/core/logic.py
import os
import re
import json
import html
import logging
import requests
from datetime import datetime
from typing import Tuple, List, Dict, Any
from requests.adapters import HTTPAdapter, Retry
import xml.etree.ElementTree as ET

from config import (
    TJ_WSDL_URL, TJ_WS_USER, TJ_WS_PASS,
    OPENROUTER_ENDPOINT, DEFAULT_MODEL,
    STRICT_CNJ_CHECK, CLASSES_CUMPRIMENTO, NS
)
from database.connection import SessionLocal
from admin.models import PromptConfig, ConfiguracaoIA
from sqlalchemy.orm import Session

logger = logging.getLogger("sistemas.assistencia_judiciaria.core.logic")

def get_openrouter_api_key():
    """Busca a API key dinamicamente do ambiente ou banco de dados."""
    # Primeiro tenta do ambiente
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key:
        return api_key
    
    # Tenta buscar do banco de dados (configuração global)
    try:
        db = SessionLocal()
        config = db.query(ConfiguracaoIA).filter_by(sistema="global", chave="openrouter_api_key").first()
        if config and config.valor:
            db.close()
            return config.valor
        db.close()
    except:
        pass
    
    return ""

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def format_cnj(num: str) -> str:
    d = only_digits(num)
    if len(d) != 20:
        return num
    return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13:14]}.{d[14:16]}.{d[16:20]}"

def cnj_checksum_ok(d: str) -> bool:
    if len(d) != 20 or not d.isdigit():
        return False
    ano = int(d[9:13])
    return 1900 <= ano <= datetime.now().year + 1

def validate_config() -> Tuple[bool, str]:
    miss = []
    if not TJ_WSDL_URL: miss.append("TJ_WSDL_URL")
    if not TJ_WS_USER:  miss.append("TJ_WS_USER")
    if not TJ_WS_PASS:  miss.append("TJ_WS_PASS")
    
    api_key = get_openrouter_api_key()
    if not api_key or api_key == "SUA_CHAVE_AQUI":
        miss.append("OPENROUTER_API_KEY")
    if miss:
        return False, "Variáveis ausentes no config: " + ", ".join(miss)
    return True, "OK"

def validate_cnj(num: str) -> Tuple[bool, str, str]:
    d = only_digits(num)
    if len(d) != 20:
        return False, d, "Número CNJ deve conter 20 dígitos."
    if STRICT_CNJ_CHECK and not cnj_checksum_ok(d):
        return False, d, "Dígito/verificação do CNJ inválido."
    return True, d, "OK"

def soap_consultar_processo(session: requests.Session, numero_processo: str, timeout=90,
                            movimentos=True, incluir_docs=False, debug=False) -> str:
    envelope = f"""
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                      xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{html.escape(TJ_WS_USER)}</tip:idConsultante>
                <tip:senhaConsultante>{html.escape(TJ_WS_PASS)}</tip:senhaConsultante>
                <tip:numeroProcesso>{html.escape(numero_processo)}</tip:numeroProcesso>
                <tip:movimentos>{"true" if movimentos else "false"}</tip:movimentos>
                <tip:incluirDocumentos>{"true" if incluir_docs else "false"}</tip:incluirDocumentos>
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>
    """.strip()
    
    if debug:
        logger.debug("Enviando SOAP request...")
        
    r = session.post(TJ_WSDL_URL, data=envelope, timeout=timeout)
    r.raise_for_status()
    return r.text

def _text_of(elem: ET.Element) -> str:
    return (elem.text or "").strip() if elem is not None and elem.text else ""

def _pretty_esaj_dt(esaj_dt_str: str) -> str:
    if not esaj_dt_str:
        return esaj_dt_str
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$", esaj_dt_str)
    if m:
        try:
            dt = datetime(*map(int, m.groups()))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return esaj_dt_str

def has_apenso_hint(xml_text: str) -> bool:
    t = xml_text.casefold()
    return (" apenso" in t) or (" apensad" in t) or (" apensamento" in t)

def _tagname(e: ET.Element) -> str:
    return e.tag.split('}')[-1] if isinstance(e.tag, str) else str(e)

def _iter_desc_elems(elem: ET.Element, name_endswith: str):
    t = name_endswith.lower()
    for e in elem.iter():
        if _tagname(e).lower().endswith(t):
            yield e

def _all_texts(elem: ET.Element, name_endswith: str) -> List[str]:
    out: List[str] = []
    for e in _iter_desc_elems(elem, name_endswith):
        if e.text and e.text.strip():
            out.append(e.text.strip())
    return out

def parse_xml_processo(xml_text: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_text)
    data: Dict[str, Any] = {
        "classeProcessual": None,
        "cumprimento": False,
        "possivel_apenso": has_apenso_hint(xml_text),
        "partes": {"AT": [], "PA": []},
        "decisoes": [],
        "todos_complementos": []  # Todos os complementos extraídos das movimentações
    }

    dados_basicos = root.find(".//ns2:dadosBasicos", NS)
    if dados_basicos is not None:
        cls = dados_basicos.attrib.get("classeProcessual")
        data["classeProcessual"] = cls
        data["cumprimento"] = (cls in CLASSES_CUMPRIMENTO)

    for polo_node in root.findall(".//ns2:polo", NS):
        polo = polo_node.attrib.get("polo")
        if polo not in ("AT", "PA"):
            continue
        for parte in polo_node.findall("ns2:parte", NS):
            ajg = (parte.attrib.get("assistenciaJudiciaria", "").lower() == "true")
            pessoa = parte.find("ns2:pessoa", NS)
            if pessoa is not None:
                nome = pessoa.attrib.get("nome")
                if nome:
                    data["partes"][polo].append({"nome": nome, "assistenciaJudiciaria": ajg})

    movimentos = root.findall(".//ns2:movimento", NS)
    
    for mov in movimentos:
        cods: List[str] = []
        descrs: List[str] = []

        for ml in mov.findall("ns2:movimentoLocal", NS):
            c = ml.attrib.get("codigoPaiNacional")
            if c: cods.append(c)
            dsc = ml.attrib.get("descricao")
            if dsc: descrs.append(dsc)

            for mlp in ml.findall("ns2:movimentoLocalPai", NS):
                cp = mlp.attrib.get("codigoPaiNacional")
                if cp: cods.append(cp)
                dp = mlp.attrib.get("descricao")
                if dp: descrs.append(dp)

        if not cods:
            for anynode in mov.iter():
                if isinstance(anynode.tag, str) and "codigoPaiNacional" in getattr(anynode, "attrib", {}):
                    cods.append(anynode.attrib.get("codigoPaiNacional"))

        if not descrs:
            descrs = _all_texts(mov, "descricao")

        # Extrai TODOS os complementos desta movimentação
        complementos = _all_texts(mov, "complemento")
        complemento_txt = "\n---\n".join(complementos) if complementos else ""
        
        # Adiciona à lista global de complementos (para contexto da IA)
        dataHora = _pretty_esaj_dt(mov.attrib.get("dataHora"))
        for comp in complementos:
            if comp.strip():
                data["todos_complementos"].append({
                    "dataHora": dataHora,
                    "descricao": descrs[0] if descrs else None,
                    "texto": comp.strip()
                })

        if not descrs:
            continue

        codigo_principal = cods[0] if cods else None
        descricao_final = descrs[0] if descrs else None

        data["decisoes"].append({
            "codigoPaiNacional": codigo_principal,
            "descricao": descricao_final,
            "dataHora": dataHora,
            "complemento": complemento_txt
        })

    return data

def build_messages_for_llm(numero_cnj_fmt: str, dados: dict, db: Session = None) -> list:
    resumo_json = json.dumps(dados, ensure_ascii=False, indent=2)

    sys = (
        "Você é um assistente especializado em análise processual. "
        "Produza um RELATÓRIO claro, objetivo e formal, em linguagem própria da prática forense. "
        "IMPORTANTE: Responda SEMPRE em português brasileiro, utilizando a norma culta da língua portuguesa. "
        "REGRA CRÍTICA: Todo nome de pessoa/parte deve ter **asteriscos duplos** em volta. "
        "Evite termos técnicos de programação (como true/false, AT/PA). "
        "Use expressões jurídicas completas, como 'polo ativo' e 'polo passivo'. "
        "Ao tratar de prazos, indique se o pagamento é imediato ou ao final do processo. "
        "Não escreva Tribunal de Justiça por extenso, apenas TJ-MS."
    )

    user_template = """
<contexto>
Processo: {numero_cnj_fmt}

DADOS EVIDENCIAIS (JSON):
{resumo_json}
</contexto>

<tarefas>
1. **Identificação das Partes**
   - Apresente as partes separadas por polo processual, utilizando "polo ativo" e "polo passivo".
   - OBRIGATÓRIO: Para cada parte, coloque o nome entre **asteriscos duplos** seguido de dois pontos.
   - Indique, em linguagem natural, se cada parte consta no sistema do TJ-MS como beneficiária da justiça gratuita.
   - Formato obrigatório: **Nome da Parte**: Consta no sistema como beneficiária da justiça gratuita.

2. **Confirmação da Gratuidade da Justiça**
   - Esclareça, para cada parte, se o sistema do TJ-MS indica a gratuidade da justiça.
   - Verifique se há decisão nos autos que conceda a gratuidade e transcreva o trecho relevante entre aspas.
   - **IMPORTANTE - IDENTIFICAÇÃO DO BENEFICIÁRIO:**
     * Analise CUIDADOSAMENTE a descrição de cada decisão/despacho para identificar QUEM é o beneficiário da justiça gratuita.
     * Se houver DÚVIDA sobre quem é o beneficiário, indique explicitamente no relatório: "⚠️ REVISÃO NECESSÁRIA".
   - Para cada parte, use o formato: **Nome da Parte**: [informação sobre gratuidade do sistema] + [informação sobre decisão judicial].

3. **Análise das Decisões sobre Perícia**
   - Analise EXCLUSIVAMENTE as decisões e despachos que tratam de perícia.
   - Se não houver nenhuma decisão ou despacho tratando de perícia, informe claramente.
   - Para cada decisão pericial encontrada, indique:
     * Se houve designação de perícia (Sim/Não)
     * O valor arbitrado para honorários periciais, quando existente
     * Quem deve arcar com o pagamento dos honorários
     * O momento do pagamento
     * Transcreva o trecho relevante da decisão entre aspas
   - Realize a análise de conformidade com a TABELA de honorários periciais (Resolução CNJ n. 232/2016).

4. **Apenso em cumprimento de sentença**
   - Se o processo não for de cumprimento de sentença, mas houve indicação de apensamento, indique isso no relatório.
   - Caso o processo seja de cumprimento de sentença e haja indícios de apensamento, finalize o relatório com a advertência.
</tarefas>

<formato_de_saida>
A resposta deve ser redigida em **Markdown**, no formato de relatório jurídico estruturado em seções numeradas:

# Relatório - Processo XXXXXXX-XX.XXXX.X.XX.XXXX

## 1. Partes, Polos Processuais e Gratuidade da Justiça
...

## 2. Análise das Decisões sobre Perícia
...

## 3. Processos Apensados
...
</formato_de_saida>
"""

    # Try to fetch from DB
    if db:
        try:
            prompt_sys_db = db.query(PromptConfig).filter_by(sistema="assistencia_judiciaria", tipo="system").first()
            prompt_user_db = db.query(PromptConfig).filter_by(sistema="assistencia_judiciaria", tipo="relatorio").first()
            
            if prompt_sys_db:
                sys = prompt_sys_db.conteudo
            if prompt_user_db:
                user_template = prompt_user_db.conteudo
        except Exception as e:
            logger.error(f"Erro ao buscar prompts no banco: {e}")

    user = user_template.format(numero_cnj_fmt=numero_cnj_fmt, resumo_json=resumo_json)

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]

def call_openrouter(messages: list, model: str = DEFAULT_MODEL, temperature=0.2, timeout=120) -> str:
    api_key = get_openrouter_api_key()
    if not api_key:
        return "Erro: OPENROUTER_API_KEY não configurada."
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pge-ms.lab",
        "X-Title": "Relatório TJMS",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 20000,
    }
    
    logger.debug(f"Chamando OpenRouter com modelo {model}...")
    r = requests.post(OPENROUTER_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    j = r.json()

    try:
        message = j["choices"][0]["message"]
        content = message.get("content", "")
        if content and content.strip():
            return content
            
        reasoning = message.get("reasoning", "")
        if reasoning and reasoning.strip():
            return reasoning
            
        return "Erro: A API retornou uma resposta vazia."
    except Exception as e:
        logger.exception("Falha ao interpretar resposta da LLM")
        return f"Erro ao processar resposta da API: {str(e)}"

def full_flow(numero_raw: str, model: str, diagnostic_mode=False) -> Tuple[Dict[str, Any], str]:
    ok_config, msg_config = validate_config()
    if not ok_config:
        raise RuntimeError(f"Falha na configuração: {msg_config}")

    ok_cnj, d, msg_cnj = validate_cnj(numero_raw)
    if not ok_cnj:
        raise ValueError(f"CNJ inválido: {msg_cnj}")
    cnj_fmt = format_cnj(d)

    session = make_session()
    xml_text = soap_consultar_processo(session, d, timeout=90, movimentos=True, incluir_docs=False)
    
    dados = parse_xml_processo(xml_text)
    
    db = SessionLocal()
    try:
        # Check for model override in DB
        try:
            config_model = db.query(ConfiguracaoIA).filter_by(sistema="assistencia_judiciaria", chave="modelo").first()
            if config_model:
                model = config_model.valor
        except Exception as e:
            logger.error(f"Erro ao buscar config no banco: {e}")

        if diagnostic_mode:
            messages = [
                {"role": "system", "content": "Você é um analisador de sanidade. Responda sucintamente."},
                {"role": "user", "content": f"Teste: recebi JSON com AT={len(dados['partes']['AT'])}"}
            ]
        else:
            messages = build_messages_for_llm(cnj_fmt, dados, db)
    finally:
        db.close()

    rel = call_openrouter(messages, model=model)
    
    if dados.get("cumprimento") and dados.get("possivel_apenso"):
        rel += "\n\nAviso: Processo de cumprimento possivelmente apensado. Talvez seja necessário consultar o processo originário para confirmar a AJG."
        
    return dados, rel
