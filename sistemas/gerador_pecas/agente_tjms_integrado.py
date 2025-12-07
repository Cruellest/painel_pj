# sistemas/gerador_pecas/agente_tjms_integrado.py
"""
Integração do Agente TJ-MS com o Gerador de Peças.

Este módulo adapta o agente_tjms para funcionar como o primeiro agente
do fluxo de geração de peças, baixando documentos e gerando resumo consolidado.
"""

import os
import sys
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Importa o agente TJ-MS do mesmo diretório
from sistemas.gerador_pecas.agente_tjms import AgenteTJMS, ResultadoAnalise, MODELO_PADRAO


@dataclass
class ResultadoAgente1:
    """Resultado do Agente 1 (Coletor TJ-MS)"""
    numero_processo: str
    numero_processo_origem: Optional[str] = None
    is_agravo: bool = False
    resumo_consolidado: str = ""
    total_documentos: int = 0
    documentos_analisados: int = 0
    erro: Optional[str] = None
    dados_brutos: Optional[ResultadoAnalise] = None


class AgenteTJMSIntegrado:
    """
    Agente 1 - Coletor de Documentos TJ-MS
    
    Responsável por:
    1. Consultar processo via API SOAP do TJ-MS
    2. Baixar documentos relevantes
    3. Gerar resumos individuais de cada documento
    4. Produzir resumo consolidado para os próximos agentes
    """
    
    def __init__(self, modelo: str = None):
        """
        Inicializa o agente.
        
        Args:
            modelo: Modelo LLM a usar (padrão: gemini-2.5-flash-lite)
        """
        self.modelo = modelo or MODELO_PADRAO
        self.agente = AgenteTJMS(modelo=self.modelo)
    
    async def coletar_e_resumir(
        self, 
        numero_processo: str,
        gerar_relatorio: bool = False  # Desativado por padrão - apenas consolida resumos
    ) -> ResultadoAgente1:
        """
        Coleta documentos do processo e gera resumo consolidado.
        
        Args:
            numero_processo: Número CNJ do processo (com ou sem formatação)
            gerar_relatorio: Se True, gera relatório final além dos resumos
            
        Returns:
            ResultadoAgente1 com resumo consolidado e metadados
        """
        resultado = ResultadoAgente1(numero_processo=numero_processo)
        
        try:
            print(f"\n🔍 AGENTE 1 - Iniciando coleta do processo {numero_processo}")
            print("=" * 60)
            
            # Executa análise completa via AgenteTJMS
            analise = await self.agente.analisar_processo(
                numero_processo=numero_processo,
                gerar_relatorio=gerar_relatorio
            )
            
            # Verifica erros
            if analise.erro_geral:
                resultado.erro = analise.erro_geral
                return resultado
            
            # Preenche metadados
            resultado.numero_processo_origem = analise.processo_origem
            resultado.is_agravo = analise.is_agravo
            resultado.total_documentos = len(analise.documentos)
            resultado.documentos_analisados = len(analise.documentos_com_resumo())
            resultado.dados_brutos = analise
            
            # Monta resumo consolidado
            resultado.resumo_consolidado = self._montar_resumo_consolidado(analise)
            
            print("=" * 60)
            print(f"✅ AGENTE 1 - Coleta concluída!")
            print(f"   📄 Documentos analisados: {resultado.documentos_analisados}")
            if resultado.is_agravo:
                print(f"   ⚖️  Agravo de Instrumento - Origem: {resultado.numero_processo_origem}")
            
            return resultado
            
        except Exception as e:
            resultado.erro = f"Erro no Agente 1: {str(e)}"
            print(f"❌ AGENTE 1 - Erro: {resultado.erro}")
            return resultado
    
    def _montar_resumo_consolidado(self, analise: ResultadoAnalise) -> str:
        """
        Monta o resumo consolidado a partir dos resumos individuais.
        
        Formato otimizado para o Agente 2 (detector de módulos) processar.
        """
        partes = []
        
        # Cabeçalho
        partes.append(f"# RESUMO CONSOLIDADO DO PROCESSO")
        partes.append(f"**Processo**: {analise.numero_processo}")
        partes.append(f"**Data da Análise**: {analise.data_analise.strftime('%d/%m/%Y %H:%M')}")
        
        if analise.is_agravo:
            partes.append(f"\n**⚠️ AGRAVO DE INSTRUMENTO**")
            partes.append(f"**Processo de Origem (1º Grau)**: {analise.processo_origem}")
        
        partes.append(f"\n**Total de Documentos Analisados**: {len(analise.documentos_com_resumo())}")
        partes.append("\n---\n")
        
        # Documentos do processo principal (ou do AI)
        docs_principal = analise.documentos_processo_principal()
        if docs_principal:
            if analise.is_agravo:
                partes.append("## DOCUMENTOS DO AGRAVO DE INSTRUMENTO\n")
            else:
                partes.append("## DOCUMENTOS DO PROCESSO\n")
            
            for i, doc in enumerate(docs_principal, 1):
                partes.append(f"### {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Documentos do processo de origem (se for agravo)
        docs_origem = analise.documentos_processo_origem()
        if docs_origem:
            partes.append(f"\n## DOCUMENTOS DO PROCESSO DE ORIGEM ({analise.processo_origem})\n")
            
            for i, doc in enumerate(docs_origem, 1):
                partes.append(f"### [ORIGEM] {i}. {doc.categoria_nome}")
                partes.append(f"**Data**: {doc.data_formatada}")
                partes.append(f"\n{doc.resumo}\n")
                partes.append("---\n")
        
        # Nota final
        partes.append("\n---")
        partes.append("*Este resumo consolidado foi gerado automaticamente a partir dos documentos do processo.*")
        
        return "\n".join(partes)


async def processar_processo_tjms(numero_processo: str) -> ResultadoAgente1:
    """
    Função de conveniência para processar um processo.
    
    Args:
        numero_processo: Número CNJ do processo
        
    Returns:
        ResultadoAgente1 com resumo consolidado
    """
    agente = AgenteTJMSIntegrado()
    return await agente.coletar_e_resumir(numero_processo)


# Teste standalone
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python agente_tjms_integrado.py <numero_processo>")
        sys.exit(1)
    
    numero = sys.argv[1]
    resultado = asyncio.run(processar_processo_tjms(numero))
    
    if resultado.erro:
        print(f"\n❌ Erro: {resultado.erro}")
    else:
        print(f"\n📋 Resumo consolidado ({len(resultado.resumo_consolidado)} caracteres):")
        print("-" * 40)
        print(resultado.resumo_consolidado[:2000] + "..." if len(resultado.resumo_consolidado) > 2000 else resultado.resumo_consolidado)
