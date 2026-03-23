# Contributing to Deal Hunter

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/giraffe-horizon/deal-hunter.git
cd deal-hunter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your Telegram bot token and chat ID

# Create a test profile
cp profiles/example.yaml profiles/test.yaml
# Edit profiles/test.yaml

# Verify everything works
python deal_hunter.py --profile test --validate
python deal_hunter.py --profile test --verify
```

## Code Style

- **Python 3.12+** — use modern syntax (type unions with `|`, generic builtins)
- **Type hints** — all function signatures and return types
- **Docstrings** — Google style, English
- **Comments** — English
- **Logging** — use `logging` module, not `print()` (exception: `--verify` mode prints to stdout)
- **Imports** — stdlib → third-party → local, separated by blank lines

### Example

```python
"""Module docstring — one line describing what this module does."""

import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .base import Source, Deal

logger = logging.getLogger(__name__)


class MySource(Source):
    """One-line class description."""

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from this source.

        Args:
            config: Profile source config dict.
        """
        ...
```

## Adding a New Source Plugin

Sources fetch deals from external websites. Each source is a separate class.

### Step by Step

1. **Create the file** — `sources/my_source.py`

2. **Implement the class:**

```python
"""MySource — short description."""

import logging
from .base import Source, Deal

logger = logging.getLogger(__name__)


class MySource(Source):
    """Scrapes deals from MySource."""

    SOURCE_NAME = "my_source"

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals. Config comes from the profile YAML.

        Args:
            config: Source config with 'urls' or 'queries' key.
        """
        urls = config.get("urls", [])
        all_deals = []

        for url in urls:
            html = self._fetch_page(url)  # Built-in rate limiting + retry
            if html:
                deals = self._parse(html)
                all_deals.extend(deals)

        return all_deals

    def _parse(self, html: str) -> list[Deal]:
        # Parse HTML and return Deal objects
        ...
```

3. **Register in `sources/__init__.py`:**

```python
from .my_source import MySource
SOURCE_REGISTRY["my_source"] = MySource
```

4. **Use in a profile:**

```yaml
sources:
  my_source:
    urls:
      - "https://example.com/deals"
```

### Key Guidelines

- Use `self._fetch_page(url)` — handles rate limiting, retry, and headers
- Use `self._rate_limit()` if you make requests manually
- Return `Deal` dataclass instances with `source=self.SOURCE_NAME`
- Generate unique IDs: `f"{self.SOURCE_NAME}:{native_id}"`
- Handle errors gracefully — log and continue, don't crash

## Adding a Custom Filter

Filters score deals beyond what the base keyword engine provides.

### Step by Step

1. **Create the file** — `filters/my_filter.py`

2. **Implement the class:**

```python
"""My custom filter — extends BaseFilter with domain-specific logic."""

import logging
from .base import BaseFilter, ScoreResult

logger = logging.getLogger(__name__)


class MyFilter(BaseFilter):
    """Extended scoring for specific product type."""

    def __init__(self, profile: dict) -> None:
        super().__init__(profile)
        custom = profile.get("custom_data", {})
        self.my_setting = custom.get("my_setting", [])

    def score_deal(self, deal) -> ScoreResult:
        """Score with additional custom logic."""
        # ALWAYS call super first — it handles all base rules
        result = super().score_deal(deal)
        if result.rejected:
            return result

        # Your additional scoring logic
        text = (deal.title + " " + deal.description).lower()
        if "special_keyword" in text:
            result.score += 15
            result.plus.append("+15 special keyword")

        return result
```

3. **Register in `filters/__init__.py`:**

```python
from .my_filter import MyFilter
FILTER_REGISTRY["my_filter.MyFilter"] = MyFilter
```

4. **Use in a profile:**

```yaml
custom_filter: "my_filter.MyFilter"
custom_data:
  my_setting:
    - "value1"
    - "value2"
```

## Creating a Profile

See [docs/creating-profiles.md](docs/creating-profiles.md) for a detailed guide and examples.

Quick version:

```bash
cp profiles/example.yaml profiles/my_product.yaml
# Edit the file, then test:
python deal_hunter.py --profile my_product --validate
python deal_hunter.py --profile my_product --verify
```

## Running Tests and Linting

Before submitting a PR, make sure all checks pass locally:

```bash
source venv/bin/activate

# Install test/lint dependencies
pip install pytest ruff mypy types-requests types-beautifulsoup4 types-PyYAML

# Run unit tests
pytest tests/ -v

# Linting (must pass clean)
ruff check .
ruff format --check .

# Type checking
mypy --ignore-missing-imports deal_hunter.py sources/ filters/ notifiers/ utils/

# Validate profiles
python deal_hunter.py --profile example --validate
```

CI runs all of the above automatically on every push and PR to `main`.

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes — follow the code style above
3. Run tests and linting (see above)
4. Test manually with `--verify` and `--validate`
5. Commit with a descriptive message: `feat:`, `fix:`, `docs:`, `chore:`
6. Open a PR against `main`

## Reporting Issues

When reporting a bug, include:
- Python version (`python --version`)
- OS and version
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
