# sistemas/pedido_calculo/agentes.py
"""
Agentes de IA para processamento do Pedido de Cálculo

Pipeline de 3 agentes:
- Agente 1: Análise do XML do processo (sem IA - extração direta)
- Agente 2: Extração de informações dos PDFs (com IA)
- Agente 3: Geração do pedido de cálculo (com IA)

Autor: LAB/PGE-MS
"""

import asyncio
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from services.gemini_service import gemini_service, get_thinking_level
from services.ia_params_resolver import get_ia_params, IAParams
from database.connection import SessionLocal
from admin.models import PromptConfig, ConfiguracaoIA


def _get_pedido_calculo_thinking_level() -> str:
    """Obtém thinking_level configurado para pedido_calculo"""
    try:
        db = SessionLocal()
        try:
            return get_thinking_level(db, "pedido_calculo")
        finally:
            db.close()
    except Exception:
        return "low"  # Default para classificação
from .ia_logger import get_logger

from .models import (
    ResultadoAgente1,
    ResultadoAgente2,
    DadosBasicos,
    DocumentosParaDownload,
    MovimentosRelevantes,
    TipoIntimacao,
    PeriodoCondenacao,
    CorrecaoMonetaria,
    JurosMoratorios,
    DatasProcessuais,
    CalculoExequente,
    PedidoCalculo,
    CertidaoCandidata,
    CertidaoCitacaoIntimacao
)
from .xml_parser import XMLParser, _primeiro_dia_util_posterior


# Nome do sistema para configurações
SISTEMA = "pedido_calculo"

# Modelo padrão (fallback)
MODELO_PADRAO = "gemini-3-flash-preview"


def _get_config(chave: str, default: str = None) -> str:
    """Busca configuração do banco de dados"""
    db = SessionLocal()
    try:
        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == SISTEMA,
            ConfiguracaoIA.chave == chave
        ).first()
        return config.valor if config else default
    finally:
        db.close()


def _get_prompt(tipo: str) -> Optional[str]:
    """Busca prompt do banco de dados"""
    db = SessionLocal()
    try:
        prompt = db.query(PromptConfig).filter(
            PromptConfig.sistema == SISTEMA,
            PromptConfig.tipo == tipo,
            PromptConfig.is_active == True
        ).first()
        return prompt.conteudo if prompt else None
    finally:
        db.close()


class Agente1AnaliseXML:
    """
    Agente 1: Análise do XML do processo
    
    Responsável por:
    1. Extrair dados básicos do processo (partes, datas, etc.)
    2. Identificar documentos relevantes para download
    3. Mapear movimentos de citação e intimações
    """
    
    def __init__(self, modelo: str = MODELO_PADRAO):
        self.modelo = modelo

    def _normalizar_texto(self, valor: Optional[str]) -> str:
        if not valor:
            return ""
        texto = unicodedata.normalize("NFKD", str(valor))
        texto = texto.encode("ascii", "ignore").decode("ascii")
        texto = re.sub(r"\s+", " ", texto).strip().lower()
        return texto

    def _texto_valido(self, valor: Optional[str]) -> Optional[str]:
        if not valor:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        texto_norm = self._normalizar_texto(texto)
        if not texto_norm:
            return None
        if texto_norm in ["null", "none"]:
            return None
        if "identificado" in texto_norm and ("nao" in texto_norm or "no" in texto_norm):
            return None
        return texto

    def _numero_processo_preenchido(self, valor: Optional[str]) -> bool:
        if not valor:
            return False
        digits = re.sub(r"\D", "", str(valor))
        return len(digits) >= 20

    def _cpf_preenchido(self, valor: Optional[str]) -> bool:
        if not valor:
            return False
        digits = re.sub(r"\D", "", str(valor))
        return len(digits) == 11

    def _formatar_numero_processo(self, valor: Any) -> Optional[str]:
        if not valor:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        digits = re.sub(r"\D", "", texto)
        if len(digits) == 20:
            return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"
        return texto

    def _formatar_cpf(self, valor: Any) -> Optional[str]:
        if not valor:
            return None
        digits = re.sub(r"\D", "", str(valor))
        if len(digits) != 11:
            return None
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"

    def _parse_data_ia(self, valor: Any) -> Optional[date]:
        if not valor:
            return None
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        texto = str(valor).strip()
        if not texto:
            return None
        formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d"]
        for fmt in formatos:
            try:
                return datetime.strptime(texto[:10], fmt).date()
            except ValueError:
                continue
        return None

    def _parse_valor_causa(self, valor: Any) -> Optional[float]:
        if valor is None:
            return None
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip()
        if not texto:
            return None
        texto = texto.replace("R$", "").replace(" ", "")
        texto = re.sub(r"[^0-9,.-]", "", texto)
        if not texto:
            return None
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "")
                texto = texto.replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto and "." not in texto:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None

    def _campos_faltantes(
        self,
        dados_basicos: DadosBasicos,
        movimentos: MovimentosRelevantes
    ) -> List[str]:
        faltantes = []

        if not self._numero_processo_preenchido(dados_basicos.numero_processo):
            faltantes.append("numero_processo")
        if not self._texto_valido(dados_basicos.autor):
            faltantes.append("autor")
        if not self._cpf_preenchido(dados_basicos.cpf_autor):
            faltantes.append("cpf_autor")
        if not self._texto_valido(dados_basicos.reu):
            faltantes.append("reu")
        if not self._texto_valido(dados_basicos.comarca):
            faltantes.append("comarca")
        if not self._texto_valido(dados_basicos.vara):
            faltantes.append("vara")
        if not dados_basicos.data_ajuizamento:
            faltantes.append("data_ajuizamento")
        if dados_basicos.valor_causa is None:
            faltantes.append("valor_causa")
        if not movimentos.transito_julgado:
            faltantes.append("transito_julgado")

        return faltantes

    def _parsear_json(self, resposta: str) -> Dict[str, Any]:
        if not resposta:
            return {}
        texto = resposta.strip()
        if texto.startswith("```json"):
            texto = texto[7:]
        if texto.startswith("```"):
            texto = texto[3:]
        if texto.endswith("```"):
            texto = texto[:-3]
        texto = texto.strip()

        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", texto, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
        return {}

    async def _fallback_ia(self, xml_texto: str, campos_faltantes: List[str]) -> Dict[str, Any]:
        if not campos_faltantes:
            return {}
        if not gemini_service.is_configured():
            return {}

        campos = ", ".join(campos_faltantes)
        prompt = f"""Extraia informacoes de um XML de processo judicial (CNJ/TJ-MS).
Retorne APENAS um JSON com as chaves abaixo. Use null quando nao encontrar.
Campos solicitados: {campos}

Formato:
{{
  "numero_processo": "...",
  "autor": "...",
  "cpf_autor": "...",
  "reu": "...",
  "comarca": "...",
  "vara": "...",
  "data_ajuizamento": "DD/MM/AAAA",
  "valor_causa": "1234.56",
  "transito_julgado": "DD/MM/AAAA"
}}

XML:
{xml_texto}
"""

        response = await gemini_service.generate(
            prompt=prompt,
            model="gemini-3-flash-preview",
            temperature=0.1,
            thinking_level=_get_pedido_calculo_thinking_level()
        )

        if not response.success:
            return {}

        return self._parsear_json(response.content)

    def _aplicar_fallback(
        self,
        dados_basicos: DadosBasicos,
        movimentos: MovimentosRelevantes,
        dados_ia: Dict[str, Any]
    ) -> None:
        if not dados_ia:
            return

        if not self._numero_processo_preenchido(dados_basicos.numero_processo):
            numero = self._formatar_numero_processo(dados_ia.get("numero_processo"))
            if numero:
                dados_basicos.numero_processo = numero

        if not self._texto_valido(dados_basicos.autor):
            autor = self._texto_valido(dados_ia.get("autor"))
            if autor:
                dados_basicos.autor = autor

        if not self._cpf_preenchido(dados_basicos.cpf_autor):
            cpf = self._formatar_cpf(dados_ia.get("cpf_autor"))
            if cpf:
                dados_basicos.cpf_autor = cpf

        if not self._texto_valido(dados_basicos.reu):
            reu = self._texto_valido(dados_ia.get("reu"))
            if reu:
                dados_basicos.reu = reu

        if not self._texto_valido(dados_basicos.comarca):
            comarca = self._texto_valido(dados_ia.get("comarca"))
            if comarca:
                dados_basicos.comarca = comarca

        if not self._texto_valido(dados_basicos.vara):
            vara = self._texto_valido(dados_ia.get("vara"))
            if vara:
                dados_basicos.vara = vara

        if not dados_basicos.data_ajuizamento:
            data_ajuizamento = self._parse_data_ia(dados_ia.get("data_ajuizamento"))
            if data_ajuizamento:
                dados_basicos.data_ajuizamento = data_ajuizamento

        if dados_basicos.valor_causa is None:
            valor_causa = self._parse_valor_causa(dados_ia.get("valor_causa"))
            if valor_causa is not None:
                dados_basicos.valor_causa = valor_causa

        if not movimentos.transito_julgado:
            transito_julgado = self._parse_data_ia(dados_ia.get("transito_julgado"))
            if transito_julgado:
                movimentos.transito_julgado = transito_julgado
    
    async def analisar(self, xml_texto: str) -> ResultadoAgente1:
        """
        Analisa o XML do processo e extrai informações estruturadas.
        
        O processamento é híbrido:
        - Dados estruturados são extraídos diretamente do XML (sem IA)
        - IA é usada apenas para identificação de contexto quando necessário
        
        Args:
            xml_texto: XML completo do processo
            
        Returns:
            ResultadoAgente1 com dados extraídos
        """
        try:
            # Parse do XML (sem IA - extração direta)
            parser = XMLParser(xml_texto)
            
            dados_basicos = parser.extrair_dados_basicos()
            documentos = parser.identificar_documentos_para_download()
            movimentos = parser.extrair_movimentos_relevantes()

            campos_faltantes = self._campos_faltantes(dados_basicos, movimentos)
            if campos_faltantes:
                try:
                    dados_ia = await self._fallback_ia(xml_texto, campos_faltantes)
                    self._aplicar_fallback(dados_basicos, movimentos, dados_ia)
                except Exception:
                    pass
            
            return ResultadoAgente1(
                dados_basicos=dados_basicos,
                documentos_para_download=documentos,
                movimentos_relevantes=movimentos
            )
            
        except Exception as e:
            return ResultadoAgente1(
                dados_basicos=DadosBasicos(
                    numero_processo="",
                    autor="Erro na extração"
                ),
                documentos_para_download=DocumentosParaDownload(),
                movimentos_relevantes=MovimentosRelevantes(),
                erro=f"Erro ao analisar XML: {str(e)}"
            )


