# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-03

### Added

- Multi-source deal scanning: Pepper.pl, Ceneo.pl, Proshop.pl, and generic web scraper (CSS selectors)
- 5 additional source plugins: Canyon, Rowertour, Veloshop, Centrumrowerowe, Sprint-Rowery
- YAML-driven scoring engine with keyword rules, penalties, budget checks, and regex support
- Custom filter system (extensible base scorer with domain-specific logic)
- Price tracking with automatic price drop detection across runs
- Telegram alerts with tiered notifications, rate limiting, and retry
- Notion integration with categories from profile
- Profile validation with type checks and sanity checks
- Cross-source deduplication (exact ID + fuzzy title+price matching)
- Graceful degradation (source/notifier failures don't crash the pipeline)
- Example profile (`examples/headphones.yaml`) for quick onboarding
- CI pipeline with linting (ruff), type checking (mypy), and tests (pytest)
- Comprehensive test suite: parser tests with HTML fixtures, state management, dedup, scoring
