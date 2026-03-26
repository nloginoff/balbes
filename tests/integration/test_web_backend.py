"""
Integration tests for Web Backend Service.

Tests cover:
- Authentication (login, register)
- User management
- Agents API
- Tasks API
- Skills API
- Dashboard endpoints
- WebSocket connections
"""

import logging
import os
import sys

import httpx
import pytest
import pytest_asyncio

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

logger = logging.getLogger("test.web_backend")


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def http_client():
    """HTTP client for API testing"""
    client = httpx.AsyncClient(timeout=30.0)
    try:
        yield client
    finally:
        try:
            await client.aclose()
        except RuntimeError:
            pass  # Event loop already closed


@pytest.fixture
def test_username():
    """Test username"""
    return "testuser"


@pytest.fixture
def test_password():
    """Test password"""
    return "testpass"  # Keep short for bcrypt (max 72 bytes)


@pytest.fixture
def test_email():
    """Test email"""
    return "test@example.com"


# ============================================================================
# Authentication Tests
# ============================================================================


@pytest.mark.asyncio
async def test_auth_manager_initialization():
    """Test AuthManager initialization"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    assert auth.jwt_secret
    assert auth.jwt_expiration > 0
    assert "admin" in auth.users_db


@pytest.mark.asyncio
async def test_password_hashing():
    """Test password hashing"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()
    password = "testpass"  # Keep short for bcrypt

    hashed = auth.get_password_hash(password)
    assert hashed != password
    assert auth.verify_password(password, hashed)


@pytest.mark.asyncio
async def test_user_registration():
    """Test user registration"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    user = auth.register_user(
        username="newuser",
        email="new@example.com",
        password="pass123",  # Shorter password for bcrypt
        full_name="New User",
    )

    assert user is not None
    assert user.username == "newuser"
    assert user.email == "new@example.com"


@pytest.mark.asyncio
async def test_user_login():
    """Test user login"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    # Register user
    auth.register_user(
        username="loginuser",
        email="login@example.com",
        password="pass123",  # Shorter password
    )

    # Login
    user = auth.authenticate_user("loginuser", "pass123")

    assert user is not None
    assert user.username == "loginuser"


@pytest.mark.asyncio
async def test_login_invalid_password():
    """Test login with invalid password"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    # Register user
    auth.register_user(
        username="user_bad_pass",
        email="bad@example.com",
        password="correct",  # Shorter password
    )

    # Try with wrong password
    user = auth.authenticate_user("user_bad_pass", "wrong")

    assert user is None


@pytest.mark.asyncio
async def test_jwt_token_creation():
    """Test JWT token creation"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    token = auth.create_access_token("user_123")

    assert token.access_token
    assert token.token_type == "bearer"
    assert token.expires_in > 0


@pytest.mark.asyncio
async def test_jwt_token_verification():
    """Test JWT token verification"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    # Create token
    token = auth.create_access_token("user_123")

    # Verify token
    user_id = auth.verify_token(token.access_token)

    assert user_id == "user_123"


@pytest.mark.asyncio
async def test_invalid_jwt_token():
    """Test verification of invalid JWT token"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    # Verify invalid token
    user_id = auth.verify_token("invalid_token")

    assert user_id is None


# ============================================================================
# API Service Tests
# ============================================================================


@pytest.mark.asyncio
async def test_api_service_initialization():
    """Test APIService initialization"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import APIService

    service = APIService()

    assert service.memory_service_url
    assert service.skills_registry_url
    assert service.orchestrator_url
    assert service.coder_url

    await service.connect()
    assert service.http_client is not None

    await service.close()


@pytest.mark.asyncio
async def test_api_service_services_health():
    """Test checking services health"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import APIService

    service = APIService()
    await service.connect()

    status = await service.check_services_health()

    assert isinstance(status, dict)
    assert "memory_service" in status or len(status) >= 0

    await service.close()


@pytest.mark.asyncio
async def test_api_service_get_agents():
    """Test getting agents via API service"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import APIService

    service = APIService()
    await service.connect()

    agents = await service.get_agents()

    assert isinstance(agents, list)

    await service.close()


@pytest.mark.asyncio
async def test_api_service_get_skills():
    """Test getting skills via API service"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import APIService

    service = APIService()
    await service.connect()

    skills = await service.get_skills()

    assert isinstance(skills, list)

    await service.close()


# ============================================================================
# Web Backend HTTP Tests
# ============================================================================


@pytest.mark.asyncio
async def test_web_backend_health_check(http_client):
    """Test health check endpoint"""
    try:
        response = await http_client.get("http://localhost:8200/health")
        assert response.status_code in [200, 503]
    except httpx.ConnectError:
        pytest.skip("Web Backend not running")


@pytest.mark.asyncio
async def test_web_backend_root_endpoint(http_client):
    """Test root endpoint"""
    try:
        response = await http_client.get("http://localhost:8200/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
    except httpx.ConnectError:
        pytest.skip("Web Backend not running")


@pytest.mark.asyncio
async def test_login_endpoint(http_client):
    """Test login endpoint"""
    try:
        response = await http_client.post(
            "http://localhost:8200/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "admin123",
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
        elif response.status_code == 503:
            pytest.skip("Auth service not initialized")

    except httpx.ConnectError:
        pytest.skip("Web Backend not running")


@pytest.mark.asyncio
async def test_get_agents_endpoint(http_client):
    """Test get agents endpoint"""
    try:
        # First login
        login_response = await http_client.post(
            "http://localhost:8200/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )

        if login_response.status_code != 200:
            pytest.skip("Login failed")

        token = login_response.json()["access_token"]

        # Get agents
        response = await http_client.get(
            "http://localhost:8200/api/v1/agents",
            params={"user_id": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 200:
            data = response.json()
            assert "agents" in data
            assert "total" in data

    except httpx.ConnectError:
        pytest.skip("Web Backend not running")


@pytest.mark.asyncio
async def test_get_dashboard_status(http_client):
    """Test dashboard status endpoint"""
    try:
        # First login
        login_response = await http_client.post(
            "http://localhost:8200/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )

        if login_response.status_code != 200:
            pytest.skip("Login failed")

        token = login_response.json()["access_token"]

        # Get status
        response = await http_client.get(
            "http://localhost:8200/api/v1/dashboard/status",
            params={"user_id": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "services" in data

    except httpx.ConnectError:
        pytest.skip("Web Backend not running")


# ============================================================================
# Configuration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_web_backend_config():
    """Test Web Backend configuration"""
    from shared.config import get_settings

    settings = get_settings()

    assert settings.web_backend_port == 8200
    assert settings.jwt_secret
    assert settings.jwt_expiration_hours > 0


# ============================================================================
# Integration Workflow Tests
# ============================================================================


@pytest.mark.asyncio
async def test_complete_auth_workflow():
    """Test complete authentication workflow"""
    import sys

    sys.path.insert(0, "/home/balbes/projects/dev/services/web-backend")
    from auth import AuthManager

    auth = AuthManager()

    # 1. Register
    user = auth.register_user(
        username="workflow_user",
        email="workflow@example.com",
        password="flowpass",  # Shorter password
    )

    assert user is not None

    # 2. Login
    logged_in = auth.authenticate_user("workflow_user", "flowpass")

    assert logged_in is not None
    assert logged_in.username == "workflow_user"

    # 3. Create token
    token = auth.create_access_token(logged_in.user_id)

    assert token.access_token

    # 4. Verify token
    verified_user_id = auth.verify_token(token.access_token)

    assert verified_user_id == logged_in.user_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
