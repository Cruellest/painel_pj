# sistemas/cumprimento_beta/services_extracao_json.py
"""
Serviço de extração de JSON de documentos para o módulo beta.

Usa a categoria "Cumprimento de Sentença" configurada em /admin/categorias-resumo-json
para gerar JSONs estruturados de cada documento relevante.
"""

import json
import logging
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from sistemas.cumprimento_beta.models import (
    SessaoCumprimentoBeta, DocumentoBeta, JSONResumoBeta
)
from sistemas.cumprimento_beta.constants import (
    StatusSessao, StatusRelevancia, CATEGORIA_CUMPRIMENTO_SENTENCA,
    MODELO_PADRAO_AGENTE1, TIMEOUT_EXTRACAO_JSON
)
from sistemas.cumprimento_beta.exceptions import CategoriaNaoEncontradaError, ExtracaoJSONError
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async

logger = logging.getLogger(__name__)


# Prompt para extração de JSON
PROMPT_EXTRACAO_JSON = """Você é um assistente jurídico especializado em extrair informações estruturadas de documentos.

Analise o documento abaixo e extraia as informações no formato JSON especificado.

## FORMATO JSON ESPERADO

```json
{formato_json}
```

{instrucoes_adicionais}

## DOCUMENTO A ANALISAR

**Tipo:** {tipo_documento}
**Data:** {data_documento}
**ID:** {documento_id}

**Conteúdo:**
{conteudo}

## RESPOSTA

Retorne APENAS o JSON preenchido, sem markdown ou explicações adicionais.
Se alguma informação não estiver disponível, use null ou string vazia conforme apropriado.
O JSON deve ser válido e seguir exatamente a estrutura especificada.
"""


# Schema padrão caso categoria não exista
SCHEMA_PADRAO_CUMPRIMENTO = {
    "document_id": "string - ID do documento",
    "tipo_documento": "string - Tipo/descrição do documento",
    "data_documento": "string - Data do documento (DD/MM/YYYY)",
    "resumo": "string - Resumo do conteúdo principal",
    "pontos_relevantes": ["lista de pontos relevantes para cumprimento"],
    "pedidos_ou_determinacoes": ["lista de pedidos ou determinações encontradas"],
    "valores_mencionados": ["lista de valores monetários mencionados"],
    "prazos_mencionados": ["lista de prazos mencionados"],
    "partes_mencionadas": ["lista de partes/nomes mencionados"],
    "observacoes": "string - Observações adicionais"
}


