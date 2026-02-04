# sistemas/cumprimento_beta/services_geracao_peca.py
"""
Serviço de geração de peças jurídicas para o módulo Cumprimento de Sentença Beta.

Gera peças em Markdown e converte para DOCX, mantendo o mesmo padrão
do gerador normal.
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, ConsolidacaoBeta, ConversaBeta, PecaGeradaBeta
)
from sistemas.cumprimento_beta.constants import (
    StatusSessao, ConfigKeys, MODELO_PADRAO_CHATBOT, MAX_TOKENS_RESPOSTA
)
from sistemas.cumprimento_beta.exceptions import GeracaoPecaError
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async
from sistemas.gerador_pecas.docx_converter import markdown_to_docx

logger = logging.getLogger(__name__)


# Diretório para arquivos DOCX
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp_docs')
os.makedirs(TEMP_DIR, exist_ok=True)


# Prompt para geração de peça
PROMPT_GERACAO_PECA = """Você é um procurador do Estado de Mato Grosso do Sul especializado em cumprimento de sentença.

Gere uma peça jurídica do tipo: **{tipo_peca}**

## Contexto do Processo

**Processo:** {numero_processo}

{resumo_processo}

{dados_adicionais}

## Instruções do Usuário

{instrucoes_usuario}

## Diretrizes para a Peça

1. Use formatação adequada para documento jurídico
2. Inclua todos os elementos necessários:
   - Endereçamento ao juízo
   - Qualificação das partes
   - Fundamentação fática e jurídica
   - Pedidos
   - Requerimentos finais
3. Use linguagem formal e técnica
4. Cite legislação e jurisprudência quando pertinente
5. Seja objetivo e fundamentado

## Formato

Gere a peça em Markdown com a seguinte estrutura:
- Cabeçalho com endereçamento
- Preâmbulo com qualificação
- Corpo com seções numeradas
- Pedidos em lista
- Fechamento com data e assinatura

