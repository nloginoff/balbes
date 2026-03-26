#!/usr/bin/env python3
"""
Validate system configuration before starting services.

Checks:
- Environment variables
- YAML configs
- Required files
- Dependencies

Usage:
    python scripts/validate_config.py
"""

import os
import sys
from pathlib import Path

import yaml

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_env():
    """Validate environment variables"""
    print("1️⃣  Validating environment variables...")

    try:
        from shared.config import Settings

        settings = Settings()

        # Check required fields
        required = {
            "openrouter_api_key": settings.openrouter_api_key,
            "telegram_bot_token": settings.telegram_bot_token,
            "telegram_user_id": settings.telegram_user_id,
            "web_auth_token": settings.web_auth_token,
            "postgres_password": settings.postgres_password,
        }

        for key, value in required.items():
            if not value or value == "your-key-here" or value == "your-password-here":
                print(f"  ❌ {key.upper()} not set or using example value")
                return False

        print("  ✅ All required environment variables set")
        print(f"     - OpenRouter API: {settings.openrouter_api_key[:10]}...")
        print(f"     - Telegram bot token: {settings.telegram_bot_token[:10]}...")
        print(f"     - Telegram user ID: {settings.telegram_user_id}")
        print(f"     - Web auth token: {settings.web_auth_token[:10]}...")
        return True

    except Exception as e:
        print(f"  ❌ Environment validation failed: {e}")
        print("     Make sure .env file exists and is properly formatted")
        return False


def validate_providers_config():
    """Validate config/providers.yaml"""
    print("\n2️⃣  Validating providers config...")

    config_path = Path("config/providers.yaml")

    if not config_path.exists():
        print(f"  ⚠️  File not found: {config_path}")
        print("     This file will be created during development")
        return True  # OK for initial setup

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check structure
        assert "providers" in config, "Missing 'providers' section"
        assert "openrouter" in config["providers"], "Missing OpenRouter provider"
        assert "fallback_chain" in config, "Missing 'fallback_chain'"
        assert "cheap_models" in config, "Missing 'cheap_models'"

        # Check providers have required fields
        for name, provider in config["providers"].items():
            assert "base_url" in provider, f"Provider {name}: missing base_url"
            assert "models" in provider, f"Provider {name}: missing models"
            assert len(provider["models"]) > 0, f"Provider {name}: no models defined"

        # Check fallback chain
        assert len(config["fallback_chain"]) > 0, "Empty fallback_chain"

        print("  ✅ Providers config valid")
        print(f"     - Providers: {', '.join(config['providers'].keys())}")
        print(f"     - Fallback chain: {len(config['fallback_chain'])} models")
        return True

    except AssertionError as e:
        print(f"  ❌ Providers config invalid: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error reading providers config: {e}")
        return False


def validate_agents_config():
    """Validate agent configs"""
    print("\n3️⃣  Validating agent configs...")

    agents_dir = Path("config/agents")

    if not agents_dir.exists():
        print(f"  ⚠️  Directory not found: {agents_dir}")
        print("     This will be created during development")
        return True

    yaml_files = list(agents_dir.glob("*.yaml"))

    if len(yaml_files) == 0:
        print(f"  ⚠️  No agent configs found in {agents_dir}")
        print("     This is OK for initial setup")
        return True

    try:
        for yaml_file in yaml_files:
            with open(yaml_file) as f:
                config = yaml.safe_load(f)

            # Check required fields
            assert "agent_id" in config, f"{yaml_file.name}: missing agent_id"
            assert "name" in config, f"{yaml_file.name}: missing name"
            assert "llm_settings" in config, f"{yaml_file.name}: missing llm_settings"
            assert "skills" in config, f"{yaml_file.name}: missing skills"
            assert "instructions" in config, f"{yaml_file.name}: missing instructions"

            print(f"  ✅ Agent config valid: {config['agent_id']}")

        return True

    except AssertionError as e:
        print(f"  ❌ Agent config invalid: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error reading agent config: {e}")
        return False


def validate_skills_config():
    """Validate skill configs"""
    print("\n4️⃣  Validating skills configs...")

    skills_dir = Path("config/skills")

    if not skills_dir.exists():
        print(f"  ⚠️  Directory not found: {skills_dir}")
        print("     This will be created during development")
        return True

    yaml_files = list(skills_dir.glob("*.yaml"))

    if len(yaml_files) == 0:
        print("  ⚠️  No skill configs found")
        print("     This is OK for initial setup")
        return True

    try:
        for yaml_file in yaml_files:
            with open(yaml_file) as f:
                config = yaml.safe_load(f)

            # Check required fields
            assert "name" in config, f"{yaml_file.name}: missing name"
            assert "description" in config, f"{yaml_file.name}: missing description"
            assert "parameters" in config, f"{yaml_file.name}: missing parameters"
            assert "implementation" in config, f"{yaml_file.name}: missing implementation"

        print(f"  ✅ Skills config valid: {len(yaml_files)} skills found")
        return True

    except AssertionError as e:
        print(f"  ❌ Skills config invalid: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error reading skills config: {e}")
        return False


def validate_directories():
    """Validate required directories exist"""
    print("\n5️⃣  Validating directory structure...")

    required_dirs = [
        "config",
        "data/logs",
        "data/coder_output",
        "scripts",
        "docs",
        "shared",
    ]

    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  ✅ {dir_path}")
        else:
            print(f"  ❌ {dir_path} - missing")
            all_exist = False

    return all_exist


def validate_dependencies():
    """Check that key Python packages are installed"""
    print("\n6️⃣  Checking Python dependencies...")

    packages = [
        "fastapi",
        "pydantic",
        "httpx",
        "asyncpg",
        "redis",
        "qdrant_client",
        "yaml",
    ]

    all_installed = True
    for package in packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - not installed")
            all_installed = False

    if not all_installed:
        print("\n  Install dependencies with:")
        print("    pip install -e .[dev]")

    return all_installed


def check_docker():
    """Check if Docker is available"""
    print("\n7️⃣  Checking Docker...")

    import subprocess

    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            print("  ✅ Docker is available")
            return True
        else:
            print("  ❌ Docker command failed")
            return False

    except FileNotFoundError:
        print("  ❌ Docker not installed")
        return False
    except Exception as e:
        print(f"  ❌ Docker check failed: {e}")
        return False


def main():
    """Main validation function"""

    print("=" * 60)
    print("Balbes Multi-Agent System - Configuration Validation")
    print("=" * 60)
    print()

    results = []

    # Run all validations
    results.append(("Environment", validate_env()))
    results.append(("Directories", validate_directories()))
    results.append(("Dependencies", validate_dependencies()))
    results.append(("Docker", check_docker()))
    results.append(("Providers Config", validate_providers_config()))
    results.append(("Agents Config", validate_agents_config()))
    results.append(("Skills Config", validate_skills_config()))

    # Summary
    print()
    print("=" * 60)
    print("Validation Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}")

    print()

    if all(result[1] for result in results):
        print("✅ All validations passed!")
        print()
        print("Ready to start development:")
        print("  make setup     # First time setup")
        print("  make dev-*     # Start individual services")
        print()
        sys.exit(0)
    else:
        print("❌ Some validations failed!")
        print()
        print("Please fix the issues above before proceeding.")
        print()
        print("Common fixes:")
        print("  - Copy .env.example to .env and fill in values")
        print("  - Run: pip install -e .[dev]")
        print("  - Run: make infra-up")
        print()
        sys.exit(1)


if __name__ == "__main__":
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    main()
