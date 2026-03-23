from .base import BaseFilter
from .bike_filter import BikeFilter

FILTER_REGISTRY = {
    "bike_filter.BikeFilter": BikeFilter,
}
