"""Base scoring engine — loads rules from YAML profile."""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Result of scoring a deal."""

    score: int
    plus: list[str] = field(default_factory=list)
    minus: list[str] = field(default_factory=list)
    rejected: bool = False
    reject_reason: str = ""
    breakdown: list[dict] = field(default_factory=list)


class BaseFilter:
    """Generic scoring engine that loads rules from YAML profile config."""

    def __init__(self, profile: dict) -> None:
        self.profile = profile
        self.score_rules: dict = profile.get("score_rules", {})
        self.penalties: dict = profile.get("penalties", {})
        self.budget_min: int = profile.get("budget", {}).get("min", 0)
        self.budget_max: int = profile.get("budget", {}).get("max", 999999)
        self.score_threshold: int = profile.get("score_threshold", 50)
        self.score_threshold_alert: int = profile.get("score_threshold_alert", 100)
        self.required_any: list = profile.get("required_any", [])
        self.excluded_words: list = profile.get("excluded_words", [])

    @staticmethod
    def _match_keyword(keyword: str, text: str) -> bool:
        """Match keyword against text. Supports regex with r/pattern/ syntax."""
        keyword_str = str(keyword)
        if keyword_str.startswith("r/") and keyword_str.endswith("/"):
            pattern = keyword_str[2:-1]
            try:
                return bool(re.search(pattern, text, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")
                return False
        return keyword_str.lower() in text

    @staticmethod
    def _find_match(keyword: str, title: str, description: str) -> tuple[bool, str, str]:
        """Find where keyword matches. Returns (matched, source, match_text).

        source is 'title', 'description', or '' if no match.
        match_text is the actual matched substring.
        """
        keyword_str = str(keyword)
        is_regex = keyword_str.startswith("r/") and keyword_str.endswith("/")

        for field_name, field_text in [("title", title), ("description", description)]:
            text = field_text.lower()
            if is_regex:
                pattern = keyword_str[2:-1]
                try:
                    m = re.search(pattern, text, re.IGNORECASE)
                    if m:
                        return True, field_name, m.group(0)
                except re.error:
                    return False, "", ""
            elif keyword_str.lower() in text:
                return True, field_name, keyword_str.lower()

        return False, "", ""

    def score_deal(self, deal) -> ScoreResult:
        """Score a deal. Returns ScoreResult with score, reasons, and rejection status."""
        result = ScoreResult(score=0)

        # Check excluded words first (hard reject)
        for word in self.excluded_words:
            matched, source, match_text = self._find_match(word, deal.title, deal.description)
            if matched:
                result.rejected = True
                result.reject_reason = f"excluded word: {word}"
                result.breakdown.append(
                    {
                        "rule": str(word),
                        "points": 0,
                        "source": source,
                        "match": match_text,
                        "type": "excluded",
                    }
                )
                return result

        # Check required_any (at least one must match)
        if self.required_any:
            any_matched = False
            matched_rule = ""
            matched_source = ""
            matched_text = ""
            for req in self.required_any:
                found, source, match_text = self._find_match(req, deal.title, deal.description)
                if found:
                    any_matched = True
                    matched_rule = str(req)
                    matched_source = source
                    matched_text = match_text
                    break
            if not any_matched:
                result.rejected = True
                result.reject_reason = "none of required_any matched"
                result.breakdown.append(
                    {
                        "rule": "required_any",
                        "points": 0,
                        "source": "",
                        "match": "",
                        "type": "required_any",
                    }
                )
                return result
            result.breakdown.append(
                {
                    "rule": matched_rule,
                    "points": 0,
                    "source": matched_source,
                    "match": matched_text,
                    "type": "required_any",
                }
            )

        # Positive score rules
        for keyword, points in self.score_rules.items():
            matched, source, match_text = self._find_match(keyword, deal.title, deal.description)
            if matched:
                result.score += points
                result.plus.append(f"+{points} {keyword}")
                match_type = "regex" if str(keyword).startswith("r/") else "keyword"
                result.breakdown.append(
                    {
                        "rule": str(keyword),
                        "points": points,
                        "source": source,
                        "match": match_text,
                        "type": match_type,
                    }
                )

        # Penalties
        for keyword, penalty in self.penalties.items():
            matched, source, match_text = self._find_match(keyword, deal.title, deal.description)
            if matched:
                result.score += penalty  # penalty is negative
                result.minus.append(f"{penalty} {keyword}")
                result.breakdown.append(
                    {
                        "rule": str(keyword),
                        "points": penalty,
                        "source": source,
                        "match": match_text,
                        "type": "penalty",
                    }
                )

        # Budget check
        price = deal.price
        if price > 0:
            if price < self.budget_min:
                result.score -= 20
                result.minus.append(f"-20 too cheap ({price} PLN)")
                result.breakdown.append(
                    {
                        "rule": "budget",
                        "points": -20,
                        "source": "price",
                        "match": f"{price} PLN (min: {self.budget_min})",
                        "type": "budget",
                    }
                )
            elif price > self.budget_max:
                result.score -= 30
                result.minus.append(f"-30 too expensive ({price} PLN)")
                result.breakdown.append(
                    {
                        "rule": "budget",
                        "points": -30,
                        "source": "price",
                        "match": f"{price} PLN (max: {self.budget_max})",
                        "type": "budget",
                    }
                )
            else:
                result.score += 5
                result.plus.append(f"+5 in budget ({price} PLN)")
                result.breakdown.append(
                    {
                        "rule": "budget",
                        "points": 5,
                        "source": "price",
                        "match": f"{price} PLN",
                        "type": "budget",
                    }
                )

        # Temperature bonus (Pepper social proof)
        temp = deal.temperature
        if temp >= 100:
            result.score += 10
            result.plus.append(f"+10 hot deal ({temp}\u00b0)")
            result.breakdown.append(
                {
                    "rule": "temperature",
                    "points": 10,
                    "source": "temperature",
                    "match": f"{temp}\u00b0",
                    "type": "temperature",
                }
            )
        elif temp >= 50:
            result.score += 5
            result.plus.append(f"+5 warm deal ({temp}\u00b0)")
            result.breakdown.append(
                {
                    "rule": "temperature",
                    "points": 5,
                    "source": "temperature",
                    "match": f"{temp}\u00b0",
                    "type": "temperature",
                }
            )
        elif temp < -10:
            result.score -= 10
            result.minus.append(f"-10 cold deal ({temp}\u00b0)")
            result.breakdown.append(
                {
                    "rule": "temperature",
                    "points": -10,
                    "source": "temperature",
                    "match": f"{temp}\u00b0",
                    "type": "temperature",
                }
            )

        # No publication date + cold = suspicious
        if not deal.published_at and temp < 0:
            result.score -= 15
            result.minus.append(f"-15 no date + cold deal ({temp}\u00b0)")
            result.breakdown.append(
                {
                    "rule": "no_date_cold",
                    "points": -15,
                    "source": "metadata",
                    "match": f"no date + {temp}\u00b0",
                    "type": "penalty",
                }
            )

        return result
