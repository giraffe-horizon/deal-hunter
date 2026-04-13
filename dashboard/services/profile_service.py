"""Profile management service for dashboard."""

import html as _html
import logging
import subprocess
from pathlib import Path

import yaml

from services.profile_manager import ProfileManager
from utils.validation import validate_profile

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent


class ProfileService:
    """Profile CRUD operations for dashboard routes."""

    def __init__(self, profile_mgr: ProfileManager) -> None:
        self.profile_mgr = profile_mgr

    def get_profile_summaries(self) -> list[dict]:
        """Get summary data for all profiles (for listing pages)."""
        summaries = []
        for name in self.profile_mgr.list_all():
            prof = self.profile_mgr.load(name)
            if prof:
                summaries.append(
                    {
                        "name": name,
                        "emoji": prof.get("emoji", "\U0001f50d"),
                        "enabled": prof.get("enabled", True),
                        "source_count": len(prof.get("sources", {})),
                        "budget_min": prof.get("budget", {}).get("min", 0),
                        "budget_max": prof.get("budget", {}).get("max", 0),
                        "score_threshold": prof.get("score_threshold", 0),
                    }
                )
        return summaries

    def save_yaml_text(self, profile_path: Path, yaml_text: str) -> list[str]:
        """Parse and validate raw YAML text, save if valid. Returns list of errors."""
        try:
            profile = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"YAML parse error: {e}"]

        if not isinstance(profile, dict):
            return ["YAML must be a mapping (dict)"]

        errors = validate_profile(profile)
        if errors:
            return errors

        with profile_path.open("w", encoding="utf-8") as f:
            f.write(yaml_text)
        return []

    def save_profile_dict(self, profile_path: Path, data: dict) -> list[str]:
        """Validate and save a profile dict as YAML. Returns list of errors."""
        errors = validate_profile(data)
        if errors:
            return errors

        with profile_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return []

    def toggle_enabled(self, profile_path: Path) -> bool:
        """Toggle profile enabled state. Returns new enabled state."""
        with profile_path.open(encoding="utf-8") as f:
            profile = yaml.safe_load(f)

        profile["enabled"] = not profile.get("enabled", True)

        with profile_path.open("w", encoding="utf-8") as f:
            yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        return profile["enabled"]

    def run_verify(self, name: str) -> str:
        """Run a profile with --verify and return HTML-safe output."""
        try:
            result = subprocess.run(  # noqa: S603, S607
                ["python", "deal_hunter.py", "--profile", name, "--verify"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(BASE_DIR),
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            output = "Run timed out after 120 seconds."
        except Exception as e:
            output = f"Error: {e}"

        return _html.escape(output)
