"""Source registry — deal fetching plugins."""

from .base import Deal, Source
from .canyon import CanyonSource
from .ceneo import CeneoSource
from .centrumrowerowe import CentrumroweroweSource
from .pepper import PepperSource
from .proshop import ProshopSource
from .rowertour import RowertourSource
from .sprint import SprintSource
from .veloshop import VeloshopSource
from .web import WebSource

__all__ = [
    "Deal",
    "Source",
    "PepperSource",
    "CeneoSource",
    "ProshopSource",
    "WebSource",
    "CanyonSource",
    "RowertourSource",
    "VeloshopSource",
    "CentrumroweroweSource",
    "SprintSource",
    "SOURCE_REGISTRY",
]

SOURCE_REGISTRY: dict[str, type[Source]] = {
    "pepper": PepperSource,
    "ceneo": CeneoSource,
    "proshop": ProshopSource,
    "web": WebSource,
    "canyon": CanyonSource,
    "rowertour": RowertourSource,
    "veloshop": VeloshopSource,
    "centrumrowerowe": CentrumroweroweSource,
    "sprint": SprintSource,
}