class AnalisadorCertidoesCumprimento:
    """
    Analisador de certidões para identificar a certidão correta de
    intimação para cumprimento/impugnação usando IA.

    A IA analisa o texto de cada certidão candidata e identifica qual
    delas se refere à intimação do Estado para cumprimento de sentença.
    """

    PROMPT_ANALISE_CERTIDAO = """Analise o texto desta certidao judicial e responda em JSON.

## TEXTO DA CERTIDAO
{texto_certidao}

## INSTRUCOES
Analise se esta certidao se refere a uma INTIMACAO DO ESTADO (PGE/Procuradoria) para:
- Cumprimento de sentenca
- Impugnacao de calculo
- Pagamento ou impugnacao (art. 523 ou 535 do CPC)
- Decurso de prazo / inexistencia de leitura (intimacao automatica)

ATENCAO CRITICA - CERTIDAO DE REMESSA vs CERTIDAO DE CIENCIA:
Existem DOIS tipos de certidoes relacionadas a intimacao eletronica:

1. CERTIDAO DE REMESSA (NAO usar como intimacao!):
   - Indica APENAS que a intimacao foi ENVIADA/DISPONIBILIZADA no portal
   - Termos tipicos: "foi encaminhado para vista/intimacao", "remessa da intimacao", "disponibilizado no portal"
   - Exemplo: "CERTIFICA-SE que, em 05/12/2025 o ato abaixo foi encaminhado para vista/intimacao"
   - Esta NAO e a data de intimacao! O Estado ainda nao tomou ciencia.
   - REJEITAR esta certidao (is_intimacao_cumprimento: false)

2. CERTIDAO DE CIENCIA/RECEBIMENTO (usar esta!):
   - Indica que o Estado EFETIVAMENTE tomou ciencia da intimacao
   - Termos tipicos: "CIENCIA DA INTIMACAO", "Declaramos ciencia nesta data", "atraves do acesso ao portal eletronico"
   - Contem "Data da Intimacao:" com data e hora especificas
   - Exemplo: "CIENCIA DA INTIMACAO... Data da Intimacao: 11/12/2025 09:14:34"
   - ESTA e a certidao correta! Use a "Data da Intimacao" como data_intimacao.

ATENCAO ESPECIAL - INTIMACAO POR DECURSO DE PRAZO:
Quando a certidao menciona "inexistencia de leitura" ou "decurso de prazo" (art. 5º, § 3º, Lei 11.419/06),
significa que a intimacao foi AUTOMATICA apos 10 dias sem leitura. Nesse caso:
- A DATA REAL DA INTIMACAO e a data em que se considera intimado (geralmente 10 dias apos disponibilizacao)
- NAO e a data da certidao/documento
- O texto geralmente dira algo como "restou intimado(a) em DD/MM/AAAA"

Procure por indicadores POSITIVOS (certidao de ciencia):
- "CIENCIA DA INTIMACAO" no inicio
- "Declaramos ciencia nesta data"
- "atraves do acesso ao portal eletronico"
- "Data da Intimacao:" seguido de data e hora
- "PROCURADORIA GERAL DO ESTADO" como intimado
- "cumprimento", "impugnar", "impugnacao"
- "art. 523", "art. 535"
- "prazo de 15 dias", "prazo de 30 dias"

Indicadores NEGATIVOS (certidao de remessa - REJEITAR):
- "foi encaminhado para vista/intimacao"
- "Certidao de Remessa"
- "preparei os autos com vista"
- Sem "Data da Intimacao:" especifica

## RESPOSTA
Retorne APENAS o JSON abaixo (sem explicacoes):
{{"is_intimacao_cumprimento": true, "intimado": "PROCURADORIA...", "data_intimacao": "DD/MM/AAAA", "data_inicio_prazo": "DD/MM/AAAA", "data_fim_prazo": "DD/MM/AAAA", "prazo_dias": 30, "tipo_intimacao": "cumprimento_sentenca", "confianca": "alta"}}

Campos:
- is_intimacao_cumprimento: true APENAS se for certidao de CIENCIA (recebimento), false se for certidao de REMESSA (envio)
- intimado: nome do intimado
- data_intimacao: DATA REAL em que o Estado EFETIVAMENTE tomou ciencia (formato DD/MM/AAAA) - MUITO IMPORTANTE!
  * Use o campo "Data da Intimacao:" quando disponivel
  * Se houver decurso de prazo, use a data em que "restou intimado", NAO a data do documento
  * Se houver "Declaramos ciencia nesta data", use essa data
  * NUNCA use a data de "encaminhamento" ou "remessa" - essa e apenas a data de envio!
- data_inicio_prazo: data em que o prazo comecou a correr (primeiro dia util apos intimacao) ou null
- data_fim_prazo: previsao de encerramento do prazo ou null
- prazo_dias: prazo em dias ou null
- tipo_intimacao: "cumprimento_sentenca", "impugnacao_calculo", "citacao", "decurso_prazo" ou "outro"
- confianca: "alta", "media" ou "baixa"

REGRA IMPORTANTE: Certidoes de REMESSA devem retornar is_intimacao_cumprimento: false.
Apenas certidoes de CIENCIA/RECEBIMENTO devem retornar is_intimacao_cumprimento: true."""

    def __init__(self, modelo: str = None, logger=None):
        # Usa resolver de parâmetros por agente
        db = SessionLocal()
        try:
            self._params = get_ia_params(db, "pedido_calculo", "extracao")
        finally:
            db.close()
        self.modelo = modelo or self._params.modelo
        self.logger = logger  # Logger opcional para debug

    def _parse_data(self, data_str: Optional[str]) -> Optional[date]:
        """Parseia string de data para date"""
        if not data_str:
            return None

        data_str = data_str.strip()
        formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S"]
        for fmt in formatos:
            try:
                return datetime.strptime(data_str[:10], fmt).date()
            except ValueError:
                continue
        return None

    async def analisar_certidao(
        self,
        id_certidao: str,
        texto_certidao: str,
        tipo_documento: str
    ) -> Dict[str, Any]:
        """
        Analisa uma única certidão usando IA.

        Returns:
            Dict com resultado da análise
        """
        # Prepara log se disponível (fora do try para garantir escopo)
        log_entry = None
        texto_limitado = texto_certidao[:8000] if len(texto_certidao) > 8000 else texto_certidao

        try:
            prompt = self.PROMPT_ANALISE_CERTIDAO.format(texto_certidao=texto_limitado)

            if self.logger:
                from .ia_logger import LogEntry
                log_entry = LogEntry("analise_certidao", f"Analisando certidão {id_certidao}")
                log_entry.set_documento(id_certidao, texto_limitado)
                log_entry.set_prompt(prompt)
                log_entry.set_modelo(self.modelo)

            response = await gemini_service.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=0.1,
                thinking_level=_get_pedido_calculo_thinking_level()
            )

            if not response.success:
                if log_entry:
                    log_entry.set_erro(response.error)
                    self.logger._logs.append(log_entry)
                return {
                    "id_certidao": id_certidao,
                    "tipo_documento": tipo_documento,
                    "is_intimacao_cumprimento": False,
                    "erro": response.error
                }

            # Parseia resposta JSON
            resposta = response.content.strip()

            # Remove marcadores de código markdown
            if resposta.startswith("```json"):
                resposta = resposta[7:]
            elif resposta.startswith("```"):
                resposta = resposta[3:]
            if resposta.endswith("```"):
                resposta = resposta[:-3]

            resposta = resposta.strip()

            # Tenta parsear diretamente
            dados = None
            try:
                dados = json.loads(resposta)
            except json.JSONDecodeError:
                # Se falhar, tenta extrair JSON do texto
                import re
                match = re.search(r'\{[\s\S]*\}', resposta)
                if match:
                    try:
                        dados = json.loads(match.group(0))
                    except json.JSONDecodeError as e2:
                        print(f"[DEBUG] Resposta IA para {id_certidao}:")
                        print(resposta[:500])
                        if log_entry:
                            log_entry.set_resposta(response.content, None)
                            self.logger._logs.append(log_entry)
                        raise e2
                else:
                    print(f"[DEBUG] Resposta IA sem JSON para {id_certidao}:")
                    print(resposta[:500])
                    if log_entry:
                        log_entry.set_resposta(response.content, None)
                        self.logger._logs.append(log_entry)
                    raise json.JSONDecodeError("No JSON found", resposta, 0)

            dados["id_certidao"] = id_certidao
            dados["tipo_documento"] = tipo_documento

            # Salva resposta no log
            if log_entry:
                log_entry.set_resposta(response.content, dados)
                self.logger._logs.append(log_entry)

            return dados

        except json.JSONDecodeError as e:
            # Log já foi salvo dentro do try quando ocorre JSONDecodeError
            return {
                "id_certidao": id_certidao,
                "tipo_documento": tipo_documento,
                "is_intimacao_cumprimento": False,
                "erro": f"Erro ao parsear JSON: {str(e)}"
            }
        except Exception as e:
            # Salva log de erro para outras exceções
            if log_entry and self.logger:
                log_entry.set_erro(str(e))
                self.logger._logs.append(log_entry)
            return {
                "id_certidao": id_certidao,
                "tipo_documento": tipo_documento,
                "is_intimacao_cumprimento": False,
                "erro": str(e)
            }

    async def analisar_certidoes_paralelo(
        self,
        certidoes_textos: Dict[str, Tuple[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Analisa múltiplas certidões em paralelo.

        Args:
            certidoes_textos: Dict com id_certidao -> (texto, tipo_documento)

        Returns:
            Lista de resultados de análise
        """
        if not certidoes_textos:
            return []

        # Cria tasks para análise paralela
        tasks = []
        for id_cert, (texto, tipo_doc) in certidoes_textos.items():
            tasks.append(self.analisar_certidao(id_cert, texto, tipo_doc))

        # Executa em paralelo
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        # Processa resultados
        resultados_processados = []
        for resultado in resultados:
            if isinstance(resultado, Exception):
                resultados_processados.append({
                    "is_intimacao_cumprimento": False,
                    "erro": str(resultado)
                })
            else:
                resultados_processados.append(resultado)

        return resultados_processados

    def identificar_certidao_cumprimento(
        self,
        resultados_analise: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Identifica a certidão de intimação para cumprimento entre os resultados.

        Prioriza por:
        1. is_intimacao_cumprimento = True
        2. confiança "alta"
        3. tipo_intimacao = "cumprimento_sentenca" ou "impugnacao_calculo"
        4. Data mais recente (certidão de ciência vem depois da remessa)

        Returns:
            Dict com dados da certidão identificada ou None
        """
        candidatas = []

        for resultado in resultados_analise:
            if resultado.get("is_intimacao_cumprimento"):
                # Calcula score de prioridade
                score = 0
                if resultado.get("confianca") == "alta":
                    score += 100
                elif resultado.get("confianca") == "media":
                    score += 50

                tipo = resultado.get("tipo_intimacao", "")
                if tipo in ["cumprimento_sentenca", "impugnacao_calculo"]:
                    score += 50
                if "procuradoria" in resultado.get("intimado", "").lower():
                    score += 30

                # Prefere certidões com data_intimacao mais recente
                # (ciência sempre vem depois da remessa)
                data_intimacao = resultado.get("data_intimacao")
                if data_intimacao:
                    try:
                        # Tenta parsear a data para usar como tiebreaker
                        data_parsed = self._parse_data(data_intimacao)
                        if data_parsed:
                            # Adiciona dias desde epoch como score secundário
                            # Isso faz certidões mais recentes terem score maior
                            score += data_parsed.toordinal() / 1000000  # Pequeno incremento
                    except:
                        pass

                candidatas.append((score, resultado))

        if not candidatas:
            return None

        # Ordena por score e retorna a melhor
        candidatas.sort(key=lambda x: x[0], reverse=True)
        return candidatas[0][1]

    def criar_certidao_intimacao(
        self,
        resultado_ia: Dict[str, Any],
        data_documento: Optional[date] = None
    ) -> CertidaoCitacaoIntimacao:
        """
        Cria objeto CertidaoCitacaoIntimacao a partir do resultado da IA.

        A IA extrai do texto da certidão:
        - data_intimacao: data REAL em que o Estado foi intimado
        - data_inicio_prazo: primeiro dia útil (início do prazo)
        - data_fim_prazo: previsão de encerramento do prazo
        """
        # Extrai data de recebimento (intimação real) do resultado da IA
        data_recebimento = self._parse_data(resultado_ia.get("data_intimacao"))

        # Se não encontrou no texto, usa a data do documento como fallback
        if not data_recebimento and data_documento:
            data_recebimento = data_documento
            print(f"[AVISO] Usando data do documento ({data_documento}) como data de intimação (não encontrada no texto)")

        # Termo inicial do prazo:
        # 1. Prioriza data_inicio_prazo extraída pela IA (já é o primeiro dia útil)
        # 2. Se não tiver, calcula a partir da data de recebimento
        termo_inicial = self._parse_data(resultado_ia.get("data_inicio_prazo"))
        if not termo_inicial and data_recebimento:
            termo_inicial = _primeiro_dia_util_posterior(data_recebimento)

        # Log para debug
        data_fim = resultado_ia.get("data_fim_prazo")
        if data_recebimento or termo_inicial:
            print(f"[CERTIDÃO] Data intimação: {data_recebimento}, Início prazo: {termo_inicial}, Fim prazo: {data_fim}")

        # Determina tipo de certidão
        tipo_doc = resultado_ia.get("tipo_documento", "")
        tipo_certidao = "sistema" if tipo_doc == "9508" else "cartorio"

        return CertidaoCitacaoIntimacao(
            tipo=TipoIntimacao.INTIMACAO_IMPUGNACAO,
            id_certidao_9508=resultado_ia.get("id_certidao"),
            data_certidao=data_documento,
            data_recebimento=data_recebimento,
            termo_inicial_prazo=termo_inicial,
            tipo_certidao=tipo_certidao,
            identificado_por_ia=True
        )


class AnalisadorPlanilhaCalculo:
    """
    Analisador de documentos para identificar a planilha de cálculo correta
    usando IA.

    Quando há múltiplos documentos candidatos (petições, anexos, docs 9509),
    a IA analisa cada um e identifica qual é realmente a planilha de cálculo
    do exequente com valores atualizados.
    """

    PROMPT_ANALISE_PLANILHA = """Analise o texto deste documento judicial e determine se é uma PLANILHA DE CÁLCULO do exequente.

## TEXTO DO DOCUMENTO (primeiros 5000 caracteres)
{texto_documento}

## O QUE É UMA PLANILHA DE CÁLCULO
Uma planilha de cálculo de cumprimento de sentença contém:
- Valor principal/base da condenação
- Correção monetária (com índices e períodos)
- Juros de mora (com taxas e períodos)
- Cálculos mês a mês ou período a período
- Valor total atualizado
- Data-base do cálculo

## O QUE NÃO É PLANILHA DE CÁLCULO
- Petição inicial ou de cumprimento (texto argumentativo, pedidos)
- Procuração (dados de advogado, poderes)
- Certidões (certificações do cartório)
- Comprovantes de pagamento
- Documentos pessoais (RG, CPF, contracheques)
- Decisões judiciais (sentenças, despachos)

## ANÁLISE
Responda APENAS com JSON:
{{
    "is_planilha_calculo": true/false,
    "confianca": "alta/media/baixa",
    "motivo": "breve explicação",
    "valor_total_encontrado": "R$ X.XXX,XX ou null",
    "data_base_encontrada": "DD/MM/AAAA ou null",
    "tipo_documento_real": "planilha_calculo/peticao/procuracao/certidao/outros"
}}"""

    def __init__(self, modelo: str = None, logger=None):
        # Usa resolver de parâmetros por agente
        db = SessionLocal()
        try:
            self._params = get_ia_params(db, "pedido_calculo", "extracao")
        finally:
            db.close()
        self.modelo = modelo or self._params.modelo
        self.logger = logger

    async def analisar_documento(
        self,
        doc_id: str,
        texto_documento: str,
        descricao: str = ""
    ) -> Dict[str, Any]:
        """
        Analisa um único documento para verificar se é planilha de cálculo.

        Returns:
            Dict com resultado da análise
        """
        log_entry = None
        # Limita texto para análise rápida
        texto_limitado = texto_documento[:5000] if len(texto_documento) > 5000 else texto_documento

        try:
            prompt = self.PROMPT_ANALISE_PLANILHA.replace("{texto_documento}", texto_limitado)

            if self.logger:
                from .ia_logger import LogEntry
                log_entry = LogEntry("analise_planilha", f"Analisando documento {doc_id}")
                log_entry.set_documento(doc_id, texto_limitado)
                log_entry.set_prompt(prompt)
                log_entry.set_modelo(self.modelo)

            response = await gemini_service.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=0.1,
                thinking_level=_get_pedido_calculo_thinking_level()
            )

            if not response.success:
                if log_entry and self.logger:
                    log_entry.set_erro(response.error)
                    self.logger._logs.append(log_entry)
                return {
                    "doc_id": doc_id,
                    "descricao": descricao,
                    "is_planilha_calculo": False,
                    "erro": response.error
                }

            # Parseia resposta JSON
            resposta = response.content.strip()

            # Remove marcadores de código markdown
            if resposta.startswith("```json"):
                resposta = resposta[7:]
            elif resposta.startswith("```"):
                resposta = resposta[3:]
            if resposta.endswith("```"):
                resposta = resposta[:-3]

            resposta = resposta.strip()

            # Normaliza espaços
            resposta = re.sub(r'\s+', ' ', resposta)

            dados = None
            try:
                dados = json.loads(resposta)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', resposta, re.DOTALL)
                if match:
                    try:
                        dados = json.loads(re.sub(r'\s+', ' ', match.group(0)))
                    except json.JSONDecodeError as e2:
                        if log_entry and self.logger:
                            log_entry.set_resposta(response.content, None)
                            self.logger._logs.append(log_entry)
                        return {
                            "doc_id": doc_id,
                            "descricao": descricao,
                            "is_planilha_calculo": False,
                            "erro": f"JSON inválido: {str(e2)}"
                        }

            dados["doc_id"] = doc_id
            dados["descricao"] = descricao

            if log_entry and self.logger:
                log_entry.set_resposta(response.content, dados)
                self.logger._logs.append(log_entry)

            return dados

        except Exception as e:
            if log_entry and self.logger:
                log_entry.set_erro(str(e))
                self.logger._logs.append(log_entry)
            return {
                "doc_id": doc_id,
                "descricao": descricao,
                "is_planilha_calculo": False,
                "erro": str(e)
            }

    async def identificar_planilha_correta(
        self,
        documentos_candidatos: Dict[str, Tuple[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Analisa múltiplos documentos candidatos e identifica a planilha de cálculo.

        Args:
            documentos_candidatos: Dict com doc_id -> (texto, descricao)

        Returns:
            Dict com dados do documento identificado como planilha ou None
        """
        if not documentos_candidatos:
            return None

        # Se só tem 1 candidato, analisa diretamente
        if len(documentos_candidatos) == 1:
            doc_id, (texto, descricao) = list(documentos_candidatos.items())[0]
            resultado = await self.analisar_documento(doc_id, texto, descricao)
            if resultado.get("is_planilha_calculo"):
                resultado["texto"] = texto
                return resultado
            return None

        # Múltiplos candidatos: analisa todos em paralelo
        print(f"[PLANILHA] Analisando {len(documentos_candidatos)} documentos candidatos com IA...")

        tasks = []
        doc_ids = []
        for doc_id, (texto, descricao) in documentos_candidatos.items():
            tasks.append(self.analisar_documento(doc_id, texto, descricao))
            doc_ids.append(doc_id)

        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtra planilhas identificadas
        planilhas_encontradas = []
        for i, resultado in enumerate(resultados):
            if isinstance(resultado, Exception):
                continue
            if resultado.get("is_planilha_calculo"):
                resultado["texto"] = documentos_candidatos[doc_ids[i]][0]
                planilhas_encontradas.append(resultado)
                print(f"[PLANILHA] ✓ Documento {resultado['doc_id']}: É planilha (confiança: {resultado.get('confianca', '?')})")
            else:
                tipo_real = resultado.get("tipo_documento_real", "?")
                print(f"[PLANILHA] ✗ Documento {resultado['doc_id']}: NÃO é planilha (tipo real: {tipo_real})")

        if not planilhas_encontradas:
            print("[PLANILHA] Nenhuma planilha de cálculo identificada entre os candidatos")
            return None

        # Se encontrou múltiplas planilhas, prioriza por confiança
        if len(planilhas_encontradas) > 1:
            # Ordena por confiança (alta > media > baixa)
            ordem_confianca = {"alta": 3, "media": 2, "baixa": 1}
            planilhas_encontradas.sort(
                key=lambda x: ordem_confianca.get(x.get("confianca", "baixa"), 0),
                reverse=True
            )
            print(f"[PLANILHA] Múltiplas planilhas encontradas, usando a de maior confiança: {planilhas_encontradas[0]['doc_id']}")

        return planilhas_encontradas[0]


class ExtratorProcessoOrigem:
    """
    Extrai o número do processo de origem de uma petição de cumprimento.

    Em cumprimentos autônomos, a petição inicial menciona o número
    do processo de conhecimento onde foi proferida a sentença.
    """

    PROMPT_EXTRACAO = """Analise o texto desta peticao de cumprimento de sentenca e extraia o numero do processo de ORIGEM.

## TEXTO DA PETICAO
{texto_peticao}

## INSTRUCOES
Esta e uma peticao de cumprimento de sentenca. Preciso encontrar o numero do PROCESSO ORIGINAL
(processo de conhecimento) onde foi proferida a sentenca que esta sendo executada.

O numero do processo geralmente aparece em frases como:
- "nos autos do processo n..."
- "processo originario n..."
- "processo de conhecimento n..."
- "conforme sentenca proferida nos autos..."
- "oriundo do processo..."
- "processo principal n..."

O numero esta no formato CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN
Exemplo: 0815077-35.2021.8.12.0110

## RESPOSTA
Retorne APENAS um JSON:
{{"numero_processo_origem": "NNNNNNN-NN.NNNN.N.NN.NNNN", "confianca": "alta/media/baixa"}}

Se nao encontrar, retorne:
{{"numero_processo_origem": null, "confianca": "baixa"}}"""

    def __init__(self, modelo: str = None):
        # Usa resolver de parâmetros por agente
        db = SessionLocal()
        try:
            self._params = get_ia_params(db, "pedido_calculo", "extracao")
        finally:
            db.close()
        self.modelo = modelo or self._params.modelo

    async def extrair_numero_origem(self, texto_peticao: str) -> Optional[str]:
        """
        Extrai o número do processo de origem do texto da petição.

        Args:
            texto_peticao: Texto extraído da petição inicial do cumprimento

        Returns:
            Número CNJ do processo de origem ou None
        """
        import re

        try:
            # Limita o texto (primeiras páginas geralmente têm a informação)
            texto_limitado = texto_peticao[:15000] if len(texto_peticao) > 15000 else texto_peticao

            prompt = self.PROMPT_EXTRACAO.format(texto_peticao=texto_limitado)

            response = await gemini_service.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=0.1,
                thinking_level=_get_pedido_calculo_thinking_level()
            )

            if not response.success:
                print(f"[ERRO] Falha ao extrair número do processo de origem: {response.error}")
                return None

            # Parseia resposta JSON
            resposta = response.content.strip()

            # Remove marcadores de código markdown
            if resposta.startswith("```json"):
                resposta = resposta[7:]
            elif resposta.startswith("```"):
                resposta = resposta[3:]
            if resposta.endswith("```"):
                resposta = resposta[:-3]

            resposta = resposta.strip()

            # Tenta extrair JSON
            try:
                dados = json.loads(resposta)
            except json.JSONDecodeError:
                # Tenta extrair JSON do texto
                match = re.search(r'\{[\s\S]*\}', resposta)
                if match:
                    dados = json.loads(match.group(0))
                else:
                    return None

            numero = dados.get("numero_processo_origem")
            confianca = dados.get("confianca", "baixa")

            if numero:
                print(f"[IA] Processo de origem extraído: {numero} (confiança: {confianca})")
                return numero

            return None

        except Exception as e:
            print(f"[ERRO] Exceção ao extrair número do processo de origem: {e}")
            return None


class Agente2ExtracaoPDFs:
    """
    Agente 2: Extração de informações dos PDFs

    Responsável por extrair de cada tipo de documento:
    - Sentenças/Acórdãos: objeto, período, critérios de correção e juros
    - Certidões 9508: datas de recebimento efetivo (CRÍTICO para prazo)
    - Petição de cumprimento: valor solicitado
    - Planilha de cálculos: metodologia e valor total

    Usa prompt configurável do banco de dados.
    """

    # Prompt padrão (fallback se não houver no banco)
    PROMPT_PADRAO = """Analise os documentos judiciais a seguir e extraia as informações em formato JSON.

## CONTEXTO
Este é um processo de CUMPRIMENTO DE SENTENÇA contra a Fazenda Pública (Estado de MS).
Preciso extrair informações para elaborar um pedido de cálculo pericial.

## DOCUMENTOS PARA ANÁLISE
{textos_documentos}

## INSTRUÇÕES CRÍTICAS PARA DATAS DE INTIMAÇÃO

### CERTIDÃO DE INTIMAÇÃO PARA CUMPRIMENTO/IMPUGNAÇÃO (TERMO INICIAL DO PRAZO)
Esta é a data MAIS IMPORTANTE para o prazo processual. Procure nas certidões por:
- "Data da Intimação: DD/MM/AAAA" ou "Data da Intimação: DD/MM/AAAA HH:MM:SS"
- "Declaramos ciência nesta data" seguido de "Data da Intimação"
- Texto que mencione "cumprimento", "impugnar", "art. 523", "art. 535", "prazo de 15 dias" ou "prazo de 30 dias"

A data que aparece como "Data da Intimação" na certidão É a data de recebimento pelo Estado.
NÃO confunda com a data de expedição do mandado/intimação.

### CERTIDÃO DE CITAÇÃO
Procure por certidões que mencionem "citação" com "Data da Intimação" ou "Data da Citação".

## INFORMAÇÕES A EXTRAIR
Retorne um JSON com a seguinte estrutura:

```json
{{
    "objeto_condenacao": "Descrição clara do que foi condenado (ex: diferenças salariais, indenização, etc.)",
    "valor_solicitado_parte": "Valor total que o exequente está requerendo (ex: R$ 50.000,00)",
    "periodo_condenacao": {{ "inicio": "MM/AAAA", "fim": "MM/AAAA" }},
    "correcao_monetaria": {{ "indice": "IPCA-E, SELIC, etc.", "termo_inicial": "data ou evento", "termo_final": "data ou evento", "observacao": "detalhes adicionais" }},
    "juros_moratorios": {{ "taxa": "1% ao mês, SELIC, etc.", "termo_inicial": "citação, vencimento, etc.", "termo_final": "pagamento, etc.", "observacao": "detalhes" }},
    "datas": {{
        "citacao_recebimento": "DD/MM/AAAA (data que a PGE RECEBEU a citação, encontrada na certidão)",
        "transito_julgado": "DD/MM/AAAA",
        "intimacao_impugnacao_recebimento": "DD/MM/AAAA (data que a PGE RECEBEU a intimação para cumprimento/impugnação - CRÍTICO)"
    }},
    "criterios_calculo": ["critério 1", "critério 2", "..."],
    "calculo_exequente": {{ "valor_total": "R$ ...", "data_base": "DD/MM/AAAA" }}
}}
```

## ATENÇÃO ESPECIAL
- Para "intimacao_impugnacao_recebimento": procure especificamente por certidões que mencionem cumprimento de sentença, impugnação, art. 523 ou art. 535 do CPC. A data está no campo "Data da Intimação" dentro da certidão.
- Para "citacao_recebimento": procure na certidão de citação pelo campo "Data da Intimação" ou "Data da Citação".
- NÃO use a data de EXPEDIÇÃO do mandado. Use a data de RECEBIMENTO que aparece na certidão.

Retorne APENAS o JSON, sem explicações adicionais. Use null para campos não encontrados."""

    def __init__(self, modelo: str = None, logger=None):
        # Usa resolver de parâmetros por agente
        db = SessionLocal()
        try:
            self._params = get_ia_params(db, "pedido_calculo", "extracao")
        finally:
            db.close()

        self.modelo = modelo or self._params.modelo
        self.temperatura = self._params.temperatura
        self.logger = logger  # Logger para debug
    
    def _get_prompt(self) -> str:
        """Busca prompt do banco ou usa padrão"""
        prompt_db = _get_prompt("extracao_pdfs")
        return prompt_db if prompt_db else self.PROMPT_PADRAO
    
    async def extrair(self, textos_documentos: Dict[str, str]) -> ResultadoAgente2:
        """
        Extrai informações dos textos dos documentos.

        Args:
            textos_documentos: Dict com tipo de documento -> texto extraído
                Exemplo: {"sentenca": "texto...", "certidao_citacao": "texto..."}

        Returns:
            ResultadoAgente2 com informações extraídas
        """
        # Prepara log
        log_entry = None
        texto_consolidado = ""

        try:
            # Monta texto consolidado dos documentos
            texto_consolidado = self._montar_texto_documentos(textos_documentos)

            if not texto_consolidado.strip():
                return ResultadoAgente2(erro="Nenhum texto de documento fornecido")

            # Busca prompt do banco de dados
            prompt_template = self._get_prompt()
            # Usa replace() ao invés de .format() para evitar conflitos com
            # chaves {} no JSON de exemplo dentro do prompt
            prompt = prompt_template.replace("{textos_documentos}", texto_consolidado)

            # Prepara log se disponível
            if self.logger:
                from .ia_logger import LogEntry
                docs_analisados = ", ".join(textos_documentos.keys())
                log_entry = LogEntry("extracao_documentos", f"Extraindo informações de: {docs_analisados}")
                log_entry.set_documento("consolidado", texto_consolidado[:50000])
                log_entry.set_prompt(prompt)
                log_entry.set_modelo(self.modelo)

            response = await gemini_service.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=self.temperatura,
                thinking_level=_get_pedido_calculo_thinking_level()
            )

            if not response.success:
                if log_entry and self.logger:
                    log_entry.set_erro(response.error)
                    self.logger._logs.append(log_entry)
                return ResultadoAgente2(erro=f"Erro na IA: {response.error}")

            # Parseia resposta JSON
            resultado = self._parsear_resposta(response.content)

            # Salva log
            if log_entry and self.logger:
                log_entry.set_resposta(response.content, resultado.to_dict() if not resultado.erro else None)
                self.logger._logs.append(log_entry)

            return resultado

        except Exception as e:
            if log_entry and self.logger:
                log_entry.set_erro(str(e))
                self.logger._logs.append(log_entry)
            return ResultadoAgente2(erro=f"Erro na extração: {str(e)}")
    
    def _montar_texto_documentos(self, textos: Dict[str, str]) -> str:
        """Monta texto consolidado dos documentos para análise"""
        partes = []
        
        ordem = ["sentenca", "acordao", "sentenca_homologacao", "certidao_citacao", 
                 "certidao_intimacao", "pedido_cumprimento", "planilha_calculo"]
        
        for tipo in ordem:
            if tipo in textos and textos[tipo]:
                titulo = tipo.replace("_", " ").title()
                partes.append(f"### {titulo}\n{textos[tipo]}\n")
        
        # Adiciona documentos não mapeados
        for tipo, texto in textos.items():
            if tipo not in ordem and texto:
                titulo = tipo.replace("_", " ").title()
                partes.append(f"### {titulo}\n{texto}\n")
        
        return "\n---\n".join(partes)
    
    def _parsear_resposta(self, resposta: str) -> ResultadoAgente2:
        """Parseia resposta JSON da IA"""
        import re

        # Remove marcadores de código se presentes
        resposta = resposta.strip()
        if resposta.startswith("```json"):
            resposta = resposta[7:]
        elif resposta.startswith("```"):
            resposta = resposta[3:]
        if resposta.endswith("```"):
            resposta = resposta[:-3]

        resposta = resposta.strip()

        # Normaliza quebras de linha e espaços em excesso dentro do JSON
        # Isso resolve problemas de formatação irregular da IA
        resposta = re.sub(r'\s+', ' ', resposta)

        # Tenta parsear diretamente
        dados = None
        try:
            dados = json.loads(resposta)
        except json.JSONDecodeError as e1:
            # Tenta extrair JSON com regex (busca do primeiro { ao último })
            match = re.search(r'\{.*\}', resposta, re.DOTALL)
            if match:
                json_text = match.group(0)
                # Normaliza novamente após extração
                json_text = re.sub(r'\s+', ' ', json_text)
                try:
                    dados = json.loads(json_text)
                except json.JSONDecodeError as e2:
                    # Tenta reparar JSON truncado (strings não terminadas)
                    json_text = self._tentar_reparar_json(json_text)
                    try:
                        dados = json.loads(json_text)
                        print("[INFO] JSON reparado com sucesso após truncamento")
                    except json.JSONDecodeError as e3:
                        print(f"[ERRO] JSON não parseável mesmo após reparo:")
                        print(f"[ERRO] Resposta original (primeiros 500 chars): {resposta[:500]}")
                        print(f"[ERRO] Erro: {str(e3)}")
                        return ResultadoAgente2(erro=f"Erro ao parsear JSON: {str(e3)}")

        if dados is None:
            print(f"[ERRO] Nenhum JSON encontrado na resposta:")
            print(resposta[:1000])
            return ResultadoAgente2(erro="Nenhum JSON encontrado na resposta da IA")
        
        # Constrói resultado
        resultado = ResultadoAgente2()
        
        resultado.objeto_condenacao = dados.get("objeto_condenacao")
        resultado.valor_solicitado_parte = dados.get("valor_solicitado_parte")
        
        # Período
        periodo = dados.get("periodo_condenacao", {})
        if periodo:
            resultado.periodo_condenacao = PeriodoCondenacao(
                inicio=periodo.get("inicio"),
                fim=periodo.get("fim")
            )
        
        # Correção monetária
        cm = dados.get("correcao_monetaria", {})
        if cm:
            resultado.correcao_monetaria = CorrecaoMonetaria(
                indice=cm.get("indice"),
                termo_inicial=cm.get("termo_inicial"),
                termo_final=cm.get("termo_final"),
                observacao=cm.get("observacao")
            )
        
        # Juros
        juros = dados.get("juros_moratorios", {})
        if juros:
            resultado.juros_moratorios = JurosMoratorios(
                taxa=juros.get("taxa"),
                termo_inicial=juros.get("termo_inicial"),
                termo_final=juros.get("termo_final"),
                observacao=juros.get("observacao")
            )
        
        # Datas
        datas = dados.get("datas", {})
        if datas:
            resultado.datas = DatasProcessuais(
                citacao_recebimento=self._parse_data(datas.get("citacao_recebimento")),
                transito_julgado=self._parse_data(datas.get("transito_julgado")),
                intimacao_impugnacao_recebimento=self._parse_data(datas.get("intimacao_impugnacao_recebimento"))
            )
        
        # Critérios
        resultado.criterios_calculo = dados.get("criterios_calculo", [])
        
        # Cálculo do exequente
        calc = dados.get("calculo_exequente", {})
        if calc:
            resultado.calculo_exequente = CalculoExequente(
                valor_total=calc.get("valor_total"),
                data_base=calc.get("data_base")
            )
        
        return resultado

    def _tentar_reparar_json(self, json_text: str) -> str:
        """
        Tenta reparar JSON truncado ou mal formado.

        Problemas comuns:
        - Strings não terminadas (Unterminated string)
        - Chaves/colchetes não fechados
        - JSON cortado no meio
        """
        import re

        texto = json_text.strip()

        # 1. Verifica se há strings não terminadas (erro mais comum)
        # Estratégia: encontra a última linha completa de JSON válido
        linhas = texto.split('\n')
        texto_reconstruido = []

        for linha in linhas:
            linha_stripped = linha.rstrip()
            if not linha_stripped:
                continue

            # Conta aspas na linha (excluindo aspas escapadas)
            aspas_na_linha = linha_stripped.count('"') - linha_stripped.count('\\"')

            # Se a linha tem número par de aspas, provavelmente está completa
            if aspas_na_linha % 2 == 0:
                texto_reconstruido.append(linha_stripped)
            else:
                # Linha com string não terminada - tenta fechar
                # Remove parte truncada e fecha a string
                # Procura pelo último valor string que foi iniciado
                match = re.search(r'^(.*"[^"]*:\s*")([^"]*?)$', linha_stripped)
                if match:
                    # Formato: "chave": "valor_incompleto
                    texto_reconstruido.append(match.group(1) + '[TRUNCADO]"')
                else:
                    # Outro caso: pode ser item de array
                    match2 = re.search(r'^(\s*")([^"]*?)$', linha_stripped)
                    if match2:
                        texto_reconstruido.append(match2.group(1) + '[TRUNCADO]"')
                    else:
                        # Ignora linha problemática
                        pass

        texto = '\n'.join(texto_reconstruido)

        # 2. Conta estruturas abertas e fechadas
        abre_chaves = texto.count('{')
        fecha_chaves = texto.count('}')
        abre_colchetes = texto.count('[')
        fecha_colchetes = texto.count(']')

        # Remove possíveis caracteres incompletos no final (vírgulas, dois-pontos soltos)
        texto = re.sub(r'[,:\s]+$', '', texto)

        # 3. Adiciona fechamentos faltantes na ordem correta
        # Reconstrói a pilha de aberturas para fechar na ordem certa
        pilha = []
        i = 0
        while i < len(texto):
            char = texto[i]
            if char == '"':
                # Pula string inteira
                i += 1
                while i < len(texto):
                    if texto[i] == '\\' and i + 1 < len(texto):
                        i += 2
                        continue
                    if texto[i] == '"':
                        break
                    i += 1
            elif char == '{':
                pilha.append('}')
            elif char == '[':
                pilha.append(']')
            elif char in '}]':
                if pilha and pilha[-1] == char:
                    pilha.pop()
            i += 1

        # Fecha na ordem inversa
        texto += ''.join(reversed(pilha))

        # 4. Remove vírgulas antes de fechamentos (JSON inválido)
        texto = re.sub(r',\s*([}\]])', r'\1', texto)

        return texto

    def _parse_data(self, data_str: Optional[str]) -> Optional[date]:
        """Parseia string de data para date"""
        if not data_str:
            return None
        
        # Remove textos extras
        data_str = data_str.strip()
        
        # Tenta diferentes formatos
        formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
        for fmt in formatos:
            try:
                return datetime.strptime(data_str[:10], fmt).date()
            except ValueError:
                continue
        
        return None


class Agente3GeracaoPedido:
    """
    Agente 3: Geração do Pedido de Cálculo
    
    Responsável por:
    1. Consolidar dados dos agentes anteriores
    2. Calcular prazos processuais
    3. Gerar documento no formato padrão PGE-MS
    
    Usa prompt configurável do banco de dados.
    """
    
    # Prompt padrão (fallback)
    PROMPT_PADRAO = """Gere um PEDIDO DE CÁLCULOS para cumprimento de sentença com base nas informações fornecidas.

## DADOS DO PROCESSO
{dados_json}

## FORMATO DO DOCUMENTO
Gere o pedido no seguinte formato MARKDOWN:

# QUADRO PEDIDO DE CÁLCULOS – CUMPRIMENTO DE SENTENÇA

**Autor:** [nome do autor]
**CPF:** [CPF formatado]
**Réu:** Estado de Mato Grosso do Sul
**Autos nº:** [número do processo formatado]
**Comarca:** [comarca]
**Vara:** [vara]

---

## 1. OBJETO DA CONDENAÇÃO
[Descrever claramente o objeto da condenação]

### 1.1 VALOR SOLICITADO PELA PARTE
**R$ [valor]** (data-base: [data])

---

## 2. PRAZO PROCESSUAL
**Termo Inicial:** [primeiro dia útil posterior à data de recebimento da intimação, conforme art. 224 do CPC]
**Termo Final:** [30 dias úteis após o termo inicial]

NOTA: O termo inicial do prazo NÃO é a data de recebimento da intimação, mas sim o PRIMEIRO DIA ÚTIL POSTERIOR a ela (art. 224 do CPC). Exemplo: se o recebimento foi em 03/12/2025 (quarta-feira), o termo inicial é 04/12/2025 (quinta-feira).

---

## 3. DATA DE CITAÇÃO
[Data de recebimento efetivo pela PGE]

---

## 4. DATAS PROCESSUAIS
**Data de Ajuizamento:** [data] 
**Trânsito em Julgado:** [data]

---

## 5. ÍNDICE DE CORREÇÃO MONETÁRIA
[Índice conforme sentença/acórdão]
**Termo Inicial:** [especificar]
**Termo Final:** [especificar]

---

## 6. TAXA DE JUROS MORATÓRIOS
[Taxa conforme sentença/acórdão]
**Termo Inicial:** [especificar]
**Termo Final:** [especificar]

---

## 7. PERÍODO DA CONDENAÇÃO
[MM/AAAA até MM/AAAA]

---

## 8. CRITÉRIOS PARA CÁLCULO
[Lista de critérios]

---

## 9. RESPONSÁVEIS
**Procurador(a) responsável:** ___________________
**Data:** {data_atual}

---

Use APENAS as informações fornecidas. Use "[A VERIFICAR]" para dados faltantes."""

    def __init__(self, modelo: str = None, logger=None):
        # Usa resolver de parâmetros por agente
        db = SessionLocal()
        try:
            self._params = get_ia_params(db, "pedido_calculo", "geracao")
        finally:
            db.close()

        self.modelo = modelo or self._params.modelo
        self.temperatura = self._params.temperatura
        self.logger = logger  # Logger para debug

    def _get_prompt(self) -> str:
        """Busca prompt do banco ou usa padrão"""
        prompt_db = _get_prompt("geracao_pedido")
        return prompt_db if prompt_db else self.PROMPT_PADRAO

    async def gerar(
        self,
        dados_agente1: ResultadoAgente1,
        dados_agente2: ResultadoAgente2
    ) -> str:
        """
        Gera o pedido de cálculo em formato Markdown.

        Args:
            dados_agente1: Resultado do Agente 1 (dados do XML)
            dados_agente2: Resultado do Agente 2 (dados dos PDFs)

        Returns:
            Pedido de cálculo em formato Markdown
        """
        log_entry = None

        try:
            # Consolida dados para o prompt
            dados_consolidados = self._consolidar_dados(dados_agente1, dados_agente2)

            # Busca prompt do banco de dados
            prompt_template = self._get_prompt()
            # Usa replace() ao invés de .format() para evitar conflitos com
            # chaves {} no exemplo dentro do prompt
            prompt = prompt_template.replace(
                "{dados_json}", json.dumps(dados_consolidados, ensure_ascii=False, indent=2)
            ).replace(
                "{data_atual}", date.today().strftime("%d/%m/%Y")
            )

            # Prepara log se disponível
            if self.logger:
                from .ia_logger import LogEntry
                log_entry = LogEntry("geracao_pedido", "Gerando pedido de cálculo")
                log_entry.set_documento("dados_consolidados", json.dumps(dados_consolidados, ensure_ascii=False, indent=2))
                log_entry.set_prompt(prompt)
                log_entry.set_modelo(self.modelo)

            response = await gemini_service.generate(
                prompt=prompt,
                model=self.modelo,
                temperature=self.temperatura,
                thinking_level=_get_pedido_calculo_thinking_level()
            )

            if not response.success:
                if log_entry and self.logger:
                    log_entry.set_erro(response.error)
                    self.logger._logs.append(log_entry)
                return f"# ERRO NA GERAÇÃO\n\n{response.error}"

            # Salva log
            if log_entry and self.logger:
                log_entry.set_resposta(response.content, None)
                self.logger._logs.append(log_entry)

            return response.content

        except Exception as e:
            if log_entry and self.logger:
                log_entry.set_erro(str(e))
                self.logger._logs.append(log_entry)
            return f"# ERRO NA GERAÇÃO\n\n{str(e)}"
    
    def _consolidar_dados(
        self,
        agente1: ResultadoAgente1,
        agente2: ResultadoAgente2
    ) -> Dict[str, Any]:
        """Consolida dados dos dois agentes para geração"""
        # Extrai dados das certidões para passar para a IA
        certidoes_info = []
        if agente1.documentos_para_download and agente1.documentos_para_download.certidoes_citacao_intimacao:
            for cert in agente1.documentos_para_download.certidoes_citacao_intimacao:
                certidoes_info.append({
                    "tipo": cert.tipo.value if cert.tipo else None,
                    "data_recebimento": cert.data_recebimento.strftime("%d/%m/%Y") if cert.data_recebimento else None,
                    "termo_inicial_prazo": cert.termo_inicial_prazo.strftime("%d/%m/%Y") if cert.termo_inicial_prazo else None,
                    "tipo_certidao": cert.tipo_certidao
                })

        # Extrai termo inicial do prazo da certidão de intimação (CRÍTICO!)
        termo_inicial = self._obter_termo_inicial_prazo(
            agente1.documentos_para_download,
            TipoIntimacao.INTIMACAO_IMPUGNACAO
        )

        # Extrai data de citação da certidão
        data_citacao_certidao = self._obter_data_recebimento_certidao(
            agente1.documentos_para_download,
            TipoIntimacao.CITACAO
        )

        return {
            "dados_basicos": agente1.dados_basicos.to_dict(),
            "movimentos": agente1.movimentos_relevantes.to_dict(),
            "extracao": agente2.to_dict(),
            "certidoes": certidoes_info,
            "prazo_processual": {
                "termo_inicial": termo_inicial.strftime("%d/%m/%Y") if termo_inicial else None,
                "data_citacao_certidao": data_citacao_certidao.strftime("%d/%m/%Y") if data_citacao_certidao else None
            }
        }

    def _obter_data_recebimento_certidao(
        self,
        documentos: DocumentosParaDownload,
        tipo: TipoIntimacao
    ) -> Optional[date]:
        if not documentos or not documentos.certidoes_citacao_intimacao:
            return None

        for certidao in documentos.certidoes_citacao_intimacao:
            if certidao.tipo == tipo:
                return certidao.data_recebimento or certidao.data_certidao
        return None

    def _obter_termo_inicial_prazo(
        self,
        documentos: DocumentosParaDownload,
        tipo: TipoIntimacao
    ) -> Optional[date]:
        """
        Obtém o termo inicial do prazo processual (primeiro dia útil posterior
        à data de recebimento, conforme art. 224 do CPC).
        """
        if not documentos or not documentos.certidoes_citacao_intimacao:
            return None

        for certidao in documentos.certidoes_citacao_intimacao:
            if certidao.tipo == tipo:
                # Prioriza o termo_inicial_prazo calculado
                if certidao.termo_inicial_prazo:
                    return certidao.termo_inicial_prazo
                # Fallback: se não tiver, usa a data de recebimento
                return certidao.data_recebimento or certidao.data_certidao
        return None

    def montar_pedido_calculo(
        self,
        dados_agente1: ResultadoAgente1,
        dados_agente2: ResultadoAgente2
    ) -> PedidoCalculo:
        """
        Monta objeto PedidoCalculo com dados consolidados.

        Usado para edição estruturada no frontend.
        """
        db = dados_agente1.dados_basicos
        ext = dados_agente2

        # Termo inicial do prazo = primeiro dia útil após recebimento (art. 224 CPC)
        prazo_termo_inicial = self._obter_termo_inicial_prazo(
            dados_agente1.documentos_para_download,
            TipoIntimacao.INTIMACAO_IMPUGNACAO
        )
        # Fallback para data extraída pelo Agente 2 se não encontrou no XML
        if not prazo_termo_inicial and ext.datas and ext.datas.intimacao_impugnacao_recebimento:
            prazo_termo_inicial = ext.datas.intimacao_impugnacao_recebimento

        data_citacao = ext.datas.citacao_recebimento if ext.datas else None
        if not data_citacao:
            data_citacao = self._obter_data_recebimento_certidao(
                dados_agente1.documentos_para_download,
                TipoIntimacao.CITACAO
            )
        
        return PedidoCalculo(
            autor=db.autor,
            cpf_autor=db.cpf_autor,
            reu=db.reu,
            numero_processo=db.numero_processo,
            comarca=db.comarca,
            vara=db.vara,
            objeto_condenacao=ext.objeto_condenacao,
            valor_solicitado_parte=ext.valor_solicitado_parte,
            prazo_termo_inicial=prazo_termo_inicial,
            data_citacao=data_citacao,
            data_ajuizamento=db.data_ajuizamento,
            transito_julgado=ext.datas.transito_julgado if ext.datas else None,
            correcao_monetaria=ext.correcao_monetaria,
            juros_moratorios=ext.juros_moratorios,
            periodo_condenacao=ext.periodo_condenacao,
            criterios_calculo=ext.criterios_calculo
        )
