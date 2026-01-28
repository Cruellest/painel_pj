# sistemas/cumprimento_beta/services_chatbot.py
"""
Serviço de chatbot para o módulo Cumprimento de Sentença Beta.

Funcionalidades:
- Histórico de conversa persistido
- Integração com banco vetorial para busca de argumentos
- Prompt de sistema configurável via admin
- Streaming de respostas
"""

import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime
from sqlalchemy.orm import Session

from admin.models import ConfiguracaoIA
from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, ConsolidacaoBeta, ConversaBeta
)
from sistemas.cumprimento_beta.constants import (
    StatusSessao, RoleChat, ConfigKeys,
    MODELO_PADRAO_CHATBOT, TIMEOUT_CHATBOT, MAX_MENSAGENS_CONTEXTO
)
from sistemas.cumprimento_beta.exceptions import CumprimentoBetaError
from services.gemini_service import gemini_service, chamar_gemini
from sistemas.gerador_pecas.services_busca_vetorial import buscar_argumentos_vetorial

logger = logging.getLogger(__name__)


# Prompt de sistema padrão
PROMPT_SISTEMA_PADRAO = """Você é um assistente jurídico especializado em cumprimento de sentença, trabalhando para a Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

## Contexto do Processo

{contexto_processo}

## Suas Responsabilidades

1. Auxiliar o procurador na elaboração de peças jurídicas de cumprimento de sentença
2. Responder dúvidas sobre o processo e sua situação atual
3. Sugerir estratégias e argumentos jurídicos relevantes
4. Gerar peças jurídicas quando solicitado

## Diretrizes

- Seja objetivo e técnico em suas respostas
- Use linguagem jurídica apropriada
- Baseie-se nas informações do processo fornecidas
- Quando gerar peças, siga o padrão da PGE-MS
- Se não souber algo, admita claramente

## Formato

- Para peças jurídicas: use markdown com formatação adequada
- Para explicações: seja claro e conciso
- Para sugestões: apresente opções de forma estruturada
"""


