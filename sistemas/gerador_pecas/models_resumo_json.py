# sistemas/gerador_pecas/models_resumo_json.py
"""
Modelos para categorias de formato de resumo JSON.

Permite definir diferentes formatos de saída JSON para resumos de documentos,
baseados no tipo de documento (código do TJ-MS).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


class CategoriaResumoJSON(Base):
    """
    Define uma categoria de formato de resumo JSON (grupo de documentos).

    Cada categoria:
    - Tem um nome identificador
    - Define quais códigos de documento do TJ-MS pertencem a ela
    - Define o formato JSON esperado para os resumos
    - Define namespace para variáveis extraídas
    - Define qual tipo de peça é a "fonte de verdade" para extração

    Exemplo:
    - Categoria "peticoes" com códigos [500, 510, 9500] e formato:
      {"tipo": "string", "partes": {"autor": "string", "reu": "string"}, "pedidos": ["string"]}
    """
    __tablename__ = "categorias_resumo_json"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    nome = Column(String(100), nullable=False, unique=True, index=True)
    titulo = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Códigos de documento TJ-MS que pertencem a esta categoria
    # Formato: lista de inteiros [500, 510, 9500]
    codigos_documento = Column(JSON, nullable=False, default=list)

    # Formato JSON esperado - estrutura de exemplo
    # Armazena o schema/exemplo que a IA deve seguir
    formato_json = Column(Text, nullable=False)

    # Prompt adicional para instruir a IA sobre este formato específico
    # Instruções extras sobre como preencher os campos
    instrucoes_extracao = Column(Text, nullable=True)

    # === NAMESPACE E FONTE DE VERDADE ===

    # Prefixo de namespace para variáveis deste grupo
    # Ex: "peticao", "nat", "sentenca"
    # Se não definido, usa o nome da categoria normalizado
    namespace_prefix = Column(String(50), nullable=True, index=True)

    # Tipos lógicos de peça possíveis neste grupo
    # Ex: ["petição inicial", "contestação", "petição intermediária"]
    # Usado para classificação de documentos pela LLM
    tipos_logicos_peca = Column(JSON, nullable=True)

    # Qual tipo lógico é a "fonte de verdade" para extração de variáveis
    # Ex: "petição inicial"
    # Se não definido, extrai de qualquer peça do grupo
    fonte_verdade_tipo = Column(String(100), nullable=True)

    # Código específico para filtrar documentos (ex: "9500")
    # Se definido, filtra apenas documentos com este código
    # Se não definido, considera todos os códigos do grupo
    fonte_verdade_codigo = Column(String(20), nullable=True)

    # Se deve classificar o documento antes de extrair
    # Se True, LLM identifica o tipo lógico e só extrai se for fonte de verdade
    requer_classificacao = Column(Boolean, default=False)

    # === FONTE ESPECIAL (alternativa a códigos) ===

    # Tipo de fonte da categoria: "code" (padrão) ou "special"
    # "code" = usa codigos_documento para filtrar
    # "special" = usa lógica especial (ex: primeiro documento do processo)
    source_type = Column(String(20), nullable=False, default="code")

    # Identificador da fonte especial (quando source_type = "special")
    # Ex: "peticao_inicial" = primeiro documento com código 9500 ou 500
    source_special_type = Column(String(50), nullable=True)

    # === ORIGEM DO JSON ===
    
    # Se o JSON atual foi gerado por IA (apenas para exibição/tag)
    json_gerado_por_ia = Column(Boolean, default=False)
    
    # Data/hora em que o JSON foi gerado pela IA
    json_gerado_em = Column(DateTime, nullable=True)
    
    # Usuário que gerou/aprovou o JSON via IA
    json_gerado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Se é a categoria residual (fallback para docs não categorizados)
    is_residual = Column(Boolean, default=False, index=True)

    # Status
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)

    # Auditoria
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    @property
    def namespace(self) -> str:
        """Retorna o namespace efetivo para variáveis deste grupo."""
        if self.namespace_prefix:
            return self.namespace_prefix
        # Normaliza o nome da categoria como fallback
        import re
        nome_normalizado = self.nome.lower()
        nome_normalizado = re.sub(r'[^a-z0-9]+', '_', nome_normalizado)
        return nome_normalizado.strip('_')

    @property
    def usa_fonte_especial(self) -> bool:
        """Retorna True se a categoria usa fonte especial em vez de códigos."""
        return self.source_type == "special" and bool(self.source_special_type)

    @property
    def tem_fonte_verdade(self) -> bool:
        """Retorna True se o grupo tem fonte de verdade configurada."""
        return bool(self.fonte_verdade_tipo and self.requer_classificacao)

    def __repr__(self):
        return f"<CategoriaResumoJSON(id={self.id}, nome='{self.nome}', namespace='{self.namespace}', residual={self.is_residual})>"


class CategoriaResumoJSONHistorico(Base):
    """Histórico de versões de uma categoria de resumo JSON"""
    
    __tablename__ = "categorias_resumo_json_historico"
    
    id = Column(Integer, primary_key=True, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_resumo_json.id"), nullable=False, index=True)
    
    # Dados da versão
    versao = Column(Integer, nullable=False)
    codigos_documento = Column(JSON, nullable=True)
    formato_json = Column(Text, nullable=False)
    instrucoes_extracao = Column(Text, nullable=True)
    
    # Auditoria
    alterado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime, default=get_utc_now)
    motivo = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<CategoriaResumoJSONHistorico(categoria_id={self.categoria_id}, v{self.versao})>"
