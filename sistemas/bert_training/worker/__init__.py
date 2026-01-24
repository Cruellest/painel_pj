# -*- coding: utf-8 -*-
"""
Worker local para treinamento BERT na GPU.

Este worker roda no PC local com GPU e:
1. Faz pull de jobs pendentes via API
2. Baixa o Excel do dataset
3. Executa o treinamento na GPU
4. Envia métricas e logs para a cloud
"""
