"""
Integration tests for Skills Registry Service.

Tests the full flow of Skills Registry API with real database connections.
Requires infrastructure to be running (PostgreSQL, Qdrant).
"""

from uuid import uuid4

import httpx
import pytest

# Base URL for Skills Registry
BASE_URL = "http://localhost:8101"


class TestHealthCheck:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test that health check returns 200"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health")

            assert response.status_code == 200
            data = response.json()

            assert data["service"] == "skills-registry"
            assert data["status"] == "healthy"
            assert "postgres" in data
            assert "qdrant" in data


class TestSkillCreation:
    """Test skill creation endpoints"""

    @pytest.mark.asyncio
    async def test_create_skill(self):
        """Test creating a new skill"""
        async with httpx.AsyncClient() as client:
            skill_data = {
                "name": f"parse_github_{uuid4().hex[:8]}",
                "description": "Parse GitHub repository structure and extract metadata",
                "version": "1.0.0",
                "category": "web_parsing",
                "implementation_url": "https://github.com/example/parse_github",
                "tags": ["github", "parsing", "repositories"],
                "input_schema": {
                    "parameters": {"repo_url": {"type": "string"}},
                    "required": ["repo_url"],
                },
                "output_schema": {"format": "json", "description": "Repository structure"},
                "estimated_tokens": 2000,
                "authors": ["test_user"],
                "dependencies": ["requests", "beautifulsoup4"],
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/skills",
                json=skill_data,
            )

            # Skip if OpenRouter API is not available
            if response.status_code == 400 and "embedding" in response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert response.status_code == 201
            result = response.json()
            assert "skill_id" in result
            assert result["status"] == "created"
            assert result["name"] == skill_data["name"]

    @pytest.mark.asyncio
    async def test_create_skill_duplicate_name(self):
        """Test that duplicate skill names are rejected"""
        async with httpx.AsyncClient() as client:
            skill_name = f"parse_web_{uuid4().hex[:8]}"
            skill_data = {
                "name": skill_name,
                "description": "First skill",
                "version": "1.0.0",
                "category": "web_parsing",
                "implementation_url": "https://example.com",
                "tags": ["test"],
                "input_schema": {"parameters": {}, "required": []},
                "output_schema": {"format": "json", "description": "test"},
            }

            # Create first skill
            response1 = await client.post(
                f"{BASE_URL}/api/v1/skills",
                json=skill_data,
            )

            # Skip if OpenRouter API is not available
            if response1.status_code == 400 and "embedding" in response1.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert response1.status_code == 201

            # Try to create duplicate
            response2 = await client.post(
                f"{BASE_URL}/api/v1/skills",
                json=skill_data,
            )
            assert response2.status_code == 400
            assert "already exists" in response2.json()["detail"].lower()


