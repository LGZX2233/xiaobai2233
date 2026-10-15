"""P04-owned delivery application services.

``DeliveryService`` is the single door for verification, selection, snapshot
approval, real delivery, reconciliation and task closure.
"""
from .service import (
    CAP_APPROVAL,
    CAP_DELIVERY,
    CAP_DISPATCH,
    CAP_VERIFICATION,
    DeliveryService,
)

__all__ = [
    "DeliveryService",
    "CAP_VERIFICATION",
    "CAP_APPROVAL",
    "CAP_DELIVERY",
    "CAP_DISPATCH",
]
