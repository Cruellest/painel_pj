# AGENT.md - Sistema de Geração Automatizada de Peças Jurídicas

## 📋 CONTEXTO DO PROJETO

Este documento especifica o desenvolvimento de um **novo serviço** no Portal PGE para geração automatizada de peças jurídicas (contestações, pareceres, recursos) a partir de processos judiciais do TJ-MS, utilizando IA via OpenRouter/Claude.

### Projeto Base
- **Localização**: `E:\Projetos\PJ\portal-pge`
- **Stack Backend**: FastAPI + Python + SQLAlchemy + PostgreSQL + JWT
- **Stack Frontend**: HTML5 + CSS3 + JavaScript Vanilla + Jinja2 Templates
- **Infraestrutura existente**: Sistema de login, dashboard, usuários, feedbacks
- **Bibliotecas disponíveis**: python-docx, PyMuPDF, lxml, Pillow

### Objetivo
Criar um sistema completo que:
1. Receba o número de um processo judicial
2. Extraia documentos relevantes via API TJ-MS (usando código existente)
3. Envie documentos para IA com prompt especializado
4. Gere peça jurídica em DOCX formatado (padrão ABNT/forense)
5. Permita edição pelo usuário antes de finalizar
6. Tenha controle de acesso por serviço/usuário
7. Sistema integrado de feedback por serviço

---

## 🎯 ESPECIFICAÇÕES FUNCIONAIS

### Fluxo Principal
````
[Usuário digita nº processo]
    ↓
[Sistema consulta API TJ-MS via SOAP]
    ↓
[Extrai documentos relevantes por código]
    ↓
[Verifica se tem Parecer NAT]
    ↓ NÃO tem
[Busca processo de origem (1º grau)]
    ↓
[Baixa PDFs dos documentos relevantes]
    ↓
[Extrai texto dos PDFs (PyMuPDF)]
    ↓
[Monta contexto completo ordenado cronologicamente]
    ↓
[IA analisa e identifica necessidades]
    ↓ TEM DÚVIDA?
[Retorna JSON com pergunta] → [Frontend exibe modal] → [Usuário responde]
    ↓
[IA gera peça jurídica estruturada (JSON)]
    ↓
[Backend converte JSON → DOCX com python-docx]
    ↓
[Retorna URL temporária do DOCX]
    ↓
[Frontend exibe modal de preview/edição]
    ↓
[Usuário edita texto via textarea]
    ↓
[POST /regenerar com texto editado]
    ↓
[Backend regenera DOCX com alterações]
    ↓
[Download do DOCX final]
    ↓
[Salva feedback vinculado ao serviço]
````

### Códigos de Documentos (já implementado)
````python
# src/services/tjms/document_filters.py
ALLOWED_DOCUMENT_CODES = {
    'peticoes': [357, 306, 8320, 8323, 8327, 8333, 215, 8338, 8426, 579, 9875, 8350, 225, 8361, 8365, 8368, 8373, 8388, 8330, 286, 238, 8356, 8367, 8428, 8423, 8380, 8387, 8390, 270, 8392, 8393, 8395, 8315, 8397, 8399, 333, 240, 8438, 9500, 500, 510, 9615, 8326, 239, 93, 330, 21, 209, 30, 8331, 8334, 256, 273, 8336, 8425, 9511, 277, 8303, 25, 9635],
    'despachos': [141, 27, 6],
    'decisoes': [8506, 517, 137, 9653, 9654, 15, 45, 44, 9817],
    'sentencas': [8, 9626, 54],
    'acordaos': [37, 202, 34, 35],
    'recursos': [17, 8435, 576, 9628, 272, 8335, 9629, 9630, 264, 62],
    'parecerNat': [207, 8451, 9636, 59, 8490],
    'outros': [3, 140, 571, 9618, 14, 99010, 99058, 99012, 9522, 9523, 9524, 9534, 9539, 9540, 8369, 9603, 9639, 310, 9501, 9623, 71, 9870, 9509, 9553, 8366]
}
````

**Regra especial**: Se não houver documentos com códigos de `parecerNat`, o sistema deve:
1. Extrair o número do processo de origem do XML (campo `processoVinculado` ou similar)
2. Consultar automaticamente esse processo de 1º grau
3. Buscar os pareceres do NAT no processo original
4. Incluir no contexto para a IA

---

## 🏗️ ARQUITETURA DO SISTEMA

### Estrutura de Diretórios
````
E:\Projetos\PJ\portal-pge\
├── src/
│   ├── api/
│   │   └── routes/
│   │       └── gerador_pecas.py          # Novas rotas da API
│   ├── services/
│   │   ├── tjms/
│   │   │   ├── client.py                 # Cliente SOAP (já existe)
│   │   │   ├── document_filters.py       # Filtros (já existe)
│   │   │   └── parser.py                 # Parser XML (já existe)
│   │   ├── ai/
│   │   │   ├── openrouter_client.py      # Cliente OpenRouter
│   │   │   └── prompts.py                # Prompts de sistema
│   │   ├── docx/
│   │   │   └── generator.py              # Gerador DOCX formatado
│   │   └── gerador_pecas/
│   │       ├── orchestrator.py           # Orquestrador principal
│   │       ├── document_processor.py     # Processamento de PDFs
│   │       └── processo_origem.py        # Busca processo origem
│   ├── models/
│   │   ├── servico.py                    # Modelo de Serviços (novo)
│   │   ├── permissao_servico.py          # Permissões usuário-serviço (novo)
│   │   └── feedback.py                   # Atualizar com campo servico_id
│   └── templates/
│       └── gerador_pecas/
│           └── index.html                # SPA do gerador
├── static/
│   └── js/
│       └── gerador_pecas/
│           ├── app.js                    # Aplicação principal
│           ├── api.js                    # Chamadas à API
│           └── editor.js                 # Editor de texto
└── migrations/
    └── add_servicos_permissions.sql      # Migração do DB
````

---

## 📦 BANCO DE DADOS

### Novos Modelos (SQLAlchemy)

#### 1. Tabela `servicos`
````python
# src/models/servico.py
from sqlalchemy import Column, Integer, String, Boolean, Text
from src.database import Base

class Servico(Base):
    __tablename__ = "servicos"
    
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)  # Ex: "gerador_pecas"
    titulo = Column(String(200), nullable=False)  # Ex: "Gerador de Peças Jurídicas"
    descricao = Column(Text)
    icone = Column(String(50))  # Nome do ícone (ex: "file-text")
    rota = Column(String(100), unique=True)  # Ex: "/gerador-pecas"
    ativo = Column(Boolean, default=True)
    ordem = Column(Integer, default=0)  # Ordem no menu
````

#### 2. Tabela `permissoes_servico`
````python
# src/models/permissao_servico.py
from sqlalchemy import Column, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from src.database import Base

class PermissaoServico(Base):
    __tablename__ = "permissoes_servico"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=False)
    ativo = Column(Boolean, default=True)
    
    usuario = relationship("Usuario", backref="permissoes_servico")
    servico = relationship("Servico", backref="permissoes")
````

#### 3. Atualizar Tabela `feedbacks`
````python
# Adicionar campo em src/models/feedback.py
servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=True)
servico = relationship("Servico", backref="feedbacks")
````

#### 4. Migration SQL
````sql
-- migrations/add_servicos_permissions.sql

-- Criar tabela de serviços
CREATE TABLE servicos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) UNIQUE NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    descricao TEXT,
    icone VARCHAR(50),
    rota VARCHAR(100) UNIQUE,
    ativo BOOLEAN DEFAULT true,
    ordem INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Criar tabela de permissões
