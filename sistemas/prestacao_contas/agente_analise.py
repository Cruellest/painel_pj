# sistemas/prestacao_contas/agente_analise.py
"""
Agente de Análise de Prestação de Contas

Analisa os documentos coletados e emite parecer sobre a regularidade
da prestação de contas em processos de medicamentos.

Autor: LAB/PGE-MS
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal, Union

from sqlalchemy.orm import Session

from sistemas.prestacao_contas.ia_logger import IALogger, LogEntry
from services.ia_params_resolver import get_ia_params, IAParams

logger = logging.getLogger(__name__)


# =====================================================
# FUNÇÕES UTILITÁRIAS DE EXTRAÇÃO (ROBUSTAS)
# =====================================================

def safe_str(value: Any) -> Optional[str]:
    """
    Extrai string de qualquer tipo de dado de forma segura.
    Retorna None se não conseguir extrair texto útil.
    """
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        return text if text else None

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, dict):
        # Tenta extrair de chaves comuns em ordem de prioridade
        for key in ["texto", "text", "descricao", "description", "nome", "name",
                    "valor", "value", "observacao", "observacoes", "finalidade",
                    "fundamentacao", "justificativa", "conteudo", "content"]:
            if key in value:
                result = safe_str(value[key])
                if result:
                    return result
        return None

    if isinstance(value, list):
        # Junta itens de lista
        parts = [safe_str(item) for item in value]
        valid_parts = [p for p in parts if p]
        return ", ".join(valid_parts) if valid_parts else None

    return None


def safe_float(value: Any) -> Optional[float]:
    """
    Extrai float de qualquer tipo de dado de forma segura.
    Retorna None se não conseguir extrair número válido.
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value) if value != 0 or isinstance(value, float) else None

    if isinstance(value, str):
        # Remove formatação brasileira
        text = value.replace("R$", "").replace(" ", "").strip()
        if not text:
            return None
        # Remove pontos de milhar e troca vírgula por ponto
        text = text.replace(".", "").replace(",", ".")
        try:
            result = float(text)
            return result if result != 0 else None
        except (ValueError, TypeError):
            return None

    if isinstance(value, dict):
        # Tenta extrair de chaves comuns
        for key in ["valor", "value", "amount", "total", "quantia", "montante"]:
            if key in value:
                result = safe_float(value[key])
                if result is not None:
                    return result
        return None

    return None


def format_currency(value: Any) -> Optional[str]:
    """
    Formata valor como moeda brasileira.
    Retorna None se valor não for válido.
    """
    num = safe_float(value)
    if num is None:
        return None
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def safe_get(data: Any, *keys, default=None):
    """
    Acessa chaves aninhadas de forma segura.
    safe_get(data, "a", "b", "c") equivale a data.get("a", {}).get("b", {}).get("c")
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default
    return result


def normalize_parecer(value: Any) -> str:
    """
    Normaliza qualquer valor para um parecer válido.
    Sempre retorna 'favoravel', 'desfavoravel' ou 'duvida'.
    """
    text = safe_str(value) or ""
    text = text.lower()

    # Remove acentos
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')

    # Mapeia para valores válidos (ordem importa!)
    if 'parcialmente regular' in text or 'parcialmente_regular' in text:
        return 'duvida'
    if 'favoravel' in text or text == 'regular':
        return 'favoravel'
    if 'desfavoravel' in text or 'irregular' in text:
        return 'desfavoravel'

    return 'duvida'


# =====================================================
# BUSCA DE PROMPTS
# =====================================================

def _buscar_prompt_admin(db: Session, nome: str) -> Optional[str]:
    """Busca um prompt configurado no admin."""
    if not db:
        return None

    try:
        from admin.models import PromptConfig

        prompt_config = db.query(PromptConfig).filter(
            PromptConfig.sistema == "prestacao_contas",
            PromptConfig.nome == nome,
            PromptConfig.is_active == True
        ).first()

        if prompt_config and prompt_config.conteudo:
            return prompt_config.conteudo

    except Exception as e:
        logger.warning(f"Erro ao buscar prompt '{nome}' do admin: {e}")

    return None


# =====================================================
# DATACLASSES
# =====================================================

@dataclass
class DadosAnalise:
    """Dados de entrada para análise"""
    extrato_subconta: str = ""
    peticao_inicial: str = ""
    peticao_prestacao: str = ""
    documentos_anexos: List[Dict[str, str]] = field(default_factory=list)
    peticoes_contexto: List[Dict[str, str]] = field(default_factory=list)
    extrato_observacao: Optional[str] = None  # Observação quando extrato não localizado


@dataclass
class ResultadoAnalise:
    """Resultado da análise de prestação de contas"""
    parecer: Literal["favoravel", "desfavoravel", "duvida"]
    fundamentacao: str

    irregularidades: Optional[List[str]] = None
    perguntas: Optional[List[str]] = None
    contexto_duvida: Optional[str] = None
    valor_bloqueado: Optional[float] = None
    valor_utilizado: Optional[float] = None
    valor_devolvido: Optional[float] = None
    medicamento_pedido: Optional[str] = None
    medicamento_comprado: Optional[str] = None
    modelo_usado: Optional[str] = None
    tokens_usados: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "parecer": self.parecer,
            "fundamentacao": self.fundamentacao,
            "irregularidades": self.irregularidades,
            "perguntas": self.perguntas,
            "contexto_duvida": self.contexto_duvida,
            "valor_bloqueado": self.valor_bloqueado,
            "valor_utilizado": self.valor_utilizado,
            "valor_devolvido": self.valor_devolvido,
            "medicamento_pedido": self.medicamento_pedido,
            "medicamento_comprado": self.medicamento_comprado,
            "modelo_usado": self.modelo_usado,
            "tokens_usados": self.tokens_usados,
        }


# =====================================================
# PROMPTS PADRÃO
# =====================================================

SYSTEM_PROMPT = """Você é um analista jurídico especializado em prestação de contas de processos judiciais de medicamentos.

