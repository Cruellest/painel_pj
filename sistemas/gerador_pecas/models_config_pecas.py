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
    
    # Categoria especial: considera apenas o primeiro documento cronológico
    # Usado para "Petição Inicial" que pega só o primeiro doc 9500/500 do processo
    is_primeiro_documento = Column(Boolean, default=False)
    
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
    
    def get_codigos_primeiro_documento(self) -> set:
        """
        Retorna códigos de categorias que devem considerar apenas o primeiro documento.
        Exemplo: Petição Inicial (só o primeiro documento 9500/500 do processo).
        """
        codigos = set()
        for categoria in self.categorias_documento:
            if categoria.ativo and categoria.is_primeiro_documento:
                codigos.update(categoria.get_codigos())
        return codigos
    
    def documento_permitido(self, codigo_documento: int) -> bool:
        """Verifica se um código de documento é permitido para este tipo de peça"""
        return codigo_documento in self.get_codigos_permitidos()


# ===========================================
# Funções auxiliares para seed inicial
# ===========================================

import json
from pathlib import Path

def carregar_categorias_json() -> dict:
    """
    Carrega as categorias de documentos do arquivo categorias_documentos.json
    e retorna um dicionário organizado por categoria.
    
    Returns:
        dict: {
            "Petição": [{"Nome": "...", "Código": "..."}, ...],
            "Decisão": [...],
            ...
        }
    """
    json_path = Path(__file__).parent.parent.parent / "categorias_documentos.json"
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            documentos = json.load(f)
    except FileNotFoundError:
        return {}
    
    # Agrupar por categoria
    categorias = {}
    for doc in documentos:
        cat = doc.get("Categoria", "Outros")
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append({
            "nome": doc.get("Nome", ""),
            "codigo": int(doc.get("Código", 0))
        })
    
    return categorias


def get_codigos_por_categoria_json() -> dict:
    """
    Retorna um dicionário com os códigos agrupados por categoria do JSON.
    
    Returns:
        dict: {"Petição": [500, 510, 9500, ...], "Decisão": [...], ...}
    """
    categorias = carregar_categorias_json()
    return {
        cat: [doc["codigo"] for doc in docs]
        for cat, docs in categorias.items()
    }


def get_categorias_documento_seed() -> list:
    """
    Retorna dados iniciais para categorias de documento baseados no JSON.
    Inclui categoria especial 'Petição Inicial'.
    """
    categorias_json = get_codigos_por_categoria_json()
    
    # Cores por categoria
    cores = {
        "Petição": "#3498db",
        "Decisão": "#9b59b6",
        "Despacho": "#8e44ad",
        "Sentença": "#e74c3c",
        "Acórdão": "#c0392b",
        "Recurso": "#d35400",
        "Recursos": "#d35400",
        "Documento": "#27ae60",
        "Parecer": "#16a085",
        "Outros": "#7f8c8d"
    }
    
    resultado = []
    ordem = 1
    
    # Categoria especial: Petição Inicial (primeiro documento 9500 ou 500)
    resultado.append({
        "nome": "peticao_inicial",
        "titulo": "Petição Inicial",
        "descricao": "Primeiro documento do processo (geralmente código 9500 ou 500). Categoria especial que considera apenas o primeiro documento cronológico.",
        "codigos_documento": [9500, 500],
        "ordem": ordem,
        "cor": "#2980b9",
        "is_primeiro_documento": True  # Marca como categoria que pega só o primeiro documento
    })
    ordem += 1
    
    # Gerar categorias a partir do JSON
    for cat_nome, codigos in categorias_json.items():
        # Normalizar nome para usar como identificador
        nome_id = cat_nome.lower().replace(" ", "_").replace("ã", "a").replace("ç", "c").replace("é", "e").replace("ó", "o")
        
        resultado.append({
            "nome": nome_id,
            "titulo": cat_nome,
            "descricao": f"Documentos da categoria '{cat_nome}' do TJ-MS ({len(codigos)} tipos)",
            "codigos_documento": codigos,
            "ordem": ordem,
            "cor": cores.get(cat_nome, "#7f8c8d")
        })
        ordem += 1
    
    # Categoria "Outros" para códigos não categorizados
    resultado.append({
        "nome": "outros",
        "titulo": "Outros",
        "descricao": "Documentos que não se enquadram em nenhuma categoria específica",
        "codigos_documento": [],  # Será preenchido dinamicamente
        "ordem": ordem,
        "cor": "#95a5a6"
    })
    
    return resultado


def get_tipos_peca_seed() -> list:
    """Retorna dados iniciais para tipos de peça usando as categorias do JSON"""
    return [
        {
            "nome": "contestacao",
            "titulo": "Contestação",
            "descricao": "Peça de defesa em ações cíveis contra o Estado",
            "icone": "file-text",
            "ordem": 1,
            "categorias": ["peticao_inicial", "peticao", "decisao", "despacho", "sentenca", "documento", "parecer"]
        },
        {
            "nome": "contrarrazoes",
            "titulo": "Contrarrazões de Apelação",
            "descricao": "Resposta a recurso de apelação",
            "icone": "git-pull-request",
            "ordem": 2,
            "categorias": ["peticao_inicial", "peticao", "decisao", "sentenca", "acordao", "recurso", "recursos", "documento"]
        },
        {
            "nome": "parecer",
            "titulo": "Parecer Jurídico",
            "descricao": "Manifestação técnico-jurídica sobre matéria consultada",
            "icone": "clipboard",
            "ordem": 3,
            "categorias": ["peticao_inicial", "peticao", "decisao", "despacho", "sentenca", "documento", "parecer"]
        },
        {
            "nome": "recurso_apelacao",
            "titulo": "Recurso de Apelação",
            "descricao": "Recurso contra sentença de primeiro grau",
            "icone": "arrow-up-circle",
            "ordem": 4,
            "categorias": ["peticao_inicial", "peticao", "decisao", "sentenca", "documento"]
        },
        {
            "nome": "agravo_instrumento",
            "titulo": "Agravo de Instrumento",
            "descricao": "Recurso contra decisão interlocutória",
            "icone": "alert-triangle",
            "ordem": 5,
            "categorias": ["peticao_inicial", "peticao", "decisao", "despacho", "documento"]
        },
    ]
