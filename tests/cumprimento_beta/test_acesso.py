# tests/cumprimento_beta/test_acesso.py
"""
Testes de controle de acesso ao módulo Cumprimento de Sentença Beta.

Verifica:
- Admin sempre tem acesso
- Usuário com grupo padrão PS tem acesso
- Usuário sem grupo PS não tem acesso
- Acesso direto por URL sem permissão é bloqueado
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException

from sistemas.cumprimento_beta.dependencies import (
    verificar_acesso_beta,
    require_beta_access
)
from sistemas.cumprimento_beta.constants import GRUPO_ACESSO_BETA


class MockPromptGroup:
    """Mock de PromptGroup para testes"""
    def __init__(self, slug: str, name: str = None):
        self.slug = slug
        self.name = name or slug


class MockUser:
    """Mock de User para testes"""
    def __init__(self, role: str = "user", default_group: MockPromptGroup = None):
        self.role = role
        self.default_group = default_group


class TestVerificarAcessoBeta:
    """Testes para função verificar_acesso_beta"""

    def test_admin_sempre_tem_acesso(self):
        """Admin deve sempre ter acesso ao beta"""
        user = MockUser(role="admin")
        db = Mock()

        resultado = verificar_acesso_beta(user, db)

        assert resultado is True

    def test_usuario_grupo_ps_tem_acesso(self):
        """Usuário com grupo padrão PS deve ter acesso"""
        grupo_ps = MockPromptGroup(slug="PS", name="Procuradoria Setorial")
        user = MockUser(role="user", default_group=grupo_ps)
        db = Mock()

        resultado = verificar_acesso_beta(user, db)

        assert resultado is True

    def test_usuario_sem_grupo_ps_nao_tem_acesso(self):
        """Usuário sem grupo PS não deve ter acesso"""
        grupo_outro = MockPromptGroup(slug="PF", name="Procuradoria Fiscal")
        user = MockUser(role="user", default_group=grupo_outro)
        db = Mock()

        resultado = verificar_acesso_beta(user, db)

        assert resultado is False

    def test_usuario_sem_grupo_padrao_nao_tem_acesso(self):
        """Usuário sem grupo padrão não deve ter acesso"""
        user = MockUser(role="user", default_group=None)
        db = Mock()

        resultado = verificar_acesso_beta(user, db)

        assert resultado is False

    def test_grupo_ps_case_insensitive_pelo_nome(self):
        """Acesso deve funcionar independente de case no nome do grupo"""
        grupo_ps = MockPromptGroup(slug="ps_lower", name="PS")
        user = MockUser(role="user", default_group=grupo_ps)
        db = Mock()

        resultado = verificar_acesso_beta(user, db)

        assert resultado is True


class TestRequireBetaAccess:
    """Testes para dependency require_beta_access"""

    @pytest.mark.asyncio
    async def test_retorna_usuario_se_tem_acesso(self):
        """Deve retornar o usuário se tiver acesso"""
        grupo_ps = MockPromptGroup(slug="PS")
        user = MockUser(role="admin", default_group=grupo_ps)
        db = Mock()

        # Testa diretamente a função (sem Depends)
        resultado = await require_beta_access(current_user=user, db=db)
        assert resultado == user

    @pytest.mark.asyncio
    async def test_levanta_403_se_nao_tem_acesso(self):
        """Deve levantar HTTPException 403 se não tiver acesso"""
        user = MockUser(role="user", default_group=None)
        db = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await require_beta_access(current_user=user, db=db)

        assert exc_info.value.status_code == 403
        assert "Acesso negado" in exc_info.value.detail


class TestConstantes:
    """Testes para constantes do módulo"""

    def test_grupo_acesso_padrao_eh_ps(self):
        """O grupo de acesso padrão deve ser PS"""
        assert GRUPO_ACESSO_BETA == "PS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