Sua função é analisar documentos de prestação de contas e emitir um parecer sobre a regularidade da utilização dos valores bloqueados judicialmente para aquisição de medicamentos.

CRITÉRIOS DE ANÁLISE:

1. ORIGEM DOS RECURSOS
   - Verificar no extrato da subconta se os valores são provenientes de bloqueio judicial contra o Estado de Mato Grosso do Sul
   - Confirmar que são recursos públicos

2. UTILIZAÇÃO INTEGRAL OU DEVOLUÇÃO
   - Comparar valor bloqueado/levantado com valor efetivamente gasto
   - Verificar se houve devolução de saldo excedente
   - Identificar se há saldo remanescente não utilizado

3. ADERÊNCIA AO PEDIDO INICIAL
   - O medicamento comprado corresponde ao pedido na petição inicial?
   - A quantidade adquirida é compatível com o tratamento autorizado?
   - O período de uso/tratamento foi respeitado?

4. DOCUMENTAÇÃO COMPROBATÓRIA
   - Notas fiscais estão legíveis e identificáveis?
   - Os valores nas notas conferem com o declarado?
   - Há recibos ou comprovantes de pagamento?

5. VERIFICAÇÃO DE MEDICAMENTOS - REGRA OBRIGATÓRIA
   ⚠️ ANTES de afirmar que um medicamento "não consta na lista autorizada", você DEVE:

   a) BUSCAR NA INTERNET o princípio ativo do medicamento encontrado na nota fiscal
   b) COMPARAR o princípio ativo com os medicamentos autorizados na decisão judicial
   c) Medicamentos com NOMES COMERCIAIS diferentes podem ter o MESMO princípio ativo

   EXEMPLOS DE EQUIVALÊNCIAS COMUNS:
   - Nourin = Cloridrato de Oxibutinina (NÃO é Fenilefrina!)
   - Retemic = Cloridrato de Oxibutinina
   - Ponstan = Ácido Mefenâmico
   - Tylenol = Paracetamol

   ⚠️ NUNCA afirme que um medicamento é "não autorizado" sem antes confirmar via busca
   ⚠️ Se o princípio ativo for o mesmo, os medicamentos são EQUIVALENTES e AUTORIZADOS

PARECERES POSSÍVEIS:

- FAVORÁVEL: Prestação de contas regular, valores utilizados corretamente
- DESFAVORÁVEL: Irregularidades identificadas (listar quais)
- DÚVIDA: Informações insuficientes para conclusão (formular perguntas específicas)

Seja objetivo e fundamentado em sua análise."""


PROMPT_ANALISE = """Analise a prestação de contas abaixo e emita um parecer.

## EXTRATO DA SUBCONTA (Valores bloqueados judicialmente)
{extrato_subconta}

## PETIÇÃO INICIAL (O que foi pedido)
{peticao_inicial}

## PETIÇÃO DE PRESTAÇÃO DE CONTAS
{peticao_prestacao}

## OUTRAS PETIÇÕES RELEVANTES
{peticoes_contexto}

## DOCUMENTOS ANEXOS (Notas fiscais, comprovantes)
{documentos_anexos}

---

Com base nos documentos acima, responda EXATAMENTE neste formato:

PARECER: [FAVORAVEL ou DESFAVORAVEL ou DUVIDA]

