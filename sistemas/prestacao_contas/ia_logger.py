# sistemas/prestacao_contas/ia_logger.py
"""
Sistema de logging para chamadas de IA no sistema de Prestação de Contas.
Permite rastrear todas as chamadas de IA para debug e auditoria.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import time

from sqlalchemy.orm import Session

from sistemas.prestacao_contas.models import LogChamadaIAPrestacao


@dataclass
class LogEntry:
    """Entrada individual de log para uma chamada de IA"""
    etapa: str
    descricao: str = ""

    # Entrada
    documento_id: Optional[str] = None
    documento_texto: Optional[str] = None
    prompt_enviado: Optional[str] = None

    # Saída
    resposta_ia: Optional[str] = None
    resposta_parseada: Optional[Dict[str, Any]] = None

    # Métricas
    modelo_usado: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    tempo_ms: Optional[int] = None

    # Status
    sucesso: bool = True
    erro: Optional[str] = None

    # Timestamp
    criado_em: datetime = field(default_factory=datetime.utcnow)

    # Para medir tempo
    _inicio: float = field(default_factory=time.time, repr=False)

    def set_documento(self, documento_id: str, texto: str):
        """Define o documento sendo analisado"""
        self.documento_id = documento_id
        self.documento_texto = texto

    def set_prompt(self, prompt: str):
        """Define o prompt enviado"""
        self.prompt_enviado = prompt

    def set_resposta(
        self,
        resposta_bruta: str,
        resposta_parseada: Optional[Dict[str, Any]] = None,
        tokens_entrada: Optional[int] = None,
        tokens_saida: Optional[int] = None
    ):
        """Define a resposta recebida da IA"""
        self.resposta_ia = resposta_bruta
        self.resposta_parseada = resposta_parseada
        self.tokens_entrada = tokens_entrada
        self.tokens_saida = tokens_saida
        self.tempo_ms = int((time.time() - self._inicio) * 1000)

    def set_modelo(self, modelo: str):
        """Define o modelo usado"""
        self.modelo_usado = modelo

    def set_erro(self, erro: str):
        """Marca como erro"""
        self.sucesso = False
        self.erro = erro
        self.tempo_ms = int((time.time() - self._inicio) * 1000)

    def finalizar(self):
        """Finaliza a medição de tempo"""
        if self.tempo_ms is None:
            self.tempo_ms = int((time.time() - self._inicio) * 1000)


class IALogger:
    """Logger para chamadas de IA do sistema de Prestação de Contas"""

    def __init__(self):
        self._logs: List[LogEntry] = []
        self._current_entry: Optional[LogEntry] = None

    def iniciar_log(self, etapa: str, descricao: str = "") -> LogEntry:
        """Inicia um novo log para uma etapa"""
        entry = LogEntry(etapa=etapa, descricao=descricao)
        self._logs.append(entry)
        self._current_entry = entry
        return entry

    def log_chamada(self, etapa: str, descricao: str = "") -> LogEntry:
        """Alias para iniciar_log"""
        return self.iniciar_log(etapa, descricao)

    @property
    def current(self) -> Optional[LogEntry]:
        """Retorna o log atual"""
        return self._current_entry

    @property
    def logs(self) -> List[LogEntry]:
        """Retorna todos os logs"""
        return self._logs

    def salvar_logs(self, db: Session, geracao_id: int):
        """Persiste todos os logs no banco de dados"""
        for entry in self._logs:
            entry.finalizar()

            log_db = LogChamadaIAPrestacao(
                geracao_id=geracao_id,
                etapa=entry.etapa,
                descricao=entry.descricao,
                prompt_enviado=entry.prompt_enviado,
                documento_id=entry.documento_id,
                documento_texto=entry.documento_texto,
                resposta_ia=entry.resposta_ia,
                resposta_parseada=entry.resposta_parseada,
                modelo_usado=entry.modelo_usado,
                tokens_entrada=entry.tokens_entrada,
                tokens_saida=entry.tokens_saida,
                tempo_ms=entry.tempo_ms,
                sucesso=entry.sucesso,
                erro=entry.erro,
                criado_em=entry.criado_em
            )
            db.add(log_db)

        db.commit()

    def limpar(self):
        """Limpa todos os logs"""
        self._logs = []
        self._current_entry = None

    def get_resumo(self) -> Dict[str, Any]:
        """Retorna um resumo dos logs"""
        total_tempo = sum(log.tempo_ms or 0 for log in self._logs)
        total_tokens_entrada = sum(log.tokens_entrada or 0 for log in self._logs)
        total_tokens_saida = sum(log.tokens_saida or 0 for log in self._logs)
        erros = [log for log in self._logs if not log.sucesso]

        return {
            "total_chamadas": len(self._logs),
            "total_tempo_ms": total_tempo,
            "total_tokens_entrada": total_tokens_entrada,
            "total_tokens_saida": total_tokens_saida,
            "total_erros": len(erros),
            "etapas": [log.etapa for log in self._logs]
        }


def create_logger() -> IALogger:
    """Factory function para criar um logger"""
    return IALogger()
