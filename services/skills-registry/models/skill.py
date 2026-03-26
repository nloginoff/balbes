"""
Skill data models for Skills Registry.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SkillInputSchema(BaseModel):
    """Input schema for a skill"""

    parameters: dict[str, Any] = Field(default_factory=dict, description="Input parameters")
    required: list[str] = Field(default_factory=list, description="Required parameter names")
    examples: dict[str, Any] | None = Field(None, description="Example inputs")


class SkillOutputSchema(BaseModel):
    """Output schema for a skill"""

    format: str = Field(description="Output format (e.g., 'json', 'text', 'python_object')")
    description: str = Field(description="Output description")
    example: Any | None = Field(None, description="Example output")


class SkillCreateRequest(BaseModel):
    """Request to create a new skill"""

    name: str = Field(description="Skill name (e.g., 'parse_github')")
    description: str = Field(description="Skill description")
    version: str = Field(default="1.0.0", description="Semantic version")
    tags: list[str] = Field(default_factory=list, description="Tags for searching")
    category: str = Field(description="Skill category (e.g., 'web_parsing', 'data_processing')")
    implementation_url: str = Field(description="URL to implementation (GitHub, gist, etc.)")
    input_schema: SkillInputSchema = Field(description="Input specification")
    output_schema: SkillOutputSchema = Field(description="Output specification")
    estimated_tokens: int = Field(default=1000, description="Estimated tokens for execution")
    authors: list[str] = Field(default_factory=list, description="Author names/handles")
    dependencies: list[str] = Field(
        default_factory=list, description="Dependencies (e.g., 'beautifulsoup4')"
    )


class SkillResponse(BaseModel):
    """Skill response model"""

    skill_id: str = Field(description="Unique skill ID (UUID)")
    name: str = Field(description="Skill name")
    description: str = Field(description="Skill description")
    version: str = Field(description="Version")
    tags: list[str] = Field(description="Tags")
    category: str = Field(description="Category")
    implementation_url: str = Field(description="Implementation URL")
    input_schema: SkillInputSchema = Field(description="Input schema")
    output_schema: SkillOutputSchema = Field(description="Output schema")
    estimated_tokens: int = Field(description="Estimated tokens")
    authors: list[str] = Field(description="Authors")
    dependencies: list[str] = Field(description="Dependencies")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    usage_count: int = Field(default=0, description="Number of times used")
    rating: float = Field(default=0.0, description="Average rating (0-5)")


class SkillSearchRequest(BaseModel):
    """Skill search request"""

    query: str = Field(description="Search query")
    category: str | None = Field(None, description="Filter by category")
    tags: list[str] = Field(default_factory=list, description="Filter by tags (AND)")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")


class SkillSearchResult(BaseModel):
    """Search result for a skill"""

    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    score: float = Field(description="Search relevance score (0-1)")
    rating: float = Field(description="User rating")
    usage_count: int = Field(description="Usage count")


class SkillUsageRecord(BaseModel):
    """Record skill usage"""

    skill_id: str = Field(description="Skill UUID")
    agent_id: str = Field(description="Agent that used the skill")
    task_id: str = Field(description="Task ID")
    success: bool = Field(description="Whether execution was successful")
    tokens_used: int = Field(description="Tokens consumed")
    execution_time_ms: int = Field(description="Execution time in milliseconds")