---FUNDAMENTACAO---
[Escreva aqui sua análise completa em Markdown, incluindo:
- Resumo dos valores identificados (bloqueado, utilizado, devolvido)
- Medicamento solicitado vs adquirido
- Análise da documentação comprobatória
- Conclusão fundamentada]

---IRREGULARIDADES---
[Se DESFAVORAVEL, liste as irregularidades uma por linha. Se não houver, escreva "Nenhuma"]

---PERGUNTAS---
[Se DUVIDA, liste as perguntas que precisam ser respondidas uma por linha. Se não houver, escreva "Nenhuma"]

IMPORTANTE:
- Use o formato acima EXATAMENTE como especificado
- A fundamentação deve ser detalhada e em Markdown
- Seja objetivo e fundamentado na análise

⚠️ REGRA CRÍTICA SOBRE MEDICAMENTOS:
Antes de afirmar que um medicamento da nota fiscal "não está autorizado", você DEVE:
1. Usar Google Search para descobrir o PRINCÍPIO ATIVO do medicamento
2. Verificar se algum medicamento autorizado tem o MESMO princípio ativo
3. Se o princípio ativo for igual, o medicamento É AUTORIZADO (são equivalentes)

Exemplo: Se a nota tem "Nourin 5mg" e a inicial pede "Oxibutinina 5mg":
- Busque: "Nourin 5mg princípio ativo"
- Resultado: Nourin = Cloridrato de Oxibutinina
- Conclusão: Nourin É EQUIVALENTE a Oxibutinina = AUTORIZADO"""


# =====================================================
# AGENTE DE ANÁLISE
# =====================================================

class AgenteAnalise:
    """Agente de IA para análise de prestação de contas."""

    def __init__(
        self,
        modelo: str = None,
        temperatura: float = None,
        ia_logger: Optional[IALogger] = None,
        db: Session = None,
        usar_busca_google: bool = True  # Habilita busca na internet para verificar medicamentos
    ):
        self.db = db
        self.ia_logger = ia_logger
        self.usar_busca_google = usar_busca_google

        # Usa resolver de parâmetros por agente
        if db:
            self._params = get_ia_params(db, "prestacao_contas", "analise")
        else:
            # Fallback para valores padrão se não houver db
            self._params = IAParams(
                modelo="gemini-3-flash-preview",
                temperatura=0.3,
                max_tokens=None,
                sistema="prestacao_contas",
                agente="analise"
            )

        self.modelo = modelo or self._params.modelo
        self.temperatura = temperatura if temperatura is not None else self._params.temperatura
        self.system_prompt = _buscar_prompt_admin(db, "system_prompt_analise") or SYSTEM_PROMPT
        self.prompt_analise = _buscar_prompt_admin(db, "prompt_analise") or PROMPT_ANALISE

    def _substituir_placeholders(self, template: str, **kwargs) -> str:
        """Substitui placeholders sem usar .format() para evitar conflito com JSON."""
        resultado = template
        for chave, valor in kwargs.items():
            placeholder = "{" + chave + "}"
            resultado = resultado.replace(placeholder, str(valor))
        return resultado

    async def analisar(self, dados: DadosAnalise) -> ResultadoAnalise:
        """Analisa a prestação de contas e emite parecer."""
        from services.gemini_service import GeminiService

        # Formata petições de contexto
        peticoes_contexto_texto = ""
        logger.warning(f"{'='*60}")
        logger.warning(f"AGENTE: Recebeu peticoes_contexto com {len(dados.peticoes_contexto)} itens")
        if dados.peticoes_contexto:
            for i, pet in enumerate(dados.peticoes_contexto, 1):
                tipo_pet = pet.get('tipo', 'Petição')
                texto_pet = pet.get('texto', '[Sem conteúdo]')
                logger.warning(f"  {i}. {tipo_pet} ({len(texto_pet)} chars)")
                peticoes_contexto_texto += f"\n### {i}. {tipo_pet}\n{texto_pet}\n"
        else:
            logger.warning("AGENTE: peticoes_contexto está VAZIO!")
            peticoes_contexto_texto = "[Nenhuma petição de contexto adicional]"
        logger.warning(f"{'='*60}")

        # Coleta imagens dos documentos anexos
        todas_imagens = []
        docs_descricao = ""

        if dados.documentos_anexos:
            for i, doc in enumerate(dados.documentos_anexos, 1):
                tipo_doc = doc.get('tipo', 'Documento')
                imagens = doc.get('imagens', [])

                if imagens:
                    docs_descricao += f"\n### Documento {i}: {tipo_doc} ({len(imagens)} página(s) - ver imagens anexas)\n"
                    todas_imagens.extend(imagens)
                else:
                    docs_descricao += f"\n### Documento {i}: {tipo_doc}\n"
                    docs_descricao += doc.get('texto', '[Sem conteúdo]')
                    docs_descricao += "\n"
        else:
            docs_descricao = "[Nenhum documento anexo encontrado]"

        if todas_imagens:
            docs_descricao += f"\n\n**ATENÇÃO:** {len(todas_imagens)} imagem(ns) de documentos anexos estão anexadas a esta mensagem. Analise-as cuidadosamente para verificar notas fiscais, recibos e comprovantes."

        # Monta texto do extrato (com observação se não disponível)
        if dados.extrato_subconta:
            extrato_texto = dados.extrato_subconta
        elif dados.extrato_observacao:
            extrato_texto = f"[EXTRATO NÃO DISPONÍVEL]\n\n{dados.extrato_observacao}"
        else:
            extrato_texto = "[Extrato não disponível]"

        # Monta prompt
        prompt = self._substituir_placeholders(
            self.prompt_analise,
            extrato_subconta=extrato_texto,
            peticao_inicial=dados.peticao_inicial or "[Petição inicial não encontrada]",
            peticao_prestacao=dados.peticao_prestacao or "[Petição de prestação não encontrada]",
            peticoes_contexto=peticoes_contexto_texto,
            documentos_anexos=docs_descricao,
        )

        # Log
        logger.info(f"=== PROMPT PARA IA ===")
        logger.info(f"  Extrato subconta: {len(dados.extrato_subconta)} chars")
        logger.info(f"  Petição inicial: {len(dados.peticao_inicial)} chars")
        logger.info(f"  Petição prestação: {len(dados.peticao_prestacao)} chars")
        logger.info(f"  Petições contexto: {len(peticoes_contexto_texto)} chars")
        logger.info(f"  Documentos anexos: {len(todas_imagens)} imagens")
        logger.info(f"  TOTAL prompt: {len(prompt)} chars")

        log_entry = None
        if self.ia_logger:
            log_entry = self.ia_logger.log_chamada("analise_final", "Análise de prestação de contas")
            log_entry.set_prompt(prompt)
            log_entry.set_modelo(self.modelo)

        try:
            service = GeminiService()
            
            # Contexto para logging
            log_context = {
                "sistema": "prestacao_contas",
                "modulo": "agente_analise",
            }

            if todas_imagens:
                logger.info(f"Enviando {len(todas_imagens)} imagens para análise")
                if self.usar_busca_google:
                    logger.info("🔍 Google Search habilitado para verificar medicamentos")
                    resposta_obj = await service.generate_with_images_and_search(
                        prompt=prompt,
                        images_base64=todas_imagens,
                        model=self.modelo,
                        temperature=self.temperatura,
                        system_prompt=self.system_prompt,
                        search_threshold=0.2,  # Limiar baixo = mais buscas
                        context=log_context,
                    )
                else:
                    resposta_obj = await service.generate_with_images(
                        prompt=prompt,
                        images_base64=todas_imagens,
                        model=self.modelo,
                        temperature=self.temperatura,
                        system_prompt=self.system_prompt,
                        context=log_context,
                    )
            else:
                if self.usar_busca_google:
                    logger.info("🔍 Google Search habilitado para verificar medicamentos")
                    resposta_obj = await service.generate_with_search(
                        prompt=prompt,
                        system_prompt=self.system_prompt,
                        model=self.modelo,
                        temperature=self.temperatura,
                        search_threshold=0.2,
                        context=log_context,
                    )
                else:
                    resposta_obj = await service.generate(
                        prompt=prompt,
                        system_prompt=self.system_prompt,
                        model=self.modelo,
                        temperature=self.temperatura,
                        context=log_context,
                    )

            if not resposta_obj.success:
                raise Exception(resposta_obj.error or "Erro na chamada da IA")

            resposta = resposta_obj.content

            if log_entry:
                log_entry.set_resposta(resposta)

            resultado = self._parse_resposta(resposta)
            resultado.modelo_usado = self.modelo
            resultado.tokens_usados = resposta_obj.tokens_used

            return resultado

        except Exception as e:
            logger.error(f"Erro na análise: {e}")
            if log_entry:
                log_entry.set_erro(str(e))

            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=f"Não foi possível realizar a análise automática devido a um erro: {str(e)}",
                perguntas=["Por favor, revise os documentos manualmente e forneça mais informações."],
                contexto_duvida=f"Erro no processamento: {str(e)}",
            )

    def _construir_fundamentacao(self, dados: dict, resposta_bruta: str = "") -> str:
        """
        Constrói fundamentação a partir de dados JSON.
        Usa as funções utilitárias seguras para extrair valores.
        Suporta estruturas complexas e aninhadas.
        """
        if not isinstance(dados, dict):
            return resposta_bruta if resposta_bruta else "Dados não estruturados"

        partes = []

        # === FORMATO v3 (estrutura complexa com markdown) ===

        # Conclusão - tenta múltiplas chaves possíveis
        conclusao = safe_get(dados, "conclusao") or {}
        if isinstance(conclusao, dict):
            # Prioriza fundamentacao_markdown sobre fundamentacao
            fund = (
                safe_str(conclusao.get("fundamentacao_markdown")) or
                safe_str(conclusao.get("fundamentacao")) or
                safe_str(conclusao.get("analise"))
            )
            if fund and len(fund) > 20:
                # Se já tem markdown formatado, usa direto
                partes.append(fund)

            # Pontos determinantes
            pontos = conclusao.get("pontos_determinantes") or []
            if isinstance(pontos, list) and pontos and not fund:
                pontos_texto = []
                for p in pontos:
                    if isinstance(p, dict):
                        ponto = safe_str(p.get("ponto"))
                        motivo = safe_str(p.get("por_que_importa"))
                        if ponto:
                            pontos_texto.append(f"**{ponto}:** {motivo}" if motivo else ponto)
                if pontos_texto:
                    partes.append("**Pontos Determinantes:**\n" + "\n".join(f"- {p}" for p in pontos_texto))

        # Identificação do bloqueio (se não veio na conclusão)
        if not partes:
            id_bloqueio = safe_get(dados, "identificacao_bloqueio") or {}
            if isinstance(id_bloqueio, dict):
                info = []
                processo = safe_str(id_bloqueio.get("processo"))
                if processo:
                    info.append(f"Processo: {processo}")
                orgao = safe_str(id_bloqueio.get("orgao_judicial"))
                if orgao:
                    info.append(f"Órgão: {orgao}")
                valor = format_currency(id_bloqueio.get("valor_bloqueado"))
                if valor:
                    info.append(f"Valor: R$ {valor}")
                # Finalidade pode ser string ou dict
                finalidade = safe_str(id_bloqueio.get("finalidade")) or safe_str(id_bloqueio.get("finalidade_bloqueio"))
                if finalidade:
                    info.append(f"Finalidade: {finalidade}")
                # Decisão
                decisao = safe_str(safe_get(id_bloqueio, "decisao_que_determinou_bloqueio", "resumo"))
                if decisao:
                    info.append(f"Decisão: {decisao}")
                if info:
                    partes.append("**Identificação do Bloqueio:**\n" + "\n".join(f"- {i}" for i in info))

        # Gastos comprovados
        gastos = safe_get(dados, "gastos_comprovados") or []
        if isinstance(gastos, list) and gastos:
            itens_gastos = []
            for g in gastos:
                if isinstance(g, dict):
                    item = safe_str(g.get("item")) or safe_str(g.get("descricao")) or ""
                    valor = format_currency(safe_get(g, "documento_fiscal", "valor"))
                    vinculo = safe_get(g, "vinculo_com_objeto_do_bloqueio") or {}
                    aderente = vinculo.get("aderente")
                    status = "✓" if aderente is True else "✗" if aderente is False else "?"
                    if item:
                        texto = f"{status} {item}"
                        if valor:
                            texto += f" - R$ {valor}"
                        just = safe_str(vinculo.get("justificativa"))
                        if just and aderente is False:
                            texto += f" ({just})"
                        itens_gastos.append(texto)
            if itens_gastos:
                partes.append("**Gastos Comprovados:**\n" + "\n".join(f"- {i}" for i in itens_gastos))

        # Conciliação financeira
        conciliacao = safe_get(dados, "conciliacao_financeira") or {}
        if isinstance(conciliacao, dict):
            info_conc = []
            total = format_currency(conciliacao.get("total_gastos_comprovados"))
            if total:
                info_conc.append(f"Total comprovado: R$ {total}")
            # Pendências
            pendencias = conciliacao.get("pendencias_ou_inconsistencias") or []
            if isinstance(pendencias, list):
                for p in pendencias:
                    if isinstance(p, dict):
                        desc = safe_str(p.get("descricao"))
                        if desc:
                            info_conc.append(f"⚠️ {desc}")
            if info_conc:
                partes.append("**Conciliação Financeira:**\n" + "\n".join(f"- {i}" for i in info_conc))

        # Saldo remanescente
        saldo = safe_get(dados, "saldo_remanescente") or {}
        if isinstance(saldo, dict):
            existe = saldo.get("existe")
            explicacao = safe_str(saldo.get("explicacao"))
            if existe is True:
                valor_saldo = format_currency(saldo.get("valor"))
                if valor_saldo:
                    partes.append(f"**Saldo Remanescente:** R$ {valor_saldo}")
            elif existe is False:
                partes.append("**Saldo Remanescente:** Não há saldo remanescente")
            elif explicacao:
                partes.append(f"**Saldo Remanescente:** {explicacao}")

        # Recomendações (pode ser string ou array de objetos)
        recomendacoes = safe_get(dados, "recomendacoes")
        if isinstance(recomendacoes, list) and recomendacoes:
            itens_rec = []
            for r in recomendacoes:
                if isinstance(r, dict):
                    acao = safe_str(r.get("acao")) or ""
                    detalhe = safe_str(r.get("detalhamento")) or ""
                    if detalhe:
                        itens_rec.append(detalhe)
                    elif acao:
                        itens_rec.append(acao.replace("_", " ").title())
                elif isinstance(r, str):
                    itens_rec.append(r)
            if itens_rec:
                partes.append("**Recomendações:**\n" + "\n".join(f"- {i}" for i in itens_rec))
        elif isinstance(recomendacoes, str) and len(recomendacoes) > 10:
            partes.append(f"**Recomendações:** {recomendacoes}")

        # === FORMATO v1 (antigo - analise_juridica) ===
        if not partes:
            analise = safe_get(dados, "analise_juridica") or dados

            # Parecer final
            justificativa = safe_str(safe_get(analise, "parecer_final", "justificativa"))
            if not justificativa:
                justificativa = safe_str(safe_get(analise, "parecer_final", "fundamentacao"))
            if justificativa:
                partes.append(f"**Conclusão:** {justificativa}")

            # Seções de análise
            for chave, titulo in [
                ("origem_recursos", "Origem dos Recursos"),
                ("utilizacao_recursos", "Utilização dos Recursos"),
                ("aderencia_pedido", "Aderência ao Pedido"),
                ("documentacao_comprovatoria", "Documentação Comprobatória"),
            ]:
                texto = safe_str(safe_get(analise, chave, "fundamentacao"))
                if not texto:
                    texto = safe_str(safe_get(analise, chave, "analise"))
                if texto and len(texto) > 20:
                    partes.append(f"**{titulo}:** {texto}")

        # === FALLBACK: Extração recursiva ===
        if not partes:
            texto = self._extrair_texto_recursivo(dados)
            if texto and len(texto) > 50:
                partes.append(texto)

        # === ÚLTIMO FALLBACK: Resposta bruta ===
        if not partes and resposta_bruta:
            texto_limpo = re.sub(r'```json\s*', '', resposta_bruta)
            texto_limpo = re.sub(r'```\s*', '', texto_limpo)
            return texto_limpo.strip()

        return "\n\n".join(partes) if partes else "Análise processada - verifique os dados estruturados"

    def _extrair_texto_recursivo(self, obj: Any) -> str:
        """Extrai texto de qualquer estrutura de forma recursiva."""
        if isinstance(obj, str):
            return obj.strip()

        if isinstance(obj, (int, float, bool)):
            return str(obj)

        if isinstance(obj, list):
            textos = [self._extrair_texto_recursivo(item) for item in obj]
            return "\n".join(t for t in textos if t)

        if isinstance(obj, dict):
            partes = []
            prioridade = ["justificativa", "fundamentacao", "analise", "conclusao", "observacao", "descricao", "texto"]

            for chave in prioridade:
                if chave in obj and obj[chave]:
                    val = safe_str(obj[chave])
                    if val and len(val) > 20:
                        partes.append(val)

            if not partes:
                for chave, valor in obj.items():
                    val = safe_str(valor)
                    if val and len(val) > 30:
                        partes.append(f"**{chave.replace('_', ' ').title()}:** {val}")

            return "\n\n".join(partes)

        return ""

    def _parse_resposta(self, resposta: str) -> ResultadoAnalise:
        """Parse da resposta da IA. Suporta Markdown e JSON."""

        def extrair_lista(texto: str) -> Optional[List[str]]:
            if not texto or texto.strip().lower() == 'nenhuma':
                return None
            linhas = [l.strip() for l in texto.strip().split('\n') if l.strip()]
            itens = []
            for linha in linhas:
                linha = re.sub(r'^[-*•]\s*', '', linha)
                linha = re.sub(r'^\d+[.)]\s*', '', linha)
                if linha and linha.lower() != 'nenhuma':
                    itens.append(linha)
            return itens if itens else None

        # Tenta formato Markdown estruturado
        parecer_match = re.search(r'PARECER:\s*\[?([^\]\n]+)\]?', resposta, re.IGNORECASE)
        fund_match = re.search(r'---FUNDAMENTACAO---\s*(.*?)(?=---IRREGULARIDADES---|---PERGUNTAS---|$)', resposta, re.DOTALL | re.IGNORECASE)
        irreg_match = re.search(r'---IRREGULARIDADES---\s*(.*?)(?=---PERGUNTAS---|$)', resposta, re.DOTALL | re.IGNORECASE)
        perg_match = re.search(r'---PERGUNTAS---\s*(.*?)$', resposta, re.DOTALL | re.IGNORECASE)

        if parecer_match and fund_match:
            return ResultadoAnalise(
                parecer=normalize_parecer(parecer_match.group(1)),
                fundamentacao=fund_match.group(1).strip(),
                irregularidades=extrair_lista(irreg_match.group(1)) if irreg_match else None,
                perguntas=extrair_lista(perg_match.group(1)) if perg_match else None,
            )

        # Fallback: JSON
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', resposta, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    return ResultadoAnalise(
                        parecer="duvida",
                        fundamentacao=resposta,
                        perguntas=["Formato de resposta não reconhecido. Revise manualmente."],
                    )

            dados = json.loads(json_str)

            # Extrai parecer (v3 > v2 > v1 > outros)
            parecer_raw = (
                safe_str(safe_get(dados, "conclusao", "classificacao")) or
                safe_str(safe_get(dados, "analise_juridica", "parecer_final", "resultado")) or
                safe_str(safe_get(dados, "parecer_final", "resultado")) or
                safe_str(safe_get(dados, "parecer_final")) or
                safe_str(safe_get(dados, "parecer")) or
                "duvida"
            )

            # Extrai fundamentação (v3 com markdown > v2 > v1)
            fundamentacao = (
                safe_str(safe_get(dados, "conclusao", "fundamentacao_markdown")) or
                safe_str(safe_get(dados, "conclusao", "fundamentacao")) or
                safe_str(safe_get(dados, "analise_juridica", "parecer_final", "justificativa")) or
                safe_str(safe_get(dados, "parecer_final", "justificativa")) or
                safe_str(safe_get(dados, "fundamentacao"))
            )

            # Se não encontrou ou é muito curta, constrói a partir dos dados
            if not fundamentacao or len(fundamentacao) < 50:
                fundamentacao = self._construir_fundamentacao(dados, resposta)

            # Extrai valores numéricos
            valor_bloqueado = (
                safe_float(safe_get(dados, "identificacao_bloqueio", "valor_bloqueado")) or
                safe_float(safe_get(dados, "conciliacao_financeira", "valor_bloqueado")) or
                safe_float(safe_get(dados, "analise_juridica", "origem_recursos", "valor_bloqueado")) or
                safe_float(safe_get(dados, "valor_bloqueado"))
            )

            # Valor utilizado - soma dos gastos comprovados ou valor direto
            valor_utilizado = (
                safe_float(safe_get(dados, "conciliacao_financeira", "total_gastos_comprovados")) or
                safe_float(safe_get(dados, "analise_juridica", "utilizacao_recursos", "valor_total_gasto")) or
                safe_float(safe_get(dados, "valor_utilizado"))
            )

            saldo_rem = safe_get(dados, "saldo_remanescente") or {}
            valor_devolvido = None
            if isinstance(saldo_rem, dict) and saldo_rem.get("existe"):
                valor_devolvido = safe_float(saldo_rem.get("valor"))
            if valor_devolvido is None:
                valor_devolvido = safe_float(safe_get(dados, "valor_devolvido"))

            # Extrai medicamentos/finalidade
            medicamento_pedido = (
                safe_str(safe_get(dados, "medicamento_pedido")) or
                safe_str(safe_get(dados, "identificacao_bloqueio", "finalidade_bloqueio", "descricao")) or
                safe_str(safe_get(dados, "identificacao_bloqueio", "finalidade")) or
                safe_str(safe_get(dados, "identificacao_bloqueio", "decisao_que_determinou_bloqueio", "resumo"))
            )

            # Medicamento comprado - tenta extrair do primeiro gasto comprovado
            medicamento_comprado = safe_str(safe_get(dados, "medicamento_comprado"))
            if not medicamento_comprado:
                gastos = safe_get(dados, "gastos_comprovados") or []
                if isinstance(gastos, list) and gastos:
                    itens = [safe_str(g.get("item")) for g in gastos if isinstance(g, dict)]
                    itens = [i for i in itens if i]
                    if itens:
                        medicamento_comprado = ", ".join(itens[:3])  # Máximo 3 itens
                        if len(itens) > 3:
                            medicamento_comprado += f" (+{len(itens)-3} itens)"

            return ResultadoAnalise(
                parecer=normalize_parecer(parecer_raw),
                fundamentacao=fundamentacao,
                irregularidades=dados.get("irregularidades") if isinstance(dados.get("irregularidades"), list) else None,
                perguntas=dados.get("perguntas") if isinstance(dados.get("perguntas"), list) else None,
                contexto_duvida=safe_str(safe_get(dados, "contexto_duvida")),
                valor_bloqueado=valor_bloqueado,
                valor_utilizado=valor_utilizado,
                valor_devolvido=valor_devolvido,
                medicamento_pedido=medicamento_pedido,
                medicamento_comprado=medicamento_comprado,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON: {e}")
            texto_limpo = re.sub(r'```[a-z]*\s*', '', resposta)
            texto_limpo = re.sub(r'```\s*', '', texto_limpo).strip()

            parecer = "duvida"
            texto_lower = texto_limpo.lower()
            if "favorável" in texto_lower or "favoravel" in texto_lower:
                parecer = "favoravel"
            elif "desfavorável" in texto_lower or "desfavoravel" in texto_lower or "irregular" in texto_lower:
                parecer = "desfavoravel"

            return ResultadoAnalise(
                parecer=parecer,
                fundamentacao=texto_limpo if texto_limpo else resposta,
            )
        except Exception as e:
            logger.error(f"Erro inesperado no parse: {e}")
            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=resposta if resposta else f"Erro no processamento: {str(e)}",
            )

    async def reanalisar_com_respostas(
        self,
        dados: DadosAnalise,
        perguntas_respostas: Dict[str, str]
    ) -> ResultadoAnalise:
        """Reanalisa com respostas do usuário às perguntas de dúvida."""
        from services.gemini_service import GeminiService

        qa_texto = "\n".join([
            f"**Pergunta:** {p}\n**Resposta:** {r}"
            for p, r in perguntas_respostas.items()
        ])

        prompt = f"""Na análise anterior, foram feitas perguntas ao usuário. Com base nas respostas, reavalie a prestação de contas.

