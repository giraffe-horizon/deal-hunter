# Deal Hunter Wiki

Welcome to the Deal Hunter documentation! Deal Hunter is a universal deal monitoring tool that scans websites, scores offers using smart rules, and sends alerts to Telegram and Notion.

## Quick Navigation

- **[Getting Started](Getting-Started.md)** — Install, configure, and run your first scan
- **[Adding a Store](Adding-a-Store.md)** — Add any website as a source in 5 minutes (YAML, no code)
- **[Creating Profiles](Creating-Profiles.md)** — Define what to search for and how to score it
- **[Scoring Engine](Scoring-Engine.md)** — How deals are scored, ranked, and filtered
- **[Docker Deployment](Docker-Deployment.md)** — Run Deal Hunter as a cron job in Docker
- **[Architecture](Architecture.md)** — Technical overview for contributors
- **[FAQ](FAQ.md)** — Common questions and troubleshooting

## What Can Deal Hunter Do?

| Feature | Description |
|---------|-------------|
| 🌐 Any website | Add stores via YAML — CSS selectors, JSON-LD, or GTM |
| 🇵🇱 Polish sites built-in | Pepper.pl, Ceneo.pl, Proshop.pl + 5 bike shops |
| 🎯 Smart scoring | Keyword matching, regex, budget ranges, temperature |
| 📱 Telegram alerts | Tiered notifications (🔥 hot / ✅ good / 💤 meh) |
| 📋 Notion database | Track deals in a structured database |
| 💰 Price tracking | Detects price drops and increases |
| 🔄 Deduplication | Cross-source dedup by title normalization |
| 🐳 Docker ready | Cron-based deployment with docker-compose |

## Version

Current: **v1.1.0** — [Changelog](../../CHANGELOG.md)
