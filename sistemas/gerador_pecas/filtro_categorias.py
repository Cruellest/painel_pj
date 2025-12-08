# sistemas/gerador_pecas/filtro_categorias.py
"""
Serviço de filtro de categorias de documentos por tipo de peça.

Gerencia quais documentos o Agente 1 deve analisar com base no tipo de peça selecionado.
"""

from typing import Optional, Set, List
from sqlalchemy.orm import Session

from sistemas.gerador_pecas.models_config_pecas import TipoPeca, CategoriaDocumento


class FiltroCategoriasDocumento:
    """
    Gerencia o filtro de categorias de documentos para cada tipo de peça.
    
    Uso:
        filtro = FiltroCategoriasDocumento(db)
        
        # Para peça manual:
        codigos = filtro.get_codigos_permitidos("contestacao")
        
        # Para modo automático:
        codigos = filtro.get_todos_codigos()
        
        # Verificação:
        if filtro.documento_permitido("contestacao", 9500):
            # processar documento
    """
    
    def __init__(self, db: Session):
        """
        Args:
            db: Sessão do banco de dados
        """
        self.db = db
        self._cache_tipos: dict = {}
        self._cache_todos_codigos: Optional[Set[int]] = None
        self._carregar_cache()
    
    def _carregar_cache(self):
        """Carrega tipos de peça e categorias em cache"""
        tipos = self.db.query(TipoPeca).filter(TipoPeca.ativo == True).all()
        
        for tipo in tipos:
            self._cache_tipos[tipo.nome.lower()] = {
                "id": tipo.id,
                "titulo": tipo.titulo,
                "codigos": tipo.get_codigos_permitidos(),
                "codigos_primeiro_doc": tipo.get_codigos_primeiro_documento()
            }
    
    def get_codigos_permitidos(self, tipo_peca: str) -> Set[int]:
        """
        Retorna os códigos de documento permitidos para um tipo de peça.
        
        Args:
            tipo_peca: Nome do tipo de peça (ex: 'contestacao')
            
        Returns:
            Conjunto de códigos de documento permitidos
        """
        tipo_lower = tipo_peca.lower() if tipo_peca else ""
        
        if tipo_lower in self._cache_tipos:
            return self._cache_tipos[tipo_lower]["codigos"]
        
        # Busca no banco se não estiver em cache
        tipo = self.db.query(TipoPeca).filter(
            TipoPeca.nome.ilike(tipo_peca),
            TipoPeca.ativo == True
        ).first()
        
        if tipo:
            codigos = tipo.get_codigos_permitidos()
            self._cache_tipos[tipo_lower] = {
                "id": tipo.id,
                "titulo": tipo.titulo,
                "codigos": codigos,
                "codigos_primeiro_doc": tipo.get_codigos_primeiro_documento()
            }
            return codigos
        
        # Se não encontrar, retorna conjunto vazio
        return set()
    
    def get_codigos_primeiro_documento(self, tipo_peca: str) -> Set[int]:
        """
        Retorna códigos que devem considerar apenas o primeiro documento cronológico.
        Exemplo: Petição Inicial (só o primeiro 9500/500 do processo).
        
        Args:
            tipo_peca: Nome do tipo de peça
            
        Returns:
            Conjunto de códigos de documentos que devem pegar só o primeiro
        """
        tipo_lower = tipo_peca.lower() if tipo_peca else ""
        
        if tipo_lower in self._cache_tipos:
            return self._cache_tipos[tipo_lower].get("codigos_primeiro_doc", set())
        
        # Busca no banco se não estiver em cache
        tipo = self.db.query(TipoPeca).filter(
            TipoPeca.nome.ilike(tipo_peca),
            TipoPeca.ativo == True
        ).first()
        
        if tipo:
            return tipo.get_codigos_primeiro_documento()
        
        return set()
    
    def get_todos_codigos(self) -> Set[int]:
        """
        Retorna todos os códigos de documento de todas as categorias ativas.
        Usado para modo automático (quando o tipo de peça não foi selecionado).
        
        Returns:
            Conjunto de todos os códigos de documento
        """
        if self._cache_todos_codigos is not None:
            return self._cache_todos_codigos
        
        categorias = self.db.query(CategoriaDocumento).filter(
            CategoriaDocumento.ativo == True
        ).all()
        
        todos_codigos = set()
        for categoria in categorias:
            todos_codigos.update(categoria.get_codigos())
        
        self._cache_todos_codigos = todos_codigos
        return todos_codigos
    
    def documento_permitido(
        self, 
        tipo_peca: Optional[str], 
        codigo_documento: int
    ) -> bool:
        """
        Verifica se um documento é permitido para o tipo de peça.
        
        Args:
            tipo_peca: Nome do tipo de peça (None = modo automático)
            codigo_documento: Código do documento TJ-MS
            
        Returns:
            True se o documento deve ser analisado
        """
        if tipo_peca:
            # Modo manual: usa apenas códigos do tipo de peça
            codigos = self.get_codigos_permitidos(tipo_peca)
        else:
            # Modo automático: usa todos os códigos
            codigos = self.get_todos_codigos()
        
        return codigo_documento in codigos
    
    def filtrar_documentos(
        self,
        documentos: List,
        tipo_peca: Optional[str]
    ) -> List:
        """
        Filtra lista de documentos por tipo de peça.
        
        Aplica lógica especial para categorias marcadas como "primeiro documento"
        (ex: Petição Inicial - pega só o primeiro documento 9500/500 cronologicamente).
        
        Args:
            documentos: Lista de DocumentoTJMS (deve estar ordenada cronologicamente)
            tipo_peca: Nome do tipo de peça (None = modo automático)
            
        Returns:
            Lista filtrada de documentos
        """
        if tipo_peca:
            codigos = self.get_codigos_permitidos(tipo_peca)
            codigos_primeiro_doc = self.get_codigos_primeiro_documento(tipo_peca)
        else:
            codigos = self.get_todos_codigos()
            codigos_primeiro_doc = set()  # No modo automático, não aplica filtro especial
        
        # Filtragem inicial por código
        docs_filtrados = []
        codigos_primeiro_doc_usados = set()  # Rastreia quais códigos especiais já foram usados
        
        for doc in documentos:
            if not doc.tipo_documento:
                continue
                
            codigo = int(doc.tipo_documento)
            
            if codigo not in codigos:
                continue
            
            # Verifica se é código de "primeiro documento"
            if codigo in codigos_primeiro_doc:
                # Se já pegamos um documento com este código, pula os demais
                if codigo in codigos_primeiro_doc_usados:
                    continue
                # Marca como usado (próximos documentos com este código serão ignorados)
                codigos_primeiro_doc_usados.add(codigo)
            
            docs_filtrados.append(doc)
        
        return docs_filtrados
    
    def filtrar_resumos_por_tipo(
        self,
        resumos: List[dict],
        tipo_peca: str
    ) -> List[dict]:
        """
        Filtra resumos já gerados por tipo de peça.
        Usado quando o modo automático gera resumos de tudo e depois 
        precisa filtrar apenas os relevantes para o tipo de peça detectado.
        
        Aplica lógica especial para categorias marcadas como "primeiro documento".
        
        Args:
            resumos: Lista de dicts com campo 'tipo_documento' (deve estar ordenada cronologicamente)
            tipo_peca: Nome do tipo de peça
            
        Returns:
            Lista filtrada de resumos
        """
        codigos = self.get_codigos_permitidos(tipo_peca)
        codigos_primeiro_doc = self.get_codigos_primeiro_documento(tipo_peca)
        
        resumos_filtrados = []
        codigos_primeiro_doc_usados = set()
        
        for resumo in resumos:
            tipo_doc = resumo.get("tipo_documento")
            if not tipo_doc:
                continue
            
            codigo = int(tipo_doc)
            
            if codigo not in codigos:
                continue
            
            # Verifica se é código de "primeiro documento"
            if codigo in codigos_primeiro_doc:
                if codigo in codigos_primeiro_doc_usados:
                    continue
                codigos_primeiro_doc_usados.add(codigo)
            
            resumos_filtrados.append(resumo)
        
        return resumos_filtrados
    
    def get_tipos_peca_disponiveis(self) -> List[dict]:
        """
        Retorna lista de tipos de peça disponíveis para seleção.
        
        Returns:
            Lista de dicts com id, nome, titulo
        """
        tipos = self.db.query(TipoPeca).filter(
            TipoPeca.ativo == True
        ).order_by(TipoPeca.ordem, TipoPeca.titulo).all()
        
        return [
            {
                "id": tipo.id,
                "nome": tipo.nome,
                "titulo": tipo.titulo,
                "icone": tipo.icone,
                "categorias_count": len(tipo.categorias_documento)
            }
            for tipo in tipos
        ]
    
    def tem_configuracao(self) -> bool:
        """
        Verifica se há configuração de tipos de peça no banco.
        
        Returns:
            True se existem tipos de peça configurados
        """
        return len(self._cache_tipos) > 0
    
    def invalidar_cache(self):
        """Invalida o cache para recarregar do banco"""
        self._cache_tipos = {}
        self._cache_todos_codigos = None
        self._carregar_cache()


def get_filtro_categorias(db: Session) -> FiltroCategoriasDocumento:
    """Factory function para criar instância do filtro"""
    return FiltroCategoriasDocumento(db)