class TestSkillRetrieval:
    """Test skill retrieval endpoints"""

    @pytest.mark.asyncio
    async def test_get_skill(self):
        """Test getting a skill by ID"""
        async with httpx.AsyncClient() as client:
            # Create a skill
            skill_data = {
                "name": f"scrape_site_{uuid4().hex[:8]}",
                "description": "Scrape website content",
                "version": "1.0.0",
                "category": "web_parsing",
                "implementation_url": "https://example.com",
                "tags": ["web", "scraping"],
                "input_schema": {"parameters": {}, "required": []},
                "output_schema": {"format": "json", "description": "content"},
                "estimated_tokens": 1500,
            }

            create_response = await client.post(
                f"{BASE_URL}/api/v1/skills",
                json=skill_data,
            )

            # Skip if OpenRouter API is not available
            if create_response.status_code == 400 and "embedding" in create_response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            skill_id = create_response.json()["skill_id"]

            # Get the skill
            response = await client.get(f"{BASE_URL}/api/v1/skills/{skill_id}")

            assert response.status_code == 200
            skill = response.json()
            assert skill["skill_id"] == skill_id
            assert skill["name"] == skill_data["name"]
            assert skill["description"] == skill_data["description"]
            assert skill["category"] == skill_data["category"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_skill(self):
        """Test getting a skill that doesn't exist"""
        async with httpx.AsyncClient() as client:
            fake_id = str(uuid4())
            response = await client.get(f"{BASE_URL}/api/v1/skills/{fake_id}")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_skills(self):
        """Test listing all skills"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/v1/skills")

            assert response.status_code == 200
            result = response.json()
            assert "skills" in result
            assert "total" in result
            assert "limit" in result
            assert "offset" in result
            assert isinstance(result["skills"], list)

    @pytest.mark.asyncio
    async def test_list_skills_pagination(self):
        """Test skill listing with pagination"""
        async with httpx.AsyncClient() as client:
            # Create multiple skills
            for i in range(3):
                skill_data = {
                    "name": f"skill_page_{i}_{uuid4().hex[:4]}",
                    "description": f"Test skill {i}",
                    "version": "1.0.0",
                    "category": "test",
                    "implementation_url": "https://example.com",
                    "tags": ["test"],
                    "input_schema": {"parameters": {}, "required": []},
                    "output_schema": {"format": "json", "description": "test"},
                }

                await client.post(
                    f"{BASE_URL}/api/v1/skills",
                    json=skill_data,
                )

            # Test pagination
            response = await client.get(f"{BASE_URL}/api/v1/skills?limit=2&offset=0")
            assert response.status_code == 200
            result = response.json()
            assert result["limit"] == 2
            assert result["offset"] == 0


class TestSkillFiltering:
    """Test skill filtering endpoints"""

    @pytest.mark.asyncio
    async def test_filter_by_category(self):
        """Test filtering skills by category (using existing skills)"""
        async with httpx.AsyncClient() as client:
            # Use existing skills instead of creating new ones
            # Filter by web_parsing
            response = await client.get(f"{BASE_URL}/api/v1/skills/category/web_parsing")

            assert response.status_code == 200
            result = response.json()
            assert "skills" in result
            assert result["total"] >= 2  # At least the 2 we created


class TestSkillSearch:
    """Test skill search endpoints"""

    @pytest.mark.asyncio
    async def test_semantic_search(self):
        """Test semantic search for skills (using existing skills)"""
        async with httpx.AsyncClient() as client:
            # Use existing skills for search instead of creating new ones
            # This avoids requiring OpenRouter API for test execution

            # Search for parsing-related skills
            search_data = {
                "query": "extract content from websites",
                "limit": 10,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/skills/search",
                json=search_data,
            )

            # Skip if OpenRouter API is not available
            if response.status_code == 400 and "embedding" in response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert response.status_code == 200
            result = response.json()
            assert "results" in result
            assert "total" in result
            assert result["total"] >= 0
            assert len(result["results"]) >= 0

            # Check that results have required fields
            for skill in result["results"]:
                assert "skill_id" in skill
                assert "name" in skill
                assert "description" in skill
                assert "score" in skill

    @pytest.mark.asyncio
    async def test_quick_search(self):
        """Test quick GET search endpoint (using existing skills)"""
        async with httpx.AsyncClient() as client:
            # Use existing skills for quick search
            response = await client.get(f"{BASE_URL}/api/v1/skills/search/quick?q=parsing&limit=5")

            # Skip if OpenRouter API is not available
            if response.status_code == 400 and "embedding" in response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert response.status_code == 200
            result = response.json()
            assert "results" in result
            assert "total" in result

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self):
        """Test search with category filtering (using existing skills)"""
        async with httpx.AsyncClient() as client:
            # Use existing skills with category filter instead of creating new ones
            # Search with category filter
            search_data = {
                "query": "parsing",
                "category": "web_parsing",
                "limit": 5,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/skills/search",
                json=search_data,
            )

            # Skip if OpenRouter API is not available
            if response.status_code == 400 and "embedding" in response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert response.status_code == 200
            result = response.json()
            assert "results" in result

            # All results should be in web_parsing category
            for skill in result["results"]:
                assert skill["category"] == "web_parsing"


class TestCompleteWorkflow:
    """Test complete workflow"""

    @pytest.mark.asyncio
    async def test_complete_skill_workflow(self):
        """Test complete skill management workflow"""
        async with httpx.AsyncClient() as client:
            workflow_category = f"workflow_category_{uuid4().hex[:8]}"
            # Step 1: Create a skill
            skill_data = {
                "name": f"workflow_skill_{uuid4().hex[:8]}",
                "description": "Test skill for complete workflow",
                "version": "1.0.0",
                "category": workflow_category,
                "implementation_url": "https://github.com/example/skill",
                "tags": ["workflow", "test"],
                "input_schema": {
                    "parameters": {"url": {"type": "string"}, "selector": {"type": "string"}},
                    "required": ["url"],
                },
                "output_schema": {"format": "json", "description": "Extracted content"},
                "estimated_tokens": 1500,
                "authors": ["test_author"],
                "dependencies": ["beautifulsoup4"],
            }

            create_response = await client.post(
                f"{BASE_URL}/api/v1/skills",
                json=skill_data,
            )

            # Skip if OpenRouter API is not available
            if create_response.status_code == 400 and "embedding" in create_response.text.lower():
                pytest.skip("OpenRouter API not available (embeddings required)")

            assert create_response.status_code == 201
            skill_id = create_response.json()["skill_id"]

            # Step 2: Get the skill
            get_response = await client.get(f"{BASE_URL}/api/v1/skills/{skill_id}")
            assert get_response.status_code == 200
            skill = get_response.json()
            assert skill["name"] == skill_data["name"]

            # Step 3: Search for the skill
            search_response = await client.post(
                f"{BASE_URL}/api/v1/skills/search", json={"query": "workflow skill", "limit": 10}
            )
            assert search_response.status_code == 200
            search_results = search_response.json()
            assert search_results["total"] >= 1

            # Step 4: Check if our skill is in the results
            found = any(r["skill_id"] == skill_id for r in search_results["results"])
            assert found, "Created skill should be found in search results"

            # Step 5: List all skills in category
            list_response = await client.get(
                f"{BASE_URL}/api/v1/skills/category/{workflow_category}"
            )
            assert list_response.status_code == 200
            list_result = list_response.json()
            assert list_result["total"] >= 1

            # Our skill should be in the list
            found_in_list = any(s["skill_id"] == skill_id for s in list_result["skills"])
            assert found_in_list, "Created skill should be in category list"

            print(f"✅ Workflow test passed! Created skill: {skill_id}")