CREATE TABLE permissoes_servico (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    servico_id INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(usuario_id, servico_id)
);

-- Adicionar campo servico_id em feedbacks
ALTER TABLE feedbacks 
ADD COLUMN servico_id INTEGER REFERENCES servicos(id) ON DELETE SET NULL;

-- Criar índices
CREATE INDEX idx_permissoes_usuario ON permissoes_servico(usuario_id);
CREATE INDEX idx_permissoes_servico ON permissoes_servico(servico_id);
CREATE INDEX idx_feedbacks_servico ON feedbacks(servico_id);

-- Inserir serviço padrão (Gerador de Peças)
INSERT INTO servicos (nome, titulo, descricao, icone, rota, ordem) VALUES
('gerador_pecas', 'Gerador de Peças Jurídicas', 'Gera contestações, pareceres e recursos automaticamente a partir de processos judiciais', 'file-text', '/gerador-pecas', 1);

-- Inserir outros serviços existentes (se necessário)
INSERT INTO servicos (nome, titulo, descricao, icone, rota, ordem) VALUES
('assistencia_judiciaria', 'Assistência Judiciária', 'Sistema de análise de assistência judiciária', 'scale', '/assistencia-judiciaria', 2),
('matriculas_confrontantes', 'Matrículas Confrontantes', 'Análise de matrículas confrontantes', 'map', '/matriculas-confrontantes', 3);
````

---

## 🔧 IMPLEMENTAÇÃO BACKEND

### 1. Cliente OpenRouter
````python
# src/services/ai/openrouter_client.py
import os
import httpx
from typing import Dict, List, Optional
import json

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    
    async def gerar_peca(
        self, 
        sistema: str, 
        documentos: List[Dict],
        pergunta_usuario: Optional[str] = None
    ) -> Dict:
        """
        Gera peça jurídica via OpenRouter
        
        Returns:
            {
                "tipo": "resposta" | "pergunta",
                "conteudo": {...} | "texto da pergunta",
                "documento": {...estrutura do documento...}
            }
        """
        
        # Monta contexto
        contexto = self._montar_contexto(documentos)
        
        messages = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": contexto}
        ]
        
        if pergunta_usuario:
            messages.append({
                "role": "user", 
                "content": f"Informação adicional: {pergunta_usuario}"
            })
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 8000
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Parse resposta
            content = result['choices'][0]['message']['content']
            
            # Tenta extrair JSON
            try:
                # Remove markdown se houver
                content = content.replace('```json', '').replace('```', '').strip()
                parsed = json.loads(content)
                return parsed
            except json.JSONDecodeError:
                # Se não for JSON válido, trata como erro
                return {
                    "tipo": "erro",
                    "mensagem": "Resposta da IA não está em formato JSON válido"
                }
    
    def _montar_contexto(self, documentos: List[Dict]) -> str:
        """Monta contexto dos documentos para a IA"""
        contexto_parts = []
        
        for doc in documentos:
            contexto_parts.append(f"""
=== {doc['categoria'].upper()}: {doc['titulo']} ===
Data: {doc['data']}
Conteúdo:
{doc['texto'][:50000]}  # Limita tamanho por documento
""")
        
        return "\n\n".join(contexto_parts)
````

### 2. Prompts de Sistema
````python
# src/services/ai/prompts.py

PROMPT_GERADOR_PECAS = """Você é um assistente jurídico especializado da Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua função é analisar processos judiciais e gerar peças jurídicas profissionais (contestações, pareceres, recursos).

## DIRETRIZES GERAIS

1. **Análise Completa**: Leia TODOS os documentos fornecidos cronologicamente
2. **Identificação Automática**: Determine qual tipo de peça é necessária baseado nos documentos
3. **Fundamentação Técnica**: Use jurisprudência e doutrina quando necessário
4. **Linguagem Forense**: Use linguagem técnico-jurídica adequada
5. **Estrutura Formal**: Siga rigorosamente a estrutura padrão de cada tipo de peça

## TIPOS DE PEÇAS

### CONTESTAÇÃO
- Usado quando: Processo em 1º grau, Estado é réu, prazo de contestação em aberto
- Estrutura: Qualificação → Preliminares → Mérito → Pedidos

### RECURSO DE APELAÇÃO
- Usado quando: Sentença desfavorável ao Estado
- Estrutura: Endereçamento → Razões Recursais → Preliminares → Mérito → Pedidos

### CONTRARRAZÕES DE RECURSO
- Usado quando: Parte contrária apresentou recurso
- Estrutura: Endereçamento → Admissibilidade → Mérito → Pedidos

### PARECER JURÍDICO
- Usado quando: Análise técnica de questão jurídica específica
- Estrutura: Relatório → Fundamentação → Conclusão

## QUANDO TEM DÚVIDAS

Se você NÃO conseguir determinar com certeza qual peça gerar ou precisar de informações adicionais, retorne:
```json
{
  "tipo": "pergunta",
  "pergunta": "Qual tipo de peça você deseja gerar? Identifiquei que...",
  "opcoes": ["contestacao", "recurso_apelacao", "contrarrazoes", "parecer"]
}
```

## FORMATO DE RESPOSTA

Quando gerar a peça, retorne JSON estruturado:
```json
{
  "tipo": "resposta",
  "tipo_peca": "contestacao",
  "documento": {
    "cabecalho": {
      "texto": "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ... VARA CÍVEL DA COMARCA DE ...",
      "alinhamento": "direita"
    },
    "qualificacao": {
      "texto": "O ESTADO DE MATO GROSSO DO SUL, pessoa jurídica de direito público interno, por sua Procuradoria-Geral...",
      "recuo_primeira_linha": 1.25,
      "espacamento_linhas": 1.5
    },
    "secoes": [
      {
        "titulo": "I - DOS FATOS",
        "titulo_negrito": true,
        "titulo_caixa_alta": true,
        "paragrafos": [
          {
            "tipo": "normal",
            "texto": "Trata-se de ação...",
            "numerado": true,
            "justificado": true,
            "recuo_primeira_linha": 1.25
          },
          {
            "tipo": "citacao",
            "texto": "Texto literal da citação doutrinária ou jurisprudencial...",
            "fonte": "AUTOR. Obra. Edição. Local: Editora, Ano, p. XX."
          }
        ]
      },
      {
        "titulo": "II - DO DIREITO",
        "paragrafos": [...]
      },
      {
        "titulo": "III - DOS PEDIDOS",
        "paragrafos": [...]
      }
    ],
    "fecho": {
      "local_data": "Campo Grande/MS, [DATA_AUTOMATICA]",
      "assinatura": "[NOME_PROCURADOR]\\n[CARGO]\\nOAB/MS nº [NUMERO]"
    }
  }
}
```

## FORMATAÇÃO ESPECIAL

### Citações Longas (3+ linhas)
- Use `"tipo": "citacao"`
- Recuo de 3cm (esquerda e direita)
- Fonte 11, espaçamento simples
- Sempre inclua a fonte completa

### Parágrafos Normais
- Recuo primeira linha: 1.25cm
- Espaçamento: 1.5
- Justificado
- Fonte 12

### Títulos de Seções
- Centralizados
- Negrito
- Caixa alta
- Numeração romana (I, II, III...)

## INFORMAÇÕES CONTEXTUAIS

- **Comarca**: Extrair dos documentos
- **Número do Processo**: Extrair e formatar (NNNNNNN-DD.AAAA.J.TR.OOOO)
- **Partes**: Identificar autor e réu
- **Valor da Causa**: Mencionar se relevante
- **Data Atual**: Usar [DATA_AUTOMATICA] que será substituída no backend

## ANÁLISE DO PARECER DO NAT

Se houver Parecer do Núcleo de Assessoria Técnica (NAT) nos documentos:
- Analise cuidadosamente as conclusões técnicas
- Incorpore os fundamentos técnico-científicos na peça
- Cite o parecer quando necessário
- Use como base para contestar laudos da parte contrária

## QUALIDADE E REVISÃO

- Verifique todos os nomes próprios (partes, comarca, vara)
- Confirme valores e datas
- Garanta coerência argumentativa
- Evite repetições desnecessárias
- Seja objetivo e direto

## IMPORTANTE

- NUNCA invente fatos não presentes nos documentos
- SEMPRE fundamente tecnicamente seus argumentos
- Use dispositivos legais completos (Lei nº X, art. Y, § Z)
- Cite jurisprudência quando houver (STF, STJ, TJMS)
- Mantenha tom formal e respeitoso
"""

