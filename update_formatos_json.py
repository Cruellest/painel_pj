#!/usr/bin/env python
"""Script para atualizar os formatos JSON de resumo"""
import sys
sys.path.insert(0, '.')

from database.init_db import SessionLocal
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON

db = SessionLocal()

# Atualiza PETIÇÕES
peticoes = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.nome == 'peticoes').first()
if peticoes:
    peticoes.formato_json = """{
  "tipo_peticao": "inicial | contestacao | recurso | apelacao | agravo | contrarrazoes | replica | manifestacao | outras",

  "partes": {
    "autor_requerente": null,
    "reu_requerido": null
  },

  "sintese_fatos": null,

  "fundamentos": {
    "fatos_narrados": [],
    "fundamentos_juridicos": [],
    "teses_principais": [],
    "argumentos_detalhados": null
  },

  "pedidos": {
    "principais": [],
    "subsidiarios": [],
    "tutelas_urgencia_liminar": [],
    "fundamentos_urgencia": null
  },

  "provas": {
    "documentos_juntados": [],
    "provas_requeridas": []
  },

  "precedentes_vinculantes": {
    "citou_stf": false,
    "citou_stj": false,
    "lista_precedentes": []
  },

  "valores": {
    "valor_causa": null,
    "valores_pleiteados": []
  },

  "observacoes_extrator": null
}"""
    peticoes.instrucoes_extracao = """- Em "sintese_fatos" faça um resumo COMPLETO E DETALHADO dos fatos narrados na petição (mínimo 3-5 frases)
- Em "fatos_narrados" liste os principais fatos alegados COM DETALHES (datas, valores, circunstâncias)
- Em "fundamentos_juridicos" liste TODOS os dispositivos legais citados (leis, artigos, súmulas, etc)
- Em "teses_principais" liste as teses jurídicas defendidas de forma COMPLETA
- Em "argumentos_detalhados" TRANSCREVA os argumentos mais importantes na íntegra ou quase íntegra
- Em "pedidos" seja ESPECÍFICO sobre o que é solicitado - liste cada pedido separadamente
- Capture TODOS os valores mencionados (danos morais, materiais, honorários, etc)
- NÃO resuma demais - é melhor informação completa do que resumida"""
    print('Petições atualizado!')

# Atualiza DECISÕES
decisoes = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.nome == 'decisoes').first()
if decisoes:
    decisoes.formato_json = """{
  "tipo_decisao": "liminar | tutela_urgencia | tutela_evidencia | saneadora | provas | recebimento_recurso | mero_expediente | interlocutoria | outra",

  "sintese_decisao": null,

  "fundamentacao_completa": null,

  "dispositivo": null,

  "decisao_determinacoes": [],

  "efeitos_praticos": null,

  "obrigacoes_impostas": [
    {
      "descricao": null,
      "sujeito_passivo": null,
      "tipo_obrigacao": "fazer | nao_fazer | pagar_quantia | entregar_coisa | outra",
      "prazo": null,
      "valor": null,
      "penalidades_previstas": []
    }
  ],

  "prazos_fixados": [],

  "precedentes_citados": {
    "citou_stf": false,
    "citou_stj": false,
    "lista_precedentes": []
  },

  "observacoes_extrator": null
}"""
    decisoes.instrucoes_extracao = """- Em "sintese_decisao" faça um resumo COMPLETO do que foi decidido (mínimo 3-5 frases)
- Em "fundamentacao_completa" TRANSCREVA os principais trechos da fundamentação (especialmente ratio decidendi)
- Em "dispositivo" TRANSCREVA a parte dispositiva (o que foi efetivamente determinado)
- Liste TODAS as obrigações impostas com seus prazos e valores específicos
- Capture QUALQUER prazo mencionado na decisão
- Em "efeitos_praticos" descreva as consequências práticas da decisão
- NÃO resuma demais - informação completa é essencial para elaborar peças"""
    print('Decisões atualizado!')

# Verifica se existe categoria de sentenças
sentencas = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.nome == 'sentencas').first()
if not sentencas:
    # Cria categoria de sentenças
    sentencas = CategoriaResumoJSON(
        nome='sentencas',
        titulo='Sentenças Judiciais',
        descricao='Sentenças judiciais de primeiro grau',
        codigos_documento=[21, 385, 386, 387, 388],  # Códigos de sentença
        is_residual=False,
        ativo=True,
        ordem=3
    )
    db.add(sentencas)
    print('Categoria sentenças criada!')

