# Contributing to CogSol

Thank you for your interest in contributing to CogSol! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Please:

- Be respectful and constructive in discussions
- Welcome newcomers and help them get started
- Focus on the issue, not the person
- Accept constructive criticism gracefully

---

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- A GitHub account

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR-USERNAME/cogsol-framework.git
cd cogsol-framework
```

3. Add the upstream remote:

```bash
git remote add upstream https://github.com/Pyxis-Cognitive-Solutions/cogsol-framework.git
```

---

## Development Setup

### Install in Development Mode

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check CLI works
cogsol-admin

# Run tests
pytest
```

---

## Making Changes

### Create a Branch

Always work on a feature branch, not `main`:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

### Branch Naming Conventions

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements

### Keep Your Branch Updated

```bash
git fetch upstream
git rebase upstream/main
```

---

## Submitting Changes

### Before Submitting

1. **Run tests**: `pytest`
2. **Check formatting**: `black --check .`
3. **Run linter**: `ruff check .`
4. **Type check**: `mypy cogsol`
5. **Update documentation** if needed

### Commit Messages

Follow conventional commit format:

```
type(scope): short description

Longer description if needed.

Fixes #123
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

Examples:
```
feat(agents): add streaming support to BaseAgent
fix(migrate): handle missing remote IDs gracefully
docs(readme): update installation instructions
```

### Pull Request Process

1. Push your branch:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template with:
   - Description of changes
   - Related issues
   - Testing done
   - Screenshots (if UI-related)

4. Wait for review and address feedback

5. Once approved, maintainers will merge

---

## Coding Standards

### Style Guide

- Follow PEP 8
- Use [Black](https://black.readthedocs.io/) for formatting
- Maximum line length: 100 characters
- Use type hints for all public APIs

### Code Quality

```bash
# Format code
black .

# Lint
ruff check . --fix

# Type check
mypy cogsol
```

### Imports

Order imports as:
1. Standard library
2. Third-party packages
3. Local imports

Use `from __future__ import annotations` for modern type hints.

### Docstrings

Use Google-style docstrings:

```python
def function(param1: str, param2: int = 10) -> bool:
    """Short description.

    Longer description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is empty.
    """
```

---

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=cogsol

# Specific file
pytest tests/test_agents.py

# Specific test
pytest tests/test_agents.py::test_base_agent_definition
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names

```python
def test_base_agent_has_default_temperature():
    """BaseAgent should have None as default temperature."""
    agent = BaseAgent()
    assert agent.temperature is None
```

### Test Coverage

Aim for high coverage on:
- Core functionality
- Edge cases
- Error handling

---

## Documentation

### Types of Documentation

1. **Docstrings**: In-code documentation for functions/classes
2. **README.md**: Project overview
3. **docs/**: Detailed guides and references

### Updating Documentation

When adding features:
1. Add docstrings to new code
2. Update relevant docs in `docs/`
3. Update README if it affects basic usage
4. Add to CHANGELOG.md

### Building Docs Locally

Documentation is Markdown-based. Preview with any Markdown viewer or:

```bash
# Using Python's built-in server
cd docs
python -m http.server 8000
```

---

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing issues before creating new ones

Thank you for contributing to CogSol! 🚀
