# -*- coding: utf-8 -*-
"""
Módulo BERT Training - Sistema de treinamento de classificadores BERT.

Arquitetura:
- Cloud (Railway): UI + API + BD + storage Excel + logs/métricas
- Worker Local (GPU): Executa treinamento na GPU local

O worker local faz pull de jobs via API, baixa Excel, treina, e envia métricas/logs.
"""

from sistemas.bert_training.router import router

__all__ = ["router"]
