from abc import ABC, abstractmethod
from typing import Dict, Any

class GeoPort(ABC):
    """
    Abstract interface for Geospatial calculations.
    """

    @abstractmethod
    def calculate_eta_seconds(self, current_lat: float, current_long: float, target_lat: float, target_long: float) -> int:
        """
        Returns estimated seconds to arrival.
        """
        pass
