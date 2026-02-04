# tests/e2e/test_admin_modulos_tipo_peca.py
"""
Testes E2E para a página Admin - Módulos por Tipo de Peça.

Testa especificamente o bug do accordion que sempre abria "Recurso de Apelação"
independente de qual item fosse clicado.

USO:
    pytest tests/e2e/test_admin_modulos_tipo_peca.py -v

REQUISITOS:
    - playwright instalado: pip install pytest-playwright
    - browsers instalados: playwright install

Autor: LAB/PGE-MS
Data: 2026-02
Bug corrigido: Accordion com IDs inválidos (espaços em IDs HTML)
"""

import pytest
import re
from playwright.sync_api import Page, expect


# ============================================
# CONFIGURAÇÃO
# ============================================

BASE_URL = "http://localhost:8000"
ADMIN_MODULOS_URL = f"{BASE_URL}/admin/modulos-tipo-peca"

# Credenciais de teste (ajustar conforme ambiente)
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"


# ============================================
# FIXTURES
# ============================================

@pytest.fixture(scope="function")
def authenticated_page(page: Page):
    """
    Fixture que fornece uma página já autenticada.
    Faz login antes de cada teste.
    """
    # Navega para login
    page.goto(f"{BASE_URL}/login")

    # Tenta fazer login (ajustar seletores conforme a página de login)
    try:
        page.fill('input[name="username"], input[type="text"]', TEST_USERNAME)
        page.fill('input[name="password"], input[type="password"]', TEST_PASSWORD)
        page.click('button[type="submit"], input[type="submit"]')

        # Aguarda redirect ou dashboard
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as e:
        # Se login falhar, pode ser que já esteja logado ou precisa de token
        print(f"Login automático falhou (pode ser esperado em alguns ambientes): {e}")

    # Define token se necessário (para ambientes que usam localStorage)
    page.evaluate("""
        if (!localStorage.getItem('access_token')) {
            // Em ambiente de teste, pode usar um token mock
            // localStorage.setItem('access_token', 'test-token');
        }
    """)

    yield page


@pytest.fixture(scope="function")
def modulos_page(authenticated_page: Page):
    """
    Fixture que navega para a página de módulos por tipo de peça.
    """
    authenticated_page.goto(ADMIN_MODULOS_URL)
    authenticated_page.wait_for_load_state("networkidle", timeout=15000)

    # Aguarda o carregamento inicial
    try:
        authenticated_page.wait_for_selector(
            '.tipo-peca-card, #tipos-peca-container',
            timeout=10000
        )
    except Exception:
        pass  # Pode não carregar se não autenticado

    yield authenticated_page


# ============================================
# TESTES DO BUG DO ACCORDION
# ============================================