class ExtracaoJSONService:
    """Serviço para extração de JSON de documentos"""

    def __init__(self, db: Session):
        self.db = db
        self._categoria = self._carregar_categoria()
        self._modelo = self._carregar_modelo()

    def _carregar_categoria(self) -> Optional[CategoriaResumoJSON]:
        """Carrega categoria de cumprimento de sentença do admin"""
        try:
            categoria = self.db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.nome == CATEGORIA_CUMPRIMENTO_SENTENCA,
                CategoriaResumoJSON.ativo == True
            ).first()

            if categoria:
                logger.info(f"[BETA] Categoria '{CATEGORIA_CUMPRIMENTO_SENTENCA}' carregada")
                return categoria

            # Tenta variações do nome
            categoria = self.db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.nome.ilike("%cumprimento%sentenca%"),
                CategoriaResumoJSON.ativo == True
            ).first()

            if categoria:
                logger.info(f"[BETA] Categoria '{categoria.nome}' encontrada (variação)")
                return categoria

            logger.warning(
                f"[BETA] Categoria '{CATEGORIA_CUMPRIMENTO_SENTENCA}' não encontrada. "
                "Usando schema padrão."
            )
            return None

        except Exception as e:
            logger.error(f"[BETA] Erro ao carregar categoria: {e}")
            return None

    def _carregar_modelo(self) -> str:
        """Carrega modelo configurado para extração"""
        from admin.models import ConfiguracaoIA
        from sistemas.cumprimento_beta.constants import ConfigKeys

        try:
            config = self.db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "cumprimento_beta",
                ConfiguracaoIA.chave == ConfigKeys.MODELO_AGENTE1
            ).first()

            if config and config.valor:
                return config.valor

        except Exception as e:
            logger.warning(f"[BETA] Erro ao carregar modelo: {e}")

        return MODELO_PADRAO_AGENTE1

    def _get_formato_json(self) -> str:
        """Retorna formato JSON a usar"""
        if self._categoria and self._categoria.formato_json:
            return self._categoria.formato_json
        return json.dumps(SCHEMA_PADRAO_CUMPRIMENTO, indent=2, ensure_ascii=False)

    def _get_instrucoes(self) -> str:
        """Retorna instruções adicionais"""
        if self._categoria and self._categoria.instrucoes_extracao:
            return f"## INSTRUÇÕES ADICIONAIS\n\n{self._categoria.instrucoes_extracao}"
        return ""

    async def extrair_json_documento(
        self,
        documento: DocumentoBeta
    ) -> Optional[JSONResumoBeta]:
        """
        Extrai JSON de um documento relevante.

        Args:
            documento: Documento a processar

        Returns:
            JSONResumoBeta criado ou None se falhar
        """
        # Verifica se documento é relevante
        if documento.status_relevancia != StatusRelevancia.RELEVANTE:
            logger.warning(f"[BETA] Documento {documento.id} não é relevante, pulando extração")
            return None

        # Verifica se tem conteúdo
        if not documento.conteudo_texto:
            logger.warning(f"[BETA] Documento {documento.id} sem conteúdo, pulando extração")
            return None

        logger.debug(f"[BETA] Extraindo JSON do documento {documento.id}")

        # Monta prompt
        prompt = PROMPT_EXTRACAO_JSON.format(
            formato_json=self._get_formato_json(),
            instrucoes_adicionais=self._get_instrucoes(),
            tipo_documento=documento.descricao_documento or f"Código {documento.codigo_documento}",
            data_documento=documento.data_documento.strftime("%d/%m/%Y") if documento.data_documento else "Não informada",
            documento_id=documento.documento_id_tjms,
            conteudo=documento.conteudo_texto[:15000]  # Limita tamanho
        )

        inicio = time.time()

        try:
            # Chama Gemini
            resposta = await chamar_gemini_async(
                prompt=prompt,
                modelo=self._modelo
            )

            tempo_ms = int((time.time() - inicio) * 1000)

            # Extrai e valida JSON
            json_extraido = self._extrair_e_validar_json(resposta)

            if json_extraido is None:
                logger.warning(f"[BETA] Falha ao extrair JSON do documento {documento.id}")
                return None

            # Cria registro
            json_resumo = JSONResumoBeta(
                documento_id=documento.id,
                json_conteudo=json_extraido,
                categoria_id=self._categoria.id if self._categoria else None,
                categoria_nome=self._categoria.nome if self._categoria else "padrao",
                modelo_usado=self._modelo,
                tempo_processamento_ms=tempo_ms,
                json_valido=True
            )

            self.db.add(json_resumo)

            logger.debug(f"[BETA] JSON extraído do documento {documento.id} em {tempo_ms}ms")

            return json_resumo

        except Exception as e:
            logger.error(f"[BETA] Erro ao extrair JSON do documento {documento.id}: {e}")
            return None

    def _extrair_e_validar_json(self, resposta: str) -> Optional[Dict[str, Any]]:
        """Extrai e valida JSON da resposta"""
        if not resposta:
            return None

        try:
            import re

            # Remove markdown se presente
            texto = resposta.strip()

            # Remove ```json ... ```
            match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', texto, re.DOTALL)
            if match:
                texto = match.group(1)

            # Tenta parsear
            dados = json.loads(texto)

            if not isinstance(dados, dict):
                return None

            return dados

        except json.JSONDecodeError as e:
            logger.warning(f"[BETA] JSON inválido: {e}")
            return None

    async def extrair_jsons_sessao(
        self,
        sessao: SessaoCumprimentoBeta,
        on_progress: Optional[callable] = None
    ) -> int:
        """
        Extrai JSONs de todos os documentos relevantes de uma sessão.

        Args:
            sessao: Sessão do beta
            on_progress: Callback para progresso

        Returns:
            Quantidade de JSONs extraídos com sucesso
        """
        # Busca documentos relevantes sem JSON
        documentos = self.db.query(DocumentoBeta).filter(
            DocumentoBeta.sessao_id == sessao.id,
            DocumentoBeta.status_relevancia == StatusRelevancia.RELEVANTE
        ).outerjoin(
            JSONResumoBeta, DocumentoBeta.id == JSONResumoBeta.documento_id
        ).filter(
            JSONResumoBeta.id == None  # Sem JSON ainda
        ).all()

        if not documentos:
            logger.info(f"[BETA] Nenhum documento relevante pendente de extração na sessão {sessao.id}")
            return 0

        logger.info(f"[BETA] Extraindo JSON de {len(documentos)} documentos relevantes")

        # Atualiza status da sessão
        sessao.status = StatusSessao.EXTRAINDO_JSON
        self.db.commit()

        extraidos = 0

        for idx, doc in enumerate(documentos):
            # Callback de progresso
            if on_progress:
                await on_progress(
                    etapa="extraindo_json",
                    atual=idx + 1,
                    total=len(documentos),
                    mensagem=f"Extraindo JSON {idx + 1}/{len(documentos)}"
                )

            # Extrai JSON
            json_resumo = await self.extrair_json_documento(doc)

            if json_resumo:
                extraidos += 1

            # Commit parcial a cada 5 documentos
            if (idx + 1) % 5 == 0:
                self.db.commit()

        # Commit final
        self.db.commit()

        logger.info(f"[BETA] Extração concluída: {extraidos}/{len(documentos)} JSONs extraídos")

        return extraidos


async def extrair_jsons_sessao(
    db: Session,
    sessao: SessaoCumprimentoBeta,
    on_progress: Optional[callable] = None
) -> int:
    """
    Função auxiliar para extrair JSONs de documentos de uma sessão.

    Args:
        db: Sessão do banco de dados
        sessao: Sessão do beta
        on_progress: Callback para progresso

    Returns:
        Quantidade de JSONs extraídos
    """
    service = ExtracaoJSONService(db)
    return await service.extrair_jsons_sessao(sessao, on_progress)
