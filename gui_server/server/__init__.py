"""
AegisVision AI Trading Server Package (GUI version)
"""

from .trading_server import create_app
from .data import *

__version__ = "1.0.0"
__all__ = ['create_app']