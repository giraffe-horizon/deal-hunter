"""Source registry — deal fetching plugins."""

from .base import Deal, Source
from .ceneo import CeneoSource
from .pepper import PepperSource
from .proshop import ProshopSource
from .web import WebSource

__all__ = [
    "Deal",
    "Source",
    "PepperSource",
    "CeneoSource",
    "ProshopSource",
    "WebSource",
    "SOURCE_REGISTRY",
]

SOURCE_REGISTRY: dict[str, type[Source]] = {
    "pepper": PepperSource,
    "ceneo": CeneoSource,
    "proshop": ProshopSource,
    "web": WebSource,
}
