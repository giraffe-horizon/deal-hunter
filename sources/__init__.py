from .base import Deal, Source
from .pepper import PepperSource
from .ceneo import CeneoSource
from .proshop import ProshopSource

SOURCE_REGISTRY = {
    "pepper": PepperSource,
    "ceneo": CeneoSource,
    "proshop": ProshopSource,
}
