"""
Message Router module initialization.

Provides message decomposition and reconstruction for the Ternion workflow.
"""

from ternion.router.message_router import MessageRouter
from ternion.router.context import TernionContext

__all__ = ["MessageRouter", "TernionContext"]
