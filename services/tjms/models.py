# services/tjms/models.py
"""
Modelos de dados para integracao com TJ-MS.

Estruturas de dados padronizadas para uso em todos os sistemas.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class TipoConsulta(Enum):
    """Tipo de consulta para otimizacao de payload."""
    COMPLETA = "completa"           # XML + movimentos + documentos
    METADATA_ONLY = "metadata"       # Apenas dados basicos
    MOVIMENTOS_ONLY = "movimentos"   # Dados + movimentos (sem docs)


@dataclass
class ConsultaOptions:
    """Opcoes de consulta customizaveis por sistema."""
    tipo: TipoConsulta = TipoConsulta.COMPLETA
    incluir_movimentos: bool = True
    incluir_documentos: bool = True
    timeout: Optional[float] = None  # None = usar padrao da config

    def __post_init__(self):
        # Ajusta flags baseado no tipo
        if self.tipo == TipoConsulta.METADATA_ONLY:
            self.incluir_movimentos = False
            self.incluir_documentos = False
        elif self.tipo == TipoConsulta.MOVIMENTOS_ONLY:
            self.incluir_documentos = False


@dataclass
class DownloadOptions:
    """Opcoes de download customizaveis por sistema."""
    batch_size: int = 5
    max_paralelo: int = 4
    timeout: Optional[float] = None  # None = usar padrao da config
    extrair_texto: bool = False
    converter_rtf: bool = True
    codigos_permitidos: Optional[List[int]] = None   # Whitelist
    codigos_excluidos: Optional[List[int]] = None    # Blacklist


@dataclass
class Parte:
    """Parte processual (polo ativo ou passivo)."""
    nome: str
    polo: str = ""  # "AT" ou "PA"
    tipo_pessoa: Optional[str] = None  # "fisica" ou "juridica"
    documento: Optional[str] = None     # CPF/CNPJ
    assistencia_judiciaria: bool = False
    tipo_representante: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nome": self.nome,
            "polo": self.polo,
            "tipo_pessoa": self.tipo_pessoa,
            "documento": self.documento,
            "assistencia_judiciaria": self.assistencia_judiciaria,
            "tipo_representante": self.tipo_representante,
        }


@dataclass
class Movimento:
    """Movimento processual."""
    codigo_nacional: Optional[int] = None
    codigo_local: Optional[str] = None
    descricao: str = ""
    data_hora: Optional[datetime] = None
    complemento: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codigo_nacional": self.codigo_nacional,
            "codigo_local": self.codigo_local,
            "descricao": self.descricao,
            "data_hora": self.data_hora.isoformat() if self.data_hora else None,
            "complemento": self.complemento,
        }


@dataclass
class DocumentoMetadata:
    """Metadados de documento (sem conteudo)."""
    id: str
    tipo_codigo: Optional[int] = None
    tipo_descricao: Optional[str] = None
    descricao: Optional[str] = None
    data_juntada: Optional[datetime] = None
    mimetype: Optional[str] = None
    nivel_sigilo: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tipo_codigo": self.tipo_codigo,
            "tipo_descricao": self.tipo_descricao,
            "descricao": self.descricao,
            "data_juntada": self.data_juntada.isoformat() if self.data_juntada else None,
            "mimetype": self.mimetype,
            "nivel_sigilo": self.nivel_sigilo,
        }


@dataclass
class ProcessoTJMS:
    """Processo completo do TJ-MS."""
    numero: str
    numero_formatado: str = ""

    # Dados basicos
    classe_processual: Optional[str] = None
    classe_codigo: Optional[int] = None
    data_ajuizamento: Optional[datetime] = None
    valor_causa: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    competencia: Optional[str] = None
    orgao_julgador: Optional[str] = None

    # Partes
    polo_ativo: List[Parte] = field(default_factory=list)
    polo_passivo: List[Parte] = field(default_factory=list)

    # Movimentos
    movimentos: List[Movimento] = field(default_factory=list)

    # Documentos (metadados apenas)
    documentos: List[DocumentoMetadata] = field(default_factory=list)

    # Processo de origem (para cumprimentos autonomos)
    processo_origem: Optional[str] = None
    is_cumprimento_autonomo: bool = False

    # XML original (para casos especiais)
    xml_raw: Optional[str] = None

    def __post_init__(self):
        if not self.numero_formatado and self.numero:
            self.numero_formatado = self._format_cnj(self.numero)

    @staticmethod
    def _format_cnj(num: str) -> str:
        """Formata numero CNJ."""
        d = "".join(c for c in num if c.isdigit())
        if len(d) != 20:
            return num
        return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13:14]}.{d[14:16]}.{d[16:20]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numero": self.numero,
            "numero_formatado": self.numero_formatado,
            "classe_processual": self.classe_processual,
            "classe_codigo": self.classe_codigo,
            "data_ajuizamento": self.data_ajuizamento.isoformat() if self.data_ajuizamento else None,
            "valor_causa": self.valor_causa,
            "comarca": self.comarca,
            "vara": self.vara,
            "competencia": self.competencia,
            "orgao_julgador": self.orgao_julgador,
            "polo_ativo": [p.to_dict() for p in self.polo_ativo],
            "polo_passivo": [p.to_dict() for p in self.polo_passivo],
            "movimentos": [m.to_dict() for m in self.movimentos],
            "documentos": [d.to_dict() for d in self.documentos],
            "processo_origem": self.processo_origem,
            "is_cumprimento_autonomo": self.is_cumprimento_autonomo,
        }

    def get_autor(self) -> Optional[str]:
        """Retorna nome do autor (primeiro do polo ativo)."""
        if self.polo_ativo:
            return self.polo_ativo[0].nome
        return None

    def get_reu(self) -> Optional[str]:
        """Retorna nome do reu (primeiro do polo passivo)."""
        if self.polo_passivo:
            return self.polo_passivo[0].nome
        return None

    def has_estado_polo_passivo(self) -> bool:
        """Verifica se Estado de MS esta no polo passivo."""
        for parte in self.polo_passivo:
            nome_lower = parte.nome.lower()
            if "estado de mato grosso do sul" in nome_lower or "estado do mato grosso do sul" in nome_lower:
                return True
        return False


@dataclass
class DocumentoTJMS:
    """Documento baixado com conteudo."""
    id: str
    numero_processo: str
    conteudo_bytes: Optional[bytes] = None
    texto_extraido: Optional[str] = None
    formato: str = "pdf"  # pdf, rtf, doc
    erro: Optional[str] = None

    @property
    def sucesso(self) -> bool:
        return self.conteudo_bytes is not None and self.erro is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "numero_processo": self.numero_processo,
            "formato": self.formato,
            "sucesso": self.sucesso,
            "erro": self.erro,
            "tamanho_bytes": len(self.conteudo_bytes) if self.conteudo_bytes else 0,
            "tem_texto": bool(self.texto_extraido),
        }


@dataclass
class ResultadoSubconta:
    """Resultado da extracao de extrato de subconta."""
    numero_processo: str
    status: str  # "ok", "sem_subconta", "erro"
    pdf_bytes: Optional[bytes] = None
    texto_extraido: Optional[str] = None
    erro: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")

    @property
    def sucesso(self) -> bool:
        return self.status == "ok" and self.pdf_bytes is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numero_processo": self.numero_processo,
            "status": self.status,
            "sucesso": self.sucesso,
            "erro": self.erro,
            "timestamp": self.timestamp,
            "tamanho_pdf": len(self.pdf_bytes) if self.pdf_bytes else 0,
            "tem_texto": bool(self.texto_extraido),
        }
