# Coder Agent Service

**Coder Agent** is an autonomous skill generation service that can:
- Generate Python code from natural language descriptions
- Create new skills automatically
- Test generated code
- Register skills in Skills Registry
- Improve existing skills based on feedback

## Features

### 🤖 Autonomous Skill Generation
- Create new skills from descriptions
- Generate tested code automatically
- Smart validation and error handling
- Register in Skills Registry

### 🔧 Code Quality
- Code validation
- Test case generation
- Error handling templates
- Logging and monitoring

### 📚 Learning & Improvement
- Accept feedback on generated skills
- Learn from test results
- Improve existing skills
- Track generated skills

## Architecture

```
CoderAgent
├── create_skill() - Generate new skill
├── improve_skill() - Improve existing skill
├── _generate_code() - Code generation
├── _validate_code() - Code validation
├── _generate_tests() - Test creation
└── _register_skill() - Registry integration
```

## API Endpoints

### Skill Generation
```
POST /api/v1/skills/generate
{
  "name": "DataProcessor",
  "description": "Process and transform data",
  "category": "data",
  "input_schema": {"data": "list"},
  "output_schema": {"result": "dict"}
}
```

### Skill Improvement
```
POST /api/v1/skills/improve
{
  "skill_name": "DataProcessor",
  "feedback": "Handle edge cases better",
  "test_results": {"failed_tests": 2}
}
```

### Get Generated Skills
```
GET /api/v1/skills/generated
```

### Get Skill Status
```
GET /api/v1/skills/{skill_id}/status
```

## Usage Examples

### Python Client
```python
import httpx
import asyncio

async def generate_skill():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8004/api/v1/skills/generate",
            json={
                "name": "TextAnalyzer",
                "description": "Analyze text sentiment and keywords",
                "category": "nlp",
                "input_schema": {"text": "string"},
                "output_schema": {"sentiment": "string", "keywords": "list"}
            }
        )
        result = response.json()
        print(f"Skill generated: {result['name']}")
        print(f"Status: {result['status']}")

asyncio.run(generate_skill())
```

### cURL
```bash
curl -X POST http://localhost:8004/api/v1/skills/generate \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Calculator",
    "description": "Perform mathematical operations",
    "category": "math",
    "input_schema": {"operation": "string", "values": "list"},
    "output_schema": {"result": "number"}
  }'
```

## Configuration

Port: 8004 (default)
Log Level: INFO
Timeout: 30 seconds

## Testing

```bash
pytest tests/integration/test_coder.py -v
```

## Workflow

```
User Request
    ↓
Skill Description
    ↓
Code Generation (using templates/LLM)
    ↓
Code Validation
    ↓
Test Generation
    ↓
Register in Skills Registry
    ↓
Skill Available for Use
    ↓
Monitor & Get Feedback
    ↓
Improve Based on Feedback
```

## Generated Skill Structure

```python
async def execute(input_data: dict) -> dict:
    """Execute the skill"""
    # Process input
    # Perform operations
    # Return output
    return result
```

## Performance

- Skill generation: 500-2000ms
- Code validation: <100ms
- Test generation: 200-500ms
- Registry registration: 100-300ms

## Next Steps

- [ ] LLM-based code generation
- [ ] Advanced validation with AST
- [ ] Performance optimization
- [ ] Skill versioning
- [ ] Automated testing framework
- [ ] Continuous improvement loop

## Files

- `agent.py` - CoderAgent class
- `main.py` - FastAPI application
- `api/skills.py` - Skill management API
- `requirements.txt` - Dependencies
- `README.md` - This file
