# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0-mvp] - 2026-03-27

### Added
- Multi-environment runtime model (`dev`/`test`/`prod`) with isolated ports and data paths on one server.
- Dedicated run scripts for each environment and cross-environment status checks.
- Release readiness documentation:
  - `RELEASE_CHECKLIST.md`
  - updated runbook guidance in `DEPLOYMENT.md`, `README.md`, `PROJECT_GUIDE.md`, `TODO.md`

### Changed
- Production app ports moved to `18100..18200` and infra ports to isolated `15xxx/16xxx` ranges.
- Health checks updated to support explicit `dev|test|prod` modes and auto-detection.
- Stop/start scripts hardened to use explicit compose files and path-safe project root resolution.
- Python runtime baseline aligned to Python 3.13 in deployment docs and operational flow.

### Fixed
- Skills workflow integration test made deterministic against semantic-search indexing lag.
- Production startup/stop scripts fixed for user-level logging and PID tracking.
- Qdrant local production client mode fixed for HTTP operation (`https=False`) to avoid SSL mismatch.
- Python compatibility issues around `datetime.UTC` usage corrected.

### Security
- Production environment requirements reinforced in docs (`WEB_AUTH_TOKEN`, JWT secrets, non-default secrets).

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
