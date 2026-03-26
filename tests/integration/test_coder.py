"""
Integration tests for Coder Service.

Tests cover:
- Skill generation
- Code validation
- Test creation
- Skills Registry integration
- Skill improvement
- API endpoints
"""

import logging
import os
import sys

import httpx
import pytest
import pytest_asyncio

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

logger = logging.getLogger("test.coder")


# =============================================================================
# Fixtures
# =============================================================================


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
            pass


@pytest.fixture
def skill_name():
    """Test skill name"""
    return "TestDataProcessor"


@pytest.fixture
def skill_description():
    """Test skill description"""
    return "Process and transform JSON data efficiently"


@pytest.fixture
def skill_category():
    """Test skill category"""
    return "data-processing"


@pytest.fixture
def input_schema():
    """Test input schema"""
    return {
        "data": "dict",
        "format": "string",
        "options": "dict",
    }


@pytest.fixture
def output_schema():
    """Test output schema"""
    return {
        "result": "dict",
        "status": "string",
        "metadata": "dict",
    }


# =============================================================================
# Coder Agent Tests
# =============================================================================


@pytest.mark.asyncio
async def test_agent_initialization():
    """Test Coder Agent initialization"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    assert agent.agent_id == "coder"
    assert agent.http_client is None

    await agent.connect()
    assert agent.http_client is not None

    await agent.close()


@pytest.mark.asyncio
async def test_create_skill(
    skill_name, skill_description, skill_category, input_schema, output_schema
):
    """Test skill creation"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    result = await agent.create_skill(
        name=skill_name,
        description=skill_description,
        category=skill_category,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    assert result["name"] == skill_name
    assert result["status"] == "success"  # Should always succeed locally
    assert "skill_id" in result

    await agent.close()


@pytest.mark.asyncio
async def test_skill_structure(
    skill_name, skill_description, skill_category, input_schema, output_schema
):
    """Test generated skill has correct structure"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    result = await agent.create_skill(
        name=skill_name,
        description=skill_description,
        category=skill_category,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    # Check response structure
    assert "skill_id" in result
    assert "name" in result
    assert "status" in result
    assert result["name"] == skill_name
    assert result["status"] == "success"

    await agent.close()


@pytest.mark.asyncio
async def test_get_generated_skills():
    """Test retrieving generated skills"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    # Should be empty initially
    skills = await agent.get_generated_skills()
    initial_count = len(skills)

    # Create a skill
    result = await agent.create_skill(
        name="TestSkill",
        description="Test skill for retrieval",
        category="test",
        input_schema={"input": "string"},
        output_schema={"output": "string"},
    )

    # Should have one more (if creation succeeded)
    skills = await agent.get_generated_skills()

    if result["status"] == "success":
        assert len(skills) > initial_count

    await agent.close()


@pytest.mark.asyncio
async def test_skill_status(
    skill_name, skill_description, skill_category, input_schema, output_schema
):
    """Test getting skill status"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    # Create skill
    result = await agent.create_skill(
        name=skill_name,
        description=skill_description,
        category=skill_category,
        input_schema=input_schema,
        output_schema=output_schema,
    )

    assert result["status"] == "success"

    skill_id = result["skill_id"]

    # Get status
    status = await agent.get_skill_status(skill_id)

    assert status["skill_id"] == skill_id
    assert status["name"] == skill_name
    assert "code_lines" in status
    assert "test_cases" in status

    await agent.close()


@pytest.mark.asyncio
async def test_code_validation():
    """Test code validation"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    # Valid code
    valid_code = """
import logging
logger = logging.getLogger(__name__)

async def execute(input_data: dict) -> dict:
    logger.info(f"Input: {input_data}")
    return {"result": input_data}
"""

    is_valid = await agent._validate_code(valid_code)
    assert is_valid

    # Invalid code (missing async def execute)
    invalid_code = """
import logging
def process_data(data):
    return data
"""

    is_invalid = await agent._validate_code(invalid_code)
    assert not is_invalid

    await agent.close()


