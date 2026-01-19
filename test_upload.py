#!/usr/bin/env python
"""
Script de teste para upload de documentos na prestação de contas.
"""
import sys
sys.path.insert(0, '.')

def main():
    # Lê o arquivo PDF
    pdf_path = r"C:\Users\kaoye\Downloads\doc_235758011.pdf"
    
    with open(pdf_path, 'rb') as f:
        pdf_content = f.read()
    
    print(f"PDF carregado: {len(pdf_content)} bytes")
    
    from sistemas.pedido_calculo.document_downloader import extrair_texto_pdf
    from sistemas.prestacao_contas.services import converter_pdf_para_imagens
    
    texto = extrair_texto_pdf(pdf_content)
    print(f"Texto extraído: {len(texto)} caracteres")
    
    # Se texto muito curto, converte para imagem
    if len(texto) < 500:
        print("Texto curto, convertendo para imagens...")
        imagens = converter_pdf_para_imagens(pdf_content)
        print(f"Imagens geradas: {len(imagens)}")
        
        doc_anexo = {
            "id": "manual_1",
            "tipo": "Nota Fiscal - doc_235758011.pdf",
            "texto": None,
            "imagens": imagens
        }
    else:
        doc_anexo = {
            "id": "manual_1",
            "tipo": "Nota Fiscal - doc_235758011.pdf",
            "texto": texto,
            "imagens": None
        }
    
    # Atualiza o banco
    import sqlite3
    import json
    
    conn = sqlite3.connect('portal.db')
    c = conn.cursor()
    
    c.execute('''
        UPDATE geracoes_prestacao_contas 
        SET documentos_anexos = ?, 
            status = 'documentos_recebidos',
            documentos_faltantes = NULL
        WHERE id = 27
    ''', (json.dumps([doc_anexo]),))
    
    conn.commit()
    
    # Verifica
    c.execute('SELECT id, status, length(documentos_anexos) FROM geracoes_prestacao_contas WHERE id = 27')
    row = c.fetchone()
    print(f"\nGeração atualizada: ID={row[0]}, Status={row[1]}, Docs anexos len={row[2]}")
    
    print("\n✅ Upload simulado com sucesso!")
    print("\nAgora abra o navegador e:")
    print("1. Vá para http://localhost:8000/prestacao-contas/")
    print("2. Clique na análise ID=27 no histórico")
    print("3. Clique em 'Reprocessar' no modal")

if __name__ == "__main__":
    main()