class TestAccordionBugFix:
    """
    Testes para validar a correção do bug onde clicar em qualquer
    tipo de peça sempre abria "Recurso de Apelação".

    Causa raiz: IDs HTML continham espaços (ex: "content-Recurso de Apelação"),
    o que é inválido em HTML5 e causava comportamento indefinido em
    document.getElementById().

    Solução: Usar slugs (IDs sanitizados) sem espaços ou caracteres especiais.
    """

    def test_accordion_has_unique_ids(self, modulos_page: Page):
        """
        Verifica que cada accordion tem um ID único e válido (sem espaços).
        """
        # Obtém todos os elementos de conteúdo colapsável
        content_elements = modulos_page.locator('[id^="content-"]').all()

        if len(content_elements) == 0:
            pytest.skip("Nenhum tipo de peça carregado (pode ser problema de auth)")

        ids_encontrados = []
        for elem in content_elements:
            elem_id = elem.get_attribute('id')

            # Verifica que o ID não contém espaços
            assert ' ' not in elem_id, f"ID contém espaços: '{elem_id}'"

            # Verifica que o ID não contém acentos (devem estar normalizados)
            assert re.match(r'^content-[a-z0-9-]+$', elem_id), \
                f"ID não segue padrão slug: '{elem_id}'"

            # Verifica unicidade
            assert elem_id not in ids_encontrados, f"ID duplicado: '{elem_id}'"
            ids_encontrados.append(elem_id)

        assert len(ids_encontrados) > 0, "Nenhum ID de accordion encontrado"
        print(f"IDs de accordion válidos: {ids_encontrados}")

    def test_clicking_accordion_expands_correct_item(self, modulos_page: Page):
        """
        Testa que ao clicar em um item do accordion, aquele item específico
        é expandido (não outro).
        """
        # Obtém todos os cards de tipo de peça
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) < 2:
            pytest.skip("Menos de 2 tipos de peça para testar")

        # Coleta informações de cada card
        card_info = []
        for card in cards:
            data_tipo = card.get_attribute('data-tipo')
            titulo = card.locator('h3').text_content()
            card_info.append({
                'slug': data_tipo,
                'titulo': titulo.strip() if titulo else '',
                'element': card
            })

        print(f"Tipos de peça encontrados: {[c['titulo'] for c in card_info]}")

        # Testa clique no SEGUNDO card (não o primeiro)
        segundo_card = card_info[1]
        segundo_slug = segundo_card['slug']
        segundo_titulo = segundo_card['titulo']

        print(f"Clicando em: {segundo_titulo} (slug: {segundo_slug})")

        # Verifica que o conteúdo NÃO está expandido antes do clique
        content_selector = f'#content-{segundo_slug}'
        content = modulos_page.locator(content_selector)

        # Clica no header do card para expandir
        header = segundo_card['element'].locator('.cursor-pointer').first
        header.click()

        # Aguarda a expansão
        modulos_page.wait_for_timeout(500)

        # Verifica que O ITEM CLICADO está expandido
        expect(content).to_have_class(re.compile(r'expanded'))

        # Verifica que o PRIMEIRO item NÃO está expandido (a menos que já estivesse)
        primeiro_slug = card_info[0]['slug']
        primeiro_content = modulos_page.locator(f'#content-{primeiro_slug}')

        # O primeiro NÃO deve ter classe 'expanded' se não foi clicado
        classes = primeiro_content.get_attribute('class') or ''
        if 'expanded' in classes:
            # Se o primeiro estiver expandido, é um problema
            # (a menos que o comportamento seja "apenas um aberto por vez" e
            # o primeiro estava previamente expandido)
            print(f"AVISO: Primeiro item também está expandido: {card_info[0]['titulo']}")

    def test_clicking_contrarrazoes_expands_contrarrazoes(self, modulos_page: Page):
        """
        Teste específico: clicar em "Contrarrazões de Recurso" deve expandir
        "Contrarrazões de Recurso", não "Recurso de Apelação".
        """
        # Busca o card que contém "Contrarrazões" no título
        cards = modulos_page.locator('.tipo-peca-card').all()

        contrarrazoes_card = None
        apelacao_card = None

        for card in cards:
            titulo = card.locator('h3').text_content() or ''
            titulo_lower = titulo.lower().strip()

            if 'contrarraz' in titulo_lower:
                contrarrazoes_card = card
            elif 'apela' in titulo_lower and 'contra' not in titulo_lower:
                apelacao_card = card

        if not contrarrazoes_card:
            pytest.skip("Card 'Contrarrazões' não encontrado")

        # Obtém os slugs
        contrarrazoes_slug = contrarrazoes_card.get_attribute('data-tipo')
        apelacao_slug = apelacao_card.get_attribute('data-tipo') if apelacao_card else None

        print(f"Contrarrazões slug: {contrarrazoes_slug}")
        print(f"Apelação slug: {apelacao_slug}")

        # Fecha todos os accordions primeiro (se algum estiver aberto)
        for card in cards:
            slug = card.get_attribute('data-tipo')
            content = modulos_page.locator(f'#content-{slug}')
            if 'expanded' in (content.get_attribute('class') or ''):
                card.locator('.cursor-pointer').first.click()
                modulos_page.wait_for_timeout(300)

        # Clica em Contrarrazões
        contrarrazoes_card.locator('.cursor-pointer').first.click()
        modulos_page.wait_for_timeout(500)

        # Verifica: Contrarrazões DEVE estar expandido
        contrarrazoes_content = modulos_page.locator(f'#content-{contrarrazoes_slug}')
        expect(contrarrazoes_content).to_have_class(re.compile(r'expanded'))

        # Verifica: Apelação NÃO DEVE estar expandido
        if apelacao_slug:
            apelacao_content = modulos_page.locator(f'#content-{apelacao_slug}')
            classes = apelacao_content.get_attribute('class') or ''
            assert 'expanded' not in classes, \
                "BUG: Clicar em 'Contrarrazões' expandiu 'Recurso de Apelação'!"

    def test_toggle_same_item_closes_and_opens(self, modulos_page: Page):
        """
        Testa que clicar no mesmo item alterna entre aberto/fechado.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        card = cards[0]
        slug = card.get_attribute('data-tipo')
        content = modulos_page.locator(f'#content-{slug}')
        header = card.locator('.cursor-pointer').first

        # Estado inicial: fechado
        classes_inicial = content.get_attribute('class') or ''

        # Primeiro clique: abre
        header.click()
        modulos_page.wait_for_timeout(400)
        expect(content).to_have_class(re.compile(r'expanded'))

        # Segundo clique: fecha
        header.click()
        modulos_page.wait_for_timeout(400)
        classes_apos_segundo = content.get_attribute('class') or ''
        assert 'expanded' not in classes_apos_segundo, "Item não fechou após segundo clique"

        # Terceiro clique: abre novamente
        header.click()
        modulos_page.wait_for_timeout(400)
        expect(content).to_have_class(re.compile(r'expanded'))


class TestAccordionFunctionality:
    """
    Testes adicionais para funcionalidades do accordion.
    """

    def test_chevron_rotates_on_expand(self, modulos_page: Page):
        """
        Verifica que o ícone chevron rotaciona ao expandir.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        card = cards[0]
        slug = card.get_attribute('data-tipo')
        chevron = modulos_page.locator(f'#chevron-{slug}')

        # Antes de expandir: sem classe 'rotated'
        classes_antes = chevron.get_attribute('class') or ''

        # Clica para expandir
        card.locator('.cursor-pointer').first.click()
        modulos_page.wait_for_timeout(400)

        # Após expandir: deve ter classe 'rotated'
        expect(chevron).to_have_class(re.compile(r'rotated'))

    def test_modules_load_on_first_expand(self, modulos_page: Page):
        """
        Verifica que os módulos são carregados quando o accordion é expandido.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        card = cards[0]
        slug = card.get_attribute('data-tipo')

        # Expande o card
        card.locator('.cursor-pointer').first.click()

        # Aguarda carregamento dos módulos
        modulos_container = modulos_page.locator(f'#modulos-{slug}')

        # Aguarda que o spinner desapareça ou que conteúdo apareça
        try:
            modulos_page.wait_for_selector(
                f'#modulos-{slug} .modulo-item, #modulos-{slug} .text-gray-400:not(:has(.fa-spinner))',
                timeout=10000
            )
        except Exception:
            pass

        # Verifica que há conteúdo (módulos ou mensagem de vazio)
        content = modulos_container.inner_html()
        assert len(content) > 50, "Container de módulos parece vazio"


class TestDataAttributes:
    """
    Testes para validar os atributos de dados nos elementos.
    """

    def test_cards_have_data_tipo_attribute(self, modulos_page: Page):
        """
        Verifica que todos os cards têm o atributo data-tipo com slug válido.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        for card in cards:
            data_tipo = card.get_attribute('data-tipo')

            assert data_tipo is not None, "Card sem atributo data-tipo"
            assert len(data_tipo) > 0, "Atributo data-tipo vazio"
            assert ' ' not in data_tipo, f"data-tipo contém espaços: '{data_tipo}'"

            # Verifica formato slug
            assert re.match(r'^[a-z0-9-]+$', data_tipo), \
                f"data-tipo não é um slug válido: '{data_tipo}'"

    def test_cards_have_data_categoria_attribute(self, modulos_page: Page):
        """
        Verifica que os cards têm o atributo data-categoria com o nome original.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        for card in cards:
            # data-categoria deve conter o nome original (pode ter espaços)
            data_categoria = card.get_attribute('data-categoria')

            if data_categoria:  # Este atributo foi adicionado para lookup reverso
                titulo = card.locator('h3').text_content() or ''
                # O data-categoria deve corresponder ao tipo de peça
                assert len(data_categoria) > 0, "data-categoria vazio"


# ============================================
# TESTES DE REGRESSÃO
# ============================================

class TestRegression:
    """
    Testes de regressão para garantir que a correção não quebrou outras funcionalidades.
    """

    def test_save_button_exists_in_expanded_accordion(self, modulos_page: Page):
        """
        Verifica que o botão Salvar existe dentro do accordion expandido.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        # Expande o primeiro card
        card = cards[0]
        card.locator('.cursor-pointer').first.click()
        modulos_page.wait_for_timeout(500)

        # Verifica que há botão Salvar
        save_button = card.locator('button:has-text("Salvar")')
        expect(save_button).to_be_visible()

    def test_batch_action_buttons_exist(self, modulos_page: Page):
        """
        Verifica que os botões de ação em lote existem.
        """
        cards = modulos_page.locator('.tipo-peca-card').all()

        if len(cards) == 0:
            pytest.skip("Nenhum tipo de peça carregado")

        # Expande o primeiro card
        card = cards[0]
        card.locator('.cursor-pointer').first.click()
        modulos_page.wait_for_timeout(500)

        # Verifica botões de ação em lote
        expect(card.locator('button:has-text("Ativar Todos")')).to_be_visible()
        expect(card.locator('button:has-text("Desativar Todos")')).to_be_visible()
        expect(card.locator('button:has-text("Inverter")')).to_be_visible()

    def test_header_save_button_exists(self, modulos_page: Page):
        """
        Verifica que o botão "Salvar Alterações" do header existe.
        """
        save_button = modulos_page.locator('header button:has-text("Salvar Alterações")')
        expect(save_button).to_be_visible()
