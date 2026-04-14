"""Filter registry — scoring engines for deal evaluation."""

from .base import BaseFilter
from .bike_filter import BikeFilter

__all__ = ["BaseFilter", "BikeFilter", "FILTER_REGISTRY"]

FILTER_REGISTRY: dict[str, type[BaseFilter]] = {
    "bike_filter.BikeFilter": BikeFilter,
}
