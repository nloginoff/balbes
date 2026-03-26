# Contributing to Balbes Multi-Agent System

Спасибо за интерес к проекту! Этот документ описывает как внести вклад.

---

## 🚀 Quick Start для контрибьютора

```bash
# 1. Fork репозиторий (когда будет на GitHub)
# 2. Clone
git clone <your-fork-url>
cd balbes

# 3. Setup
make setup

# 4. Create branch
git checkout -b feature/my-feature

# 5. Develop
# ... your changes ...

# 6. Test
make test

# 7. Quality check
make quality

# 8. Commit
git commit -m "feat: add my feature"

# 9. Push
git push origin feature/my-feature

# 10. Create Pull Request
```

---

## 📋 Code of Conduct

Будьте уважительны, профессиональны, и конструктивны.

---

## 🎯 Что можно улучшить?

### High Priority
- 🐛 **Bug fixes** - исправление ошибок
- 📚 **Documentation** - улучшение docs, примеры
- ✅ **Tests** - добавление тестов

### Medium Priority
- ✨ **Features** - новые возможности из backlog
- ⚡ **Performance** - оптимизации
- 🎨 **UI/UX** - улучшения интерфейса

### Low Priority
- 🧹 **Refactoring** - улучшение кода
- 📊 **Analytics** - новые метрики

---

## 📝 Процесс контрибуции

### 1. Выбрать задачу

- Посмотрите Issues (TODO для MVP или будущие features)
- Или предложите свою идею (создайте Issue для обсуждения)

### 2. Создать ветку

```bash
# Feature
git checkout -b feature/short-description

# Bug fix
git checkout -b bugfix/issue-number-short-description

# Documentation
git checkout -b docs/what-you-document
```

### 3. Разработка

**Следуйте стандартам проекта**:
- Type hints везде
- Docstrings (Google style)
- Async/await для I/O
- PEP 8 (через ruff)
- Tests для новых features

### 4. Testing

```bash
# Unit tests для нового кода
pytest tests/unit/test_your_feature.py -v

# Integration tests если затрагивает сервисы
pytest tests/integration/test_your_integration.py -v

# Все тесты
make test

# Coverage (желательно >80%)
make test-cov
```

### 5. Quality Checks

```bash
# Linting
make lint

# Formatting
make format

# Pre-commit hooks
pre-commit run --all-files
```

### 6. Commit

**Формат commit message**:
```
<type>(<scope>): <short summary>

<detailed description if needed>

<footer: references to issues, breaking changes, etc>
```

**Types**:
- `feat`: новая feature
- `fix`: bug fix
- `docs`: изменения в документации
- `refactor`: рефакторинг без изменения функциональности
- `test`: добавление тестов
- `chore`: изменения в build/CI/etc

**Examples**:
```
feat(coder): add retry logic for failed tests

Coder now retries up to 3 times when tests fail,
with exponential backoff between attempts.

Closes #42
```

```
fix(orchestrator): handle telegram connection errors

Added retry logic and better error messages when
Telegram API is temporarily unavailable.

Fixes #35
```

```
docs(deployment): add SSL setup instructions

Added step-by-step guide for setting up Let's Encrypt
certificates with nginx.
```

### 7. Push и Pull Request

```bash
# Push to your fork
git push origin feature/my-feature

# Create PR on GitHub
# - Clear title
# - Description of changes
# - Link to related issues
# - Screenshots if UI changes
```

---

## 🧪 Testing Guidelines

### Что тестировать?

**Обязательно**:
- Новые features
- Bug fixes
- Public API methods
- Critical paths (task execution, LLM calls)

**Опционально**:
- Private methods (если сложная логика)
- Edge cases
- Error handling

### Типы тестов

**Unit** (`tests/unit/`):
- Тестируют отдельные функции/классы
- Mock все внешние зависимости
- Быстрые (< 1s per test)

**Integration** (`tests/integration/`):
- Тестируют взаимодействие компонентов
- Требуют running infrastructure (make infra-up)
- Средние по скорости (1-5s per test)

**E2E** (`tests/e2e/`):
- Тестируют полные workflows
- Требуют все сервисы running
- Медленные (10-60s per test)

### Структура теста

```python
import pytest

@pytest.mark.asyncio
async def test_feature_success():
    """Test that feature works in happy path"""
    # Arrange
    agent = create_test_agent()
    task = create_test_task()

    # Act
    result = await agent.execute_task(task)

    # Assert
    assert result.status == "success"
    assert result.data is not None


@pytest.mark.asyncio
async def test_feature_error_handling():
    """Test that feature handles errors gracefully"""
    # Arrange
    agent = create_test_agent()
    invalid_task = create_invalid_task()

    # Act
    result = await agent.execute_task(invalid_task)

    # Assert
    assert result.status == "error"
    assert "error" in result.error.lower()
```

---

## 📐 Code Style

### Python

**PEP 8** через ruff:
```python
# Good
def calculate_total_tokens(prompt: str, response: str) -> int:
    """Calculate total tokens used in LLM call."""
    return len(prompt) + len(response)


# Bad
def calc(p,r):  # No type hints, unclear names
    return len(p)+len(r)  # No spaces around operators
```

**Type Hints**:
```python
# Good
async def execute_skill(
    self,
    skill_name: str,
    params: dict[str, Any]
) -> SkillResult:
    """Execute a skill with given parameters."""
    ...


# Bad
async def execute_skill(self, skill_name, params):  # No types
    ...
```

