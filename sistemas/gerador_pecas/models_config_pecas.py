# sistemas/gerador_pecas/models_config_pecas.py
"""
Modelos para configuração de tipos de peças jurídicas e categorias de documentos.

Permite definir:
- Tipos de peça disponíveis no sistema (contestação, contrarrazões, etc)
- Categorias de documentos do TJ-MS
- Quais categorias de documentos são analisadas para cada tipo de peça
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, Table
from sqlalchemy.orm import relationship
from database.connection import Base


# Tabela de associação entre TipoPeca e CategoriaDocumento (muitos-para-muitos)
tipo_peca_categorias = Table(
    'tipo_peca_categorias',
    Base.metadata,
    Column('tipo_peca_id', Integer, ForeignKey('tipos_peca.id'), primary_key=True),
    Column('categoria_documento_id', Integer, ForeignKey('categorias_documento.id'), primary_key=True)
)


class CategoriaDocumento(Base):
    """
    Define uma categoria de documento do TJ-MS.
    
    Cada categoria agrupa tipos de documento por finalidade jurídica.
    Exemplo: "Petições", "Decisões", "Laudos Médicos"
    """
    __tablename__ = "categorias_documento"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identificação
    nome = Column(String(100), nullable=False, unique=True, index=True)
    titulo = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    
    # Códigos de documento TJ-MS que pertencem a esta categoria
    # Formato: lista de inteiros [500, 510, 9500, 8320]
    codigos_documento = Column(JSON, nullable=False, default=list)
    
    # Status
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)
    
    # Cor para exibição no frontend (opcional)
    cor = Column(String(20), nullable=True)
    
    # Auditoria
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    tipos_peca = relationship(
        "TipoPeca",
        secondary=tipo_peca_categorias,
        back_populates="categorias_documento"
    )
    
    def __repr__(self):
        return f"<CategoriaDocumento(id={self.id}, nome='{self.nome}')>"
    
    def get_codigos(self) -> list:
        """Retorna lista de códigos de documento"""
        return self.codigos_documento if self.codigos_documento else []


class TipoPeca(Base):
    """
    Define um tipo de peça jurídica disponível no sistema.
    
    Cada tipo de peça:
    - Tem um identificador único (ex: 'contestacao', 'contrarrazoes')
    - Define quais categorias de documentos são analisadas pelo Agente 1
    - Pode ter configurações específicas (modelo de IA, prompts, etc)
    """
    __tablename__ = "tipos_peca"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identificação
    nome = Column(String(50), nullable=False, unique=True, index=True)  # ex: 'contestacao'
    titulo = Column(String(200), nullable=False)  # ex: 'Contestação'
    descricao = Column(Text, nullable=True)
    
    # Ícone para exibição no frontend (opcional, ex: 'file-text', 'gavel')
    icone = Column(String(50), nullable=True)
    
    # Status
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)
    
    # Se é o tipo padrão quando nenhum for selecionado
    is_padrao = Column(Boolean, default=False)
    
    # Configurações específicas (JSON flexível)
    # Pode incluir: modelo_ia, max_documentos, etc
    configuracoes = Column(JSON, nullable=True)
    
    # Auditoria
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    categorias_documento = relationship(
        "CategoriaDocumento",
        secondary=tipo_peca_categorias,
        back_populates="tipos_peca"
    )
    
    def __repr__(self):
        return f"<TipoPeca(id={self.id}, nome='{self.nome}')>"
    
    def get_codigos_permitidos(self) -> set:
        """
        Retorna conjunto de todos os códigos de documento permitidos para este tipo de peça.
        Agrega os códigos de todas as categorias associadas.
        """
        codigos = set()
        for categoria in self.categorias_documento:
            if categoria.ativo:
                codigos.update(categoria.get_codigos())
        return codigos
    
    def documento_permitido(self, codigo_documento: int) -> bool:
        """Verifica se um código de documento é permitido para este tipo de peça"""
        return codigo_documento in self.get_codigos_permitidos()


# ===========================================
# Funções auxiliares para seed inicial
# ===========================================

def get_categorias_documento_seed() -> list:
    """Retorna dados iniciais para categorias de documento"""
    return [
        {
            "nome": "peticoes",
            "titulo": "Petições",
            "descricao": "Petições iniciais, intermediárias, contestações e manifestações",
            "codigos_documento": [500, 510, 9500, 8320, 8323, 8338],
            "ordem": 1,
            "cor": "#3498db"
        },
        {
            "nome": "decisoes",
            "titulo": "Decisões Judiciais",
            "descricao": "Despachos, decisões interlocutórias, sentenças e acórdãos",
            "codigos_documento": [6, 8, 15, 34, 44, 137],
            "ordem": 2,
            "cor": "#9b59b6"
        },
        {
            "nome": "recursos",
            "titulo": "Recursos",
            "descricao": "Recursos de apelação, agravos e contrarrazões",
            "codigos_documento": [8335, 8305],
            "ordem": 3,
            "cor": "#e74c3c"
        },
        {
            "nome": "laudos_medicos",
            "titulo": "Laudos e Documentos Médicos",
            "descricao": "Laudos periciais, receitas, exames e pareceres médicos",
            "codigos_documento": [9534, 8369, 59, 9827],
            "ordem": 4,
            "cor": "#2ecc71"
        },
        {
            "nome": "documentos_parte",
            "titulo": "Documentos da Parte",
            "descricao": "Documentos pessoais, declarações e comprovantes juntados pelas partes",
            "codigos_documento": [9509, 9512, 9513, 9600, 9612, 9740],
            "ordem": 5,
            "cor": "#f39c12"
        },
        {
            "nome": "mp_defensoria",
            "titulo": "Peças do MP e Defensoria",
            "descricao": "Manifestações do Ministério Público e peças da Defensoria",
            "codigos_documento": [21, 30, 8333],
            "ordem": 6,
            "cor": "#1abc9c"
        },
        {
            "nome": "mandados_citacao",
            "titulo": "Mandados e Citações",
            "descricao": "Mandados de citação, intimação e certidões de oficiais",
            "codigos_documento": [1, 19, 8366],
            "ordem": 7,
            "cor": "#95a5a6"
        },
    ]


def get_tipos_peca_seed() -> list:
    """Retorna dados iniciais para tipos de peça"""
    return [
        {
            "nome": "contestacao",
            "titulo": "Contestação",
            "descricao": "Peça de defesa em ações cíveis contra o Estado",
            "icone": "file-text",
            "ordem": 1,
            "categorias": ["peticoes", "decisoes", "laudos_medicos", "documentos_parte", "mp_defensoria"]
        },
        {
            "nome": "contrarrazoes",
            "titulo": "Contrarrazões de Apelação",
            "descricao": "Resposta a recurso de apelação",
            "icone": "git-pull-request",
            "ordem": 2,
            "categorias": ["peticoes", "decisoes", "recursos", "laudos_medicos", "documentos_parte"]
        },
        {
            "nome": "parecer",
            "titulo": "Parecer Jurídico",
            "descricao": "Manifestação técnico-jurídica sobre matéria consultada",
            "icone": "clipboard",
            "ordem": 3,
            "categorias": ["peticoes", "decisoes", "laudos_medicos", "mp_defensoria"]
        },
        {
            "nome": "recurso_apelacao",
            "titulo": "Recurso de Apelação",
            "descricao": "Recurso contra sentença de primeiro grau",
            "icone": "arrow-up-circle",
            "ordem": 4,
            "categorias": ["peticoes", "decisoes", "recursos", "laudos_medicos"]
        },
        {
            "nome": "agravo_instrumento",
            "titulo": "Agravo de Instrumento",
            "descricao": "Recurso contra decisão interlocutória",
            "icone": "alert-triangle",
            "ordem": 5,
            "categorias": ["peticoes", "decisoes", "laudos_medicos"]
        },
    ]
