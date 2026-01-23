# tests/test_agravo_detector.py
"""
Testes automatizados para o detector de Agravo de Instrumento.

Cobertura:
- Detecção básica de Agravo de Instrumento com número CNJ
- Variações textuais de grafia e pontuação
- Menção a agravo sem número CNJ
- Número CNJ sem menção a agravo
- Confirmação correta por partes
- Rejeição por partes incompatíveis

Autor: LAB/PGE-MS
"""

import pytest
from datetime import date

from sistemas.relatorio_cumprimento.agravo_detector import (
    normalize_text,
    normalize_numero_cnj,
    format_numero_cnj,
    _texto_contem_agravo,
    _extrair_numeros_cnj,
    extract_agravo_candidates_from_xml,
    compare_parties,
    _calcular_similaridade_nome
)
from sistemas.relatorio_cumprimento.models import (
    AgravoCandidato,
    ParteProcesso
)


# ============================================
# Testes de Normalização
# ============================================

class TestNormalizacao:
    """Testes para funções de normalização"""

    def test_normalize_text_maiusculas(self):
        """Deve converter para maiúsculas"""
        assert normalize_text("teste") == "TESTE"
        assert normalize_text("TeSte MiSto") == "TESTE MISTO"

    def test_normalize_text_acentos(self):
        """Deve remover acentos"""
        assert normalize_text("José") == "JOSE"
        assert normalize_text("Ação") == "ACAO"
        assert normalize_text("Côrte") == "CORTE"
        assert normalize_text("São Paulo") == "SAO PAULO"

    def test_normalize_text_pontuacao(self):
        """Deve remover pontuação"""
        assert normalize_text("João, Silva.") == "JOAO SILVA"
        assert normalize_text("CPF: 123.456.789-00") == "CPF 123 456 789 00"

    def test_normalize_text_espacos(self):
        """Deve remover múltiplos espaços"""
        assert normalize_text("João    Silva") == "JOAO SILVA"
        assert normalize_text("  teste  ") == "TESTE"

    def test_normalize_text_vazio(self):
        """Deve tratar string vazia"""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_normalize_numero_cnj(self):
        """Deve extrair apenas dígitos do número CNJ"""
        assert normalize_numero_cnj("1400494-59.2026.8.12.0000") == "14004945920268120000"
        assert normalize_numero_cnj("1400494592026812XXXX") == "14004945920268120000"[:16]  # Extrai apenas números

    def test_format_numero_cnj(self):
        """Deve formatar número CNJ corretamente"""
        assert format_numero_cnj("14004945920268120000") == "1400494-59.2026.8.12.0000"
        # Número inválido retorna original
        assert format_numero_cnj("123") == "123"


# ============================================
# Testes de Detecção de Agravo
# ============================================

class TestDeteccaoAgravo:
    """Testes para detecção de referências a agravo"""

    def test_texto_contem_agravo_basico(self):
        """Deve detectar 'Agravo de Instrumento' básico"""
        assert _texto_contem_agravo("Agravo de Instrumento - 1400494-59.2026.8.12.0000")
        assert _texto_contem_agravo("agravo de instrumento interposto")

    def test_texto_contem_agravo_maiusculas(self):
        """Deve detectar independente de caixa"""
        assert _texto_contem_agravo("AGRAVO DE INSTRUMENTO")
        assert _texto_contem_agravo("Agravo De Instrumento")
        assert _texto_contem_agravo("aGrAvO dE iNsTrUmEnTo")

    def test_texto_contem_agravo_sem_acento(self):
        """Deve detectar mesmo sem acentos (já normalizado)"""
        # A função normaliza internamente
        assert _texto_contem_agravo("Agravo de Instrumento")

    def test_texto_contem_agravo_abreviado(self):
        """Deve detectar abreviações"""
        assert _texto_contem_agravo("Ag. Inst. nº 123")
        assert _texto_contem_agravo("AG. INST.")

    def test_texto_nao_contem_agravo(self):
        """Não deve detectar textos sem agravo"""
        assert not _texto_contem_agravo("Sentença proferida")
        assert not _texto_contem_agravo("Recurso de Apelação")
        assert not _texto_contem_agravo("")
        assert not _texto_contem_agravo(None)

    def test_extrair_numeros_cnj_basico(self):
        """Deve extrair número CNJ do texto"""
        texto = "Agravo de Instrumento - 1400494-59.2026.8.12.0000"
        numeros = _extrair_numeros_cnj(texto)
        assert len(numeros) == 1
        assert numeros[0] == "14004945920268120000"

    def test_extrair_numeros_cnj_multiplos(self):
        """Deve extrair múltiplos números CNJ"""
        texto = "Processos: 1400494-59.2026.8.12.0000 e 0815077-35.2021.8.12.0110"
        numeros = _extrair_numeros_cnj(texto)
        assert len(numeros) == 2

    def test_extrair_numeros_cnj_sem_formatacao(self):
        """Deve extrair número sem pontuação"""
        texto = "Agravo 14004945920268120000"
        numeros = _extrair_numeros_cnj(texto)
        assert len(numeros) == 1

    def test_extrair_numeros_cnj_vazio(self):
        """Deve retornar lista vazia se não houver números"""
        assert _extrair_numeros_cnj("Texto sem número") == []
        assert _extrair_numeros_cnj("") == []


