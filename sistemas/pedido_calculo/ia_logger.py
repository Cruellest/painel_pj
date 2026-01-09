# sistemas/pedido_calculo/ia_logger.py
"""
Serviço de logging para chamadas de IA no Pedido de Cálculo.

Registra cada interação com o modelo de IA para debug e auditoria.
"""

import time
from datetime import datetime
from typing import Optional, Any, Dict
from contextlib import contextmanager

from sqlalchemy.orm import Session
from database.connection import SessionLocal
from .models import LogChamadaIA, GeracaoPedidoCalculo


class IALogger:
    """
    Logger para chamadas de IA.

    Uso:
        logger = IALogger()
        logger.set_geracao_id(geracao_id)  # Opcional, vincula ao registro de geração

        with logger.log_chamada("analise_certidao", "Analisando certidão 123") as log:
            log.set_documento("123", texto_certidao)
            log.set_prompt(prompt)
            resposta = await ia.generate(prompt)
            log.set_resposta(resposta.content, dados_parseados)
    """

    def __init__(self):
        self.geracao_id: Optional[int] = None
        self._logs: list = []  # Buffer de logs para salvar em batch

    def set_geracao_id(self, geracao_id: int):
        """Define o ID da geração para vincular os logs"""
        self.geracao_id = geracao_id

    @contextmanager
    def log_chamada(self, etapa: str, descricao: str = None):
        """
        Context manager para logar uma chamada de IA.

        Args:
            etapa: Identificador da etapa (ex: "analise_certidao", "extracao_docs")
            descricao: Descrição legível da operação
        """
        log_entry = LogEntry(etapa, descricao)
        log_entry.geracao_id = self.geracao_id

        try:
            yield log_entry
        except Exception as e:
            log_entry.set_erro(str(e))
            raise
        finally:
            self._logs.append(log_entry)

    def salvar_logs(self, db: Session = None):
        """Salva todos os logs pendentes no banco de dados"""
        if not self._logs:
            return

        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            for log_entry in self._logs:
                # Propaga o geracao_id para os logs individuais
                if self.geracao_id and not log_entry.geracao_id:
                    log_entry.geracao_id = self.geracao_id

                log_model = LogChamadaIA(
                    geracao_id=log_entry.geracao_id,
                    etapa=log_entry.etapa,
                    descricao=log_entry.descricao,
                    prompt_enviado=log_entry.prompt_enviado,
                    documento_id=log_entry.documento_id,
                    documento_texto=log_entry.documento_texto,
                    resposta_ia=log_entry.resposta_ia,
                    resposta_parseada=log_entry.resposta_parseada,
                    modelo_usado=log_entry.modelo_usado,
                    tokens_entrada=log_entry.tokens_entrada,
                    tokens_saida=log_entry.tokens_saida,
                    tempo_ms=log_entry.tempo_ms,
                    sucesso=log_entry.sucesso,
                    erro=log_entry.erro,
                    criado_em=log_entry.criado_em
                )
                db.add(log_model)

            db.commit()
            self._logs.clear()

        except Exception as e:
            db.rollback()
            print(f"[ERRO] Falha ao salvar logs de IA: {e}")
        finally:
            if close_session:
                db.close()

    def get_logs_pendentes(self) -> list:
        """Retorna logs pendentes (não salvos)"""
        return [log.to_dict() for log in self._logs]


class LogEntry:
    """Entrada individual de log"""

    def __init__(self, etapa: str, descricao: str = None):
        self.etapa = etapa
        self.descricao = descricao
        self.geracao_id: Optional[int] = None

        # Entrada
        self.prompt_enviado: Optional[str] = None
        self.documento_id: Optional[str] = None
        self.documento_texto: Optional[str] = None

        # Saída
        self.resposta_ia: Optional[str] = None
        self.resposta_parseada: Optional[Dict] = None

        # Metadados
        self.modelo_usado: Optional[str] = None
        self.tokens_entrada: Optional[int] = None
        self.tokens_saida: Optional[int] = None
        self.tempo_ms: Optional[int] = None
        self.sucesso: bool = True
        self.erro: Optional[str] = None

        # Timestamps
        self.criado_em = datetime.utcnow()
        self._inicio = time.time()

    def set_documento(self, documento_id: str, texto: str = None):
        """Define o documento sendo analisado"""
        self.documento_id = documento_id
        if texto:
            # Limita o texto para não estourar o banco
            self.documento_texto = texto[:50000] if len(texto) > 50000 else texto

    def set_prompt(self, prompt: str):
        """Define o prompt enviado"""
        self.prompt_enviado = prompt

    def set_modelo(self, modelo: str):
        """Define o modelo usado"""
        self.modelo_usado = modelo

    def set_resposta(self, resposta_bruta: str, resposta_parseada: Dict = None, tokens_entrada: int = None, tokens_saida: int = None):
        """Define a resposta da IA"""
        self.resposta_ia = resposta_bruta
        self.resposta_parseada = resposta_parseada
        self.tokens_entrada = tokens_entrada
        self.tokens_saida = tokens_saida
        self.tempo_ms = int((time.time() - self._inicio) * 1000)

    def set_erro(self, erro: str):
        """Define erro ocorrido"""
        self.sucesso = False
        self.erro = erro
        self.tempo_ms = int((time.time() - self._inicio) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "etapa": self.etapa,
            "descricao": self.descricao,
            "documento_id": self.documento_id,
            "prompt_enviado": self.prompt_enviado[:500] + "..." if self.prompt_enviado and len(self.prompt_enviado) > 500 else self.prompt_enviado,
            "resposta_parseada": self.resposta_parseada,
            "modelo_usado": self.modelo_usado,
            "tempo_ms": self.tempo_ms,
            "sucesso": self.sucesso,
            "erro": self.erro,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None
        }


# Instância global do logger (será substituída por request-scoped em produção)
_current_logger: Optional[IALogger] = None


def get_logger() -> IALogger:
    """Obtém o logger atual ou cria um novo"""
    global _current_logger
    if _current_logger is None:
        _current_logger = IALogger()
    return _current_logger


def create_logger() -> IALogger:
    """Cria um novo logger (para nova requisição)"""
    global _current_logger
    _current_logger = IALogger()
    return _current_logger


def clear_logger():
    """Limpa o logger atual"""
    global _current_logger
    _current_logger = None
