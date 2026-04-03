# FAQ

## General

### How often should I run Deal Hunter?
Every 15-30 minutes is a good balance. More frequent = more API calls to target sites (risk of being blocked). Less frequent = might miss time-limited deals.

### Does it work outside Poland?
Yes! The generic web scraper and YAML store system work with any website. The built-in Polish stores (Pepper.pl, Ceneo.pl, etc.) are just included batteries. See [Adding a Store](Adding-a-Store.md).

### Can I monitor multiple products?
Yes — create one profile per product/category. Run all with `--all` or individually with `--profile name`.

### Will I get duplicate notifications?
No. Deal Hunter tracks seen deals in `state/*.json` (14-day memory). A deal is only notified once, unless its price changes.

## Profiles

### My profile finds no deals
1. Run `--validate` to check for YAML errors
2. Run `--verify` to see raw results before scoring
3. Check `excluded_words` — are you accidentally filtering everything?
4. Check `required_any` — too restrictive?
5. Check source URLs/queries — do they return results in a browser?

### How do I find my Telegram topic_id?
1. Right-click the topic message in Telegram desktop
2. Click "Copy Message Link"
3. The URL is like `https://t.me/c/CHAT_ID/TOPIC_ID/MESSAGE_ID`
4. The `TOPIC_ID` number is what you need

### What's the difference between excluded_words and penalties?
- `excluded_words` → **hard reject** — deal is completely dropped, never shown
- `penalties` → **soft penalty** — deal loses points but may still appear if other scores are high enough

Use `excluded_words` for things you absolutely never want (e.g., "replacement parts"). Use `penalties` for things you'd rather avoid but might accept at a great price.

### How do regex keywords work?
Wrap in `r/` and `/`:
```yaml
"r/\\bkeyword\\b/": 10    # \\b = word boundary
"r/size-(xl|xxl)/": 15    # alternation
"r/\\d{2}cm/": 5          # digit patterns
```
Always case-insensitive. Test your regex at regex101.com first.

## Sources & Stores

### What's the difference between stores/ and sources/?
- `stores/*.yaml` — **declarative** store definitions (most stores)
- `sources/*.py` — **Python** source plugins (only for complex scraping like Pepper's Vue3)

Both appear identically in profiles. You don't need to care which is which when creating profiles.

### A store stopped finding deals
Website probably changed their HTML structure. Options:
1. Open the store URL in Chrome → Inspect → find new CSS selectors
2. Update the YAML file in `stores/`
3. Try adding `json-ld` to strategies — it's more resilient to layout changes

### Can I add a store that requires login?
Not directly — Deal Hunter doesn't manage authentication. Workarounds:
- Some stores show prices without login (just restricted features)
- You could add cookies to the request headers in a custom Python source

## Docker

### Container starts but no notifications
1. Check `.env` is properly mounted: `docker-compose exec deal-hunter cat /app/.env`
2. Check logs: `docker-compose logs -f`
3. Check state directory has write permissions

### How do I add a profile to a running container?
Just put the YAML file in your local `profiles/` directory. The volume mount makes it instantly available. Next cron run will pick it up.

### Changing cron schedule
Edit `docker-compose.yml` → `CRON_SCHEDULE`, then:
```bash
docker-compose down && docker-compose up -d
```

## Troubleshooting

### "Rate limited" / "HTTP 429" in logs
You're scanning too frequently. Increase cron interval or reduce the number of URLs per source.

### "State file corrupted" warning
The state file got damaged (disk full, power loss). Deal Hunter auto-resets it — you'll get re-notifications for already-seen deals once.

### High memory usage
Large category pages with 100+ products can use more RAM during HTML parsing. This is normal and temporary (freed after each source).
