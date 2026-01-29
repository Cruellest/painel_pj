# utils/pymupdf_lock.py
"""
Lock global para operações PyMuPDF/MuPDF.

IMPORTANTE: PyMuPDF (fitz) e pymupdf4llm NÃO são thread-safe!
A biblioteca C subjacente (MuPDF) pode causar Segmentation Fault
quando múltiplas threads acessam simultaneamente.

SOLUÇÃO: Use este lock para TODAS as operações com fitz/pymupdf4llm.

Exemplo de uso:
    from utils.pymupdf_lock import pymupdf_lock

    with pymupdf_lock:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # ... operações com doc ...
        doc.close()

Autor: LAB/PGE-MS
"""

import threading

# Lock global único para toda a aplicação
pymupdf_lock = threading.Lock()
