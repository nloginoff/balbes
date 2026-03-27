"""
Orchestrator Agent - главный координирующий агент системы.

Управляет:
- Анализом задач пользователя
- Выбором и вызовом скиллов через Skills Registry
- Управлением контекстом через Memory Service
- Координацией с другими агентами через Message Bus
- Отправкой результатов пользователю
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.agent")


class OrchestratorAgent:
    """
    Orchestrator Agent координирует работу всей системы.

    Основные функции:
    - Обработка запросов пользователя
    - Поиск релевантных скиллов
    - Выполнение скиллов
    - Управление памятью и контекстом
    - Возврат результатов
    """

    def __init__(self):
        self.agent_id = "orchestrator"
        self.memory_service_url = f"http://localhost:{settings.memory_service_port}"
        self.skills_registry_url = f"http://localhost:{settings.skills_registry_port}"
        self.http_client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Orchestrator Agent initialized")

    async def close(self) -> None:
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("Orchestrator Agent closed")

    async def execute_task(
        self,
        description: str,
        user_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Выполнить задачу пользователя.

        Args:
            description: Описание задачи от пользователя
            user_id: ID пользователя (обычно Telegram user_id)
            context: Дополнительный контекст

        Returns:
            Результат выполнения задачи
        """
        task_id = str(uuid4())
        start_time = datetime.now(timezone.utc)

        try:
            logger.info(f"[{task_id}] Starting task: {description[:50]}...")

            # Шаг 1: Получить контекст из Memory Service
            logger.debug(f"[{task_id}] Retrieving context from Memory Service")
            agent_context = await self._get_context(user_id)

            # Шаг 2: Поиск релевантных скиллов в Skills Registry
            logger.debug(f"[{task_id}] Searching for relevant skills")
            relevant_skills = await self._search_skills(description)

            if not relevant_skills:
                logger.warning(f"[{task_id}] No relevant skills found")
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": "No relevant skills found for this task",
                    "duration_ms": (datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                }

            # Шаг 3: Выбрать лучший скилл
            selected_skill = relevant_skills[0]
            logger.info(
                f"[{task_id}] Selected skill: {selected_skill['name']} (score: {selected_skill['score']:.2f})"
            )

            # Шаг 4: Сохранить контекст задачи в Memory Service
            await self._save_task_context(
                user_id=user_id,
                task_id=task_id,
                description=description,
                selected_skill=selected_skill,
            )

            # Шаг 5: Выполнить скилл (в реальной системе это через Message Bus)
            result = await self._execute_skill(
                skill_name=selected_skill["name"],
                description=description,
                context=agent_context,
            )

            # Шаг 6: Сохранить результат в Memory Service
            await self._save_result(
                user_id=user_id,
                task_id=task_id,
                skill_name=selected_skill["name"],
                result=result,
                success=True,
            )

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.info(f"[{task_id}] Task completed in {duration_ms:.0f}ms")

            return {
                "task_id": task_id,
                "status": "success",
                "result": result,
                "skill_used": selected_skill["name"],
                "duration_ms": duration_ms,
            }

        except Exception as e:
            logger.error(f"[{task_id}] Task failed: {e}", exc_info=True)

            # Сохранить ошибку в Memory Service
            await self._save_result(
                user_id=user_id,
                task_id=task_id,
                skill_name="error_handler",
                result={"error": str(e)},
                success=False,
            )

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
            }

    async def _get_context(self, user_id: str) -> dict[str, Any]:
        """Получить контекст пользователя из Memory Service"""
        try:
            if not self.http_client:
                return {}

            response = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/context/orchestrator/{user_id}"
            )

            if response.status_code == 200:
                return response.json().get("value", {})
            elif response.status_code == 404:
                # No context found - not an error
                return {}
            return {}

        except Exception as e:
            logger.warning(f"Failed to get context: {e}")
            return {}

    async def _search_skills(self, query: str) -> list[dict[str, Any]]:
        """Поиск релевантных скиллов в Skills Registry"""
        try:
            if not self.http_client:
                return []

            response = await self.http_client.post(
                f"{self.skills_registry_url}/api/v1/skills/search",
                json={
                    "query": query,
                    "limit": 5,
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            return []

        except Exception as e:
            logger.warning(f"Failed to search skills: {e}")
            return []

    async def _execute_skill(
        self,
        skill_name: str,
        description: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Выполнить скилл"""
        logger.debug(f"Executing skill: {skill_name}")

        # В реальной системе это будет отправка в Message Bus
        # Для сейчас возвращаем mock результат
        return {
            "skill": skill_name,
            "input": description,
            "output": f"Executed {skill_name} successfully",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _save_task_context(
        self,
        user_id: str,
        task_id: str,
        description: str,
        selected_skill: dict[str, Any],
    ) -> None:
        """Сохранить контекст задачи в Memory Service"""
        try:
            if not self.http_client:
                return

            context_data = {
                "key": f"task_{task_id}",
                "value": {
                    "user_id": user_id,
                    "description": description,
                    "selected_skill": selected_skill["name"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "ttl": 3600,  # 1 час
            }

            await self.http_client.post(
                f"{self.memory_service_url}/api/v1/context/{user_id}",
                json=context_data,
            )

        except Exception as e:
            logger.warning(f"Failed to save task context: {e}")

    async def _save_result(
        self,
        user_id: str,
        task_id: str,
        skill_name: str,
        result: dict[str, Any],
        success: bool,
    ) -> None:
        """Сохранить результат в Memory Service"""
        try:
            if not self.http_client:
                return

            memory_data = {
                "agent_id": self.agent_id,
                "content": f"Task {task_id}: {skill_name} {'completed' if success else 'failed'}",
                "memory_type": "task_result",
                "importance": 0.8 if success else 0.9,
                "metadata": {
                    "task_id": task_id,
                    "user_id": user_id,
                    "skill": skill_name,
                    "success": success,
                    "result": result,
                },
            }

            await self.http_client.post(
                f"{self.memory_service_url}/api/v1/memory",
                json=memory_data,
            )

        except Exception as e:
            logger.warning(f"Failed to save result: {e}")

    async def get_agent_status(self) -> dict[str, Any]:
        """Получить статус агента"""
        return {
            "agent_id": self.agent_id,
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "memory_service": f"http://localhost:{settings.memory_service_port}",
                "skills_registry": f"http://localhost:{settings.skills_registry_port}",
            },
        }
