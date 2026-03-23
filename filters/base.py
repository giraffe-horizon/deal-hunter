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

    def score_deal(self, deal) -> ScoreResult:
        """Score a deal. Returns ScoreResult with score, reasons, and rejection status."""
        text = (deal.title + " " + deal.description).lower()
        result = ScoreResult(score=0)

        # Check excluded words first (hard reject)
        for word in self.excluded_words:
            if self._match_keyword(word, text):
                result.rejected = True
                result.reject_reason = f"excluded word: {word}"
                return result

        # Check required_any (at least one must match)
        if self.required_any:
            if not any(self._match_keyword(req, text) for req in self.required_any):
                result.rejected = True
                result.reject_reason = "none of required_any matched"
                return result

        # Positive score rules
        for keyword, points in self.score_rules.items():
            if self._match_keyword(keyword, text):
                result.score += points
                result.plus.append(f"+{points} {keyword}")

        # Penalties
        for keyword, penalty in self.penalties.items():
            if self._match_keyword(keyword, text):
                result.score += penalty  # penalty is negative
                result.minus.append(f"{penalty} {keyword}")

        # Budget check
        price = deal.price
        if price > 0:
            if price < self.budget_min:
                result.score -= 20
                result.minus.append(f"-20 too cheap ({price} PLN)")
            elif price > self.budget_max:
                result.score -= 30
                result.minus.append(f"-30 too expensive ({price} PLN)")
            else:
                result.score += 5
                result.plus.append(f"+5 in budget ({price} PLN)")

        # Temperature bonus (Pepper social proof)
        temp = deal.temperature
        if temp >= 100:
            result.score += 10
            result.plus.append(f"+10 hot deal ({temp}\u00b0)")
        elif temp >= 50:
            result.score += 5
            result.plus.append(f"+5 warm deal ({temp}\u00b0)")
        elif temp < -10:
            result.score -= 10
            result.minus.append(f"-10 cold deal ({temp}\u00b0)")

        # No publication date + cold = suspicious
        if not deal.published_at and temp < 0:
            result.score -= 15
            result.minus.append(f"-15 no date + cold deal ({temp}\u00b0)")

        return result
