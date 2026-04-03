"""Source registry — deal fetching plugins.

Python sources (pepper, web) are registered explicitly.
YAML store definitions in stores/*.yaml are auto-discovered and registered,
taking priority over any Python source with the same name.
"""

import logging

from .base import Deal, Source
from .pepper import PepperSource
from .web import WebSource
from .yaml_source import YamlSource, load_all_store_definitions, make_yaml_source_class

logger = logging.getLogger(__name__)

__all__ = [
    "Deal",
    "Source",
    "PepperSource",
    "WebSource",
    "YamlSource",
    "SOURCE_REGISTRY",
]

# Python-only sources
SOURCE_REGISTRY: dict[str, type[Source]] = {
    "pepper": PepperSource,
    "web": WebSource,
}

# Auto-discover YAML store definitions — YAML wins over Python for same name
for _name, _store_def in load_all_store_definitions().items():
    SOURCE_REGISTRY[_name] = make_yaml_source_class(_store_def)
    logger.debug(f"Registered YAML store: {_name}")