class ChatbotService:
    """Serviço de chatbot do beta"""

    def __init__(self, db: Session):
        self.db = db
        self._modelo = self._carregar_modelo()
        self._prompt_sistema = self._carregar_prompt_sistema()

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado para o chatbot"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.MODELO_CHATBOT
            ).first()

            if config and config.valor:
                logger.info(f"[BETA] Modelo chatbot carregado: {config.valor}")
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        return MODELO_PADRAO_CHATBOT

    def _carregar_prompt_sistema(self) -> str:
        """Carrega prompt de sistema do admin"""
        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.PROMPT_SISTEMA_BETA
            ).first()

            if config and config.valor:
                logger.info("[BETA] Prompt de sistema customizado carregado")
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar prompt sistema: {e}")

        return PROMPT_SISTEMA_PADRAO

    def _montar_contexto_processo(self, sessao: SessaoCumprimentoBeta) -> str:
        """Monta contexto do processo para o prompt"""
        contexto_partes = [f"**Processo:** {sessao.numero_processo_formatado or sessao.numero_processo}"]

        # Busca consolidação
        consolidacao = self.db.query(ConsolidacaoBeta).filter(
            ConsolidacaoBeta.sessao_id == sessao.id
        ).first()

        if consolidacao:
            contexto_partes.append(f"\n**Resumo do Processo:**\n{consolidacao.resumo_consolidado}")

            if consolidacao.dados_processo:
                dados = consolidacao.dados_processo
                if dados.get("exequente"):
                    contexto_partes.append(f"**Exequente:** {dados['exequente']}")
                if dados.get("executado"):
                    contexto_partes.append(f"**Executado:** {dados['executado']}")
                if dados.get("valor_execucao"):
                    contexto_partes.append(f"**Valor:** {dados['valor_execucao']}")

            if consolidacao.sugestoes_pecas:
                sugestoes = "\n".join([
                    f"- {s['tipo']}: {s.get('descricao', '')}"
                    for s in consolidacao.sugestoes_pecas
                ])
                contexto_partes.append(f"\n**Sugestões de Peças:**\n{sugestoes}")

        return "\n".join(contexto_partes)

    def _montar_historico(self, sessao: SessaoCumprimentoBeta) -> List[Dict[str, str]]:
        """Monta histórico de mensagens para contexto"""
        mensagens = self.db.query(ConversaBeta).filter(
            ConversaBeta.sessao_id == sessao.id
        ).order_by(
            ConversaBeta.created_at.desc()
        ).limit(MAX_MENSAGENS_CONTEXTO).all()

        # Inverte para ordem cronológica
        mensagens = list(reversed(mensagens))

        return [
            {"role": m.role, "content": m.conteudo}
            for m in mensagens
        ]

    async def _buscar_argumentos(self, query: str) -> List[Dict[str, Any]]:
        """Busca argumentos relevantes no banco vetorial"""
        try:
            argumentos = await buscar_argumentos_vetorial(
                db=self.db,
                query=query,
                tipo_peca="cumprimento",
                limit=3,
                threshold=0.4
            )
            return argumentos
        except Exception as e:
            logger.warning(f"[BETA] Erro na busca vetorial: {e}")
            return []

    def _salvar_mensagem(
        self,
        sessao_id: int,
        role: str,
        conteudo: str,
        modelo: Optional[str] = None,
        usou_busca: bool = False,
        argumentos: Optional[List[int]] = None
    ) -> ConversaBeta:
        """Salva mensagem no histórico"""
        mensagem = ConversaBeta(
            sessao_id=sessao_id,
            role=role,
            conteudo=conteudo,
            modelo_usado=modelo,
            usou_busca_vetorial=usou_busca,
            argumentos_encontrados=argumentos
        )
        self.db.add(mensagem)
        self.db.commit()
        self.db.refresh(mensagem)
        return mensagem

    async def enviar_mensagem(
        self,
        sessao: SessaoCumprimentoBeta,
        mensagem_usuario: str
    ) -> ConversaBeta:
        """
        Processa mensagem do usuário e gera resposta.

        Args:
            sessao: Sessão do beta
            mensagem_usuario: Mensagem do usuário

        Returns:
            ConversaBeta com resposta do assistente
        """
        logger.info(f"[BETA] Processando mensagem na sessão {sessao.id}")

        # Salva mensagem do usuário
        self._salvar_mensagem(sessao.id, RoleChat.USER, mensagem_usuario)

        # Busca argumentos relevantes
        argumentos = await self._buscar_argumentos(mensagem_usuario)
        argumentos_ids = [a.get("id") for a in argumentos if a.get("id")]

        # Monta contexto
        contexto_processo = self._montar_contexto_processo(sessao)
        historico = self._montar_historico(sessao)

        # Monta prompt completo
        prompt_sistema = self._prompt_sistema.format(contexto_processo=contexto_processo)

        # Adiciona argumentos encontrados se houver
        if argumentos:
            argumentos_texto = "\n\n## Argumentos Jurídicos Relevantes\n\n"
            for arg in argumentos:
                argumentos_texto += f"### {arg.get('titulo', 'Argumento')}\n{arg.get('conteudo', '')}\n\n"
            prompt_sistema += argumentos_texto

        # Monta mensagens para a API
        mensagens_api = [{"role": "system", "content": prompt_sistema}]
        mensagens_api.extend(historico)
        mensagens_api.append({"role": "user", "content": mensagem_usuario})

        # Chama Gemini
        try:
            # Monta prompt completo com histórico
            prompt_completo = mensagem_usuario
            if historico:
                historico_texto = "\n".join([
                    f"{m['role'].upper()}: {m['content']}" for m in historico[-4:]
                ])
                prompt_completo = f"Histórico recente:\n{historico_texto}\n\nMensagem atual: {mensagem_usuario}"

            resposta = await chamar_gemini(
                prompt=prompt_completo,
                modelo=self._modelo,
                system_prompt=prompt_sistema
            )

            # Salva resposta
            mensagem_resposta = self._salvar_mensagem(
                sessao_id=sessao.id,
                role=RoleChat.ASSISTANT,
                conteudo=resposta,
                modelo=self._modelo,
                usou_busca=len(argumentos) > 0,
                argumentos=argumentos_ids if argumentos_ids else None
            )

            logger.info(f"[BETA] Resposta gerada ({len(resposta)} chars)")

            return mensagem_resposta

        except Exception as e:
            logger.error(f"[BETA] Erro ao gerar resposta: {e}")
            raise CumprimentoBetaError(f"Erro ao processar mensagem: {e}")

    async def enviar_mensagem_streaming(
        self,
        sessao: SessaoCumprimentoBeta,
        mensagem_usuario: str
    ) -> AsyncGenerator[str, None]:
        """
        Processa mensagem com streaming de resposta.

        Yields:
            Chunks de texto da resposta
        """
        logger.info(f"[BETA] Processando mensagem streaming na sessão {sessao.id}")

        # Salva mensagem do usuário
        self._salvar_mensagem(sessao.id, RoleChat.USER, mensagem_usuario)

        # Busca argumentos
        argumentos = await self._buscar_argumentos(mensagem_usuario)
        argumentos_ids = [a.get("id") for a in argumentos if a.get("id")]

        # Monta contexto
        contexto_processo = self._montar_contexto_processo(sessao)
        historico = self._montar_historico(sessao)

        prompt_sistema = self._prompt_sistema.format(contexto_processo=contexto_processo)

        if argumentos:
            argumentos_texto = "\n\n## Argumentos Jurídicos Relevantes\n\n"
            for arg in argumentos:
                argumentos_texto += f"### {arg.get('titulo', 'Argumento')}\n{arg.get('conteudo', '')}\n\n"
            prompt_sistema += argumentos_texto

        resposta_completa = ""

        try:
            # Monta prompt completo com histórico
            prompt_completo = mensagem_usuario
            if historico:
                historico_texto = "\n".join([
                    f"{m['role'].upper()}: {m['content']}" for m in historico[-4:]
                ])
                prompt_completo = f"Histórico recente:\n{historico_texto}\n\nMensagem atual: {mensagem_usuario}"

            async for chunk in gemini_service.generate_stream(
                prompt=prompt_completo,
                model=self._modelo,
                system_prompt=prompt_sistema
            ):
                resposta_completa += chunk
                yield chunk

            # Salva resposta completa
            self._salvar_mensagem(
                sessao_id=sessao.id,
                role=RoleChat.ASSISTANT,
                conteudo=resposta_completa,
                modelo=self._modelo,
                usou_busca=len(argumentos) > 0,
                argumentos=argumentos_ids if argumentos_ids else None
            )

        except Exception as e:
            logger.error(f"[BETA] Erro no streaming: {e}")
            yield f"\n\n[Erro: {str(e)}]"


async def enviar_mensagem_chat(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    mensagem: str
) -> ConversaBeta:
    """Função auxiliar para enviar mensagem"""
    service = ChatbotService(db)
    return await service.enviar_mensagem(sessao, mensagem)


async def enviar_mensagem_chat_streaming(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    mensagem: str
) -> AsyncGenerator[str, None]:
    """Função auxiliar para enviar mensagem com streaming"""
    service = ChatbotService(db)
    async for chunk in service.enviar_mensagem_streaming(sessao, mensagem):
        yield chunk


def obter_historico_chat(
    db: Session,
    sessao_id: int
) -> List[ConversaBeta]:
    """Obtém histórico de conversas de uma sessão"""
    return db.query(ConversaBeta).filter(
        ConversaBeta.sessao_id == sessao_id
    ).order_by(
        ConversaBeta.created_at.asc()
    ).all()
