# tests/test_modulos_tipo_peca.py
"""
Testes para a funcionalidade de módulos por tipo de peça.

Testa:
1. Contagem correta de módulos ativos/inativos no endpoint resumo-configuracao-tipos-peca
2. Filtragem por group_id na contagem
3. Persistência correta da configuração de módulos
4. Atualização das contagens após alterações

Bug fix: Contagens de ativos/inativos não refletiam estado real após alterações.
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.connection import SessionLocal
from admin.models_prompts import PromptModulo, ModuloTipoPeca
from admin.models_prompt_groups import PromptGroup
from auth.models import User  # Necessário para resolver relações do SQLAlchemy


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def db_transactional():
    """
    Fornece uma sessão transacional que faz rollback no final.
    """
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def mock_db():
    """Mock de sessão de banco para testes unitários."""
    return MagicMock()


@pytest.fixture
def grupo_teste(db_transactional):
    """Cria um grupo de teste."""
    import uuid
    unique_slug = f"teste_modulos_{uuid.uuid4().hex[:8]}"
    grupo = PromptGroup(
        name="Grupo Teste Modulos",
        slug=unique_slug,
        active=True
    )
    db_transactional.add(grupo)
    db_transactional.flush()
    return grupo


@pytest.fixture
def tipo_peca_teste(db_transactional, grupo_teste):
    """Cria um tipo de peça de teste."""
    tipo_peca = PromptModulo(
        nome="tipo_peca_teste",
        titulo="Tipo de Peça Teste",
        tipo="peca",
        categoria="tipo_peca_teste",
        conteudo="Prompt de teste",
        ativo=True,
        group_id=grupo_teste.id
    )
    db_transactional.add(tipo_peca)
    db_transactional.flush()
    return tipo_peca


@pytest.fixture
def modulos_conteudo_teste(db_transactional, grupo_teste):
    """Cria módulos de conteúdo de teste."""
    modulos = []
    for i in range(5):
        modulo = PromptModulo(
            nome=f"modulo_conteudo_teste_{i}",
            titulo=f"Módulo Conteúdo Teste {i}",
            tipo="conteudo",
            categoria=f"Categoria {i // 2}",
            conteudo=f"Prompt de conteúdo teste {i}",
            ativo=True,
            group_id=grupo_teste.id
        )
        db_transactional.add(modulo)
        modulos.append(modulo)
    db_transactional.flush()
    return modulos


# ============================================================================
# TESTES UNITÁRIOS - Cálculo de Contagens
# ============================================================================

class TestContagemCalculation:
    """Testes unitários para a lógica de cálculo de contagens."""

    def test_contagem_todos_ativos_por_padrao(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Quando não há configuração explícita (ModuloTipoPeca),
        todos os módulos devem ser considerados ativos por padrão.
        """
        # Sem criar nenhuma associação em ModuloTipoPeca
        # Consulta módulos de conteúdo
        total_modulos = db_transactional.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).count()

        # Consulta associações
        associacoes = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).all()

        ativos_configurados = sum(1 for a in associacoes if a.ativo)
        inativos_configurados = sum(1 for a in associacoes if not a.ativo)
        sem_config = total_modulos - ativos_configurados - inativos_configurados

        # Ativos totais = configurados como ativos + sem configuração (padrão ativo)
        ativos_total = ativos_configurados + sem_config

        assert total_modulos == 5
        assert ativos_configurados == 0
        assert inativos_configurados == 0
        assert sem_config == 5
        assert ativos_total == 5

    def test_contagem_com_modulos_desativados(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Quando alguns módulos são desativados, a contagem deve refletir corretamente.
        """
        # Desativa 2 módulos
        for i, modulo in enumerate(modulos_conteudo_teste[:2]):
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        # Consulta associações
        associacoes = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).all()

        inativos = sum(1 for a in associacoes if not a.ativo)
        ativos_configurados = sum(1 for a in associacoes if a.ativo)
        total_modulos = 5
        sem_config = total_modulos - len(associacoes)
        ativos_total = ativos_configurados + sem_config

        assert inativos == 2
        assert ativos_total == 3  # 5 - 2 desativados

    def test_contagem_todos_desativados(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Quando todos os módulos são desativados, contagem de ativos deve ser 0.
        """
        # Desativa todos os módulos
        for modulo in modulos_conteudo_teste:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        associacoes = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).all()

        inativos = sum(1 for a in associacoes if not a.ativo)
        ativos = sum(1 for a in associacoes if a.ativo)

        assert inativos == 5
        assert ativos == 0

    def test_contagem_mix_ativados_desativados(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Com uma mistura de módulos explicitamente ativos e inativos,
        a contagem deve ser precisa.
        """
        # Configura: 2 ativos explícitos, 2 inativos explícitos, 1 sem config
        for i, modulo in enumerate(modulos_conteudo_teste[:4]):
            ativo = i < 2  # Primeiros 2 ativos, próximos 2 inativos
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=ativo
            )
            db_transactional.add(assoc)
        # modulos_conteudo_teste[4] não tem associação (ativo por padrão)
        db_transactional.flush()

        associacoes = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).all()

        ativos_config = sum(1 for a in associacoes if a.ativo)
        inativos_config = sum(1 for a in associacoes if not a.ativo)
        sem_config = 5 - len(associacoes)
        ativos_total = ativos_config + sem_config

        assert ativos_config == 2
        assert inativos_config == 2
        assert sem_config == 1
        assert ativos_total == 3  # 2 explícitos + 1 sem config


# ============================================================================
# TESTES DE FILTRAGEM POR GROUP_ID
# ============================================================================

class TestFiltragemGroupId:
    """Testes para verificar que a filtragem por group_id funciona corretamente."""

    def test_contagem_filtrada_por_grupo(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Quando group_id é especificado, apenas módulos desse grupo devem ser contados.
        """
        # Cria outro grupo com mais módulos
        import uuid
        outro_grupo = PromptGroup(
            name="Outro Grupo Teste",
            slug=f"outro_grupo_{uuid.uuid4().hex[:8]}",
            active=True
        )
        db_transactional.add(outro_grupo)
        db_transactional.flush()

        # Adiciona módulos ao outro grupo
        for i in range(3):
            modulo = PromptModulo(
                nome=f"modulo_outro_grupo_{i}",
                titulo=f"Módulo Outro Grupo {i}",
                tipo="conteudo",
                categoria="Outra Categoria",
                conteudo="Prompt outro grupo",
                ativo=True,
                group_id=outro_grupo.id
            )
            db_transactional.add(modulo)
        db_transactional.flush()

        # Conta módulos filtrando pelo primeiro grupo
        modulos_grupo1 = db_transactional.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).count()

        modulos_grupo2 = db_transactional.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == outro_grupo.id
        ).count()

        assert modulos_grupo1 == 5
        assert modulos_grupo2 == 3

    def test_contagem_associacoes_filtra_por_grupo(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Ao contar associações (ativos/inativos), deve filtrar por grupo
        através de join com PromptModulo.
        """
        from sqlalchemy import func, case

        # Cria outro grupo
        import uuid
        outro_grupo = PromptGroup(
            name="Outro",
            slug=f"outro_{uuid.uuid4().hex[:8]}",
            active=True
        )
        db_transactional.add(outro_grupo)
        db_transactional.flush()

        # Cria módulo no outro grupo
        modulo_outro = PromptModulo(
            nome="modulo_outro_grupo",
            titulo="Módulo Outro Grupo",
            tipo="conteudo",
            categoria="Outra",
            conteudo="...",
            ativo=True,
            group_id=outro_grupo.id
        )
        db_transactional.add(modulo_outro)
        db_transactional.flush()

        # Cria associações - 2 inativos no grupo_teste, 1 inativo no outro_grupo
        for modulo in modulos_conteudo_teste[:2]:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)

        assoc_outro = ModuloTipoPeca(
            modulo_id=modulo_outro.id,
            tipo_peca=tipo_peca_teste.categoria,
            ativo=False
        )
        db_transactional.add(assoc_outro)
        db_transactional.flush()

        # Query com filtro de grupo (correta)
        contagens = db_transactional.query(
            ModuloTipoPeca.tipo_peca,
            func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
            func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
        ).join(
            PromptModulo,
            ModuloTipoPeca.modulo_id == PromptModulo.id
        ).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).group_by(ModuloTipoPeca.tipo_peca).all()

        resultado = {c.tipo_peca: {'ativos': int(c.ativos or 0), 'inativos': int(c.inativos or 0)} for c in contagens}

        # Deve ter apenas 2 inativos (do grupo_teste), não 3
        assert tipo_peca_teste.categoria in resultado
        assert resultado[tipo_peca_teste.categoria]['inativos'] == 2
        assert resultado[tipo_peca_teste.categoria]['ativos'] == 0


# ============================================================================
# TESTES DE INTEGRAÇÃO - Persistência e Atualização
# ============================================================================

class TestPersistenciaConfiguracao:
    """Testes de integração para a persistência de configurações."""

    def test_salvar_e_recuperar_configuracao(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Após salvar uma configuração, a recuperação deve retornar os valores corretos.
        """
        # Desativa 3 módulos
        modulos_desativar = modulos_conteudo_teste[:3]
        for modulo in modulos_desativar:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        # Recupera configuração
        associacoes = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).all()

        mapa_associacoes = {a.modulo_id: a.ativo for a in associacoes}

        # Verifica cada módulo
        for modulo in modulos_desativar:
            assert mapa_associacoes.get(modulo.id) == False

        # Módulos não configurados não estão no mapa
        for modulo in modulos_conteudo_teste[3:]:
            assert modulo.id not in mapa_associacoes

    def test_atualizar_configuracao_existente(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Atualizar uma configuração existente deve sobrescrever o valor anterior.
        """
        modulo = modulos_conteudo_teste[0]

        # Primeira configuração: inativo
        assoc = ModuloTipoPeca(
            modulo_id=modulo.id,
            tipo_peca=tipo_peca_teste.categoria,
            ativo=False
        )
        db_transactional.add(assoc)
        db_transactional.flush()

        # Verifica que está inativo
        assoc_check = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.modulo_id == modulo.id,
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).first()
        assert assoc_check.ativo == False

        # Atualiza para ativo
        assoc_check.ativo = True
        db_transactional.flush()

        # Verifica que agora está ativo
        assoc_check2 = db_transactional.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.modulo_id == modulo.id,
            ModuloTipoPeca.tipo_peca == tipo_peca_teste.categoria
        ).first()
        assert assoc_check2.ativo == True


# ============================================================================
# TESTES DE INTEGRAÇÃO COM API (usando mocks)
# ============================================================================

class TestAPIResumoConfiguracao:
    """Testes para o endpoint resumo-configuracao-tipos-peca."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock das dependências de autenticação e DB."""
        mock_user = MagicMock()
        mock_user.is_active = True
        return mock_user

    def test_resumo_retorna_contagens_corretas(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste, mock_dependencies):
        """
        O endpoint deve retornar contagens corretas de ativos/inativos.
        """
        from sqlalchemy import func, case

        # Setup: 2 módulos inativos
        for modulo in modulos_conteudo_teste[:2]:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        # Simula a lógica do endpoint
        total_modulos = db_transactional.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).count()

        query_contagens = db_transactional.query(
            ModuloTipoPeca.tipo_peca,
            func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
            func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
        ).join(
            PromptModulo,
            ModuloTipoPeca.modulo_id == PromptModulo.id
        ).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        )
        contagens = query_contagens.group_by(ModuloTipoPeca.tipo_peca).all()

        contagens_map = {c.tipo_peca: {'ativos': int(c.ativos or 0), 'inativos': int(c.inativos or 0)} for c in contagens}

        # Calcula resultado final
        contagem = contagens_map.get(tipo_peca_teste.categoria, {'ativos': 0, 'inativos': 0})
        ativos = contagem['ativos']
        inativos = contagem['inativos']
        sem_config = total_modulos - ativos - inativos
        ativos_total = ativos + sem_config

        assert total_modulos == 5
        assert inativos == 2
        assert ativos == 0  # Nenhum explicitamente ativo
        assert sem_config == 3  # 5 - 0 - 2
        assert ativos_total == 3  # 0 + 3


