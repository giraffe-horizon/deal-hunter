"""Profile loading, listing, validation, and path safety."""

import re
from pathlib import Path

import yaml

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class ProfileManager:
    """Unified profile management for CLI and dashboard."""

    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = profiles_dir

    def list_all(self, include_disabled: bool = True) -> list[str]:
        """List available profile names."""
        if not self.profiles_dir.exists():
            return []
        names: list[str] = []
        for p in sorted(self.profiles_dir.glob("*.yaml")):
            if not include_disabled:
                data = self._read_yaml(p)
                if data and not data.get("enabled", True):
                    continue
            names.append(p.stem)
        return names

    def load(self, name: str) -> dict | None:
        """Load a profile by name. Returns None if not found or invalid."""
        path = self.safe_path(name)
        if path is None or not path.exists():
            return None
        return self._read_yaml(path)

    def safe_path(self, name: str) -> Path | None:
        """Validate name and return resolved path, or None if invalid."""
        if not _PROFILE_NAME_RE.match(name):
            return None
        path = (self.profiles_dir / f"{name}.yaml").resolve()
        if not path.is_relative_to(self.profiles_dir.resolve()):
            return None
        return path

    def validate(self, profile: dict) -> list[str]:
        """Validate a profile dict. Returns list of error messages."""
        from utils.validation import validate_profile

        return validate_profile(profile)

    def _read_yaml(self, path: Path) -> dict | None:
        """Read a YAML file safely."""
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return dict(data) if data else None
        except (yaml.YAMLError, OSError):
            return None
