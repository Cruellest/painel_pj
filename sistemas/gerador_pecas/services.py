# sistemas/gerador_pecas/services.py
"""
Serviços do sistema Gerador de Peças Jurídicas
Utiliza prompts modulares: BASE + PEÇA + CONTEÚDO
"""

import os
import json
import uuid
import httpx
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

from sistemas.gerador_pecas.models import GeracaoPeca
from admin.models_prompts import PromptModulo


class GeradorPecasService:
    """
    Serviço principal para geração de peças jurídicas.
    
    Utiliza sistema de prompts modulares:
    - BASE: System prompt (sempre ativo)
    - PEÇA: Estrutura específica do tipo de peça (ativado por escolha)
    - CONTEÚDO: Argumentos/teses (ativados por detecção de situação)
    """
    
    def __init__(
        self, 
        modelo: str = "anthropic/claude-3.5-sonnet",
        db: Session = None
    ):
        self.modelo = modelo
        self.db = db
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Diretório para arquivos temporários
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'temp_docs')
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def _carregar_modulos_base(self) -> List[PromptModulo]:
        """Carrega todos os módulos BASE (sempre ativos)"""
        if not self.db:
            return []
        return self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "base",
            PromptModulo.ativo == True
        ).order_by(PromptModulo.ordem).all()
    
    def _carregar_modulo_peca(self, tipo_peca: str) -> Optional[PromptModulo]:
        """Carrega o módulo de PEÇA específico"""
        if not self.db:
            return None
        return self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "peca",
            PromptModulo.categoria == tipo_peca,
            PromptModulo.ativo == True
        ).first()
    
    def _carregar_modulos_conteudo(self, palavras_detectadas: List[str] = None) -> List[PromptModulo]:
        """
        Carrega módulos de CONTEÚDO com base nas palavras-chave detectadas.
        Se nenhuma palavra for passada, retorna todos os módulos ativos.
        """
        if not self.db:
            return []
        
        query = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True
        )
        
        modulos = query.order_by(PromptModulo.ordem).all()
        
        if not palavras_detectadas:
            return modulos
        
        # Filtra módulos que têm palavras-chave correspondentes
        modulos_relevantes = []
        for modulo in modulos:
            if modulo.palavras_chave:
                for palavra in modulo.palavras_chave:
                    if any(palavra.lower() in p.lower() for p in palavras_detectadas):
                        modulos_relevantes.append(modulo)
                        break
        
        return modulos_relevantes
    
    def _montar_prompt_sistema(self, tipo_peca: str = None, palavras_detectadas: List[str] = None) -> str:
        """
        Monta o prompt de sistema combinando módulos:
        BASE + PEÇA + CONTEÚDO
        """
        partes = []
        
        # 1. Módulos BASE (sempre incluídos)
        modulos_base = self._carregar_modulos_base()
        for modulo in modulos_base:
            partes.append(f"## {modulo.titulo}\n\n{modulo.conteudo}")
        
        # 2. Módulo de PEÇA (se tipo especificado)
        if tipo_peca:
            modulo_peca = self._carregar_modulo_peca(tipo_peca)
            if modulo_peca:
                partes.append(f"## ESTRUTURA DA PEÇA: {modulo_peca.titulo}\n\n{modulo_peca.conteudo}")
        
        # 3. Módulos de CONTEÚDO (baseado em detecção)
        modulos_conteudo = self._carregar_modulos_conteudo(palavras_detectadas)
        if modulos_conteudo:
            partes.append("## ARGUMENTOS E TESES APLICÁVEIS\n")
            for modulo in modulos_conteudo:
                partes.append(f"### {modulo.titulo}\n{modulo.conteudo}\n")
        
        # Se não há módulos no banco, usa prompt padrão
        if not partes:
            return self._get_prompt_padrao()
        
        return "\n\n".join(partes)
    
    def _get_prompt_padrao(self) -> str:
        """Retorna prompt padrão caso não haja módulos no banco"""
        return """Você é um assistente jurídico especializado da Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

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

## IMPORTANTE

- NUNCA invente fatos não presentes nos documentos
- SEMPRE fundamente tecnicamente seus argumentos
- Use dispositivos legais completos (Lei nº X, art. Y, § Z)
- Cite jurisprudência quando houver (STF, STJ, TJMS)
- Mantenha tom formal e respeitoso
"""
    
    async def processar_processo(
        self,
        numero_cnj: str,
        numero_cnj_formatado: str = None,
        tipo_peca: Optional[str] = None,
        resposta_usuario: Optional[str] = None,
        usuario_id: int = None,
        palavras_detectadas: List[str] = None
    ) -> Dict:
        """
        Processa um processo e gera a peça jurídica
        
        Args:
            numero_cnj: Número do processo sem formatação
            numero_cnj_formatado: Número formatado para exibição
            tipo_peca: Tipo de peça a gerar (contestacao, recurso_apelacao, etc)
            resposta_usuario: Resposta a uma pergunta anterior
            usuario_id: ID do usuário
            palavras_detectadas: Palavras-chave detectadas nos documentos
        """
        try:
            # TODO: Implementar integração com TJ-MS
            # Por enquanto, simula uma resposta de pergunta
            
            if not tipo_peca and not resposta_usuario:
                return {
                    "status": "pergunta",
                    "pergunta": f"Qual tipo de peça jurídica você deseja gerar para o processo {numero_cnj_formatado or numero_cnj}?",
                    "opcoes": ["contestacao", "recurso_apelacao", "contrarrazoes", "parecer"],
                    "mensagem": "Sistema em implementação. A integração com o TJ-MS será adicionada em breve."
                }
            
            # Se tem tipo de peça, gera documento de exemplo
            tipo_final = tipo_peca or resposta_usuario
            
            # Monta o prompt usando módulos
            prompt_sistema = self._montar_prompt_sistema(tipo_final, palavras_detectadas)
            
            # Log dos módulos usados (para debug)
            print(f"🧩 Prompt montado com {len(prompt_sistema)} caracteres")
            
            # Gera documento de exemplo
            conteudo = self._gerar_documento_exemplo(numero_cnj_formatado or numero_cnj, tipo_final)
            
            # Salva no banco
            geracao = GeracaoPeca(
                numero_cnj=numero_cnj,
                numero_cnj_formatado=numero_cnj_formatado,
                tipo_peca=tipo_final,
                conteudo_gerado=conteudo,
                modelo_usado=self.modelo,
                usuario_id=usuario_id
            )
            
            if self.db:
                self.db.add(geracao)
                self.db.commit()
                self.db.refresh(geracao)
            
            # Gera arquivo DOCX
            filename = f"{uuid.uuid4()}.docx"
            filepath = os.path.join(self.temp_dir, filename)
            self.gerar_docx(conteudo, filepath)
            
            return {
                "status": "sucesso",
                "geracao_id": geracao.id if self.db else None,
                "url_download": f"/gerador-pecas/api/download/{filename}",
                "tipo_peca": tipo_final,
                "conteudo_json": conteudo
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "status": "erro",
                "mensagem": str(e)
            }
    
    def _gerar_documento_exemplo(self, numero_cnj: str, tipo_peca: str) -> Dict:
        """Gera documento de exemplo para demonstração"""
        
        tipo_labels = {
            "contestacao": "CONTESTAÇÃO",
            "recurso_apelacao": "RECURSO DE APELAÇÃO",
            "contrarrazoes": "CONTRARRAZÕES DE RECURSO",
            "parecer": "PARECER JURÍDICO"
        }
        
        titulo = tipo_labels.get(tipo_peca, "PEÇA JURÍDICA")
        
        return {
            "cabecalho": {
                "texto": f"EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA ___ VARA CÍVEL DA COMARCA DE CAMPO GRANDE - MS",
                "alinhamento": "direita"
            },
            "qualificacao": {
                "texto": f"Processo nº {numero_cnj}\n\nO ESTADO DE MATO GROSSO DO SUL, pessoa jurídica de direito público interno, inscrito no CNPJ sob o nº 15.412.257/0001-28, por meio de sua Procuradoria-Geral, vem, respeitosamente, à presença de Vossa Excelência, apresentar a presente {titulo}, pelos fundamentos de fato e de direito a seguir expostos.",
                "recuo_primeira_linha": 1.25
            },
            "secoes": [
                {
                    "titulo": "I - DOS FATOS",
                    "titulo_negrito": True,
                    "titulo_caixa_alta": True,
                    "paragrafos": [
                        {
                            "tipo": "normal",
                            "texto": "Trata-se de ação judicial em que o Estado de Mato Grosso do Sul figura no polo passivo. [DESCRIÇÃO DOS FATOS SERÁ INSERIDA AQUI COM BASE NOS DOCUMENTOS DO PROCESSO]",
                            "numerado": False,
                            "justificado": True,
                            "recuo_primeira_linha": 1.25
                        }
                    ]
                },
                {
                    "titulo": "II - DO DIREITO",
                    "titulo_negrito": True,
                    "titulo_caixa_alta": True,
                    "paragrafos": [
                        {
                            "tipo": "normal",
                            "texto": "[FUNDAMENTAÇÃO JURÍDICA SERÁ INSERIDA AQUI COM BASE NA ANÁLISE DO PROCESSO]",
                            "numerado": False,
                            "justificado": True,
                            "recuo_primeira_linha": 1.25
                        }
                    ]
                },
                {
                    "titulo": "III - DOS PEDIDOS",
                    "titulo_negrito": True,
                    "titulo_caixa_alta": True,
                    "paragrafos": [
                        {
                            "tipo": "normal",
                            "texto": "Ante o exposto, requer seja julgado improcedente o pedido formulado na inicial, condenando-se a parte autora ao pagamento das custas processuais e honorários advocatícios.",
                            "numerado": False,
                            "justificado": True,
                            "recuo_primeira_linha": 1.25
                        }
                    ]
                }
            ],
            "fecho": {
                "local_data": f"Campo Grande/MS, {datetime.now().strftime('%d de %B de %Y')}",
                "assinatura": "[NOME DO PROCURADOR]\nProcurador do Estado\nOAB/MS nº [NÚMERO]"
            }
        }
    
    def gerar_docx(self, conteudo: Dict, filepath: str) -> None:
        """Gera documento Word a partir do conteúdo JSON"""
        
        doc = Document()
        
        # Configurar margens (ABNT: 3cm esq/sup, 2cm dir/inf)
        for section in doc.sections:
            section.top_margin = Cm(3)
            section.bottom_margin = Cm(2)
            section.left_margin = Cm(3)
            section.right_margin = Cm(2)
        
        # Cabeçalho
        if 'cabecalho' in conteudo:
            cab = conteudo['cabecalho']
            p = doc.add_paragraph(cab.get('texto', ''))
            if cab.get('alinhamento') == 'direita':
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif cab.get('alinhamento') == 'centro':
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(12)
            p.paragraph_format.space_after = Pt(24)
        
        # Qualificação
        if 'qualificacao' in conteudo:
            qual = conteudo['qualificacao']
            p = doc.add_paragraph(qual.get('texto', ''))
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(qual.get('recuo_primeira_linha', 1.25))
            p.paragraph_format.line_spacing = 1.5
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(12)
            p.paragraph_format.space_after = Pt(12)
        
        # Seções
        for secao in conteudo.get('secoes', []):
            # Título da seção
            p_titulo = doc.add_paragraph(secao.get('titulo', ''))
            p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p_titulo.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(12)
                if secao.get('titulo_negrito', True):
                    run.bold = True
            p_titulo.paragraph_format.space_before = Pt(12)
            p_titulo.paragraph_format.space_after = Pt(12)
            
            # Parágrafos da seção
            for paragrafo in secao.get('paragrafos', []):
                if paragrafo.get('tipo') == 'citacao':
                    # Citação com recuo especial
                    p = doc.add_paragraph(paragrafo.get('texto', ''))
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p.paragraph_format.left_indent = Cm(3)
                    p.paragraph_format.right_indent = Cm(3)
                    p.paragraph_format.line_spacing = 1.0
                    for run in p.runs:
                        run.font.name = 'Arial'
                        run.font.size = Pt(11)
                    
                    # Fonte da citação
                    if paragrafo.get('fonte'):
                        p_fonte = doc.add_paragraph(paragrafo['fonte'])
                        p_fonte.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                        p_fonte.paragraph_format.left_indent = Cm(3)
                        for run in p_fonte.runs:
                            run.font.name = 'Arial'
                            run.font.size = Pt(10)
                else:
                    # Parágrafo normal
                    p = doc.add_paragraph(paragrafo.get('texto', ''))
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p.paragraph_format.first_line_indent = Cm(paragrafo.get('recuo_primeira_linha', 1.25))
                    p.paragraph_format.line_spacing = 1.5
                    for run in p.runs:
                        run.font.name = 'Arial'
                        run.font.size = Pt(12)
                    p.paragraph_format.space_after = Pt(6)
        
        # Fecho
        if 'fecho' in conteudo:
            fecho = conteudo['fecho']
            
            # Local e data
            if fecho.get('local_data'):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(24)
                p.add_run(fecho['local_data'])
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                for run in p.runs:
                    run.font.name = 'Arial'
                    run.font.size = Pt(12)
            
            # Assinatura
            if fecho.get('assinatura'):
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(36)
                linhas = fecho['assinatura'].replace('\\n', '\n').split('\n')
                for i, linha in enumerate(linhas):
                    if i > 0:
                        p.add_run('\n')
                    p.add_run(linha)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in p.runs:
                    run.font.name = 'Arial'
                    run.font.size = Pt(12)
        
        # Salvar documento
        doc.save(filepath)
    
    async def _chamar_ia(
        self, 
        mensagens: List[Dict],
        temperatura: float = 0.3
    ) -> Dict:
        """Chama a API do OpenRouter"""
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY não configurada")
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.modelo,
                    "messages": mensagens,
                    "temperature": temperatura,
                    "max_tokens": 8000
                }
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result['choices'][0]['message']['content']
            
            # Tenta extrair JSON
            try:
                content = content.replace('```json', '').replace('```', '').strip()
                return json.loads(content)
            except json.JSONDecodeError:
                return {
                    "tipo": "erro",
                    "mensagem": "Resposta da IA não está em formato JSON válido"
                }
