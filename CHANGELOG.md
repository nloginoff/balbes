# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for MVP
- Orchestrator Agent with Telegram bot
- Coder Agent for creating Python skills
- Memory Service (Redis + Qdrant + PostgreSQL)
- Skills Registry
- Web UI (React + FastAPI backend)
- Multi-provider LLM client with fallback
- Token tracking and budget management
- Basic logging and monitoring

## [0.1.0] - 2026-03-26

### Added
- Initial project structure
- Documentation:
  - Technical specification
  - MVP scope definition
  - Project structure
  - Data models and DB schemas
  - API specification
  - Agents guide
  - Development plan
  - Deployment guide
  - Architecture decisions
  - Configuration guide
  - Examples and use cases
- Environment configuration (.env.example)
- README with project overview

### Notes
- This is the planning phase
- Development starts after this
- MVP target: 15-20 days

---

## Release Notes Template (for future releases)

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features
- New agents
- New skills

### Changed
- Modified existing functionality
- Updated dependencies
- Configuration changes

### Fixed
- Bug fixes
- Performance improvements

### Deprecated
- Features marked for removal

### Removed
- Removed features

### Security
- Security updates and fixes
```

---

## Version Numbering

**Format**: MAJOR.MINOR.PATCH

- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

**Examples**:
- `0.1.0` - Initial MVP
- `0.2.0` - Added Blogger agent
- `0.2.1` - Fixed token tracking bug
- `1.0.0` - First stable release