# ============================================
# Testes de Extração de XML
# ============================================

class TestExtracaoXML:
    """Testes para extração de candidatos do XML"""

    def test_extract_agravo_candidates_basico(self):
        """Deve extrair agravo de movimento com complemento"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623" nivelSigilo="0">
                <complemento>Agravo de Instrumento - 1400494-59.2026.8.12.0000</complemento>
                <movimentoLocal codigoMovimento="50248" descricao="Informação do Sistema"/>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 1
        assert candidatos[0].numero_cnj == "14004945920268120000"
        assert candidatos[0].fonte == "movimento"

    def test_extract_agravo_candidates_multiplos(self):
        """Deve extrair múltiplos agravos"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Agravo de Instrumento - 1400494-59.2026.8.12.0000</complemento>
            </movimento>
            <movimento dataHora="20260120103000">
                <complemento>Agravo de Instrumento - 1500000-00.2026.8.12.0001</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 2

    def test_extract_agravo_candidates_sem_agravo(self):
        """Não deve extrair se não houver agravo"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Sentença proferida</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 0

    def test_extract_agravo_candidates_sem_numero(self):
        """Não deve extrair agravo sem número CNJ"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Agravo de Instrumento interposto pela parte</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 0

    def test_extract_agravo_candidates_numero_sem_agravo(self):
        """Não deve extrair número se não mencionar agravo"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Processo relacionado: 1400494-59.2026.8.12.0000</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 0


# ============================================
# Testes de Comparação de Partes
# ============================================

class TestComparacaoPartes:
    """Testes para validação por comparação de partes"""

    def test_similaridade_nome_identico(self):
        """Nomes idênticos devem ter score 1.0"""
        score = _calcular_similaridade_nome("JOAO SILVA", "JOAO SILVA")
        assert score == 1.0

    def test_similaridade_nome_parcial(self):
        """Nomes parcialmente iguais devem ter score intermediário"""
        score = _calcular_similaridade_nome("JOAO SILVA SANTOS", "JOAO SILVA")
        assert 0.5 < score < 1.0

    def test_similaridade_nome_diferente(self):
        """Nomes diferentes devem ter score baixo"""
        score = _calcular_similaridade_nome("JOAO SILVA", "MARIA SOUZA")
        assert score < 0.3

    def test_similaridade_nome_vazio(self):
        """Nomes vazios devem ter score 0"""
        assert _calcular_similaridade_nome("", "JOAO") == 0.0
        assert _calcular_similaridade_nome("JOAO", "") == 0.0

    def test_compare_parties_match_direto(self):
        """Deve validar quando partes coincidem no mesmo polo"""
        partes_origem_at = [ParteProcesso("João Silva", "JOAO SILVA", "AT", "12345678900")]
        partes_origem_pa = [ParteProcesso("Estado de MS", "ESTADO DE MS", "PA")]
        partes_agravo_at = [ParteProcesso("João Silva", "JOAO SILVA", "AT", "12345678900")]
        partes_agravo_pa = [ParteProcesso("Estado de MS", "ESTADO DE MS", "PA")]

        validado, score, motivo = compare_parties(
            partes_origem_at, partes_origem_pa,
            partes_agravo_at, partes_agravo_pa
        )

        assert validado is True
        assert score >= 0.5

    def test_compare_parties_match_invertido(self):
        """Deve validar quando partes coincidem com polos invertidos"""
        # Na origem: João é autor, Estado é réu
        partes_origem_at = [ParteProcesso("João Silva", "JOAO SILVA", "AT")]
        partes_origem_pa = [ParteProcesso("Estado de MS", "ESTADO DE MS", "PA")]
        # No agravo: Estado é agravante (AT), João é agravado (PA)
        partes_agravo_at = [ParteProcesso("Estado de MS", "ESTADO DE MS", "AT")]
        partes_agravo_pa = [ParteProcesso("João Silva", "JOAO SILVA", "PA")]

        validado, score, motivo = compare_parties(
            partes_origem_at, partes_origem_pa,
            partes_agravo_at, partes_agravo_pa
        )

        assert validado is True
        assert "invertido" in motivo.lower()

    def test_compare_parties_match_por_documento(self):
        """Deve validar por CPF/CNPJ quando disponível"""
        partes_origem_at = [ParteProcesso("João S.", "JOAO S", "AT", "12345678900")]
        partes_origem_pa = [ParteProcesso("Estado", "ESTADO", "PA")]
        partes_agravo_at = [ParteProcesso("João Silva", "JOAO SILVA", "AT", "12345678900")]
        partes_agravo_pa = [ParteProcesso("Estado de MS", "ESTADO DE MS", "PA")]

        validado, score, motivo = compare_parties(
            partes_origem_at, partes_origem_pa,
            partes_agravo_at, partes_agravo_pa
        )

        assert validado is True
        assert score >= 0.5

    def test_compare_parties_rejeicao_partes_diferentes(self):
        """Deve rejeitar quando partes não coincidem"""
        partes_origem_at = [ParteProcesso("João Silva", "JOAO SILVA", "AT")]
        partes_origem_pa = [ParteProcesso("Estado de MS", "ESTADO DE MS", "PA")]
        partes_agravo_at = [ParteProcesso("Maria Souza", "MARIA SOUZA", "AT")]
        partes_agravo_pa = [ParteProcesso("Município X", "MUNICIPIO X", "PA")]

        validado, score, motivo = compare_parties(
            partes_origem_at, partes_origem_pa,
            partes_agravo_at, partes_agravo_pa
        )

        assert validado is False
        assert score < 0.5

    def test_compare_parties_sem_partes_origem(self):
        """Deve rejeitar se origem não tem partes"""
        validado, score, motivo = compare_parties(
            [], [],
            [ParteProcesso("João", "JOAO", "AT")],
            [ParteProcesso("Estado", "ESTADO", "PA")]
        )

        assert validado is False
        assert "sem partes" in motivo.lower()

    def test_compare_parties_sem_partes_agravo(self):
        """Deve rejeitar se agravo não tem partes"""
        validado, score, motivo = compare_parties(
            [ParteProcesso("João", "JOAO", "AT")],
            [ParteProcesso("Estado", "ESTADO", "PA")],
            [], []
        )

        assert validado is False
        assert "sem partes" in motivo.lower()


# ============================================
# Testes de Integração (sem I/O real)
# ============================================

class TestIntegracao:
    """Testes de integração do pipeline completo (mock)"""

    def test_pipeline_completo_sem_agravo(self):
        """Pipeline deve funcionar normalmente sem agravo"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <dadosBasicos numero="08150773520218120110">
                <polo polo="AT">
                    <parte>
                        <pessoa nome="João Silva"/>
                    </parte>
                </polo>
            </dadosBasicos>
            <movimento dataHora="20260119183623">
                <complemento>Sentença proferida</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 0

    def test_pipeline_agravo_detectado(self):
        """Pipeline deve detectar agravo corretamente"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <dadosBasicos numero="08150773520218120110">
                <polo polo="AT">
                    <parte>
                        <pessoa nome="João Silva"/>
                    </parte>
                </polo>
            </dadosBasicos>
            <movimento dataHora="20260119183623">
                <complemento>Agravo de Instrumento - 1400494-59.2026.8.12.0000</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 1
        assert candidatos[0].numero_cnj == "14004945920268120000"


# ============================================
# Testes de Casos Especiais
# ============================================

class TestCasosEspeciais:
    """Testes para casos especiais e edge cases"""

    def test_agravo_com_quebra_de_linha(self):
        """Deve detectar agravo mesmo com quebra de linha"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Agravo de
                Instrumento - 1400494-59.2026.8.12.0000</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 1

    def test_agravo_com_pontuacao_variada(self):
        """Deve detectar agravo com diferentes pontuações"""
        textos = [
            "Agravo de Instrumento: 1400494-59.2026.8.12.0000",
            "Agravo de Instrumento nº 1400494-59.2026.8.12.0000",
            "Agravo de Instrumento n. 1400494-59.2026.8.12.0000",
            "Agravo de Instrumento -- 1400494-59.2026.8.12.0000",
        ]
        for texto in textos:
            assert _texto_contem_agravo(texto), f"Falhou para: {texto}"

    def test_numero_cnj_duplicado(self):
        """Não deve duplicar números CNJ iguais"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <processo>
            <movimento dataHora="20260119183623">
                <complemento>Agravo de Instrumento - 1400494-59.2026.8.12.0000 (ref: 1400494-59.2026.8.12.0000)</complemento>
            </movimento>
        </processo>
        """
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 1

    def test_xml_malformado(self):
        """Deve tratar XML malformado graciosamente"""
        xml = "isso não é xml válido"
        candidatos = extract_agravo_candidates_from_xml(xml)
        assert len(candidatos) == 0  # Não deve quebrar


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
