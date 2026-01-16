# sistemas/gerador_pecas/models_teste_categorias.py
"""
Modelos para persistência de testes de categorias JSON.

Armazena o estado dos documentos testados por usuário e categoria,
permitindo persistência entre sessões e acesso de qualquer dispositivo.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from database.connection import Base


class TesteDocumento(Base):
    """
    Documento de teste para uma categoria.

    Armazena o estado de cada processo testado, incluindo:
    - Status do documento (pendente, baixado, classificado, etc.)
    - Resultado JSON da classificação
    - Observações e flags de revisão

    Cada combinação (usuario, categoria, processo) é única.
    """
    __tablename__ = "teste_categoria_documentos"

    id = Column(Integer, primary_key=True, index=True)

    # Relacionamentos
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_resumo_json.id"), nullable=False, index=True)

    # Identificação do processo
    processo = Column(String(30), nullable=False, index=True)  # Formato CNJ

    # Status: pendente, baixado, classificado, erro
    status = Column(String(20), nullable=False, default="pendente", index=True)

    # Resultado da classificação
    json_resultado = Column(JSON, nullable=True)

    # Informações adicionais
    num_documentos = Column(Integer, default=0)  # Quantidade de docs baixados
    erro = Column(Text, nullable=True)  # Mensagem de erro se houver
    revisado = Column(Boolean, default=False, index=True)

    # Timestamps
    data_criacao = Column(DateTime, default=datetime.utcnow)
    data_download = Column(DateTime, nullable=True)
    data_classificacao = Column(DateTime, nullable=True)
    data_revisao = Column(DateTime, nullable=True)

    # Constraint: um processo por usuario/categoria
    __table_args__ = (
        UniqueConstraint('usuario_id', 'categoria_id', 'processo', name='uq_teste_doc_usuario_categoria_processo'),
        Index('ix_teste_doc_usuario_categoria', 'usuario_id', 'categoria_id'),
    )

    def __repr__(self):
        return f"<TesteDocumento(id={self.id}, processo='{self.processo}', status='{self.status}')>"

    def to_dict(self):
        """Converte para dicionário para API"""
        return {
            "id": self.id,
            "processo": self.processo,
            "categoria_id": self.categoria_id,
            "status": self.status,
            "json_resultado": self.json_resultado,
            "num_documentos": self.num_documentos,
            "erro": self.erro,
            "revisado": self.revisado,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
            "data_download": self.data_download.isoformat() if self.data_download else None,
            "data_classificacao": self.data_classificacao.isoformat() if self.data_classificacao else None,
            "data_revisao": self.data_revisao.isoformat() if self.data_revisao else None,
        }


class TesteObservacao(Base):
    """
    Observações persistentes por categoria (por usuário).

    Permite que cada usuário mantenha notas sobre cada categoria.
    """
    __tablename__ = "teste_categoria_observacoes"

    id = Column(Integer, primary_key=True, index=True)

    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_resumo_json.id"), nullable=False, index=True)

    texto = Column(Text, nullable=True)

    data_atualizacao = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('usuario_id', 'categoria_id', name='uq_teste_obs_usuario_categoria'),
    )

    def __repr__(self):
        return f"<TesteObservacao(usuario_id={self.usuario_id}, categoria_id={self.categoria_id})>"