def get_prompt_sistema(tipo_peca: Optional[str] = None) -> str:
    """Retorna prompt de sistema, opcionalmente customizado por tipo"""
    
    if tipo_peca == "contestacao":
        return PROMPT_GERADOR_PECAS + "\n\nFOCO: Gere uma CONTESTAÇÃO completa."
    elif tipo_peca == "recurso":
        return PROMPT_GERADOR_PECAS + "\n\nFOCO: Gere um RECURSO DE APELAÇÃO."
    elif tipo_peca == "contrarrazoes":
        return PROMPT_GERADOR_PECAS + "\n\nFOCO: Gere CONTRARRAZÕES DE RECURSO."
    
    return PROMPT_GERADOR_PECAS
````

### 3. Gerador DOCX
````python
# src/services/docx/generator.py
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from typing import Dict
from datetime import datetime

class DocxGenerator:
    def __init__(self):
        self.fonte_padrao = 'Arial'
        self.tamanho_fonte_normal = 12
        self.tamanho_fonte_citacao = 11
        self.tamanho_fonte_fonte = 10
    
    def gerar_documento(self, conteudo: Dict, numero_processo: str) -> Document:
        """Gera documento Word formatado"""
        
        doc = Document()
        self._configurar_margens(doc)
        
        # 1. Cabeçalho
        if 'cabecalho' in conteudo:
            self._adicionar_cabecalho(doc, conteudo['cabecalho'])
        
        # 2. Qualificação
        if 'qualificacao' in conteudo:
            self._adicionar_qualificacao(doc, conteudo['qualificacao'])
        
        # 3. Seções
        for secao in conteudo.get('secoes', []):
            self._adicionar_secao(doc, secao)
        
        # 4. Fecho
        if 'fecho' in conteudo:
            self._adicionar_fecho(doc, conteudo['fecho'])
        
        return doc
    
    def _configurar_margens(self, doc: Document):
        """Configura margens ABNT: 3cm esq/sup, 2cm dir/inf"""
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1.18)     # 3cm
            section.bottom_margin = Inches(0.79)   # 2cm
            section.left_margin = Inches(1.18)     # 3cm
            section.right_margin = Inches(0.79)    # 2cm
    
    def _adicionar_cabecalho(self, doc: Document, cabecalho: Dict):
        """Adiciona cabeçalho do documento"""
        p = doc.add_paragraph(cabecalho['texto'])
        
        if cabecalho.get('alinhamento') == 'direita':
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif cabecalho.get('alinhamento') == 'centro':
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        self._aplicar_fonte(p, self.tamanho_fonte_normal)
        p.paragraph_format.space_after = Pt(cabecalho.get('espacamento_depois', 12))
    
    def _adicionar_qualificacao(self, doc: Document, qualificacao: Dict):
        """Adiciona qualificação das partes"""
        p = doc.add_paragraph(qualificacao['texto'])
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.first_line_indent = Inches(
            qualificacao.get('recuo_primeira_linha', 1.25)
        )
        p.paragraph_format.line_spacing = qualificacao.get('espacamento_linhas', 1.5)
        self._aplicar_fonte(p, self.tamanho_fonte_normal)
        p.paragraph_format.space_after = Pt(12)
    
    def _adicionar_secao(self, doc: Document, secao: Dict):
        """Adiciona seção com título e parágrafos"""
        
        # Título
        p_titulo = doc.add_paragraph(secao['titulo'])
        p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._aplicar_fonte(p_titulo, self.tamanho_fonte_normal, bold=True)
        
        if secao.get('titulo_caixa_alta'):
            p_titulo.runs[0].text = p_titulo.runs[0].text.upper()
        
        p_titulo.paragraph_format.space_before = Pt(12)
        p_titulo.paragraph_format.space_after = Pt(12)
        
        # Parágrafos
        contador = 1
        for paragrafo in secao.get('paragrafos', []):
            if paragrafo.get('tipo') == 'citacao':
                self._adicionar_citacao(doc, paragrafo)
            else:
                self._adicionar_paragrafo_normal(doc, paragrafo, contador)
                if paragrafo.get('numerado'):
                    contador += 1
    
    def _adicionar_paragrafo_normal(self, doc: Document, paragrafo: Dict, numero: int):
        """Adiciona parágrafo normal"""
        texto = paragrafo['texto']
        
        if paragrafo.get('numerado'):
            texto = f"{numero}. {texto}"
        
        p = doc.add_paragraph(texto)
        
        if paragrafo.get('justificado', True):
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        
        p.paragraph_format.first_line_indent = Inches(
            paragrafo.get('recuo_primeira_linha', 1.25)
        )
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(6)
        
        self._aplicar_fonte(p, self.tamanho_fonte_normal)
    
    def _adicionar_citacao(self, doc: Document, citacao: Dict):
        """Adiciona citação com formatação especial (recuo 3cm, fonte 11)"""
        
        # Citação
        p = doc.add_paragraph(citacao['texto'])
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        
        # Recuos de 3cm
        p.paragraph_format.left_indent = Inches(1.18)   # 3cm
        p.paragraph_format.right_indent = Inches(1.18)  # 3cm
        p.paragraph_format.first_line_indent = Inches(0)  # Sem recuo primeira linha
        
        # Espaçamento simples
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        
        # Fonte menor
        self._aplicar_fonte(p, self.tamanho_fonte_citacao)
        
        # Fonte/referência
        if 'fonte' in citacao:
            p_fonte = doc.add_paragraph(citacao['fonte'])
            p_fonte.paragraph_format.left_indent = Inches(1.18)
            p_fonte.paragraph_format.right_indent = Inches(1.18)
            p_fonte.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p_fonte.paragraph_format.space_after = Pt(12)
            self._aplicar_fonte(p_fonte, self.tamanho_fonte_fonte)
    
    def _adicionar_fecho(self, doc: Document, fecho: Dict):
        """Adiciona fecho do documento (local/data e assinatura)"""
        
        # Local e data
        if 'local_data' in fecho:
            p_local = doc.add_paragraph()
            p_local.paragraph_format.space_before = Pt(24)
            
            texto_local = fecho['local_data']
            # Substituir placeholder de data
            if '[DATA_AUTOMATICA]' in texto_local:
                texto_local = texto_local.replace(
                    '[DATA_AUTOMATICA]', 
                    datetime.now().strftime('%d de %B de %Y')
                )
            
            p_local.add_run(texto_local)
            p_local.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            self._aplicar_fonte(p_local, self.tamanho_fonte_normal)
        
        # Assinatura
        if 'assinatura' in fecho:
            p_assinatura = doc.add_paragraph()
            p_assinatura.paragraph_format.space_before = Pt(36)
            
            # Quebrar linhas \\n
            linhas = fecho['assinatura'].split('\\n')
            for i, linha in enumerate(linhas):
                if i > 0:
                    p_assinatura.add_run('\n')
                p_assinatura.add_run(linha)
            
            p_assinatura.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._aplicar_fonte(p_assinatura, self.tamanho_fonte_normal)
    
    def _aplicar_fonte(self, paragraph, size: int, bold: bool = False):
        """Aplica formatação de fonte a um parágrafo"""
        for run in paragraph.runs:
            run.font.name = self.fonte_padrao
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor(0, 0, 0)
    
    def salvar(self, doc: Document, caminho: str):
        """Salva documento em disco"""
        doc.save(caminho)
