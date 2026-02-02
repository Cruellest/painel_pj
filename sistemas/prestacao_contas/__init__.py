# sistemas/prestacao_contas/__init__.py
"""
Sistema de Análise de Prestação de Contas

Análise automatizada de prestação de contas em processos judiciais
de bloqueio de valores do Estado para compra de medicamentos.

Pipeline:
1. Scrapper baixa PDF do extrato da subconta
2. XML do TJ-MS para listar documentos
3. Identifica petição de prestação de contas
4. Baixa documentos anexados (notas fiscais, comprovantes)
5. Agente de IA analisa e emite parecer
"""