@pytest.mark.asyncio
async def test_improve_skill():
    """Test skill improvement"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    # Create a skill first
    create_result = await agent.create_skill(
        name="ImprovableSkill",
        description="Skill to improve",
        category="test",
        input_schema={"data": "string"},
        output_schema={"result": "string"},
    )

    assert create_result["status"] == "success"

    # Improve it
    improve_result = await agent.improve_skill(
        skill_name="ImprovableSkill",
        feedback="Handle empty inputs better",
        test_results={"failed_tests": 1},
    )

    assert "status" in improve_result
    assert improve_result["skill_name"] == "ImprovableSkill"

    await agent.close()


@pytest.mark.asyncio
async def test_multiple_skill_creation():
    """Test creating multiple skills"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    skills_to_create = [
        ("Skill1", "First skill", "category1"),
        ("Skill2", "Second skill", "category2"),
        ("Skill3", "Third skill", "category3"),
    ]

    results = []

    for name, desc, category in skills_to_create:
        result = await agent.create_skill(
            name=name,
            description=desc,
            category=category,
            input_schema={"input": "string"},
            output_schema={"output": "string"},
        )
        results.append(result)

    # Check that skills were created
    assert len(results) == 3
    assert all(r["name"] for r in results)

    await agent.close()


# =============================================================================
# API Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_coder_health_check(http_client):
    """Test health check endpoint"""
    try:
        response = await http_client.get("http://localhost:8103/health")
        assert response.status_code in [200, 503]
    except httpx.ConnectError:
        pytest.skip("Coder service not running")


@pytest.mark.asyncio
async def test_coder_root_endpoint(http_client):
    """Test root endpoint"""
    try:
        response = await http_client.get("http://localhost:8103/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "Coder"
    except httpx.ConnectError:
        pytest.skip("Coder service not running")


@pytest.mark.asyncio
async def test_skill_generation_api(http_client):
    """Test skill generation via API"""
    try:
        response = await http_client.post(
            "http://localhost:8103/api/v1/skills/generate",
            json={
                "name": "APITestSkill",
                "description": "Skill created via API",
                "category": "test",
                "input_schema": {"input": "string"},
                "output_schema": {"output": "string"},
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "skill_id" in data
            assert data["status"] in ["success", "failed"]
        elif response.status_code == 503:
            pytest.skip("Coder service not initialized")

    except httpx.ConnectError:
        pytest.skip("Coder service not running")


@pytest.mark.asyncio
async def test_get_generated_skills_api(http_client):
    """Test getting generated skills via API"""
    try:
        response = await http_client.get("http://localhost:8103/api/v1/skills/generated")

        if response.status_code == 200:
            data = response.json()
            assert "total" in data
            assert "skills" in data
            assert isinstance(data["skills"], list)
        elif response.status_code == 503:
            pytest.skip("Coder service not initialized")

    except httpx.ConnectError:
        pytest.skip("Coder service not running")


# =============================================================================
# Configuration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_coder_config():
    """Test Coder configuration"""
    from shared.config import get_settings

    settings = get_settings()

    assert settings.coder_port == 8103
    assert settings.orchestrator_port == 8102
    assert settings.skills_registry_port == 8101


# =============================================================================
# Integration Workflow Tests
# =============================================================================


@pytest.mark.asyncio
async def test_complete_skill_creation_workflow():
    """Test complete workflow: create -> validate -> test -> register"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    initial_count = len(await agent.get_generated_skills())

    # Create skill with full details
    result = await agent.create_skill(
        name="WorkflowTestSkill",
        description="Complete workflow test skill",
        category="workflow",
        input_schema={
            "input_data": "dict",
            "format": "string",
        },
        output_schema={
            "result": "dict",
            "status": "string",
        },
    )

    # Verify creation
    assert "skill_id" in result
    assert result["name"] == "WorkflowTestSkill"
    assert result["status"] == "success"

    # Check generated skills
    skills = await agent.get_generated_skills()
    assert len(skills) == initial_count + 1

    await agent.close()


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in Coder Agent"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()
    await agent.connect()

    # Try to improve non-existent skill
    result = await agent.improve_skill(
        skill_name="NonExistentSkill",
        feedback="This skill doesn't exist",
        test_results={},
    )

    assert result["status"] == "failed"
    assert "error" in result

    await agent.close()


@pytest.mark.asyncio
async def test_generated_code_structure():
    """Test that generated code has proper structure"""
    from services.coder.agent import CoderAgent

    agent = CoderAgent()

    # Generate code directly
    code = await agent._generate_code(
        name="TestCodeGen",
        description="Test code generation",
        input_schema={"input": "string"},
        output_schema={"output": "string"},
    )

    # Verify code structure
    assert "async def execute" in code
    assert "import logging" in code
    assert "logger" in code
    assert "return" in code
    assert "'''\"" in code or '"""' in code  # Docstring


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
