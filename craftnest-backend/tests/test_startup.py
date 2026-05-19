import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_startup_fails_with_postgres_user():
    """Verify that startup fails with SystemExit when connecting as the 'postgres' superuser."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = "postgres"
    mock_session.execute.return_value = mock_result
    
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_session
    
    with patch("app.main.SessionLocal", mock_sessionmaker):
        from app.main import app
        with pytest.raises(SystemExit) as exc_info:
            async with app.router.lifespan_context(app):
                pass
        assert exc_info.value.code == 1

@pytest.mark.asyncio
async def test_startup_fails_with_superuser_role():
    """Verify that startup fails with SystemExit when connecting as a role containing 'superuser'."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = "custom_superuser"
    mock_session.execute.return_value = mock_result
    
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_session
    
    with patch("app.main.SessionLocal", mock_sessionmaker):
        from app.main import app
        with pytest.raises(SystemExit) as exc_info:
            async with app.router.lifespan_context(app):
                pass
        assert exc_info.value.code == 1

@pytest.mark.asyncio
async def test_startup_succeeds_with_normal_user():
    """Verify that startup succeeds when connecting as a normal, non-privileged user like 'craftnest_app'."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = "craftnest_app"
    mock_session.execute.return_value = mock_result
    
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__.return_value = mock_session
    
    with patch("app.main.SessionLocal", mock_sessionmaker):
        from app.main import app
        # Should execute startup and shutdown of lifespan without raising SystemExit
        async with app.router.lifespan_context(app):
            pass
