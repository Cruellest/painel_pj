# sistemas/gerador_pecas/detector_modulos.py
"""
Serviço de detecção inteligente de módulos de CONTEÚDO usando IA.
Utiliza Gemini Flash Lite para análise rápida e eficiente.
"""

import os
import json
import httpx
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from admin.models_prompts import PromptModulo
from sistemas.gerador_pecas.gemini_client import chamar_gemini_async, normalizar_modelo


class DetectorModulosIA:
    """
    Detector inteligente que usa IA para analisar documentos e determinar:
    1. Qual TIPO DE PEÇA é mais adequado (contestação, recurso, etc)
    2. Quais módulos de CONTEÚDO são relevantes para o caso

    Utiliza API direta do Gemini para análise rápida e de baixo custo.
    """

    def __init__(
        self,
        db: Session,
        modelo: str = "gemini-3-flash-preview",
        cache_ttl_minutes: int = 60
    ):
        """
        Args:
            db: Sessão do banco de dados
            modelo: Modelo a ser usado (padrão: gemini-3-flash-preview)
            cache_ttl_minutes: Tempo de vida do cache em minutos
        """
        self.db = db
        self.modelo = normalizar_modelo(modelo)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

        # Cache em memória {hash_documentos: (modulos_ids, timestamp)}
        self._cache = {}
        # Cache para detecção de tipo de peça
        self._cache_tipo_peca = {}

    async def detectar_modulos_relevantes(
        self,
        documentos_resumo: str,
        documentos_completos: Optional[str] = None,
        tipo_peca: Optional[str] = None
    ) -> List[int]:
        """
        Analisa os documentos e retorna IDs dos módulos de CONTEÚDO relevantes.

        Args:
            documentos_resumo: Resumo dos documentos do processo
            documentos_completos: Texto completo dos documentos (opcional)
            tipo_peca: Tipo de peça para filtrar módulos disponíveis (opcional)

        Returns:
            Lista de IDs dos módulos relevantes
        """
        # Verificar cache (inclui tipo_peca na chave)
        cache_key = self._gerar_cache_key(f"{tipo_peca or ''}:{documentos_resumo}")
        cached = self._verificar_cache(cache_key)
        if cached is not None:
            print(f"✅ Cache hit - módulos detectados anteriormente")
            return cached

        # Carregar módulos de CONTEÚDO disponíveis (filtrado por tipo de peça se especificado)
        modulos = self._carregar_modulos_disponiveis(tipo_peca)

        if not modulos:
            if tipo_peca:
                print(f"⚠️ Nenhum módulo de CONTEÚDO disponível para tipo de peça '{tipo_peca}'")
            else:
                print("⚠️ Nenhum módulo de CONTEÚDO disponível no banco")
            return []

        if tipo_peca:
            print(f"📋 {len(modulos)} módulos disponíveis para tipo '{tipo_peca}'")

        # Preparar prompt para a IA
        prompt_deteccao = self._montar_prompt_deteccao(
            documentos_resumo,
            documentos_completos,
            modulos
        )

        # Chamar a IA para análise
        try:
            resultado = await self._chamar_ia(prompt_deteccao)
            modulos_relevantes = self._processar_resposta_ia(resultado, modulos)

            # Salvar no cache
            self._salvar_cache(cache_key, modulos_relevantes)

            print(f"🎯 Detectados {len(modulos_relevantes)} módulos relevantes")
            return modulos_relevantes

        except Exception as e:
            print(f"❌ Erro na detecção por IA: {e}")
            # Fallback: usar detecção simples por palavras-chave
            return self._detectar_por_palavras_chave(documentos_resumo, modulos)

    def _carregar_modulos_disponiveis(self, tipo_peca: str = None) -> List[PromptModulo]:
        """
        Carrega módulos de CONTEÚDO ativos do banco.
        
        Se tipo_peca for especificado, filtra apenas módulos ativos para esse tipo.
        """
        from admin.models_prompts import ModuloTipoPeca
        
        # Busca todos os módulos de conteúdo ativos globalmente
        modulos = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True
        ).order_by(PromptModulo.ordem).all()
        
        # Se não há tipo de peça especificado, retorna todos
        if not tipo_peca:
            return modulos
        
        # Busca associações para este tipo de peça
        associacoes = self.db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca
        ).all()
        
        # Se não há associações configuradas, retorna todos (retrocompatibilidade)
        if not associacoes:
            return modulos
        
        # Cria mapa: modulo_id -> ativo
        mapa_ativo = {a.modulo_id: a.ativo for a in associacoes}
        
        # Filtra módulos
        modulos_filtrados = []
        for modulo in modulos:
            # Se não tem associação configurada, considera ativo (retrocompatibilidade)
            ativo_para_tipo = mapa_ativo.get(modulo.id, True)
            if ativo_para_tipo:
                modulos_filtrados.append(modulo)
        
        return modulos_filtrados

    def _montar_prompt_deteccao(
        self,
        documentos_resumo: str,
        documentos_completos: Optional[str],
        modulos: List[PromptModulo]
    ) -> str:
        """Monta o prompt para o agente de detecção"""

        # Preparar lista de módulos disponíveis - usando apenas a CONDIÇÃO DE ATIVAÇÃO
        modulos_info = []
        for idx, modulo in enumerate(modulos):
            # Usa condicao_ativacao para a detecção, não o conteúdo completo
            condicao = modulo.condicao_ativacao or ""
            if not condicao:
                # Fallback: se não tem condição definida, usa início do conteúdo
                condicao = modulo.conteudo[:200] + "..." if len(modulo.conteudo) > 200 else modulo.conteudo
            
            info = {
                "id": idx,  # Índice temporário para a IA
                "nome": modulo.nome,
                "titulo": modulo.titulo,
                "categoria": modulo.categoria or "",
                "subcategoria": modulo.subcategoria or "",
                "condicao_ativacao": condicao  # Apenas a condição, não o conteúdo
            }
            modulos_info.append(info)

        prompt = f"""Você é um assistente especializado em análise jurídica para a Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua tarefa é analisar os documentos de um processo judicial e identificar quais módulos de argumentos e teses jurídicas são RELEVANTES para o caso.

## DOCUMENTOS DO PROCESSO

### Resumo:
{documentos_resumo}
"""

        if documentos_completos:
            prompt += f"""
### Documentos Completos:
{documentos_completos[:5000]}  # Limita a 5000 caracteres
"""

        prompt += f"""

## MÓDULOS DISPONÍVEIS

A seguir, uma lista de módulos de argumentos/teses disponíveis. O campo "condicao_ativacao" descreve a SITUAÇÃO FÁTICA em que cada módulo deve ser acionado.

```json
{json.dumps(modulos_info, ensure_ascii=False, indent=2)}
```

## SUA TAREFA

Analise os documentos do processo e selecione APENAS os módulos cuja condição de ativação é **claramente atendida** pelos fatos do caso.

### Critérios de seleção:

1. **Correspondência direta**: A condição de ativação deve estar presente nos fatos do processo
2. **Evidência concreta**: Deve haver menção explícita ou forte indicação nos documentos
3. **Relevância prática**: O módulo deve realmente contribuir para a defesa do Estado neste caso específico

### O que NÃO fazer:

- NÃO inclua módulos por "precaução" ou "por via das dúvidas"
- NÃO inclua módulos apenas por semelhança temática genérica
- NÃO inclua módulos cuja condição não apareça claramente nos fatos

### Regra de ouro:

Se a condição de ativação não estiver **evidenciada nos documentos**, NÃO inclua o módulo. É melhor incluir poucos módulos relevantes do que muitos módulos genéricos.

## FORMATO DE RESPOSTA

Responda APENAS com um objeto JSON no seguinte formato:

```json
{{
  "modulos_relevantes": [
    {{"id": 0, "motivo": "Fato X do processo atende a condição Y"}},
    {{"id": 3, "motivo": "Documento Z menciona situação W"}}
  ],
  "confianca": "alta|media|baixa"
}}
```

Onde:
- `modulos_relevantes`: Array de objetos com ID (índice) e motivo curto (máx 15 palavras)
- `confianca`: Nível de confiança na detecção

Responda SOMENTE com o JSON, sem texto adicional.
"""

        return prompt

    async def _chamar_ia(self, prompt: str) -> Dict:
        """Chama a API do Gemini diretamente"""

        content = await chamar_gemini_async(
            prompt=prompt,
            modelo=self.modelo,
            max_tokens=50000,  # Aumentado para evitar truncamento
            temperature=0.1  # Baixa temperatura para resposta determinística
        )

        # Extrair JSON da resposta
        content = content.strip()
        
        # Remover markdown se houver
        if content.startswith('```'):
            lines = content.split('\n')
            # Remove primeira e última linha com ```
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            content = '\n'.join(lines).strip()
        
        # Tentar encontrar JSON dentro do texto
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao parsear JSON: {e}")
            print(f"⚠️ Conteúdo recebido: {content[:200]}...")

            # Tenta extrair módulos do novo formato: {"id": X, "motivo": "..."}
            modulos_obj_match = re.findall(r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"motivo"\s*:\s*"([^"]*)"', content)
            if modulos_obj_match:
                modulos = [{"id": int(m[0]), "motivo": m[1]} for m in modulos_obj_match]
                print(f"🔧 Recuperados {len(modulos)} módulos de JSON truncado (formato novo)")
                return {
                    "modulos_relevantes": modulos,
                    "confianca": "media"
                }

            # Fallback: tenta formato antigo [1, 2, 3, ...]
            modulos_match = re.search(r'"modulos_relevantes"\s*:\s*\[([\d,\s]+)', content)
            if modulos_match:
                try:
                    nums_str = modulos_match.group(1).rstrip(',').strip()
                    if nums_str:
                        modulos = [int(n.strip()) for n in nums_str.split(',') if n.strip().isdigit()]
                        print(f"🔧 Recuperados {len(modulos)} módulos de JSON truncado (formato antigo)")
                        return {
                            "modulos_relevantes": modulos,
                            "confianca": "media"
                        }
                except:
                    pass

            # Retorna estrutura vazia para fallback
            return {"modulos_relevantes": [], "confianca": "baixa"}

    def _processar_resposta_ia(
        self,
        resposta: Dict,
        modulos: List[PromptModulo]
    ) -> List[int]:
        """
        Processa a resposta da IA e retorna os IDs reais dos módulos.

        Args:
            resposta: Dicionário com a resposta da IA
            modulos: Lista de módulos disponíveis

        Returns:
            Lista de IDs reais dos módulos no banco de dados
        """
        modulos_info = resposta.get('modulos_relevantes', [])
        confianca = resposta.get('confianca', 'media')

        print(f"📊 Detecção IA - Confiança: {confianca}")

        # Converter índices temporários para IDs reais
        ids_reais = []

        for item in modulos_info:
            # Suporta tanto o formato novo (objeto com id e motivo) quanto o antigo (apenas índice)
            if isinstance(item, dict):
                idx = item.get('id', -1)
                motivo = item.get('motivo', '')
            else:
                idx = item
                motivo = ''

            if 0 <= idx < len(modulos):
                ids_reais.append(modulos[idx].id)
                if motivo:
                    print(f"   ✓ {modulos[idx].titulo}: {motivo}")
                else:
                    print(f"   ✓ {modulos[idx].titulo}")

        return ids_reais

    def _detectar_por_palavras_chave(
        self,
        texto: str,
        modulos: List[PromptModulo]
    ) -> List[int]:
        """
        Fallback: Detecção simples por palavras-chave.
        Usado quando a IA falha.
        """
        print("⚠️ Usando detecção fallback por palavras-chave")

        texto_lower = texto.lower()
        ids_relevantes = []

        for modulo in modulos:
            if modulo.palavras_chave:
                for palavra in modulo.palavras_chave:
                    if palavra.lower() in texto_lower:
                        ids_relevantes.append(modulo.id)
                        print(f"   ✓ {modulo.titulo} (palavra: {palavra})")
                        break

        return ids_relevantes

    def _gerar_cache_key(self, documentos: str) -> str:
        """Gera chave de cache baseada nos documentos"""
        import hashlib
        return hashlib.md5(documentos.encode()).hexdigest()

    def _verificar_cache(self, cache_key: str) -> Optional[List[int]]:
        """Verifica se há resultado em cache válido"""
        if cache_key in self._cache:
            modulos_ids, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                return modulos_ids
            else:
                # Cache expirado
                del self._cache[cache_key]
        return None

    def _salvar_cache(self, cache_key: str, modulos_ids: List[int]) -> None:
        """Salva resultado no cache"""
        self._cache[cache_key] = (modulos_ids, datetime.now())

    def limpar_cache(self) -> None:
        """Limpa todo o cache"""
        self._cache.clear()
        self._cache_tipo_peca.clear()
        print("🗑️ Cache de detecções limpo")
    
    async def detectar_tipo_peca(
        self,
        documentos_resumo: str
    ) -> Dict:
        """
        Analisa os documentos e determina automaticamente qual TIPO DE PEÇA
        é mais adequado para o caso.
        
        Args:
            documentos_resumo: Resumo consolidado dos documentos do processo
            
        Returns:
            Dict com tipo_peca detectado, justificativa e confiança
        """
        # Verificar cache
        cache_key = self._gerar_cache_key(f"tipo_peca:{documentos_resumo}")
        if cache_key in self._cache_tipo_peca:
            resultado, timestamp = self._cache_tipo_peca[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                print(f"✅ Cache hit - tipo de peça detectado anteriormente: {resultado.get('tipo_peca')}")
                return resultado
            else:
                del self._cache_tipo_peca[cache_key]
        
        # Buscar tipos de peça disponíveis no banco
        from admin.models_prompts import PromptModulo
        modulos_peca = self.db.query(PromptModulo).filter(
            PromptModulo.tipo == "peca",
            PromptModulo.ativo == True
        ).order_by(PromptModulo.ordem).all()
        
        if not modulos_peca:
            print("⚠️ Nenhum módulo de peça disponível no banco")
            return {
                "tipo_peca": None,
                "justificativa": "Nenhum tipo de peça configurado no sistema",
                "confianca": "baixa"
            }
        
        # Preparar lista de tipos disponíveis para a IA
        tipos_info = []
        for modulo in modulos_peca:
            # Usa condição de ativação ou início do conteúdo
            condicao = modulo.condicao_ativacao or ""
            if not condicao:
                condicao = modulo.conteudo[:300] + "..." if len(modulo.conteudo) > 300 else modulo.conteudo
            
            tipos_info.append({
                "categoria": modulo.categoria,  # ex: "contestacao", "recurso_apelacao"
                "titulo": modulo.titulo,        # ex: "Contestação", "Recurso de Apelação"
                "quando_usar": condicao
            })
        
        # Montar prompt de detecção
        prompt = f"""Você é um assistente jurídico especializado da Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS).

Sua tarefa é analisar os documentos de um processo judicial e determinar qual TIPO DE PEÇA JURÍDICA deve ser elaborada pela Procuradoria em defesa do Estado.

## DOCUMENTOS DO PROCESSO

{documentos_resumo}

## TIPOS DE PEÇA DISPONÍVEIS

```json
{json.dumps(tipos_info, ensure_ascii=False, indent=2)}
```

## SUA TAREFA

Analise os documentos e determine qual tipo de peça o Estado deve apresentar. Considere:

1. **Fase processual**: O processo está em fase de conhecimento (1º grau), recursal (2º grau)?
2. **Último ato processual**: Houve citação do Estado? Sentença? Recurso da parte contrária?
3. **Prazo**: Qual peça está dentro do prazo para apresentação?
4. **Posição do Estado**: O Estado é réu, apelante, apelado?

**REGRAS IMPORTANTES**:
- Se o Estado foi CITADO e ainda não contestou → CONTESTAÇÃO
- Se houve SENTENÇA DESFAVORÁVEL ao Estado → RECURSO DE APELAÇÃO  
- Se a parte adversa apresentou RECURSO → CONTRARRAZÕES
- Se é uma consulta interna ou análise → PARECER

## FORMATO DE RESPOSTA

Responda APENAS com um objeto JSON:

```json
{{
  "tipo_peca": "categoria_do_tipo",
  "justificativa": "Breve explicação de por que este tipo de peça é adequado",
  "confianca": "alta|media|baixa"
}}
```

O campo "tipo_peca" deve conter EXATAMENTE uma das categorias disponíveis: {', '.join([t['categoria'] for t in tipos_info])}

Responda SOMENTE com o JSON, sem texto adicional.
"""
        
        try:
            resultado = await self._chamar_ia(prompt)
            
            tipo_detectado = resultado.get('tipo_peca')
            justificativa = resultado.get('justificativa', '')
            confianca = resultado.get('confianca', 'media')
            
            # Valida se o tipo retornado existe
            tipos_validos = [t['categoria'] for t in tipos_info]
            if tipo_detectado not in tipos_validos:
                print(f"⚠️ Tipo detectado '{tipo_detectado}' não é válido. Tipos válidos: {tipos_validos}")
                # Tenta encontrar correspondência parcial
                for tipo in tipos_validos:
                    if tipo in str(tipo_detectado).lower() or str(tipo_detectado).lower() in tipo:
                        tipo_detectado = tipo
                        break
                else:
                    tipo_detectado = tipos_validos[0] if tipos_validos else None
                    confianca = "baixa"
            
            resultado_final = {
                "tipo_peca": tipo_detectado,
                "justificativa": justificativa,
                "confianca": confianca
            }
            
            print(f"🎯 Tipo de peça detectado: {tipo_detectado}")
            print(f"📊 Confiança: {confianca}")
            print(f"💡 Justificativa: {justificativa}")
            
            # Salvar no cache
            self._cache_tipo_peca[cache_key] = (resultado_final, datetime.now())
            
            return resultado_final
            
        except Exception as e:
            print(f"❌ Erro na detecção de tipo de peça: {e}")
            # Fallback: retorna o primeiro tipo disponível
            return {
                "tipo_peca": tipos_info[0]['categoria'] if tipos_info else None,
                "justificativa": f"Erro na detecção automática: {str(e)}. Usando tipo padrão.",
                "confianca": "baixa"
            }
