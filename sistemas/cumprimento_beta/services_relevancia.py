# sistemas/cumprimento_beta/services_relevancia.py
"""
Serviço de avaliação de relevância de documentos para o módulo beta.

Usa o prompt "Critérios de Relevância de Documentos" configurado em /admin/prompts-config
para classificar cada documento como relevante ou irrelevante.
"""

import json
import logging
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import SessaoCumprimentoBeta, DocumentoBeta
from sistemas.cumprimento_beta.constants import (
    StatusSessao, StatusRelevancia, ConfigKeys,
    MODELO_PADRAO_AGENTE1, TIMEOUT_AVALIACAO_RELEVANCIA
)
from sistemas.cumprimento_beta.exceptions import PromptNaoEncontradoError, GeminiError
from sistemas.gerador_pecas.extrator_resumo_json import obter_criterios_relevancia
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async

logger = logging.getLogger(__name__)


# Prompt para avaliação de relevância
PROMPT_AVALIACAO_RELEVANCIA = """Você é um assistente jurídico especializado em avaliar relevância de documentos.

Analise o documento abaixo e determine se ele é RELEVANTE ou IRRELEVANTE para um processo de cumprimento de sentença.

{criterios_relevancia}

## DOCUMENTO A AVALIAR

**Tipo:** {tipo_documento}
**Data:** {data_documento}

**Conteúdo:**
{conteudo}

## RESPOSTA

Responda APENAS com um JSON no formato:
```json
{{
  "relevante": true ou false,
  "motivo": "breve explicação da classificação"
}}
```
"""


class RelevanciaService:
    """Serviço para avaliação de relevância de documentos"""

    def __init__(self, db: Session):
        self.db = db
        self._modelo = self._carregar_modelo()
        self._criterios = self._carregar_criterios_relevancia()

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado para o Agente 1"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == "modelo_agente1"
            ).first()

            if config and config.valor:
                logger.info(f"[BETA] Modelo Agente 1 carregado: {config.valor}")
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        logger.info(f"[BETA] Usando modelo padrão: {MODELO_PADRAO_AGENTE1}")
        return MODELO_PADRAO_AGENTE1

    def _carregar_criterios_relevancia(self) -> str:
        """Carrega critérios de relevância do admin"""
        criterios = obter_criterios_relevancia(self.db)
        logger.info("[BETA] Critérios de relevância carregados do admin")
        return criterios

    async def avaliar_documento(
        self,
        documento: DocumentoBeta
    ) -> Tuple[bool, str]:
        """
        Avalia se um documento é relevante.

        Args:
            documento: Documento a avaliar

        Returns:
            Tuple (é_relevante, motivo)
        """
        # Se não tem conteúdo, marca como irrelevante
        if not documento.conteudo_texto or len(documento.conteudo_texto.strip()) < 50:
            return False, "Documento sem conteúdo textual suficiente"

        # Monta prompt
        prompt = PROMPT_AVALIACAO_RELEVANCIA.format(
            criterios_relevancia=self._criterios,
            tipo_documento=documento.descricao_documento or f"Código {documento.codigo_documento}",
            data_documento=documento.data_documento.strftime("%d/%m/%Y") if documento.data_documento else "Não informada",
            conteudo=documento.conteudo_texto[:10000]  # Limita tamanho
        )

        try:
            # Chama Gemini
            resposta = await chamar_gemini_async(
                prompt=prompt,
                modelo=self._modelo
            )

            # Extrai JSON da resposta
            resultado = self._extrair_json_resposta(resposta)

            if resultado:
                relevante = resultado.get("relevante", False)
                motivo = resultado.get("motivo", "Sem motivo informado")

                # Registra modelo usado
                documento.modelo_avaliacao = self._modelo

                return relevante, motivo

            # Se não conseguiu extrair JSON, considera irrelevante
            return False, "Não foi possível avaliar automaticamente"

        except Exception as e:
            logger.error(f"[BETA] Erro ao avaliar documento {documento.id}: {e}")
            return False, f"Erro na avaliação: {str(e)}"

    def _extrair_json_resposta(self, resposta: str) -> Optional[dict]:
        """Extrai JSON da resposta do Gemini"""
        if not resposta:
            return None

        try:
            # Tenta encontrar JSON na resposta
            import re

            # Procura por bloco ```json
            match = re.search(r'```json\s*(\{.*?\})\s*```', resposta, re.DOTALL)
            if match:
                return json.loads(match.group(1))

            # Procura por JSON direto
            match = re.search(r'\{[^{}]*"relevante"[^{}]*\}', resposta, re.DOTALL)
            if match:
                return json.loads(match.group(0))

            # Tenta parsear resposta inteira
            return json.loads(resposta.strip())

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[BETA] Erro ao extrair JSON: {e}")
            return None

    async def avaliar_documentos_sessao(
        self,
        sessao: SessaoCumprimentoBeta,
        on_progress: Optional[callable] = None
    ) -> Tuple[int, int]:
        """
        Avalia relevância de todos os documentos pendentes de uma sessão.

        Args:
            sessao: Sessão do beta
            on_progress: Callback para progresso

        Returns:
            Tuple (relevantes, irrelevantes)
        """
        # Busca documentos pendentes (não ignorados)
        documentos = self.db.query(DocumentoBeta).filter(
            DocumentoBeta.sessao_id == sessao.id,
            DocumentoBeta.status_relevancia == StatusRelevancia.PENDENTE
        ).all()

        if not documentos:
            logger.info(f"[BETA] Nenhum documento pendente para avaliar na sessão {sessao.id}")
            return 0, 0

        logger.info(f"[BETA] Avaliando relevância de {len(documentos)} documentos")

        # Atualiza status da sessão
        sessao.status = StatusSessao.AVALIANDO_RELEVANCIA
        self.db.commit()

        relevantes = 0
        irrelevantes = 0

        for idx, doc in enumerate(documentos):
            # Callback de progresso
            if on_progress:
                await on_progress(
                    etapa="avaliando_relevancia",
                    atual=idx + 1,
                    total=len(documentos),
                    mensagem=f"Avaliando documento {idx + 1}/{len(documentos)}"
                )

            # Avalia documento
            eh_relevante, motivo = await self.avaliar_documento(doc)

            # Atualiza documento
            if eh_relevante:
                doc.status_relevancia = StatusRelevancia.RELEVANTE
                relevantes += 1
                sessao.documentos_relevantes += 1
            else:
                doc.status_relevancia = StatusRelevancia.IRRELEVANTE
                doc.motivo_irrelevancia = motivo
                irrelevantes += 1
                sessao.documentos_irrelevantes += 1

            doc.avaliado_em = datetime.utcnow()

            # Commit parcial a cada 5 documentos
            if (idx + 1) % 5 == 0:
                self.db.commit()

        # Commit final
        self.db.commit()

        logger.info(
            f"[BETA] Avaliação concluída: {relevantes} relevantes, {irrelevantes} irrelevantes"
        )

        return relevantes, irrelevantes


async def avaliar_relevancia_sessao(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    on_progress: Optional[callable] = None
) -> Tuple[int, int]:
    """
    Função auxiliar para avaliar relevância de documentos de uma sessão.

    Args:
        db: Sessão do banco de dados
        sessao: Sessão do beta
        on_progress: Callback para progresso

    Returns:
        Tuple (relevantes, irrelevantes)
    """
    service = RelevanciaService(db)
    return await service.avaliar_documentos_sessao(sessao, on_progress)
