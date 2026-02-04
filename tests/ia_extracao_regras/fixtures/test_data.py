# tests/ia_extracao_regras/fixtures/test_data.py
"""
Dados de teste para o sistema de extração e regras determinísticas.
"""

# Perguntas de extração em linguagem natural
PERGUNTAS_EXTRACAO = [
    {
        "pergunta": "Qual é o nome completo do autor da ação?",
        "nome_variavel_sugerido": "nome_autor",
        "tipo_sugerido": "text",
        "descricao": "Nome do requerente"
    },
    {
        "pergunta": "Qual é o valor total da causa?",
        "nome_variavel_sugerido": "valor_causa",
        "tipo_sugerido": "currency",
        "descricao": "Valor em reais"
    },
    {
        "pergunta": "O autor é idoso (60 anos ou mais)?",
        "tipo_sugerido": "boolean"
    },
    {
        "pergunta": "Qual o tipo de medicamento solicitado?",
        "tipo_sugerido": "choice",
        "opcoes_sugeridas": ["Alto custo", "Básico", "Especial"]
    },
    {
        "pergunta": "O medicamento está na lista RENAME?",
        "tipo_sugerido": "boolean"
    }
]

# Schemas JSON válidos
SCHEMAS_VALIDOS = {
    "simples": {
        "nome_autor": {"type": "text", "description": "Nome do autor"},
        "valor_causa": {"type": "currency", "description": "Valor da causa"}
    },
    "com_choice": {
        "tipo_acao": {
            "type": "choice",
            "description": "Tipo da ação",
            "options": ["Medicamentos", "Cirurgia", "Outros"]
        }
    },
    "completo": {
        "nome_autor": {"type": "text", "description": "Nome completo do autor"},
        "cpf_autor": {"type": "text", "description": "CPF do autor"},
        "valor_causa": {"type": "currency", "description": "Valor da causa"},
        "data_ajuizamento": {"type": "date", "description": "Data de ajuizamento"},
        "autor_idoso": {"type": "boolean", "description": "Se autor é idoso"},
        "tipo_acao": {
            "type": "choice",
            "description": "Tipo da ação",
            "options": ["Medicamentos", "Cirurgia", "Internação", "Outros"]
        },
        "medicamentos": {"type": "list", "description": "Lista de medicamentos"}
    }
}

# Schemas inválidos para testes de validação
SCHEMAS_INVALIDOS = {
    "vazio": {},
    "sem_tipo": {
        "campo": {"description": "Campo sem tipo"}
    },
    "tipo_invalido": {
        "campo": {"type": "tipo_invalido", "description": "Tipo inválido"}
    },
    "choice_sem_opcoes": {
        "campo": {"type": "choice", "description": "Choice sem opções"}
    },
    "choice_uma_opcao": {
        "campo": {
            "type": "choice",
            "description": "Choice com uma opção",
            "options": ["Única"]
        }
    }
}

# Regras determinísticas para testes
REGRAS_DETERMINISTICAS = {
    "simples": {
        "type": "condition",
        "variable": "valor_causa",
        "operator": "greater_than",
        "value": 100000
    },
    "and": {
        "type": "and",
        "conditions": [
            {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
            {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
        ]
    },
    "or": {
        "type": "or",
        "conditions": [
            {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
            {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
        ]
    },
    "not": {
        "type": "not",
        "conditions": [
            {"type": "condition", "variable": "status", "operator": "equals", "value": "arquivado"}
        ]
    },
    "aninhada": {
        "type": "and",
        "conditions": [
            {
                "type": "or",
                "conditions": [
                    {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
                    {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": True}
                ]
            },
            {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
        ]
    },
    "medicamento_alto_custo": {
        "type": "and",
        "conditions": [
            {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": True},
            {"type": "condition", "variable": "medicamento_rename", "operator": "equals", "value": False}
        ]
    }
}

# Dados de extração para testes de runtime
DADOS_EXTRACAO = {
    "idoso_valor_alto": {
        "nome_autor": "João da Silva",
        "valor_causa": 150000,
        "autor_idoso": True,
        "autor_crianca": False,
        "status": "ativo",
        "medicamento_alto_custo": True,
        "medicamento_rename": False
    },
    "crianca_valor_baixo": {
        "nome_autor": "Maria Santos",
        "valor_causa": 30000,
        "autor_idoso": False,
        "autor_crianca": True,
        "status": "ativo",
        "medicamento_alto_custo": False,
        "medicamento_rename": True
    },
    "adulto_valor_medio": {
        "nome_autor": "Pedro Oliveira",
        "valor_causa": 75000,
        "autor_idoso": False,
        "autor_crianca": False,
        "status": "ativo",
        "medicamento_alto_custo": True,
        "medicamento_rename": True
    },
    "arquivado": {
        "nome_autor": "Ana Costa",
        "valor_causa": 50000,
        "autor_idoso": False,
        "autor_crianca": False,
        "status": "arquivado",
        "medicamento_alto_custo": False,
        "medicamento_rename": False
    },
    "formato_brasileiro": {
        "nome_autor": "Carlos Ferreira",
        "valor_causa": "R$ 250.000,00",
        "autor_idoso": "sim",
        "autor_crianca": "não",
        "status": "ativo"
    }
}

# Variáveis de teste
VARIAVEIS_TESTE = [
    {"slug": "nome_autor", "label": "Nome do Autor", "tipo": "text"},
    {"slug": "valor_causa", "label": "Valor da Causa", "tipo": "currency"},
    {"slug": "autor_idoso", "label": "Autor Idoso", "tipo": "boolean"},
    {"slug": "autor_crianca", "label": "Autor Criança", "tipo": "boolean"},
    {"slug": "tipo_acao", "label": "Tipo de Ação", "tipo": "text"},
    {"slug": "medicamento_alto_custo", "label": "Medicamento Alto Custo", "tipo": "boolean"},
    {"slug": "medicamento_rename", "label": "Medicamento RENAME", "tipo": "boolean"},
    {"slug": "status", "label": "Status", "tipo": "text"},
]