**Docstrings** (Google style):
```python
def parse_website(url: str, selectors: dict[str, str]) -> dict[str, Any]:
    """
    Parse website and extract data using CSS selectors.

    Args:
        url: Website URL to parse
        selectors: CSS selectors for data extraction

    Returns:
        dict: Extracted data with keys from selectors

    Raises:
        ValueError: If URL is invalid
        TimeoutError: If request times out

    Example:
        >>> result = parse_website(
        ...     "https://news.ycombinator.com",
        ...     {"title": "span.titleline > a"}
        ... )
        >>> print(result["title"])
    """
    ...
```

**Async/Await**:
```python
# Good - async для I/O
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()


# Bad - sync I/O в async функции
async def fetch_data(url: str) -> dict:
    response = requests.get(url)  # Blocking!
    return response.json()
```

### TypeScript/React

```typescript
// Good - explicit types
interface AgentCardProps {
  agentId: string;
  name: string;
  status: "idle" | "working" | "error";
  tokensUsed: number;
}

export const AgentCard: React.FC<AgentCardProps> = ({
  agentId,
  name,
  status,
  tokensUsed,
}) => {
  return <div>...</div>;
};


// Bad - any types
export const AgentCard = (props: any) => {
  return <div>...</div>;
};
```

---

## 📁 Где добавлять код?

### Новый agent
```
services/{agent_name}/
├── main.py
├── agent.py
├── requirements.txt
└── Dockerfile
```

### Новый skill
```
shared/skills/{skill_name}.py        # Implementation
config/skills/{skill_name}.yaml      # Definition
tests/unit/test_skills/test_{skill_name}.py  # Tests
```

### Новый API endpoint
```
services/{service}/api/{resource}.py
```

### Новая UI page
```
services/web/frontend/src/pages/{PageName}.tsx
```

---

## 🔍 Code Review Checklist

Перед отправкой PR проверьте:

### Functionality
- [ ] Feature работает как задумано
- [ ] Нет регрессий (старые фичи работают)
- [ ] Edge cases обработаны

### Code Quality
- [ ] Type hints добавлены
- [ ] Docstrings написаны
- [ ] Нет дублирования кода
- [ ] Понятные имена переменных
- [ ] Комментарии только где нужно (не obvious things)

### Testing
- [ ] Тесты написаны
- [ ] Тесты проходят (`make test`)
- [ ] Coverage разумный (>80% для новых features)

### Standards
- [ ] Ruff check проходит (`make lint`)
- [ ] Ruff format применен (`make format`)
- [ ] Pre-commit hooks проходят
- [ ] Нет TODO в коде (или созданы Issues)

### Documentation
- [ ] README updated (если нужно)
- [ ] CHANGELOG.md updated
- [ ] Docstrings в коде
- [ ] Примеры добавлены (если нужно)

### Security
- [ ] Нет hardcoded secrets
- [ ] Валидация входных данных
- [ ] Нет SQL injection возможностей
- [ ] File paths проверяются

---

## 🐛 Reporting Bugs

### Создайте Issue со следующей информацией:

**Title**: Краткое описание проблемы

**Description**:
```markdown
## Описание
Что пошло не так?

## Шаги для воспроизведения
1. Запустить X
2. Выполнить Y
3. Наблюдать Z

## Ожидаемое поведение
Что должно было произойти

## Фактическое поведение
Что произошло на самом деле

## Логи
```
<paste relevant logs>
```

## Environment
- OS: Ubuntu 22.04
- Python: 3.13.2
- Version: git commit hash
- Services: orchestrator, coder

## Дополнительный контекст
Screenshots, configs, etc
```

---

## 💡 Предложение Features

### Создайте Issue с описанием:

```markdown
## Feature Description
Что вы хотите добавить?

## Use Case
Зачем это нужно? Какую проблему решает?

## Proposed Solution
Как вы видите реализацию?

## Alternatives Considered
Рассматривали другие подходы?

## Additional Context
Mockups, examples, references
```

---

## 📖 Documentation Contributions

Документация важна! Приветствуются:
- Исправления ошибок и опечаток
- Дополнения и уточнения
- Новые примеры
- Переводы (в будущем)
- Диаграммы и визуализации

**Стиль документации**:
- Четко и лаконично
- Практические примеры
- Ссылки на related docs
- Используйте эмодзи для навигации
- Code blocks с правильным syntax highlighting

---

## 🔄 Release Process (для мейнтейнеров)

### Подготовка релиза

1. Обновить CHANGELOG.md
2. Обновить version в pyproject.toml
3. Создать git tag
4. Build Docker images
5. Тестирование на staging (если есть)
6. Deploy в production
7. Announcement

### Versioning

**Semantic Versioning**: MAJOR.MINOR.PATCH

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

**Examples**:
- `0.1.0` → `0.2.0`: Added Blogger agent (new feature)
- `0.2.0` → `0.2.1`: Fixed token tracking bug (patch)
- `0.2.1` → `1.0.0`: Changed API format (breaking change)

---

## 🏆 Recognition

Все контрибьюторы будут упомянуты в:
- CHANGELOG.md (для значимых изменений)
- README.md Contributors section (когда настроим)

---

## 📞 Questions?

- **Technical**: См. docs/ или создайте Issue
- **Process**: Этот документ или Issue
- **Urgent**: Напрямую мейнтейнерам

---

## 🙏 Thanks

Спасибо что помогаете сделать Balbes лучше!

---

**Happy coding!** 🚀