if sentencas:
    sentencas.formato_json = """{
  "tipo_sentenca": "procedencia | improcedencia | parcial_procedencia | extincao_sem_merito | homologatoria | outra",

  "partes": {
    "autor": null,
    "reu": null
  },

  "relatorio_resumo": null,

  "fundamentacao": {
    "questoes_preliminares": [],
    "analise_merito": null,
    "teses_acolhidas": [],
    "teses_rejeitadas": [],
    "fundamentos_principais": null
  },

  "dispositivo": {
    "resultado": null,
    "condenacoes": [],
    "obrigacoes_impostas": [],
    "valores_fixados": []
  },

  "custas_honorarios": {
    "responsavel_custas": null,
    "honorarios_sucumbencia": null,
    "percentual_honorarios": null
  },

  "precedentes_citados": {
    "citou_stf": false,
    "citou_stj": false,
    "lista_precedentes": []
  },

  "observacoes_extrator": null
}"""
    sentencas.instrucoes_extracao = """- Em "relatorio_resumo" faça um resumo do relatório da sentença
- Em "analise_merito" TRANSCREVA ou resuma detalhadamente a análise do mérito
- Liste TODAS as teses acolhidas e rejeitadas separadamente
- Em "fundamentos_principais" TRANSCREVA os trechos mais importantes da fundamentação
- No "dispositivo" seja ESPECÍFICO sobre o resultado e todas as condenações
- Capture TODOS os valores (indenizações, honorários, multas, etc)
- NÃO resuma demais - informação completa é essencial para recursos"""
    print('Sentenças atualizado!')

# Verifica se existe categoria de Parecer NAT
parecer_nat = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.nome == 'parecer_nat').first()
if not parecer_nat:
    # Cria categoria de Parecer NAT
    parecer_nat = CategoriaResumoJSON(
        nome='parecer_nat',
        titulo='Parecer NAT/CATES/NATJus',
        descricao='Pareceres técnicos do Núcleo de Apoio Técnico (NAT), CATES e NATJus',
        codigos_documento=[8451, 9636, 59, 8490],  # Códigos do Parecer NAT e Nota Técnica NATJus
        is_residual=False,
        ativo=True,
        ordem=4
    )
    db.add(parecer_nat)
    print('Categoria Parecer NAT criada!')
else:
    # Atualiza códigos para incluir Nota Técnica NATJus
    parecer_nat.codigos_documento = [8451, 9636, 59, 8490]
    print('Codigos do Parecer NAT atualizados!')

if parecer_nat:
    parecer_nat.formato_json = """{
  "identificacao": {
    "numero_parecer": null,
    "data_emissao": null,
    "orgao_emissor": "NAT | CATES | NATJus | outro",
    "profissional_responsavel": null
  },

  "demanda_analisada": {
    "medicamento_tratamento_solicitado": null,
    "principio_ativo": null,
    "indicacao_clinica": null,
    "cid_doenca": null,
    "pergunta_formulada": null
  },

  "analise_tecnica": {
    "registro_anvisa": {
      "possui_registro": null,
      "indicacoes_aprovadas": []
    },
    "incorporacao_sus": {
      "incorporado_ao_sus": null,
      "pcdt_aplicavel": null,
      "protocolo_clinico": null
    },
    "evidencias_cientificas": {
      "nivel_evidencia": null,
      "estudos_citados": [],
      "eficacia_comprovada": null,
      "seguranca": null
    },
    "alternativas_terapeuticas": {
      "existem_alternativas_sus": null,
      "alternativas_disponiveis": [],
      "justificativa_alternativas": null
    }
  },

  "conclusao": {
    "recomendacao": "favoravel | desfavoravel | favoravel_com_ressalvas | inconclusivo",
    "fundamentos_conclusao": null,
    "transcricao_conclusao": null
  },

  "observacoes_extrator": null
}"""
    parecer_nat.instrucoes_extracao = """IMPORTANTE: Este é um documento técnico essencial para a defesa do Estado em ações de saúde.

- Em "medicamento_tratamento_solicitado" identifique o medicamento ou tratamento analisado
- Em "principio_ativo" extraia o nome do princípio ativo/substância
- Em "incorporacao_sus" seja ESPECÍFICO sobre se está ou não incorporado ao SUS
- Em "alternativas_terapeuticas" liste TODAS as alternativas mencionadas pelo parecer
- Em "recomendacao" identifique claramente se o parecer é favorável ou desfavorável ao fornecimento
- Em "transcricao_conclusao" TRANSCREVA NA ÍNTEGRA o trecho de conclusão/recomendação do parecer
- Em "fundamentos_conclusao" resuma os principais argumentos técnicos da conclusão
- Capture TODOS os estudos e evidências científicas citados
- Este documento é CRUCIAL para a contestação - NÃO resuma demais, preserve detalhes técnicos"""
    print('Parecer NAT atualizado!')

db.commit()
db.close()
print('\nFormatos atualizados com sucesso!')