````

### 4. Processador de Documentos
````python
# src/services/gerador_pecas/document_processor.py
import fitz  # PyMuPDF
from typing import List, Dict
import base64
from io import BytesIO

class DocumentProcessor:
    def __init__(self):
        self.max_chars_per_doc = 50000  # Limite por documento
    
    def extrair_texto_pdf(self, pdf_bytes: bytes) -> str:
        """Extrai texto de PDF usando PyMuPDF"""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texto_completo = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                texto = page.get_text()
                texto_completo.append(texto)
            
            doc.close()
            
            texto_final = "\n\n".join(texto_completo)
            
            # Limitar tamanho
            if len(texto_final) > self.max_chars_per_doc:
                texto_final = texto_final[:self.max_chars_per_doc] + "\n\n[DOCUMENTO TRUNCADO - MUITO LONGO]"
            
            return texto_final
            
        except Exception as e:
            return f"[ERRO AO EXTRAIR TEXTO: {str(e)}]"
    
    def processar_documentos(self, documentos_raw: List[Dict]) -> List[Dict]:
        """
        Processa lista de documentos, extrai texto e retorna estrutura para IA
        
        Args:
            documentos_raw: Lista de dicts com {id, titulo, categoria, data, pdf_base64}
        
        Returns:
            Lista de dicts com {titulo, categoria, data, texto}
        """
        documentos_processados = []
        
        for doc in documentos_raw:
            try:
                # Decodificar base64
                pdf_bytes = base64.b64decode(doc['pdf_base64'])
                
                # Extrair texto
                texto = self.extrair_texto_pdf(pdf_bytes)
                
                documentos_processados.append({
                    'titulo': doc['titulo'],
                    'categoria': doc['categoria'],
                    'data': doc['data'],
                    'texto': texto
                })
                
            except Exception as e:
                print(f"Erro ao processar documento {doc['titulo']}: {str(e)}")
                continue
        
        return documentos_processados
````

### 5. Orquestrador Principal
````python
# src/services/gerador_pecas/orchestrator.py
from typing import Dict, List, Optional
from src.services.tjms.client import consultarProcesso, baixarDocumento
from src.services.ai.openrouter_client import OpenRouterClient
from src.services.ai.prompts import get_prompt_sistema
from src.services.docx.generator import DocxGenerator
from src.services.gerador_pecas.document_processor import DocumentProcessor
from src.services.gerador_pecas.processo_origem import buscar_processo_origem
import os
import uuid

class GeradorPecasOrchestrator:
    def __init__(self):
        self.ai_client = OpenRouterClient()
        self.docx_generator = DocxGenerator()
        self.doc_processor = DocumentProcessor()
        self.temp_dir = "/tmp/gerador_pecas"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def processar_processo(
        self, 
        numero_cnj: str,
        tipo_peca: Optional[str] = None,
        resposta_usuario: Optional[str] = None
    ) -> Dict:
        """
        Fluxo completo de geração de peça
        
        Returns:
            {
                "status": "sucesso" | "pergunta" | "erro",
                "pergunta": str (se status == "pergunta"),
                "url_download": str (se status == "sucesso"),
                "mensagem": str
            }
        """
        
        try:
            # 1. Consultar processo no TJ-MS
            print(f"[Orquestrador] Consultando processo {numero_cnj}")
            processo = await consultarProcesso(numero_cnj)
            
            # 2. Verificar se tem Parecer do NAT
            tem_parecer_nat = any(
                doc['categoria'] == 'Parecer NAT' 
                for doc in processo['documentos']
            )
            
            # 3. Se não tem parecer e é 2º grau, buscar processo de origem
            documentos_completos = processo['documentos'].copy()
            
            if not tem_parecer_nat and processo['instancia'] == 2:
                print("[Orquestrador] Sem parecer NAT, buscando processo origem...")
                docs_origem = await buscar_processo_origem(numero_cnj)
                documentos_completos.extend(docs_origem)
            
            # 4. Baixar PDFs dos documentos
            print(f"[Orquestrador] Baixando {len(documentos_completos)} documentos")
            documentos_com_pdf = []
            
            for doc in documentos_completos:
                if doc['temConteudo']:
                    try:
                        pdf_blob = await baixarDocumento(doc['id'], numero_cnj)
                        pdf_bytes = await pdf_blob.arrayBuffer()
                        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                        
                        documentos_com_pdf.append({
                            **doc,
                            'pdf_base64': pdf_base64
                        })
                    except Exception as e:
                        print(f"Erro ao baixar doc {doc['id']}: {str(e)}")
                        continue
            
            # 5. Extrair texto dos PDFs
            print("[Orquestrador] Extraindo texto dos PDFs")
            documentos_processados = self.doc_processor.processar_documentos(
                documentos_com_pdf
            )
            
            # 6. Ordenar cronologicamente
            documentos_processados.sort(key=lambda d: d['data'])
            
            # 7. Enviar para IA
            print("[Orquestrador] Enviando para IA")
            prompt_sistema = get_prompt_sistema(tipo_peca)
            
            resposta_ia = await self.ai_client.gerar_peca(
                sistema=prompt_sistema,
                documentos=documentos_processados,
                pergunta_usuario=resposta_usuario
            )
            
            # 8. Processar resposta
            if resposta_ia['tipo'] == 'pergunta':
                return {
                    "status": "pergunta",
                    "pergunta": resposta_ia['pergunta'],
                    "opcoes": resposta_ia.get('opcoes', [])
                }
            
            elif resposta_ia['tipo'] == 'resposta':
                # Gerar DOCX
                print("[Orquestrador] Gerando DOCX")
                doc = self.docx_generator.gerar_documento(
                    resposta_ia['documento'],
                    numero_cnj
                )
                
                # Salvar temporariamente
                filename = f"{uuid.uuid4()}.docx"
                filepath = os.path.join(self.temp_dir, filename)
                self.docx_generator.salvar(doc, filepath)
                
                return {
                    "status": "sucesso",
                    "url_download": f"/api/gerador-pecas/download/{filename}",
                    "tipo_peca": resposta_ia['tipo_peca'],
                    "conteudo_json": resposta_ia['documento']  # Para edição
                }
            
            else:
                return {
                    "status": "erro",
                    "mensagem": resposta_ia.get('mensagem', 'Erro desconhecido')
                }
        
        except Exception as e:
            print(f"[Orquestrador] Erro: {str(e)}")
            return {
                "status": "erro",
                "mensagem": str(e)
            }
````

### 6. Busca Processo de Origem
````python
# src/services/gerador_pecas/processo_origem.py
from typing import List, Dict
from src.services.tjms.client import consultarProcesso
from src.services.tjms.document_filters import ALLOWED_DOCUMENT_CODES

