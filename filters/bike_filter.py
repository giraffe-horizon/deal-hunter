"""Bike-specific filter — extends BaseFilter with size, color, tire, race logic."""

import logging
import re

from .base import BaseFilter, ScoreResult

logger = logging.getLogger(__name__)


class BikeFilter(BaseFilter):
    """Extended scoring for bikes: sizes, colors, tire widths, race keywords."""

    def __init__(self, profile: dict) -> None:
        super().__init__(profile)
        custom = profile.get("custom_data", {})
        self.brand_sizes: dict = custom.get("brand_sizes", {})
        self.generic_good_sizes: list = custom.get("generic_good_sizes", [])
        self.excluded_colors: list = custom.get("excluded_colors", [])
        self.race_keywords: list = custom.get("race_keywords", [])

    def score_deal(self, deal) -> ScoreResult:
        """Score a bike deal with additional bike-specific checks."""
        text = (deal.title + " " + deal.description).lower()

        # Pre-filter: wrong size -> reject
        size_result = self._check_size(text)
        if size_result == "wrong":
            result = ScoreResult(score=0, rejected=True, reject_reason="wrong size")
            result.breakdown.append({
                "rule": "size", "points": 0, "source": "title",
                "match": "wrong size", "type": "size",
            })
            return result

        # Run base scoring
        result = super().score_deal(deal)
        if result.rejected:
            return result

        # Size scoring
        if size_result == "good":
            result.score += 10
            result.plus.append("+10 good size")
            result.breakdown.append({
                "rule": "size", "points": 10, "source": "title",
                "match": "good size", "type": "size",
            })
        elif size_result == "unknown":
            result.score -= 30
            result.minus.append("-30 no size info")
            result.breakdown.append({
                "rule": "size", "points": -30, "source": "title",
                "match": "no size info", "type": "size",
            })

        # Color exclusion
        for color in self.excluded_colors:
            if color.lower() in text:
                color_source = "title" if color.lower() in deal.title.lower() else "description"
                result.score -= 100
                result.minus.append(f"-100 color {color}")
                result.breakdown.append({
                    "rule": f"color:{color}", "points": -100, "source": color_source,
                    "match": color.lower(), "type": "color",
                })

        # Tire width scoring
        tire_match = re.search(r"(\d{2})\s*(?:mm|c)\b", text)
        if tire_match:
            tire_width = int(tire_match.group(1))
            if 38 <= tire_width <= 50:
                result.score += 20
                result.plus.append(f"+20 tire {tire_width}mm (ideal)")
                result.breakdown.append({
                    "rule": "tire_width", "points": 20, "source": "title",
                    "match": f"{tire_width}mm (ideal)", "type": "tire",
                })
            elif 32 <= tire_width <= 37:
                result.score += 10
                result.plus.append(f"+10 tire {tire_width}mm (OK)")
                result.breakdown.append({
                    "rule": "tire_width", "points": 10, "source": "title",
                    "match": f"{tire_width}mm (OK)", "type": "tire",
                })
            elif 23 <= tire_width <= 27:
                result.score -= 10
                result.minus.append(f"-10 narrow tire {tire_width}mm")
                result.breakdown.append({
                    "rule": "tire_width", "points": -10, "source": "title",
                    "match": f"{tire_width}mm (narrow)", "type": "tire",
                })

        # Race keywords penalty
        race_count = sum(1 for kw in self.race_keywords if kw.lower() in text)
        if race_count > 0:
            penalty = race_count * -15
            result.score += penalty
            result.minus.append(f"{penalty} race keywords (x{race_count})")
            result.breakdown.append({
                "rule": "race_keywords", "points": penalty, "source": "title",
                "match": f"x{race_count} race keywords", "type": "race",
            })

        return result

    def _check_size(self, text: str) -> str:
        """Check if size fits. Returns 'good', 'wrong', or 'unknown'."""
        size_patterns = [
            r"(?:rozm(?:iar)?|size|roz\.?|wielko\u015b\u0107)\s*:?\s*(xs|s|m|l|xl|xxl|2xl|\d{2})",
            r"\b(4[89]|5[0-9]|6[0-4])\s*cm\b",
            r"(?:^|[\s,/|(])(xl|xxl|2xl)(?:[\s,/|)]|$)",
            r"(?:^|[\s,/|(])(5[4-9]|6[0-4])(?:[\s,/|)]|$)",
        ]

        found_sizes: set[str] = set()
        for pattern in size_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                found_sizes.add(m.lower().strip())

        if not found_sizes:
            return "unknown"

        # Check per brand
        for brand, target_sizes in self.brand_sizes.items():
            if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE):
                if any(sz in [s.lower() for s in target_sizes] for sz in found_sizes):
                    return "good"
                else:
                    return "wrong"

        # Generic check
        generic_lower = [s.lower() for s in self.generic_good_sizes]
        if any(sz in generic_lower for sz in found_sizes):
            return "good"
        return "wrong"
