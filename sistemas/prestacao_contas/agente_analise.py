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

    # Valores extraídos
    valor_bloqueado: Optional[float] = None
    valor_utilizado: Optional[float] = None
    valor_devolvido: Optional[float] = None
    medicamento_pedido: Optional[str] = None
    medicamento_comprado: Optional[str] = None

    # Se desfavorável
    irregularidades: Optional[List[str]] = None

    # Se dúvida
    perguntas: Optional[List[str]] = None
    contexto_duvida: Optional[str] = None

    # Metadados
    modelo_usado: Optional[str] = None
    tokens_usados: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "parecer": self.parecer,
            "fundamentacao": self.fundamentacao,
            "valor_bloqueado": self.valor_bloqueado,
            "valor_utilizado": self.valor_utilizado,
            "valor_devolvido": self.valor_devolvido,
            "medicamento_pedido": self.medicamento_pedido,
            "medicamento_comprado": self.medicamento_comprado,
            "irregularidades": self.irregularidades,
            "perguntas": self.perguntas,
            "contexto_duvida": self.contexto_duvida,
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

Com base nos documentos acima, responda em formato JSON:

```json
{{
  "parecer": "favoravel" | "desfavoravel" | "duvida",
  "fundamentacao": "Texto em markdown explicando a análise e conclusão",
  "valor_bloqueado": número ou null,
  "valor_utilizado": número ou null,
  "valor_devolvido": número ou null,
  "medicamento_pedido": "nome do medicamento pedido" ou null,
  "medicamento_comprado": "nome do medicamento comprado" ou null,
  "irregularidades": ["lista de irregularidades"] ou null (se desfavorável),
  "perguntas": ["lista de perguntas ao usuário"] ou null (se dúvida),
  "contexto_duvida": "explicação do que precisa ser esclarecido" ou null (se dúvida)
}}
```

IMPORTANTE:
- Seja objetivo e fundamentado
- Extraia os valores monetários quando possível
- Se não conseguir determinar algo, use null
- A fundamentação deve ser clara e em markdown"""


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

            # Parse do JSON da resposta
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
        """Parse da resposta JSON da IA - suporta estrutura aninhada ou flat"""
        import unicodedata

        def normalizar_parecer(p: str) -> str:
            p = p.lower()
            return ''.join(c for c in unicodedata.normalize('NFD', p) if unicodedata.category(c) != 'Mn')

        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', resposta, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', resposta, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("JSON nao encontrado na resposta")

            dados = json.loads(json_str)

            if "analise_juridica" in dados:
                analise = dados["analise_juridica"]
                parecer_raw = analise.get("parecer_final") or analise.get("parecer") or "duvida"
                parecer = normalizar_parecer(parecer_raw)

                bloqueio = analise.get("identificacao_bloqueio", {})
                utilizacao = analise.get("utilizacao_recursos", {})
                aderencia = analise.get("aderencia_pedido", {})

                return ResultadoAnalise(
                    parecer=parecer,
                    fundamentacao=analise.get("fundamentacao", "Analise nao disponivel"),
                    valor_bloqueado=bloqueio.get("valor_total_bloqueado"),
                    valor_utilizado=utilizacao.get("valor_comprovado_gasto"),
                    valor_devolvido=utilizacao.get("valor_remanescente_subconta"),
                    medicamento_pedido=aderencia.get("compatibilidade_tratamento"),
                    medicamento_comprado=aderencia.get("correspondencia_medicamento_servico"),
                    irregularidades=analise.get("irregularidades"),
                    perguntas=analise.get("perguntas"),
                    contexto_duvida=analise.get("contexto_duvida"),
                )
            else:
                parecer_raw = dados.get("parecer_final") or dados.get("parecer") or "duvida"
                parecer = normalizar_parecer(parecer_raw)

                return ResultadoAnalise(
                    parecer=parecer,
                    fundamentacao=dados.get("fundamentacao", "Analise nao disponivel"),
                    valor_bloqueado=dados.get("valor_bloqueado"),
                    valor_utilizado=dados.get("valor_utilizado"),
                    valor_devolvido=dados.get("valor_devolvido"),
                    medicamento_pedido=dados.get("medicamento_pedido"),
                    medicamento_comprado=dados.get("medicamento_comprado"),
                    irregularidades=dados.get("irregularidades"),
                    perguntas=dados.get("perguntas"),
                    contexto_duvida=dados.get("contexto_duvida"),
                )

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON: {e}")
            return ResultadoAnalise(
                parecer="duvida",
                fundamentacao=resposta,
                perguntas=["A resposta da IA nao pode ser processada. Revise manualmente."],
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

Com base nas respostas do usuário, emita um parecer final. Responda no mesmo formato JSON anterior."""

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
