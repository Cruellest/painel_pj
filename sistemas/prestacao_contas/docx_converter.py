# sistemas/prestacao_contas/docx_converter.py
"""
Conversor de Parecer para DOCX

Converte o parecer de prestação de contas em documento Word formatado.

Autor: LAB/PGE-MS
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE


# Diretório para arquivos temporários
TEMP_DIR = Path(__file__).parent / "temp_docs"
TEMP_DIR.mkdir(exist_ok=True)


def _criar_documento_base() -> Document:
    """Cria documento com configurações base"""
    doc = Document()

    # Configura margens ABNT
    sections = doc.sections
    for section in sections:
        section.top_margin = Cm(3)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2)

    return doc


def _adicionar_cabecalho(doc: Document, numero_cnj: str):
    """Adiciona cabeçalho do parecer"""
    # Título
    titulo = doc.add_paragraph()
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = titulo.add_run("PARECER DE PRESTAÇÃO DE CONTAS")
    run.bold = True
    run.font.size = Pt(14)
    run.font.name = "Arial"

    # Número do processo
    processo = doc.add_paragraph()
    processo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = processo.add_run(f"Processo nº {numero_cnj}")
    run.font.size = Pt(12)
    run.font.name = "Arial"

    # Linha em branco
    doc.add_paragraph()


def _adicionar_parecer_badge(doc: Document, parecer: str):
    """Adiciona indicador visual do parecer"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if parecer == "favoravel":
        texto = "PARECER: FAVORÁVEL"
    elif parecer == "desfavoravel":
        texto = "PARECER: DESFAVORÁVEL"
    else:
        texto = "PARECER: PENDENTE DE ESCLARECIMENTOS"

    run = p.add_run(texto)
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = "Arial"

    # Linha em branco
    doc.add_paragraph()


def _processar_markdown(doc: Document, texto: str):
    """Processa texto markdown e adiciona ao documento"""
    linhas = texto.split('\n')

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        # Cabeçalhos
        if linha.startswith('### '):
            p = doc.add_paragraph()
            run = p.add_run(linha[4:])
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Arial"
            continue

        if linha.startswith('## '):
            p = doc.add_paragraph()
            run = p.add_run(linha[3:])
            run.bold = True
            run.font.size = Pt(12)
            run.font.name = "Arial"
            continue

        if linha.startswith('# '):
            p = doc.add_paragraph()
            run = p.add_run(linha[2:])
            run.bold = True
            run.font.size = Pt(14)
            run.font.name = "Arial"
            continue

        # Lista com bullet
        if linha.startswith('- ') or linha.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            texto_item = linha[2:]
            _adicionar_texto_formatado(p, texto_item)
            continue

        # Lista numerada
        match = re.match(r'^(\d+)\.\s+(.+)', linha)
        if match:
            p = doc.add_paragraph(style='List Number')
            texto_item = match.group(2)
            _adicionar_texto_formatado(p, texto_item)
            continue

        # Parágrafo normal
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _adicionar_texto_formatado(p, linha)


def _adicionar_texto_formatado(paragrafo, texto: str):
    """Adiciona texto com formatação inline (negrito, itálico)"""
    # Processa negrito
    partes = re.split(r'\*\*(.+?)\*\*', texto)

    for i, parte in enumerate(partes):
        if not parte:
            continue

        # Partes ímpares são negrito
        if i % 2 == 1:
            run = paragrafo.add_run(parte)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(12)
        else:
            # Processa itálico dentro do texto normal
            subpartes = re.split(r'\*(.+?)\*', parte)
            for j, subparte in enumerate(subpartes):
                if not subparte:
                    continue
                run = paragrafo.add_run(subparte)
                run.font.name = "Arial"
                run.font.size = Pt(12)
                if j % 2 == 1:
                    run.italic = True


def _adicionar_irregularidades(doc: Document, irregularidades: List[str]):
    """Adiciona seção de irregularidades"""
    p = doc.add_paragraph()
    run = p.add_run("IRREGULARIDADES IDENTIFICADAS")
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = "Arial"

    for irreg in irregularidades:
        p = doc.add_paragraph(style='List Bullet')
        run = p.add_run(irreg)
        run.font.name = "Arial"
        run.font.size = Pt(12)

    doc.add_paragraph()


def _adicionar_rodape(doc: Document):
    """Adiciona rodapé com data e assinatura"""
    doc.add_paragraph()

    # Data
    data = datetime.now().strftime("%d de %B de %Y")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"Campo Grande/MS, {data}")
    run.font.name = "Arial"
    run.font.size = Pt(12)

    doc.add_paragraph()
    doc.add_paragraph()

    # Assinatura
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("_" * 40)
    run.font.name = "Arial"

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Procurador do Estado")
    run.font.name = "Arial"
    run.font.size = Pt(12)


async def converter_parecer_docx(
    numero_cnj: str,
    parecer: str,
    fundamentacao: str,
    irregularidades: Optional[List[str]] = None,
) -> str:
    """
    Converte parecer para DOCX.

    Args:
        numero_cnj: Número do processo
        parecer: Tipo do parecer (favoravel, desfavoravel, duvida)
        fundamentacao: Texto em markdown da fundamentação
        irregularidades: Lista de irregularidades (se desfavorável)

    Returns:
        Caminho do arquivo DOCX gerado
    """
    doc = _criar_documento_base()

    # Cabeçalho
    _adicionar_cabecalho(doc, numero_cnj)

    # Badge do parecer
    _adicionar_parecer_badge(doc, parecer)

    # Fundamentação
    p = doc.add_paragraph()
    run = p.add_run("FUNDAMENTAÇÃO")
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = "Arial"

    doc.add_paragraph()

    _processar_markdown(doc, fundamentacao)

    # Irregularidades (se houver)
    if irregularidades:
        doc.add_paragraph()
        _adicionar_irregularidades(doc, irregularidades)

    # Rodapé
    _adicionar_rodape(doc)

    # Salva documento
    numero_limpo = re.sub(r'[^\d]', '', numero_cnj)
    nome_arquivo = f"parecer_{numero_limpo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    caminho = TEMP_DIR / nome_arquivo

    doc.save(str(caminho))

    return str(caminho)
