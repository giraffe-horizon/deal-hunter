# Scoring Engine

Deal Hunter uses a points-based scoring system to rank deals. Every deal gets a score, and the score determines the alert tier.

## How Scoring Works

```
Deal arrives from source
        ↓
1. Excluded words check     → REJECT (score = 0, deal dropped)
        ↓
2. Required any check       → REJECT if none match
        ↓
3. Score rules              → +points per keyword match
        ↓
4. Penalties                → -points per keyword match
        ↓
5. Budget check             → +5 (in range), -20 (too cheap), -30 (too expensive)
        ↓
6. Temperature (Pepper only) → +10 (≥100°), +5 (≥50°), -10 (<-10°)
        ↓
Final score → alert tier
```

## Alert Tiers

| Tier | Emoji | Default Threshold | Meaning |
|------|-------|-------------------|---------|
| Hot | 🔥 | 30+ | Drop everything, this is a great deal |
| Good | ✅ | 15-29 | Solid deal, worth checking out |
| Meh | 💤 | 0-14 | Borderline, included for completeness |
| Dropped | — | <0 | Not shown, not notified |

Thresholds are configurable per profile.

## Keyword Matching

Keywords are matched against `title + description` (case-insensitive).

### Plain keywords
```yaml
"sony wh-1000xm5": 20    # exact substring match
"bluetooth": 5             # matches anywhere in text
```

### Regex keywords
Prefix with `r/` and suffix with `/`:
```yaml
"r/\\bwh-?1000xm[45]\\b/": 20     # word boundary match
"r/\\b(xl|58|59)\\b/": 10          # match any of these sizes
"r/gravel|cx|cyclocross/": 8       # match any bike type
```

Regex runs with `re.IGNORECASE`.

## Budget Scoring

| Condition | Points | Logic |
|-----------|--------|-------|
| In budget (min ≤ price ≤ max) | +5 | Sweet spot |
| Below min | -20 | Probably junk or incomplete |
| Above max | -30 | Over budget |
| Price unknown (0) | 0 | No budget scoring applied |

## Temperature Scoring (Pepper only)

Pepper.pl has community voting that produces a "temperature" per deal:

| Temperature | Points | Meaning |
|-------------|--------|---------|
| ≥ 100° | +10 | Community-validated hot deal |
| ≥ 50° | +5 | Warm — decent interest |
| ≥ 0° | 0 | Neutral |
| < -10° | -10 | Community thinks it's bad |

## Custom Filters

For domain-specific scoring (e.g., bikes), create a custom filter class:

```python
class BikeFilter(BaseFilter):
    def score_deal(self, deal):
        result = super().score_deal(deal)  # base scoring first
        if result.rejected:
            return result
        # Add custom logic
        if "preferred_size" in deal.title:
            result.score += 15
            result.plus.append("+15 preferred size")
        return result
```

Enable in profile:
```yaml
custom_filter: "bike_filter.BikeFilter"
custom_data:
  preferred_sizes: ["XL", "58"]
```

## Score Breakdown

Use `--verify` to see the full breakdown:

```
🔥 [HOT] Sony WH-1000XM5 — 599 PLN (score: 45)
  + sony: +15
  + wh-1000xm5: +20
  + anc: +10
  + in budget: +5
  - used: -5
```

This helps you tune your `score_rules` and `penalties` for optimal results.
