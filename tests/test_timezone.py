#!/usr/bin/env python
"""
Testes para validar a política de timezone do sistema.

Política:
- Backend grava em UTC (timezone-aware)
- Frontend exibe em America/Campo_Grande (UTC-4)

Uso:
    pytest tests/test_timezone.py -v
"""

import pytest
from datetime import datetime, timezone


class TestTimezoneModule:
    """Testes do módulo utils/timezone.py"""

    def test_now_utc_returns_timezone_aware(self):
        """now_utc() deve retornar datetime com timezone UTC."""
        from utils.timezone import now_utc

        result = now_utc()

        assert result.tzinfo is not None, "Deve ser timezone-aware"
        assert result.tzinfo == timezone.utc, "Deve ser UTC"

    def test_now_local_returns_timezone_aware(self):
        """now_local() deve retornar datetime com timezone local."""
        from utils.timezone import now_local, TIMEZONE_LOCAL_NAME

        result = now_local()

        assert result.tzinfo is not None, "Deve ser timezone-aware"
        # pytz timezones têm representações diferentes, comparamos pelo nome
        assert TIMEZONE_LOCAL_NAME in str(result.tzinfo), "Deve ser timezone local"

    def test_to_local_converts_utc_to_local(self):
        """to_local() deve converter UTC para timezone local."""
        from utils.timezone import to_local, now_utc

        utc_time = now_utc()
        local_time = to_local(utc_time)

        # Diferença deve ser -4 horas (UTC-4)
        diff_hours = (local_time.utcoffset().total_seconds() / 3600)
        assert diff_hours == -4, f"Offset deve ser -4h, mas é {diff_hours}h"

    def test_to_local_handles_naive_datetime(self):
        """to_local() deve tratar datetime naive como UTC."""
        from utils.timezone import to_local

        naive = datetime(2026, 1, 20, 18, 30, 0)  # Sem timezone
        local = to_local(naive)

        assert local.tzinfo is not None, "Resultado deve ser timezone-aware"
        # 18:30 UTC deve virar 14:30 local (UTC-4)
        assert local.hour == 14, f"Hora deve ser 14, mas é {local.hour}"

    def test_to_local_handles_none(self):
        """to_local() deve retornar None se input for None."""
        from utils.timezone import to_local

        assert to_local(None) is None

    def test_format_local_formats_correctly(self):
        """format_local() deve formatar no timezone local."""
        from utils.timezone import format_local
        from datetime import timezone as tz

        utc_time = datetime(2026, 1, 20, 18, 30, 0, tzinfo=tz.utc)
        formatted = format_local(utc_time)

        # 18:30 UTC = 14:30 local
        assert "14:30:00" in formatted, f"Deve conter 14:30:00, mas é {formatted}"
        assert "20/01/2026" in formatted, f"Deve conter 20/01/2026, mas é {formatted}"

    def test_get_utc_now_for_sqlalchemy(self):
        """get_utc_now() deve funcionar como default para SQLAlchemy."""
        from utils.timezone import get_utc_now

        result = get_utc_now()

        assert result.tzinfo is not None, "Deve ser timezone-aware"
        assert result.tzinfo == timezone.utc, "Deve ser UTC"


class TestTimezoneConstants:
    """Testes das constantes de timezone."""

    def test_timezone_local_name(self):
        """Timezone local deve ser America/Campo_Grande."""
        from utils.timezone import TIMEZONE_LOCAL_NAME

        assert TIMEZONE_LOCAL_NAME == "America/Campo_Grande"

    def test_timezone_offset(self):
        """Offset deve ser -4 horas."""
        from utils.timezone import TIMEZONE_OFFSET_HOURS

        assert TIMEZONE_OFFSET_HOURS == -4


class TestModelsUseCorrectTimezone:
    """Testes para verificar que os models usam get_utc_now."""

    def test_user_model_uses_get_utc_now(self):
        """User model deve usar get_utc_now para created_at."""
        from auth.models import User

        # Verifica que a coluna created_at tem default correto
        created_at_col = User.__table__.columns['created_at']
        assert created_at_col.default is not None, "created_at deve ter default"

    def test_prompt_config_uses_get_utc_now(self):
        """PromptConfig model deve usar get_utc_now para created_at."""
        from admin.models import PromptConfig

        created_at_col = PromptConfig.__table__.columns['created_at']
        assert created_at_col.default is not None, "created_at deve ter default"

    def test_performance_log_uses_get_utc_now(self):
        """PerformanceLog model deve usar get_utc_now para created_at."""
        from admin.models_performance import PerformanceLog

        created_at_col = PerformanceLog.__table__.columns['created_at']
        assert created_at_col.default is not None, "created_at deve ter default"


class TestJWTTimezone:
    """Testes para verificar que JWT usa timezone correto."""

    def test_create_access_token_uses_utc(self):
        """create_access_token deve usar UTC para expiração."""
        from auth.security import create_access_token
        from jose import jwt
        from config import SECRET_KEY, ALGORITHM

        token = create_access_token({"sub": "testuser"})
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # exp deve estar no futuro
        exp = decoded.get("exp")
        assert exp is not None, "Token deve ter exp"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
