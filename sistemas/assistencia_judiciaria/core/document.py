# sistemas/assistencia_judiciaria/core/document.py
"""
Módulo de geração de documentos DOCX para Assistência Judiciária.

Utiliza o mesmo template e formatação do Gerador de Peças para garantir
consistência visual nos documentos do Portal PGE-MS.

Formatação padrão:
- Margens ABNT: 3cm (esq/sup), 2cm (dir/inf)
- Fonte: Times New Roman 12pt
- Espaçamento: 1.5 entre linhas
- Cabeçalho: Logo PGE-MS
- Rodapé: Texto institucional
"""
import os
import logging
from typing import Union

logger = logging.getLogger("sistemas.assistencia_judiciaria.core.document")


def markdown_to_docx(markdown_text: str, output_path: str, numero_processo: str = "") -> Union[bool, str]:
    """
    Converte markdown para DOCX usando o template padronizado do Portal PGE-MS.

    Utiliza o DocxConverter do Gerador de Peças para garantir:
    - Margens ABNT (3cm esq/sup, 2cm dir/inf)
    - Cabeçalho com logo institucional
    - Rodapé padronizado
    - Formatação profissional

    Args:
        markdown_text: Texto em formato Markdown a ser convertido
        output_path: Caminho de saída para o arquivo .docx
        numero_processo: Número CNJ do processo (opcional, para referência)

    Returns:
        True se conversão bem sucedida, string de erro caso contrário
    """
    try:
        # Usa o DocxConverter do Gerador de Peças para padronização
        from sistemas.gerador_pecas.docx_converter import DocxConverter

        # Configurações específicas para relatórios de Assistência Judiciária
        # - Margens ABNT padrão
        # - Recuo de primeira linha de 2cm para parágrafos
        # - Sem numeração automática de títulos (relatório usa formato próprio)
        converter = DocxConverter(
            # Margens ABNT (padrão do conversor)
            margin_top_cm=3.0,
            margin_bottom_cm=2.0,
            margin_left_cm=3.0,
            margin_right_cm=2.0,
            # Formatação de texto
            font_name="Times New Roman",
            font_size=12,
            first_line_indent_cm=2.0,
            line_spacing=1.5,
            space_after_pt=6,
            # Citações
            quote_indent_cm=3.0,
            quote_font_size=11,
            quote_line_spacing=1.0,
            # Listas
            list_indent_cm=3.0,
            # Não numerar títulos automaticamente
            numerar_titulos=False,
            # Linhas após direcionamento (não aplicável para relatórios)
            linhas_apos_direcionamento=2,
        )

        # Converte o markdown para DOCX
        success = converter.convert(markdown_text, output_path)

        if success:
            logger.info(f"DOCX gerado com sucesso: {output_path}")
            return True
        else:
            return "ERRO: Falha na conversão do documento"

    except ImportError as e:
        logger.error(f"Erro de importação: {e}")
        return "ERRO: Dependências não instaladas (python-docx ou docx_converter)"
    except Exception as e:
        logger.exception("Erro ao gerar DOCX")
        return f"ERRO: {str(e)}"

def docx_to_pdf(docx_path: str, pdf_path: str) -> Union[bool, str]:
    """
    Converte DOCX para PDF usando LibreOffice ou docx2pdf
    """
    try:
        import subprocess
        
        # Opção 1: LibreOffice
        try:
            output_dir = os.path.dirname(pdf_path)
            cmd = [
                "soffice", "--headless", "--convert-to", "pdf",
                "--outdir", output_dir, docx_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                docx_name = os.path.splitext(os.path.basename(docx_path))[0]
                generated_pdf = os.path.join(output_dir, docx_name + ".pdf")
                if os.path.exists(generated_pdf) and generated_pdf != pdf_path:
                    if os.path.exists(pdf_path): os.remove(pdf_path)
                    os.rename(generated_pdf, pdf_path)
                return True
        except Exception:
            pass

        # Opção 2: docx2pdf
        try:
            from docx2pdf import convert
            convert(docx_path, pdf_path)
            return True
        except ImportError:
            pass

        return "ERRO: Instale LibreOffice ou docx2pdf para gerar PDF."

    except Exception as e:
        return f"ERRO: {str(e)}"
