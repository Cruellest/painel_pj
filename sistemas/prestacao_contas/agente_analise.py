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
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal

from sqlalchemy.orm import Session

from sistemas.prestacao_contas.ia_logger import IALogger, LogEntry

logger = logging.getLogger(__name__)


def _buscar_prompt_admin(db: Session, nome: str) -> Optional[str]:
    """
    Busca um prompt configurado no admin.

    Args:
        db: Sessão do banco de dados
        nome: Nome do prompt (ex: 'system_prompt_analise', 'prompt_analise')

    Returns:
        Conteúdo do prompt ou None se não encontrar
    """
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


@dataclass
class DadosAnalise:
    """Dados de entrada para análise"""
    extrato_subconta: str = ""
    peticao_inicial: str = ""
    peticao_prestacao: str = ""
    documentos_anexos: List[Dict[str, str]] = field(default_factory=list)
    peticoes_contexto: List[Dict[str, str]] = field(default_factory=list)  # [{id, tipo, texto}]


@dataclass
class ResultadoAnalise:
    """Resultado da análise de prestação de contas"""
    parecer: Literal["favoravel", "desfavoravel", "duvida"]
    fundamentacao: str  # Markdown

    # Se desfavorável
    irregularidades: Optional[List[str]] = None

    # Se dúvida
    perguntas: Optional[List[str]] = None
    contexto_duvida: Optional[str] = None
    valor_bloqueado: Optional[float] = None
    valor_utilizado: Optional[float] = None
    valor_devolvido: Optional[float] = None
    medicamento_pedido: Optional[str] = None
    medicamento_comprado: Optional[str] = None


    # Metadados
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
# PROMPTS
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
- Seja objetivo e fundamentado na análise"""


class AgenteAnalise:
    """
    Agente de IA para análise de prestação de contas.
    Os prompts são buscados do painel admin ou usados os padrões.
    """

    def __init__(
        self,
        modelo: str = "gemini-3-flash-preview",
        temperatura: float = 0.3,
        ia_logger: Optional[IALogger] = None,
        db: Session = None
    ):
        """
        Args:
            modelo: Modelo de IA a ser usado
            temperatura: Temperatura para geração
            ia_logger: Logger de chamadas de IA
            db: Sessão do banco para buscar prompts do admin
        """
        self.modelo = modelo
        self.temperatura = temperatura
        self.ia_logger = ia_logger
        self.db = db

        # Busca prompts do admin ou usa padrões
        self.system_prompt = _buscar_prompt_admin(db, "system_prompt_analise") or SYSTEM_PROMPT
        self.prompt_analise = _buscar_prompt_admin(db, "prompt_analise") or PROMPT_ANALISE

    async def analisar(self, dados: DadosAnalise) -> ResultadoAnalise:
        """
        Analisa a prestação de contas e emite parecer.

        Args:
            dados: Dados de entrada para análise

        Returns:
            ResultadoAnalise com parecer e fundamentação
        """
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
                    # Documento com imagens
                    docs_descricao += f"\n### Documento {i}: {tipo_doc} ({len(imagens)} página(s) - ver imagens anexas)\n"
                    todas_imagens.extend(imagens)
                else:
                    # Documento com texto (fallback)
                    docs_descricao += f"\n### Documento {i}: {tipo_doc}\n"
                    docs_descricao += doc.get('texto', '[Sem conteúdo]')
                    docs_descricao += "\n"
        else:
            docs_descricao = "[Nenhum documento anexo encontrado]"

        # Adiciona instruções sobre as imagens no prompt
        if todas_imagens:
            docs_descricao += f"\n\n**ATENÇÃO:** {len(todas_imagens)} imagem(ns) de documentos anexos estão anexadas a esta mensagem. Analise-as cuidadosamente para verificar notas fiscais, recibos e comprovantes."

        # Monta prompt (usa prompt do admin ou padrão)
        prompt = self.prompt_analise.format(
            extrato_subconta=dados.extrato_subconta or "[Extrato não disponível]",
            peticao_inicial=dados.peticao_inicial or "[Petição inicial não encontrada]",
            peticao_prestacao=dados.peticao_prestacao or "[Petição de prestação não encontrada]",
            peticoes_contexto=peticoes_contexto_texto,
            documentos_anexos=docs_descricao,
        )

        # Log do tamanho do prompt
        logger.info(f"=== PROMPT PARA IA ===")
        logger.info(f"  Extrato subconta: {len(dados.extrato_subconta)} chars")
        logger.info(f"  Petição inicial: {len(dados.peticao_inicial)} chars")
        logger.info(f"  Petição prestação: {len(dados.peticao_prestacao)} chars")
        logger.info(f"  Petições contexto: {len(peticoes_contexto_texto)} chars ({len(dados.peticoes_contexto)} docs)")
        logger.info(f"  Documentos anexos: {len(todas_imagens)} imagens")
        logger.info(f"  TOTAL prompt: {len(prompt)} chars")

        # Log da chamada
        log_entry = None
        if self.ia_logger:
            log_entry = self.ia_logger.log_chamada("analise_final", "Análise de prestação de contas")
            log_entry.set_prompt(prompt)
            log_entry.set_modelo(self.modelo)

        try:
            service = GeminiService()

            # Usa generate_with_images se houver imagens, senão usa generate
            if todas_imagens:
                logger.info(f"Enviando {len(todas_imagens)} imagens para análise")
                resposta_obj = await service.generate_with_images(
                    prompt=prompt,
                    images_base64=todas_imagens,
                    model=self.modelo,
                    temperature=self.temperatura,
                    system_prompt=self.system_prompt,
                )
            else:
                resposta_obj = await service.generate(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                    model=self.modelo,
                    temperature=self.temperatura,
                )

            # Extrai conteúdo do GeminiResponse
            if not resposta_obj.success:
                raise Exception(resposta_obj.error or "Erro na chamada da IA")

            resposta = resposta_obj.content

            # Log da resposta
            if log_entry:
                log_entry.set_resposta(resposta)

            # Parse da resposta (Markdown ou JSON)
            resultado = self._parse_resposta(resposta)
            resultado.modelo_usado = self.modelo
            resultado.tokens_usados = resposta_obj.tokens_used

            return resultado

        except Exception as e:
            logger.error(f"Erro na análise: {e}")
            if log_entry:
                log_entry.set_erro(str(e))

            # Retorna resultado de dúvida em caso de erro
            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=f"Não foi possível realizar a análise automática devido a um erro: {str(e)}",
                perguntas=["Por favor, revise os documentos manualmente e forneça mais informações."],
                contexto_duvida=f"Erro no processamento: {str(e)}",
            )

    def _parse_resposta(self, resposta: str) -> ResultadoAnalise:
        """
        Parse da resposta da IA.
        Suporta formato Markdown estruturado ou JSON (fallback).
        """
        import unicodedata

        def normalizar_parecer(p) -> str:
            """Normaliza o parecer para formato padrão"""
            # Se for dict, tenta extrair valor
            if isinstance(p, dict):
                p = p.get('valor') or p.get('parecer') or p.get('resultado') or 'duvida'

            # Garante que é string
            p = str(p).lower().strip()

            # Remove acentos
            p = ''.join(c for c in unicodedata.normalize('NFD', p) if unicodedata.category(c) != 'Mn')

            # Mapeia para valores válidos
            if 'favoravel' in p or 'regular' in p:
                return 'favoravel'
            elif 'desfavoravel' in p or 'irregular' in p:
                return 'desfavoravel'
            else:
                return 'duvida'

        def extrair_lista(texto: str) -> Optional[List[str]]:
            """Extrai lista de itens de um texto"""
            if not texto or texto.strip().lower() == 'nenhuma':
                return None

            linhas = [l.strip() for l in texto.strip().split('\n') if l.strip()]
            # Remove marcadores de lista
            itens = []
            for linha in linhas:
                linha = re.sub(r'^[-*•]\s*', '', linha)
                linha = re.sub(r'^\d+[.)]\s*', '', linha)
                if linha and linha.lower() != 'nenhuma':
                    itens.append(linha)

            return itens if itens else None

        # Tenta extrair formato Markdown estruturado
        parecer_match = re.search(r'PARECER:\s*\[?([^\]\n]+)\]?', resposta, re.IGNORECASE)
        fund_match = re.search(r'---FUNDAMENTACAO---\s*(.*?)(?=---IRREGULARIDADES---|---PERGUNTAS---|$)', resposta, re.DOTALL | re.IGNORECASE)
        irreg_match = re.search(r'---IRREGULARIDADES---\s*(.*?)(?=---PERGUNTAS---|$)', resposta, re.DOTALL | re.IGNORECASE)
        perg_match = re.search(r'---PERGUNTAS---\s*(.*?)$', resposta, re.DOTALL | re.IGNORECASE)

        if parecer_match and fund_match:
            # Formato Markdown encontrado
            parecer = normalizar_parecer(parecer_match.group(1))
            fundamentacao = fund_match.group(1).strip()
            irregularidades = extrair_lista(irreg_match.group(1)) if irreg_match else None
            perguntas = extrair_lista(perg_match.group(1)) if perg_match else None

            return ResultadoAnalise(
                parecer=parecer,
                fundamentacao=fundamentacao,
                irregularidades=irregularidades,
                perguntas=perguntas,
            )

        # Fallback: tenta JSON
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', resposta, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # Nenhum formato reconhecido - usa resposta como fundamentação
                    return ResultadoAnalise(
                        parecer="duvida",
                        fundamentacao=resposta,
                        perguntas=["Formato de resposta não reconhecido. Revise manualmente."],
                    )

            dados = json.loads(json_str)

            # Extrai parecer com tratamento robusto
            parecer_raw = dados.get("parecer_final") or dados.get("parecer") or "duvida"
            parecer = normalizar_parecer(parecer_raw)

            return ResultadoAnalise(
                parecer=parecer,
                fundamentacao=dados.get("fundamentacao", "Análise não disponível"),
                irregularidades=dados.get("irregularidades"),
                perguntas=dados.get("perguntas"),
                contexto_duvida=dados.get("contexto_duvida"),
                valor_bloqueado=dados.get("valor_bloqueado"),
                valor_utilizado=dados.get("valor_utilizado"),
                valor_devolvido=dados.get("valor_devolvido"),
                medicamento_pedido=dados.get("medicamento_pedido"),
                medicamento_comprado=dados.get("medicamento_comprado"),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON: {e}")
            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=resposta,
                perguntas=["A resposta da IA não pode ser processada. Revise manualmente."],
            )

    async def reanalisar_com_respostas(
        self,
        dados: DadosAnalise,
        perguntas_respostas: Dict[str, str]
    ) -> ResultadoAnalise:
        """
        Reanalisa com respostas do usuário às perguntas de dúvida.

        Args:
            dados: Dados originais da análise
            perguntas_respostas: Dict com pergunta -> resposta do usuário

        Returns:
            ResultadoAnalise atualizado
        """
        from services.gemini_service import GeminiService

        # Formata perguntas e respostas
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

            # Extrai conteúdo do GeminiResponse
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


async def analisar_prestacao_contas(
    extrato_subconta: str,
    peticao_inicial: str,
    peticao_prestacao: str,
    documentos_anexos: List[Dict[str, str]],
    modelo: str = "gemini-3-flash-preview",
    temperatura: float = 0.3,
    ia_logger: Optional[IALogger] = None,
    db: Session = None,
) -> ResultadoAnalise:
    """
    Função de conveniência para analisar prestação de contas.

    Args:
        extrato_subconta: Texto do extrato da subconta
        peticao_inicial: Texto da petição inicial
        peticao_prestacao: Texto da petição de prestação de contas
        documentos_anexos: Lista de documentos anexos [{tipo, texto}]
        modelo: Modelo de IA
        temperatura: Temperatura
        ia_logger: Logger de IA
        db: Sessão do banco para buscar prompts do admin

    Returns:
        ResultadoAnalise
    """
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
    )

    return await agente.analisar(dados)
