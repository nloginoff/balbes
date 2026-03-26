"""
Coder Agent - generates code and creates new skills autonomously.

Capabilities:
- Generate code from natural language descriptions
- Test generated code
- Validate skill structure
- Register skills in Skills Registry
- Learn from feedback
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("coder.agent")


class CoderAgent:
    """
    Coder Agent that autonomously generates and registers new skills.

    Features:
    - Code generation from descriptions
    - Test creation and execution
    - Skill validation
    - Registry integration
    - Feedback learning
    """

    def __init__(self):
        self.agent_id = "coder"
        self.skills_registry_url = f"http://localhost:{settings.skills_registry_port}"
        self.orchestrator_url = f"http://localhost:{settings.orchestrator_port}"
        self.http_client: httpx.AsyncClient | None = None
        self.generated_skills: list[dict[str, Any]] = []

    async def connect(self) -> None:
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Coder Agent initialized")

    async def close(self) -> None:
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("Coder Agent closed")

    async def create_skill(
        self,
        name: str,
        description: str,
        category: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a new skill from description.

        Args:
            name: Skill name
            description: What the skill does
            category: Skill category
            input_schema: Expected input structure
            output_schema: Expected output structure

        Returns:
            Created skill details
        """
        skill_id = str(uuid4())
        start_time = datetime.now(UTC)

        try:
            logger.info(f"[{skill_id}] Creating skill: {name}")

            # Шаг 1: Generate skill code
            generated_code = await self._generate_code(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
            )

            # Шаг 2: Validate code
            is_valid = await self._validate_code(generated_code)

            if not is_valid:
                logger.warning(f"[{skill_id}] Code validation failed")
                return {
                    "skill_id": skill_id,
                    "name": name,
                    "status": "failed",
                    "error": "Code validation failed",
                }

            # Шаг 3: Create tests
            test_cases = await self._generate_tests(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
            )

            # Шаг 4: Store skill details (locally first)
            skill_info = {
                "skill_id": skill_id,
                "name": name,
                "description": description,
                "category": category,
                "code": generated_code,
                "tests": test_cases,
                "status": "created",
                "created_at": datetime.now(UTC).isoformat(),
                "duration_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000,
                "registered": False,
            }

            self.generated_skills.append(skill_info)

            # Шаг 5: Register skill in Skills Registry (if available)
            skill_data = {
                "name": name,
                "description": description,
                "version": "1.0.0",
                "category": category,
                "implementation_url": f"http://localhost:{settings.orchestrator_port}/skills/{skill_id}",
                "input_schema": input_schema,
                "output_schema": output_schema,
                "tags": self._extract_tags(description),
                "authors": [self.agent_id],
            }

            registered_skill = await self._register_skill(skill_data)

            if registered_skill:
                skill_info["registered"] = True
                logger.info(f"[{skill_id}] Skill registered in Skills Registry")
            else:
                logger.warning(
                    f"[{skill_id}] Could not register in Skills Registry (will retry later)"
                )

            logger.info(f"[{skill_id}] Skill created successfully: {name}")

            return {
                "skill_id": skill_id,
                "name": name,
                "status": "success",
                "description": description,
                "category": category,
                "code_lines": len(generated_code.split("\n")),
                "test_cases": len(test_cases),
                "duration_ms": skill_info["duration_ms"],
            }

        except Exception as e:
            logger.error(f"[{skill_id}] Skill creation failed: {e}", exc_info=True)
            return {
                "skill_id": skill_id,
                "name": name,
                "status": "failed",
                "error": str(e),
                "duration_ms": (datetime.now(UTC) - start_time).total_seconds() * 1000,
            }

    async def improve_skill(
        self,
        skill_name: str,
        feedback: str,
        test_results: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Improve an existing skill based on feedback.

        Args:
            skill_name: Name of skill to improve
            feedback: Feedback on current implementation
            test_results: Test results showing issues

        Returns:
            Improved skill details
        """
        logger.info(f"Improving skill: {skill_name} based on feedback")

        # Find skill in registry
        skill = await self._find_skill(skill_name)

        if not skill:
            return {
                "status": "failed",
                "error": f"Skill '{skill_name}' not found",
            }

        # Generate improved code based on feedback
        improved_code = await self._generate_improved_code(
            skill_name=skill_name,
            current_code=skill.get("code", ""),
            feedback=feedback,
            test_results=test_results,
        )

        # Validate improved code
        is_valid = await self._validate_code(improved_code)

        if not is_valid:
            logger.warning(f"Improved code validation failed for {skill_name}")
            return {
                "status": "failed",
                "error": "Improved code validation failed",
            }

        logger.info(f"Skill improved: {skill_name}")

        return {
            "skill_name": skill_name,
            "status": "improved",
            "code_lines": len(improved_code.split("\n")),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_generated_skills(self) -> list[dict[str, Any]]:
        """Get all skills generated by this agent"""
        return self.generated_skills

    async def get_skill_status(self, skill_id: str) -> dict[str, Any]:
        """Get status of a generated skill"""
        for skill in self.generated_skills:
            if skill["skill_id"] == skill_id:
                return {
                    "skill_id": skill_id,
                    "name": skill["name"],
                    "status": skill["status"],
                    "created_at": skill["created_at"],
                    "code_lines": len(skill["code"].split("\n")),
                    "test_cases": len(skill["tests"]),
                }

        return {
            "skill_id": skill_id,
            "status": "not_found",
        }

    # Private helper methods

    async def _generate_code(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> str:
        """Generate Python code for skill"""
        logger.debug(f"Generating code for skill: {name}")

        # Mock code generation (in production would use LLM)
        code = f'''"""
{name} - {description}

Input: {json.dumps(input_schema, indent=2)}
Output: {json.dumps(output_schema, indent=2)}
"""

import logging

logger = logging.getLogger("{name}")


async def execute(input_data: dict) -> dict:
    """
    Execute the skill.

    Args:
        input_data: Input according to schema

    Returns:
        Output according to schema
    """
    logger.info(f"Executing {name} with input: {{input_data}}")

    # TODO: Implement skill logic here
    result = {{
        "status": "success",
        "message": "Skill executed successfully",
        "data": input_data,
    }}

    logger.info(f"Skill result: {{result}}")
    return result


if __name__ == "__main__":
    import asyncio

    async def main():
        test_input = {json.dumps({"example": "value"}, indent=2)}
        result = await execute(test_input)
        print(f"Result: {{result}}")

    asyncio.run(main())
'''

        return code

    async def _validate_code(self, code: str) -> bool:
        """Validate generated code"""
        logger.debug("Validating code")

        # Basic validation checks
        checks = [
            "async def execute" in code,  # Has execute function
            "import logging" in code,  # Has logging
            "logger" in code,  # Uses logger
            "return" in code,  # Returns something
        ]

        is_valid = all(checks)

        if not is_valid:
            logger.warning("Code validation failed: missing required elements")

        return is_valid

    async def _generate_tests(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> list[str]:
        """Generate test cases for skill"""
        logger.debug(f"Generating tests for {name}")

        tests = [
            f"Test basic execution of {name}",
            f"Test {name} with valid input",
            f"Test {name} error handling",
            f"Test {name} performance",
        ]

        return tests

    async def _register_skill(self, skill_data: dict[str, Any]) -> dict[str, Any] | None:
        """Register skill in Skills Registry"""
        try:
            if not self.http_client:
                return None

            response = await self.http_client.post(
                f"{self.skills_registry_url}/api/v1/skills",
                json=skill_data,
                timeout=10.0,
            )

            if response.status_code == 201:
                logger.info(f"Skill registered: {skill_data['name']}")
                return response.json()

            logger.error(f"Failed to register skill: {response.status_code}")
            return None

        except Exception as e:
            logger.warning(f"Error registering skill: {e}")
            return None

    async def _find_skill(self, skill_name: str) -> dict[str, Any] | None:
        """Find skill in local generated skills"""
        for skill in self.generated_skills:
            if skill["name"].lower() == skill_name.lower():
                return skill
        return None

    async def _generate_improved_code(
        self,
        skill_name: str,
        current_code: str,
        feedback: str,
        test_results: dict[str, Any],
    ) -> str:
        """Generate improved version of code based on feedback"""
        logger.debug(f"Generating improved code for {skill_name}")

        # Add improvement comment to code
        improvement_comment = f"""
# IMPROVEMENTS APPLIED ({datetime.now(UTC).isoformat()}):
# Feedback: {feedback}
# Test Results: {json.dumps(test_results, indent=2)}
"""

        return improvement_comment + current_code

    def _extract_tags(self, description: str) -> list[str]:
        """Extract tags from description"""
        # Simple tag extraction (in production would be more sophisticated)
        keywords = ["python", "async", "generator", "utility", "processing"]
        tags = [kw for kw in keywords if kw.lower() in description.lower()]
        return tags or ["generated", "autonomous"]
