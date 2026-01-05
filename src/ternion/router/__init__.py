"""
Message Router module initialization.

Provides message decomposition and reconstruction for the Ternion workflow.
"""

from ternion.router.context import TernionContext
from ternion.router.message_router import MessageRouter

__all__ = ["MessageRouter", "TernionContext"]
