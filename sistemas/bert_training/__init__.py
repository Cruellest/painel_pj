# -*- coding: utf-8 -*-
"""
Módulo BERT Training - Sistema de treinamento de classificadores BERT.

Arquitetura:
- Cloud (Railway): UI + API + BD + storage Excel + logs/métricas
- Worker Local (GPU): Executa treinamento na GPU local

O worker local faz pull de jobs via API, baixa Excel, treina, e envia métricas/logs.

NOTA: router é importado APENAS pela aplicação FastAPI, não pelo worker.
      Worker usa inference_server.py diretamente.
"""

# Importa router apenas quando solicitado (lazy import se necessário)
# __all__ listado sem importar router automaticamente

__all__ = ["get_router"]


def get_router():
    """Import lazy do router para evitar dependência de FastAPI no worker."""
    from sistemas.bert_training.router import router
    return router