async def buscar_processo_origem(numero_cnj_recurso: str) -> List[Dict]:
    """
    Busca processo de origem (1º grau) a partir de um recurso/processo de 2º grau
    
    Returns:
        Lista de documentos (filtrados: apenas pareceres do NAT)
    """
    
    try:
        # 1. Consultar processo de 2º grau
        processo_recurso = await consultarProcesso(numero_cnj_recurso)
        
        # 2. Extrair número do processo de origem
        # (Normalmente vem em campo específico do XML ou nas movimentações)
        numero_origem = extrair_numero_origem(processo_recurso)
        
        if not numero_origem:
            print("[Processo Origem] Não encontrado número do processo de origem")
            return []
        
        print(f"[Processo Origem] Encontrado: {numero_origem}")
        
        # 3. Consultar processo de origem
        processo_origem = await consultarProcesso(numero_origem)
        
        # 4. Filtrar apenas pareceres do NAT
        pareceres_nat = [
            doc for doc in processo_origem['documentos']
            if doc['categoria'] == 'Parecer NAT'
        ]
        
        print(f"[Processo Origem] {len(pareceres_nat)} pareceres NAT encontrados")
        
        return pareceres_nat
        
    except Exception as e:
        print(f"[Processo Origem] Erro: {str(e)}")
        return []

def extrair_numero_origem(processo: Dict) -> str:
    """
    Extrai número do processo de origem a partir dos dados do processo de 2º grau
    
    Estratégias:
    1. Campo específico 'processoVinculado' no XML
    2. Primeira movimentação com texto "Remetidos os autos do processo nº..."
    3. Campo 'outroParametro' com nome="processoOrigem"
    """
    
    # Estratégia 1: Campo direto (se existir)
    if 'processoOrigem' in processo:
        return processo['processoOrigem']
    
    # Estratégia 2: Buscar nas movimentações
    import re
    for mov in processo.get('movimentacoes', []):
        texto = mov.get('complemento', '') + ' ' + mov.get('descricao', '')
        
        # Procurar por número CNJ no texto
        match = re.search(r'(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})', texto)
        if match:
            return match.group(1)
    
    return None
````

### 7. Rotas da API
````python
# src/api/routes/gerador_pecas.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from src.database import get_db
from src.models.usuario import Usuario
from src.models.servico import Servico
from src.models.permissao_servico import PermissaoServico
from src.models.feedback import Feedback
from src.api.auth import get_current_user
from src.services.gerador_pecas.orchestrator import GeradorPecasOrchestrator
from pydantic import BaseModel
from typing import Optional
import os

router = APIRouter(prefix="/api/gerador-pecas", tags=["Gerador de Peças"])

class ProcessarProcessoRequest(BaseModel):
    numero_cnj: str
    tipo_peca: Optional[str] = None
    resposta_usuario: Optional[str] = None

class RegenerarDocxRequest(BaseModel):
    conteudo_editado: str  # JSON string do documento editado

class FeedbackRequest(BaseModel):
    nota: int  # 1-5
    comentario: Optional[str] = None
    numero_processo: str
    tipo_peca: str

