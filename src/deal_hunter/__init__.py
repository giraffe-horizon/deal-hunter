"""Deal Hunter — universal multi-source deal monitor."""

import contextlib
import importlib.metadata

__version__ = "0.15.3"  # maintained by semantic-release
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("deal-hunter")