Gere APENAS a peça, sem comentários adicionais.
"""


class GeracaoPecaService:
    """Serviço para geração de peças jurídicas"""

    def __init__(self, db: Session):
        self.db = db
        self._modelo = self._carregar_modelo()

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.MODELO_CHATBOT
            ).first()

            if config and config.valor:
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        return MODELO_PADRAO_CHATBOT

    def _montar_resumo_processo(self, sessao: SessaoCumprimentoBeta) -> str:
        """Monta resumo do processo para o prompt"""
        consolidacao = self.db.query(ConsolidacaoBeta).filter(
            ConsolidacaoBeta.sessao_id == sessao.id
        ).first()

        if consolidacao:
            return consolidacao.resumo_consolidado

        return "Informações do processo não disponíveis."

    def _montar_dados_adicionais(self, sessao: SessaoCumprimentoBeta) -> str:
        """Monta dados adicionais (partes, valores, etc.)"""
        consolidacao = self.db.query(ConsolidacaoBeta).filter(
            ConsolidacaoBeta.sessao_id == sessao.id
        ).first()

        if not consolidacao or not consolidacao.dados_processo:
            return ""

        dados = consolidacao.dados_processo
        partes = []

        if dados.get("exequente"):
            partes.append(f"**Exequente:** {dados['exequente']}")
        if dados.get("executado"):
            partes.append(f"**Executado:** {dados['executado']}")
        if dados.get("valor_execucao"):
            partes.append(f"**Valor da Execução:** {dados['valor_execucao']}")
        if dados.get("objeto"):
            partes.append(f"**Objeto:** {dados['objeto']}")

        if partes:
            return "## Dados do Processo\n\n" + "\n".join(partes)

        return ""

    async def gerar_peca(
        self,
        sessao: SessaoCumprimentoBeta,
        tipo_peca: str,
        instrucoes_adicionais: Optional[str] = None,
        conversa_id: Optional[int] = None
    ) -> PecaGeradaBeta:
        """
        Gera uma peça jurídica.

        Args:
            sessao: Sessão do beta
            tipo_peca: Tipo da peça a gerar
            instrucoes_adicionais: Instruções extras do usuário
            conversa_id: ID da conversa que originou o pedido

        Returns:
            PecaGeradaBeta criada
        """
        logger.info(f"[BETA] Gerando peça '{tipo_peca}' para sessão {sessao.id}")

        # Atualiza status
        sessao.status = StatusSessao.GERANDO_PECA
        self.db.commit()

        # Monta prompt
        prompt = PROMPT_GERACAO_PECA.format(
            tipo_peca=tipo_peca,
            numero_processo=sessao.numero_processo_formatado or sessao.numero_processo,
            resumo_processo=self._montar_resumo_processo(sessao),
            dados_adicionais=self._montar_dados_adicionais(sessao),
            instrucoes_usuario=instrucoes_adicionais or "Gere a peça conforme as melhores práticas jurídicas."
        )

        inicio = time.time()

        try:
            # Gera conteúdo
            conteudo_markdown = await chamar_gemini_async(
                prompt=prompt,
                modelo=self._modelo,
                max_tokens=MAX_TOKENS_RESPOSTA
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Gera título
            titulo = self._gerar_titulo(tipo_peca, sessao.numero_processo)

            # Converte para DOCX
            docx_path = None
            try:
                docx_filename = f"peca_beta_{sessao.id}_{int(time.time())}.docx"
                docx_path = os.path.join(TEMP_DIR, docx_filename)
                markdown_to_docx(conteudo_markdown, docx_path)
                logger.info(f"[BETA] DOCX gerado: {docx_path}")
            except Exception as e:
                logger.warning(f"[BETA] Erro ao gerar DOCX: {e}")
                docx_path = None

            # Cria registro
            peca = PecaGeradaBeta(
                sessao_id=sessao.id,
                conversa_id=conversa_id,
                tipo_peca=tipo_peca,
                titulo=titulo,
                conteudo_markdown=conteudo_markdown,
                conteudo_docx_path=docx_path,
                instrucoes_usuario=instrucoes_adicionais,
                modelo_usado=self._modelo,
                tempo_geracao_ms=tempo_ms
            )

            self.db.add(peca)

            # Atualiza status da sessão
            sessao.status = StatusSessao.CHATBOT
            self.db.commit()
            self.db.refresh(peca)

            logger.info(f"[BETA] Peça gerada em {tempo_ms}ms: {len(conteudo_markdown)} chars")

            return peca

        except Exception as e:
            logger.error(f"[BETA] Erro ao gerar peça: {e}")
            sessao.status = StatusSessao.CHATBOT
            self.db.commit()
            raise GeracaoPecaError(f"Falha ao gerar peça: {e}")

    def _gerar_titulo(self, tipo_peca: str, numero_processo: str) -> str:
        """Gera título para a peça"""
        tipo_formatado = tipo_peca.upper()
        return f"{tipo_formatado} - Processo {numero_processo}"


async def gerar_peca(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    tipo_peca: str,
    instrucoes: Optional[str] = None,
    conversa_id: Optional[int] = None
) -> PecaGeradaBeta:
    """Função auxiliar para gerar peça"""
    service = GeracaoPecaService(db)
    return await service.gerar_peca(sessao, tipo_peca, instrucoes, conversa_id)


def obter_peca(db: Session, peca_id: int) -> Optional[PecaGeradaBeta]:
    """Obtém uma peça pelo ID"""
    return db.query(PecaGeradaBeta).filter(
        PecaGeradaBeta.id == peca_id
    ).first()


def listar_pecas_sessao(db: Session, sessao_id: int) -> list:
    """Lista peças de uma sessão"""
    return db.query(PecaGeradaBeta).filter(
        PecaGeradaBeta.sessao_id == sessao_id
    ).order_by(
        PecaGeradaBeta.created_at.desc()
    ).all()
