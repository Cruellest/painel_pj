#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Entry point para o worker de inferência.

Este módulo evita imports desnecessários do router FastAPI.
Executa diretamente o servidor de inferência.
"""

import sys
from sistemas.bert_training.worker.inference_server import main

if __name__ == "__main__":
    sys.exit(main())