# Dependency: verificar permissão
async def verificar_permissao(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verifica se usuário tem permissão para usar o serviço"""
    
    servico = db.query(Servico).filter(Servico.nome == "gerador_pecas").first()
    if not servico:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço não configurado"
        )
    
    permissao = db.query(PermissaoServico).filter(
        PermissaoServico.usuario_id == current_user.id,
        PermissaoServico.servico_id == servico.id,
        PermissaoServico.ativo == True
    ).first()
    
    if not permissao:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para usar este serviço"
        )
    
    return servico

@router.post("/processar")
async def processar_processo(
    request: ProcessarProcessoRequest,
    servico: Servico = Depends(verificar_permissao),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Processa um processo e gera a peça jurídica
    
    Returns:
        - Se status == "pergunta": {"pergunta": "...", "opcoes": [...]}
        - Se status == "sucesso": {"url_download": "...", "tipo_peca": "...", "conteudo_json": {...}}
        - Se status == "erro": {"mensagem": "..."}
    """
    
    orchestrator = GeradorPecasOrchestrator()
    
    resultado = await orchestrator.processar_processo(
        numero_cnj=request.numero_cnj,
        tipo_peca=request.tipo_peca,
        resposta_usuario=request.resposta_usuario
    )
    
    return resultado

@router.post("/regenerar")
async def regenerar_docx(
    request: RegenerarDocxRequest,
    servico: Servico = Depends(verificar_permissao),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Regenera o DOCX com conteúdo editado pelo usuário
    """
    import json
    
    try:
        conteudo_json = json.loads(request.conteudo_editado)
        
        from src.services.docx.generator import DocxGenerator
        import uuid
        
        generator = DocxGenerator()
        doc = generator.gerar_documento(conteudo_json, "editado")
        
        filename = f"{uuid.uuid4()}.docx"
        filepath = os.path.join("/tmp/gerador_pecas", filename)
        generator.salvar(doc, filepath)
        
        return {
            "status": "sucesso",
            "url_download": f"/api/gerador-pecas/download/{filename}"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao regenerar documento: {str(e)}"
        )

@router.get("/download/{filename}")
async def download_documento(
    filename: str,
    servico: Servico = Depends(verificar_permissao),
    current_user: Usuario = Depends(get_current_user)
):
    """Download do documento gerado"""
    
    filepath = os.path.join("/tmp/gerador_pecas", filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado ou expirado"
        )
    
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"peca_judicial_{filename}"
    )

@router.post("/feedback")
async def enviar_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db),
    servico: Servico = Depends(verificar_permissao),
    current_user: Usuario = Depends(get_current_user)
):
    """Salva feedback do usuário"""
    
    feedback = Feedback(
        usuario_id=current_user.id,
        servico_id=servico.id,
        nota=request.nota,
        comentario=request.comentario,
        metadata={
            "numero_processo": request.numero_processo,
            "tipo_peca": request.tipo_peca
        }
    )
    
    db.add(feedback)
    db.commit()
    
    return {"status": "sucesso", "mensagem": "Feedback registrado com sucesso"}
````

---

## 🎨 IMPLEMENTAÇÃO FRONTEND

### 1. Template Principal (Jinja2)
````html
<!-- templates/gerador_pecas/index.html -->
{% extends "base.html" %}

{% block title %}Gerador de Peças Jurídicas{% endblock %}

{% block content %}
<div id="app-gerador-pecas" class="container mx-auto p-6">
    <!-- Header -->
    <header class="mb-8">
        <h1 class="text-3xl font-bold text-gray-800">Gerador de Peças Jurídicas</h1>
        <p class="text-gray-600 mt-2">
            Sistema inteligente de geração automatizada de contestações, pareceres e recursos
        </p>
    </header>

    <!-- Formulário Principal -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
        <form id="form-processo" class="space-y-4">
            <div>
                <label for="numero-cnj" class="block text-sm font-medium text-gray-700 mb-2">
                    Número do Processo (CNJ)
                </label>
                <input 
                    type="text" 
                    id="numero-cnj" 
                    name="numero_cnj"
                    placeholder="0000000-00.2024.8.12.0001"
                    class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    required
                />
            </div>

            <div id="tipo-peca-container" class="hidden">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    Tipo de Peça (opcional)
                </label>
                <select 
                    id="tipo-peca" 
                    name="tipo_peca"
                    class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                    <option value="">Detectar automaticamente</option>
                    <option value="contestacao">Contestação</option>
                    <option value="recurso_apelacao">Recurso de Apelação</option>
                    <option value="contrarrazoes">Contrarrazões</option>
                    <option value="parecer">Parecer Jurídico</option>
                </select>
            </div>

            <button 
                type="submit" 
                id="btn-gerar"
                class="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
            >
                Gerar Peça Jurídica
            </button>
        </form>
    </div>

    <!-- Loading -->
    <div id="loading" class="hidden bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
        <div class="flex items-center">
            <svg class="animate-spin h-5 w-5 mr-3 text-blue-600" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <div>
                <p class="font-semibold text-blue-800">Processando...</p>
                <p id="loading-message" class="text-sm text-blue-600">Consultando processo no TJ-MS</p>
            </div>
        </div>
    </div>

    <!-- Modal de Pergunta -->
    <div id="modal-pergunta" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-8 max-w-2xl w-full mx-4">
            <h2 class="text-2xl font-bold mb-4">Informação Necessária</h2>
            <p id="pergunta-texto" class="text-gray-700 mb-6"></p>
            
            <div id="opcoes-container" class="space-y-2 mb-6"></div>
            
            <textarea 
                id="resposta-usuario" 
                placeholder="Ou digite sua resposta aqui..."
                class="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
                rows="3"
            ></textarea>
            
            <div class="flex justify-end space-x-3">
                <button 
                    id="btn-cancelar-pergunta"
                    class="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                    Cancelar
                </button>
                <button 
                    id="btn-enviar-resposta"
                    class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                    Continuar
                </button>
            </div>
        </div>
    </div>

    <!-- Modal de Edição -->
    <div id="modal-edicao" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-8 max-w-6xl w-full mx-4 max-h-[90vh] flex flex-col">
            <h2 class="text-2xl font-bold mb-4">Revisar e Editar Documento</h2>
            
            <div class="flex-1 overflow-y-auto mb-6 border border-gray-300 rounded-lg p-4">
                <div id="preview-container" class="prose max-w-none"></div>
            </div>
            
            <div class="flex justify-between items-center">
                <button 
                    id="btn-editar-texto"
                    class="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                    ✏️ Editar Texto
                </button>
                
                <div class="space-x-3">
                    <button 
                        id="btn-cancelar-edicao"
                        class="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                        Cancelar
                    </button>
                    <button 
                        id="btn-download"
                        class="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                    >
                        📥 Download DOCX
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal de Feedback -->
    <div id="modal-feedback" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-8 max-w-md w-full mx-4">
            <h2 class="text-2xl font-bold mb-4">Como foi a experiência?</h2>
            <p class="text-gray-600 mb-6">Seu feedback nos ajuda a melhorar o sistema</p>
            
            <!-- Estrelas -->
            <div class="flex justify-center space-x-2 mb-6">
                <button class="estrela text-4xl text-gray-300 hover:text-yellow-400" data-nota="1">★</button>
                <button class="estrela text-4xl text-gray-300 hover:text-yellow-400" data-nota="2">★</button>
                <button class="estrela text-4xl text-gray-300 hover:text-yellow-400" data-nota="3">★</button>
                <button class="estrela text-4xl text-gray-300 hover:text-yellow-400" data-nota="4">★</button>
                <button class="estrela text-4xl text-gray-300 hover:text-yellow-400" data-nota="5">★</button>
            </div>
            
            <textarea 
                id="feedback-comentario" 
                placeholder="Comentários adicionais (opcional)"
                class="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
                rows="3"
            ></textarea>
            
            <div class="flex justify-end space-x-3">
                <button 
                    id="btn-pular-feedback"
                    class="px-6 py-2 text-gray-600 hover:text-gray-800"
                >
                    Pular
                </button>
                <button 
                    id="btn-enviar-feedback"
                    class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    disabled
                >
                    Enviar Feedback
                </button>
            </div>
        </div>
    </div>
</div>

<script src="/static/js/gerador_pecas/app.js"></script>
{% endblock %}
````

### 2. JavaScript Principal
````javascript
// static/js/gerador_pecas/app.js

class GeradorPecasApp {
    constructor() {
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.conteudoJSON = null;
        this.urlDownload = null;
        
        this.initEventListeners();
    }
    
    initEventListeners() {
        // Form submit
        document.getElementById('form-processo').addEventListener('submit', (e) => {
            e.preventDefault();
            this.iniciarProcessamento();
        });
        
        // Modal pergunta
        document.getElementById('btn-cancelar-pergunta').addEventListener('click', () => {
            this.fecharModal('modal-pergunta');
        });
        
        document.getElementById('btn-enviar-resposta').addEventListener('click', () => {
            this.enviarResposta();
        });
        
        // Modal edição
        document.getElementById('btn-cancelar-edicao').addEventListener('click', () => {
            this.fecharModal('modal-edicao');
        });
        
        document.getElementById('btn-download').addEventListener('click', () => {
            this.download();
        });
        
        // Feedback
        document.querySelectorAll('.estrela').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.selecionarNota(parseInt(e.target.dataset.nota));
            });
        });
        
        document.getElementById('btn-pular-feedback').addEventListener('click', () => {
            this.fecharModal('modal-feedback');
            this.resetar();
        });
        
        document.getElementById('btn-enviar-feedback').addEventListener('click', () => {
            this.enviarFeedback();
        });
    }
    
    async iniciarProcessamento() {
        this.numeroCNJ = document.getElementById('numero-cnj').value;
        this.tipoPeca = document.getElementById('tipo-peca').value || null;
        
        this.mostrarLoading('Consultando processo no TJ-MS...');
        
        try {
            const response = await fetch('/api/gerador-pecas/processar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: this.numeroCNJ,
                    tipo_peca: this.tipoPeca
                })
            });
            
            const data = await response.json();
            
            if (data.status === 'pergunta') {
                this.exibirPergunta(data);
            } else if (data.status === 'sucesso') {
                this.exibirPreview(data);
            } else {
                alert('Erro: ' + data.mensagem);
            }
            
        } catch (error) {
            alert('Erro ao processar: ' + error.message);
        } finally {
            this.esconderLoading();
        }
    }
    
    exibirPergunta(data) {
        document.getElementById('pergunta-texto').textContent = data.pergunta;
        
        const opcoesContainer = document.getElementById('opcoes-container');
        opcoesContainer.innerHTML = '';
        
        if (data.opcoes && data.opcoes.length > 0) {
            data.opcoes.forEach(opcao => {
                const btn = document.createElement('button');
                btn.className = 'w-full px-4 py-3 text-left border border-gray-300 rounded-lg hover:bg-blue-50 hover:border-blue-500';
                btn.textContent = this.formatarOpcao(opcao);
                btn.addEventListener('click', () => {
                    this.tipoPeca = opcao;
                    this.enviarResposta();
                });
                opcoesContainer.appendChild(btn);
            });
        }
        
        this.abrirModal('modal-pergunta');
    }
    
    async enviarResposta() {
        const resposta = document.getElementById('resposta-usuario').value || this.tipoPeca;
        
        this.fecharModal('modal-pergunta');
        this.mostrarLoading('Gerando documento...');
        
        try {
            const response = await fetch('/api/gerador-pecas/processar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    numero_cnj: this.numeroCNJ,
                    tipo_peca: this.tipoPeca,
                    resposta_usuario: resposta
                })
            });
            
            const data = await response.json();
            
            if (data.status === 'sucesso') {
                this.exibirPreview(data);
            } else {
                alert('Erro: ' + data.mensagem);
            }
            
        } catch (error) {
            alert('Erro: ' + error.message);
        } finally {
            this.esconderLoading();
        }
    }
    
    exibirPreview(data) {
        this.urlDownload = data.url_download;
        this.conteudoJSON = data.conteudo_json;
        this.tipoPeca = data.tipo_peca;
        
        // Renderizar preview
        const previewContainer = document.getElementById('preview-container');
        previewContainer.innerHTML = this.renderizarPreview(data.conteudo_json);
        
        this.abrirModal('modal-edicao');
    }
    
    renderizarPreview(conteudo) {
        let html = '';
        
        // Cabeçalho
        if (conteudo.cabecalho) {
            html += `<div class="text-right mb-4">${conteudo.cabecalho.texto}</div>`;
        }
        
        // Qualificação
        if (conteudo.qualificacao) {
            html += `<p class="mb-4 text-justify">${conteudo.qualificacao.texto}</p>`;
        }
        
        // Seções
        conteudo.secoes.forEach(secao => {
            html += `<h2 class="text-center font-bold my-4">${secao.titulo}</h2>`;
            
            secao.paragrafos.forEach((p, i) => {
                if (p.tipo === 'citacao') {
                    html += `<blockquote class="border-l-4 border-gray-300 pl-4 italic my-2 text-sm">${p.texto}</blockquote>`;
                    if (p.fonte) {
                        html += `<p class="text-xs text-right text-gray-600 mb-2">${p.fonte}</p>`;
                    }
                } else {
                    const numero = p.numerado ? `${i + 1}. ` : '';
                    html += `<p class="mb-2 text-justify">${numero}${p.texto}</p>`;
                }
            });
        });
        
        // Fecho
        if (conteudo.fecho) {
            html += `<div class="text-right mt-8">${conteudo.fecho.local_data}</div>`;
            html += `<div class="text-center mt-8">${conteudo.fecho.assinatura.replace(/\\n/g, '<br>')}</div>`;
        }
        
        return html;
    }
    
    async download() {
        this.fecharModal('modal-edicao');
        
        // Iniciar download
        const link = document.createElement('a');
        link.href = this.urlDownload;
        link.download = `peca_${this.numeroCNJ.replace(/[\/\-\.]/g, '_')}.docx`;
        link.click();
        
        // Aguardar 1s e abrir modal de feedback
        setTimeout(() => {
            this.abrirModal('modal-feedback');
        }, 1000);
    }
    
    selecionarNota(nota) {
        this.notaSelecionada = nota;
        
        document.querySelectorAll('.estrela').forEach((btn, idx) => {
            if (idx < nota) {
                btn.classList.add('text-yellow-400');
                btn.classList.remove('text-gray-300');
            } else {
                btn.classList.remove('text-yellow-400');
                btn.classList.add('text-gray-300');
            }
        });
        
        document.getElementById('btn-enviar-feedback').disabled = false;
    }
    
    async enviarFeedback() {
        const comentario = document.getElementById('feedback-comentario').value;
        
        try {
            await fetch('/api/gerador-pecas/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({
                    nota: this.notaSelecionada,
                    comentario: comentario || null,
                    numero_processo: this.numeroCNJ,
                    tipo_peca: this.tipoPeca
                })
            });
            
            alert('Feedback enviado! Obrigado!');
            
        } catch (error) {
            console.error('Erro ao enviar feedback:', error);
        } finally {
            this.fecharModal('modal-feedback');
            this.resetar();
        }
    }
    
    // Utilitários
    mostrarLoading(mensagem) {
        document.getElementById('loading-message').textContent = mensagem;
        document.getElementById('loading').classList.remove('hidden');
    }
    
    esconderLoading() {
        document.getElementById('loading').classList.add('hidden');
    }
    
    abrirModal(id) {
        document.getElementById(id).classList.remove('hidden');
    }
    
    fecharModal(id) {
        document.getElementById(id).classList.add('hidden');
    }
    
    formatarOpcao(opcao) {
        const labels = {
            'contestacao': 'Contestação',
            'recurso_apelacao': 'Recurso de Apelação',
            'contrarrazoes': 'Contrarrazões de Recurso',
            'parecer': 'Parecer Jurídico'
        };
        return labels[opcao] || opcao;
    }
    
    getToken() {
        // Assumindo que o token JWT está em localStorage
        return localStorage.getItem('access_token');
    }
    
    resetar() {
        document.getElementById('form-processo').reset();
        this.numeroCNJ = null;
        this.tipoPeca = null;
        this.conteudoJSON = null;
        this.urlDownload = null;
        this.notaSelecionada = null;
    }
}

// Inicializar app
document.addEventListener('DOMContentLoaded', () => {
    new GeradorPecasApp();
});
````

---

## 🔐 SISTEMA DE PERMISSÕES

### Atualizar Dashboard para Exibir Apenas Serviços Permitidos
````python
# src/api/routes/dashboard.py (atualizar)
from sqlalchemy.orm import Session
from src.models.servico import Servico
from src.models.permissao_servico import PermissaoServico

@router.get("/servicos-disponiveis")
async def listar_servicos_usuario(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista serviços que o usuário tem permissão"""
    
    servicos = db.query(Servico).join(PermissaoServico).filter(
        PermissaoServico.usuario_id == current_user.id,
        PermissaoServico.ativo == True,
        Servico.ativo == True
    ).order_by(Servico.ordem).all()
    
    return {
        "servicos": [
            {
                "id": s.id,
                "nome": s.nome,
                "titulo": s.titulo,
                "descricao": s.descricao,
                "icone": s.icone,
                "rota": s.rota
            }
            for s in servicos
        ]
    }
````

### Painel de Administração de Permissões
````html
<!-- templates/admin/permissoes.html -->
{% extends "admin/base.html" %}

{% block content %}
<div class="container mx-auto p-6">
    <h1 class="text-3xl font-bold mb-6">Gerenciar Permissões de Serviços</h1>
    
    <div class="bg-white rounded-lg shadow-md p-6">
        <!-- Filtros -->
        <div class="mb-6">
            <select id="filtro-usuario" class="px-4 py-2 border rounded-lg">
                <option value="">Selecione um usuário</option>
                {% for usuario in usuarios %}
                <option value="{{ usuario.id }}">{{ usuario.nome }} ({{ usuario.email }})</option>
                {% endfor %}
            </select>
        </div>
        
        <!-- Lista de Serviços -->
        <div id="lista-servicos" class="space-y-4">
            {% for servico in servicos %}
            <div class="border border-gray-200 rounded-lg p-4 flex items-center justify-between">
                <div>
                    <h3 class="font-semibold">{{ servico.titulo }}</h3>
                    <p class="text-sm text-gray-600">{{ servico.descricao }}</p>
                </div>
                <label class="flex items-center space-x-2">
                    <input 
                        type="checkbox" 
                        class="form-checkbox h-5 w-5 text-blue-600"
                        data-servico-id="{{ servico.id }}"
                    />
                    <span class="text-sm">Permitir</span>
                </label>
            </div>
            {% endfor %}
        </div>
        
        <button id="btn-salvar-permissoes" class="mt-6 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            Salvar Permissões
        </button>
    </div>
</div>

<script src="/static/js/admin/permissoes.js"></script>
{% endblock %}
````

---

## 📊 DASHBOARD DE FEEDBACKS COM FILTRO POR SERVIÇO

### Atualizar Template de Feedbacks
````html
<!-- templates/admin/feedbacks.html -->
{% extends "admin/base.html" %}

{% block content %}
<div class="container mx-auto p-6">
    <h1 class="text-3xl font-bold mb-6">Feedbacks do Sistema</h1>
    
    <div class="bg-white rounded-lg shadow-md p-6">
        <!-- Filtros -->
        <div class="mb-6 flex space-x-4">
            <select id="filtro-servico" class="px-4 py-2 border rounded-lg">
                <option value="">Todos os serviços</option>
                {% for servico in servicos %}
                <option value="{{ servico.id }}">{{ servico.titulo }}</option>
                {% endfor %}
            </select>
            
            <select id="filtro-nota" class="px-4 py-2 border rounded-lg">
                <option value="">Todas as notas</option>
                <option value="5">⭐⭐⭐⭐⭐ (5 estrelas)</option>
                <option value="4">⭐⭐⭐⭐ (4 estrelas)</option>
                <option value="3">⭐⭐⭐ (3 estrelas)</option>
                <option value="2">⭐⭐ (2 estrelas)</option>
                <option value="1">⭐ (1 estrela)</option>
            </select>
            
            <input 
                type="date" 
                id="filtro-data-inicio" 
                class="px-4 py-2 border rounded-lg"
            />
            <input 
                type="date" 
                id="filtro-data-fim" 
                class="px-4 py-2 border rounded-lg"
            />
            
            <button id="btn-filtrar" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                Filtrar
            </button>
        </div>
        
        <!-- Estatísticas -->
        <div class="grid grid-cols-4 gap-4 mb-6">
            <div class="bg-blue-50 p-4 rounded-lg">
                <p class="text-sm text-gray-600">Total de Feedbacks</p>
                <p id="stat-total" class="text-2xl font-bold">-</p>
            </div>
            <div class="bg-green-50 p-4 rounded-lg">
                <p class="text-sm text-gray-600">Média de Notas</p>
                <p id="stat-media" class="text-2xl font-bold">-</p>
            </div>
            <div class="bg-yellow-50 p-4 rounded-lg">
                <p class="text-sm text-gray-600">Com Comentário</p>
                <p id="stat-comentarios" class="text-2xl font-bold">-</p>
            </div>
            <div class="bg-purple-50 p-4 rounded-lg">
                <p class="text-sm text-gray-600">Última Semana</p>
                <p id="stat-semana" class="text-2xl font-bold">-</p>
            </div>
        </div>
        
        <!-- Lista de Feedbacks -->
        <div id="lista-feedbacks" class="space-y-4">
            <!-- Preenchido via JavaScript -->
        </div>
    </div>
</div>

<script src="/static/js/admin/feedbacks.js"></script>
{% endblock %}
````

### API de Feedbacks com Filtros
````python
# src/api/routes/admin.py
from fastapi import Query
from datetime import datetime

@router.get("/feedbacks")
async def listar_feedbacks(
    servico_id: Optional[int] = Query(None),
    nota: Optional[int] = Query(None),
    data_inicio: Optional[datetime] = Query(None),
    data_fim: Optional[datetime] = Query(None),
    current_user: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Lista feedbacks com filtros"""
    
    query = db.query(Feedback).join(Usuario).join(Servico, isouter=True)
    
    if servico_id:
        query = query.filter(Feedback.servico_id == servico_id)
    
    if nota:
        query = query.filter(Feedback.nota == nota)
    
    if data_inicio:
        query = query.filter(Feedback.created_at >= data_inicio)
    
    if data_fim:
        query = query.filter(Feedback.created_at <= data_fim)
    
    feedbacks = query.order_by(Feedback.created_at.desc()).all()
    
    return {
        "feedbacks": [
            {
                "id": f.id,
                "usuario": f.usuario.nome,
                "servico": f.servico.titulo if f.servico else "Geral",
                "nota": f.nota,
                "comentario": f.comentario,
                "created_at": f.created_at.isoformat(),
                "metadata": f.metadata
            }
            for f in feedbacks
        ],
        "estatisticas": {
            "total": len(feedbacks),
            "media": sum(f.nota for f in feedbacks) / len(feedbacks) if feedbacks else 0,
            "com_comentario": sum(1 for f in feedbacks if f.comentario),
        }
    }
````

---

## 📦 DEPLOYMENT & CONFIGURAÇÃO

### Variáveis de Ambiente
````bash
# .env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

TJMS_PROXY_URL=https://proxytjms.fly.dev
TJMS_ID_CONSULTANTE=...
TJMS_SENHA=...

DATABASE_URL=postgresql://user:pass@localhost/portal_pge
JWT_SECRET_KEY=...
````

### Requirements.txt (adicionar)
````
# Adicionar ao requirements.txt existente
httpx==0.25.0           # Cliente HTTP assíncrono
pymupdf==1.23.0         # PyMuPDF para extração de texto
````

### Script de Migração
````bash
# Executar migration
python -m alembic upgrade head

# Ou SQL direto
psql -U postgres -d portal_pge -f migrations/add_servicos_permissions.sql
````

### Script de Seed (Dados Iniciais)
````python
# scripts/seed_servicos.py
from src.database import SessionLocal
from src.models.servico import Servico
from src.models.usuario import Usuario
from src.models.permissao_servico import PermissaoServico

db = SessionLocal()

# Criar serviço
servico = Servico(
    nome="gerador_pecas",
    titulo="Gerador de Peças Jurídicas",
    descricao="Sistema de geração automatizada de peças jurídicas",
    icone="file-text",
    rota="/gerador-pecas",
    ordem=1
)
db.add(servico)
db.commit()

# Dar permissão para admin
admin = db.query(Usuario).filter(Usuario.email == "admin@pge.ms.gov.br").first()
if admin:
    permissao = PermissaoServico(
        usuario_id=admin.id,
        servico_id=servico.id,
        ativo=True
    )
    db.add(permissao)
    db.commit()

print("✅ Serviço criado e permissão concedida ao admin")
````

---

## ✅ CHECKLIST DE IMPLEMENTAÇÃO

### Backend
- [ ] Criar models (Servico, PermissaoServico, atualizar Feedback)
- [ ] Executar migration do banco
- [ ] Implementar OpenRouterClient
- [ ] Implementar DocxGenerator
- [ ] Implementar DocumentProcessor
- [ ] Implementar ProcessoOrigemService
- [ ] Implementar GeradorPecasOrchestrator
- [ ] Criar rotas da API (/processar, /regenerar, /download, /feedback)
- [ ] Implementar middleware de permissões
- [ ] Testar com processo real do TJ-MS

### Frontend
- [ ] Criar template index.html
- [ ] Implementar app.js principal
- [ ] Implementar modals (pergunta, edição, feedback)
- [ ] Implementar sistema de preview
- [ ] Testar fluxo completo end-to-end

### Administração
- [ ] Criar painel de gerenciamento de permissões
- [ ] Atualizar dashboard de feedbacks com filtros
- [ ] Criar script de seed para dados iniciais

### Testes
- [ ] Testar com processo de 1º grau (com parecer NAT)
- [ ] Testar com processo de 2º grau (sem parecer - buscar origem)
- [ ] Testar diferentes tipos de peças
- [ ] Testar modal de perguntas
- [ ] Testar edição de documento
- [ ] Testar sistema de feedback
- [ ] Testar permissões de acesso

---

## 🚀 PRÓXIMOS PASSOS (Futuro)

1. **Cache de Processos**: Armazenar processos consultados para evitar requisições repetidas
2. **Histórico de Gerações**: Salvar peças geradas para consulta posterior
3. **Templates Customizados**: Permitir usuários criarem templates próprios
4. **Assinatura Digital**: Integração com certificado digital para assinar documentos
5. **Exportação para PDF**: Além de DOCX, gerar também PDF
6. **Notificações**: Avisar por email quando peça estiver pronta (para processos longos)
7. **Análise de Qualidade**: Métricas automáticas de qualidade da peça gerada
8. **Multi-idioma**: Suporte a geração em outros idiomas

---

## 📞 SUPORTE & CONTATO

Para dúvidas sobre implementação, entre em contato com a equipe do LAB/PGE-MS.

**Desenvolvedor responsável**: Kaoye  
**Email**: [seu-email]  
**Lab**: Laboratório de Inovação e Tecnologia - PGE-MS