from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class PosIntegrationPort(ABC):
    """
    Abstract interface for POS System Integrations (Toast, Square, Clover, etc.)
    
    Arrive delegates all payment processing to the POS. This port defines
    the contract for syncing orders and status between Arrive and the POS.
    """

    @abstractmethod
    def push_order(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push a new Arrive session to the POS system.
        Returns a dict containing at least {"pos_order_id": "..."}
        """
        pass

    @abstractmethod
    def update_order_status(self, pos_order_id: str, status: str) -> bool:
        """
        Notify the POS that an order's status has changed.
        Returns True if successful.
        """
        pass

    @abstractmethod
    def get_menu(self, restaurant_id: str) -> List[Dict[str, Any]]:
        """
        Pull the current menu from the POS system.
        Returns a list of menu items in Arrive's Resource format.
        """
        pass

    @abstractmethod
    def send_tip(self, pos_order_id: str, tip_cents: int) -> bool:
        """
        Forward a tip amount to the POS system (for prepaid orders).
        Returns True if successful.
        """
        pass