## PERGUNTAS E RESPOSTAS DO USUÁRIO
{qa_texto}

## DADOS ORIGINAIS

### Extrato da Subconta
{dados.extrato_subconta or "[Não disponível]"}

### Petição Inicial
{dados.peticao_inicial or "[Não disponível]"}

### Petição de Prestação de Contas
{dados.peticao_prestacao or "[Não disponível]"}

---

Com base nas respostas do usuário, emita um parecer final.

Responda EXATAMENTE neste formato:

PARECER: [FAVORAVEL ou DESFAVORAVEL ou DUVIDA]

---FUNDAMENTACAO---
[Sua análise em Markdown]

---IRREGULARIDADES---
[Lista ou "Nenhuma"]

---PERGUNTAS---
[Lista ou "Nenhuma"]"""

        log_entry = None
        if self.ia_logger:
            log_entry = self.ia_logger.log_chamada("reanalise_com_respostas", "Reanálise com respostas do usuário")
            log_entry.set_prompt(prompt)
            log_entry.set_modelo(self.modelo)

        try:
            service = GeminiService()
            resposta_obj = await service.generate(
                prompt=prompt,
                system_prompt=self.system_prompt,
                model=self.modelo,
                temperature=self.temperatura,
            )

            if not resposta_obj.success:
                raise Exception(resposta_obj.error or "Erro na chamada da IA")

            resposta = resposta_obj.content

            if log_entry:
                log_entry.set_resposta(resposta)

            resultado = self._parse_resposta(resposta)
            resultado.modelo_usado = self.modelo
            resultado.tokens_usados = resposta_obj.tokens_used
            return resultado

        except Exception as e:
            logger.error(f"Erro na reanálise: {e}")
            if log_entry:
                log_entry.set_erro(str(e))

            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=f"Não foi possível realizar a reanálise: {str(e)}",
                perguntas=["Por favor, revise os documentos manualmente."],
            )


# =====================================================
# FUNÇÃO DE CONVENIÊNCIA
# =====================================================

async def analisar_prestacao_contas(
    extrato_subconta: str,
    peticao_inicial: str,
    peticao_prestacao: str,
    documentos_anexos: List[Dict[str, str]],
    modelo: str = "gemini-3-flash-preview",
    temperatura: float = 0.3,
    ia_logger: Optional[IALogger] = None,
    db: Session = None,
    usar_busca_google: bool = True,
) -> ResultadoAnalise:
    """Função de conveniência para analisar prestação de contas."""
    dados = DadosAnalise(
        extrato_subconta=extrato_subconta,
        peticao_inicial=peticao_inicial,
        peticao_prestacao=peticao_prestacao,
        documentos_anexos=documentos_anexos,
    )

    agente = AgenteAnalise(
        modelo=modelo,
        temperatura=temperatura,
        ia_logger=ia_logger,
        db=db,
        usar_busca_google=usar_busca_google,
    )

    return await agente.analisar(dados)