# ============================================================================
# TESTES DE REGRESSÃO - Bug específico
# ============================================================================

class TestBugContagensIncorretas:
    """
    Testes de regressão para o bug onde as contagens de ativos/inativos
    não refletiam o estado real após alterações.

    Bug original: A UI mostrava "59 ativos, 0 inativos" mesmo após
    desmarcar vários módulos.

    Causa raiz:
    1. Frontend: Não atualizava os contadores no header após salvar
    2. Backend: Query de contagem não filtrava por group_id
    """

    def test_contagem_apos_desativar_modulos(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Após desativar módulos, a contagem de inativos deve ser > 0.
        """
        # Estado inicial: todos ativos por padrão (sem configuração)
        total = len(modulos_conteudo_teste)

        # Simula desativação de módulos (como faria a UI)
        desativados = 3
        for modulo in modulos_conteudo_teste[:desativados]:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        # Recalcula contagens (como faria o backend)
        from sqlalchemy import func, case

        query_contagens = db_transactional.query(
            ModuloTipoPeca.tipo_peca,
            func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
            func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
        ).join(
            PromptModulo,
            ModuloTipoPeca.modulo_id == PromptModulo.id
        ).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).group_by(ModuloTipoPeca.tipo_peca).all()

        contagens_map = {c.tipo_peca: {'ativos': int(c.ativos or 0), 'inativos': int(c.inativos or 0)} for c in query_contagens}

        contagem = contagens_map.get(tipo_peca_teste.categoria, {'ativos': 0, 'inativos': 0})
        inativos = contagem['inativos']
        ativos_config = contagem['ativos']
        sem_config = total - ativos_config - inativos
        ativos_total = ativos_config + sem_config

        # VERIFICAÇÃO DO BUG: inativos deve ser igual ao número desativado
        assert inativos == desativados, f"Esperado {desativados} inativos, obteve {inativos}"
        assert ativos_total == total - desativados, f"Esperado {total - desativados} ativos, obteve {ativos_total}"

    def test_contagem_com_grupo_incorreto_nao_afeta(self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste):
        """
        Módulos de outros grupos não devem afetar a contagem quando group_id é filtrado.
        Este teste verifica o bug onde a query não filtrava por group_id.
        """
        from sqlalchemy import func, case

        # Cria outro grupo com módulos
        import uuid
        outro_grupo = PromptGroup(
            name="Outro Grupo",
            slug=f"outro_grupo_{uuid.uuid4().hex[:8]}",
            active=True
        )
        db_transactional.add(outro_grupo)
        db_transactional.flush()

        # Cria módulos no outro grupo e desativa todos
        modulos_outro = []
        for i in range(10):
            modulo = PromptModulo(
                nome=f"modulo_outro_{i}",
                titulo=f"Módulo Outro {i}",
                tipo="conteudo",
                categoria="Outro",
                conteudo="...",
                ativo=True,
                group_id=outro_grupo.id
            )
            db_transactional.add(modulo)
            modulos_outro.append(modulo)
        db_transactional.flush()

        # Desativa todos os módulos do outro grupo
        for modulo in modulos_outro:
            assoc = ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca_teste.categoria,
                ativo=False
            )
            db_transactional.add(assoc)
        db_transactional.flush()

        # Query COM filtro de grupo (correta - como deve estar após a correção)
        contagens_filtrado = db_transactional.query(
            ModuloTipoPeca.tipo_peca,
            func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
            func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
        ).join(
            PromptModulo,
            ModuloTipoPeca.modulo_id == PromptModulo.id
        ).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.ativo == True,
            PromptModulo.group_id == grupo_teste.id
        ).group_by(ModuloTipoPeca.tipo_peca).all()

        # Query SEM filtro de grupo (bugada - como estava antes da correção)
        contagens_sem_filtro = db_transactional.query(
            ModuloTipoPeca.tipo_peca,
            func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
            func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
        ).group_by(ModuloTipoPeca.tipo_peca).all()

        mapa_filtrado = {c.tipo_peca: int(c.inativos or 0) for c in contagens_filtrado}
        mapa_sem_filtro = {c.tipo_peca: int(c.inativos or 0) for c in contagens_sem_filtro}

        # Com filtro: 0 inativos (nenhum módulo do grupo_teste foi desativado)
        assert mapa_filtrado.get(tipo_peca_teste.categoria, 0) == 0

        # Sem filtro: 10 inativos (inclui módulos do outro grupo)
        assert mapa_sem_filtro.get(tipo_peca_teste.categoria, 0) == 10

        # Este é exatamente o bug que foi corrigido!
        assert mapa_filtrado != mapa_sem_filtro or len(contagens_sem_filtro) == 0


# ============================================================================
# TESTES DE GATE - Módulos inativos NÃO devem ser avaliados
# ============================================================================

class TestGateModulosInativos:
    """
    Testes para verificar que módulos inativos por tipo de peça funcionam
    como um GATE ABSOLUTO - não são avaliados nem ativados, independente
    de regras determinísticas ou modo LLM.

    Regra de Ouro:
    1. Selecionar módulos associados ao tipo de peça
    2. FILTRAR apenas módulos ATIVOS para aquele tipo de peça (GATE)
    3. Aplicar lógica de ativação (determinística e/ou LLM)
    4. Gerar lista final de módulos

    Se o filtro (2) não existir ou estiver depois do (3), é um bug.
    """

    def test_modulo_inativo_nao_aparece_na_lista_de_disponiveis(
        self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste
    ):
        """
        Módulo marcado como INATIVO para um tipo de peça não deve aparecer
        na lista de módulos disponíveis para detecção.
        """
        from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA

        # Marca módulo 0 como INATIVO para o tipo de peça
        modulo_desativado = modulos_conteudo_teste[0]
        assoc = ModuloTipoPeca(
            modulo_id=modulo_desativado.id,
            tipo_peca=tipo_peca_teste.categoria,
            ativo=False
        )
        db_transactional.add(assoc)
        db_transactional.flush()

        # Carrega módulos disponíveis usando o detector
        detector = DetectorModulosIA(db_transactional)
        modulos_disponiveis = detector._carregar_modulos_disponiveis(
            tipo_peca=tipo_peca_teste.categoria,
            group_id=grupo_teste.id
        )

        # Verifica que o módulo desativado NÃO está na lista
        ids_disponiveis = [m.id for m in modulos_disponiveis]
        assert modulo_desativado.id not in ids_disponiveis, \
            f"Módulo inativo {modulo_desativado.id} não deveria estar disponível"

        # Verifica que os outros módulos ESTÃO na lista
        for modulo in modulos_conteudo_teste[1:]:
            assert modulo.id in ids_disponiveis, \
                f"Módulo ativo {modulo.id} deveria estar disponível"

    def test_modulo_inativo_com_regra_deterministica_verdadeira_nao_ativa(
        self, db_transactional, grupo_teste, tipo_peca_teste
    ):
        """
        Mesmo que um módulo tenha uma regra determinística que seria TRUE,
        se ele estiver INATIVO para o tipo de peça, ele NÃO deve ser ativado.

        Este é o teste crítico: a regra seria satisfeita, mas o gate impede.
        """
        from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
        import uuid

        # Cria módulo com regra determinística que SEMPRE é TRUE
        modulo_com_regra = PromptModulo(
            nome=f"modulo_regra_sempre_true_{uuid.uuid4().hex[:8]}",
            titulo="Módulo Regra Sempre True",
            tipo="conteudo",
            categoria="Teste Gate",
            conteudo="Conteúdo do módulo",
            condicao_ativacao="Sempre ativar este módulo",
            ativo=True,
            group_id=grupo_teste.id,
            modo_ativacao="deterministic",
            # Regra que sempre é TRUE: valor_teste == True
            regra_deterministica={
                "type": "condition",
                "variable": "valor_teste",
                "operator": "equals",
                "value": True
            }
        )
        db_transactional.add(modulo_com_regra)
        db_transactional.flush()

        # Marca como INATIVO para o tipo de peça
        assoc = ModuloTipoPeca(
            modulo_id=modulo_com_regra.id,
            tipo_peca=tipo_peca_teste.categoria,
            ativo=False  # INATIVO!
        )
        db_transactional.add(assoc)
        db_transactional.flush()

        # Carrega módulos disponíveis
        detector = DetectorModulosIA(db_transactional)
        modulos_disponiveis = detector._carregar_modulos_disponiveis(
            tipo_peca=tipo_peca_teste.categoria,
            group_id=grupo_teste.id
        )

        # O módulo NÃO deve estar disponível (GATE absoluto)
        ids_disponiveis = [m.id for m in modulos_disponiveis]
        assert modulo_com_regra.id not in ids_disponiveis, \
            "Módulo INATIVO não deveria estar disponível, mesmo com regra TRUE"

    def test_modulo_ativo_com_regra_deterministica_verdadeira_ativa(
        self, db_transactional, grupo_teste, tipo_peca_teste
    ):
        """
        Módulo ATIVO com regra determinística TRUE deve ser ativado normalmente.
        Este é o caso de controle para garantir que o sistema funciona.
        """
        from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
        import uuid

        # Cria módulo com regra determinística que SEMPRE é TRUE
        modulo_com_regra = PromptModulo(
            nome=f"modulo_regra_ativo_{uuid.uuid4().hex[:8]}",
            titulo="Módulo Regra Ativo",
            tipo="conteudo",
            categoria="Teste Gate",
            conteudo="Conteúdo do módulo",
            condicao_ativacao="Sempre ativar este módulo",
            ativo=True,
            group_id=grupo_teste.id,
            modo_ativacao="deterministic",
            regra_deterministica={
                "type": "condition",
                "variable": "valor_teste",
                "operator": "equals",
                "value": True
            }
        )
        db_transactional.add(modulo_com_regra)
        db_transactional.flush()

        # Marca como ATIVO para o tipo de peça
        assoc = ModuloTipoPeca(
            modulo_id=modulo_com_regra.id,
            tipo_peca=tipo_peca_teste.categoria,
            ativo=True  # ATIVO!
        )
        db_transactional.add(assoc)
        db_transactional.flush()

        # Carrega módulos disponíveis
        detector = DetectorModulosIA(db_transactional)
        modulos_disponiveis = detector._carregar_modulos_disponiveis(
            tipo_peca=tipo_peca_teste.categoria,
            group_id=grupo_teste.id
        )

        # O módulo DEVE estar disponível
        ids_disponiveis = [m.id for m in modulos_disponiveis]
        assert modulo_com_regra.id in ids_disponiveis, \
            "Módulo ATIVO deveria estar disponível"

    def test_filtro_acontece_antes_da_separacao_deterministic_llm(
        self, db_transactional, grupo_teste, tipo_peca_teste
    ):
        """
        Verifica que a filtragem por ativo/inativo acontece ANTES da
        separação entre módulos determinísticos e LLM.

        Isso garante que módulos inativos nunca chegam à etapa de avaliação.
        """
        from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA
        import uuid

        # Cria 3 módulos:
        # 1. Determinístico + INATIVO
        # 2. LLM + INATIVO
        # 3. Determinístico + ATIVO (controle)

        modulo_det_inativo = PromptModulo(
            nome=f"det_inativo_{uuid.uuid4().hex[:8]}",
            titulo="Det Inativo",
            tipo="conteudo",
            categoria="Teste",
            conteudo="...",
            ativo=True,
            group_id=grupo_teste.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "x", "operator": "equals", "value": True}
        )

        modulo_llm_inativo = PromptModulo(
            nome=f"llm_inativo_{uuid.uuid4().hex[:8]}",
            titulo="LLM Inativo",
            tipo="conteudo",
            categoria="Teste",
            conteudo="...",
            ativo=True,
            group_id=grupo_teste.id,
            modo_ativacao="llm"  # Sem regra determinística
        )

        modulo_det_ativo = PromptModulo(
            nome=f"det_ativo_{uuid.uuid4().hex[:8]}",
            titulo="Det Ativo",
            tipo="conteudo",
            categoria="Teste",
            conteudo="...",
            ativo=True,
            group_id=grupo_teste.id,
            modo_ativacao="deterministic",
            regra_deterministica={"type": "condition", "variable": "y", "operator": "equals", "value": True}
        )

        db_transactional.add_all([modulo_det_inativo, modulo_llm_inativo, modulo_det_ativo])
        db_transactional.flush()

        # Marca os dois primeiros como INATIVOS
        assoc1 = ModuloTipoPeca(modulo_id=modulo_det_inativo.id, tipo_peca=tipo_peca_teste.categoria, ativo=False)
        assoc2 = ModuloTipoPeca(modulo_id=modulo_llm_inativo.id, tipo_peca=tipo_peca_teste.categoria, ativo=False)
        assoc3 = ModuloTipoPeca(modulo_id=modulo_det_ativo.id, tipo_peca=tipo_peca_teste.categoria, ativo=True)
        db_transactional.add_all([assoc1, assoc2, assoc3])
        db_transactional.flush()

        # Carrega módulos disponíveis
        detector = DetectorModulosIA(db_transactional)
        modulos_disponiveis = detector._carregar_modulos_disponiveis(
            tipo_peca=tipo_peca_teste.categoria,
            group_id=grupo_teste.id
        )

        ids_disponiveis = [m.id for m in modulos_disponiveis]

        # Apenas o módulo ATIVO deve estar disponível
        assert modulo_det_inativo.id not in ids_disponiveis, "Det inativo não deveria estar disponível"
        assert modulo_llm_inativo.id not in ids_disponiveis, "LLM inativo não deveria estar disponível"
        assert modulo_det_ativo.id in ids_disponiveis, "Det ativo deveria estar disponível"

    def test_sem_associacao_considera_ativo_por_padrao(
        self, db_transactional, grupo_teste, tipo_peca_teste, modulos_conteudo_teste
    ):
        """
        Módulos SEM associação em ModuloTipoPeca devem ser considerados
        ATIVOS por padrão (retrocompatibilidade).
        """
        from sistemas.gerador_pecas.detector_modulos import DetectorModulosIA

        # Não cria nenhuma associação - todos devem aparecer como ativos

        detector = DetectorModulosIA(db_transactional)
        modulos_disponiveis = detector._carregar_modulos_disponiveis(
            tipo_peca=tipo_peca_teste.categoria,
            group_id=grupo_teste.id
        )

        ids_disponiveis = [m.id for m in modulos_disponiveis]

        # Todos os módulos devem estar disponíveis
        for modulo in modulos_conteudo_teste:
            assert modulo.id in ids_disponiveis, \
                f"Módulo {modulo.id} sem associação deveria estar disponível (padrão ativo)"
