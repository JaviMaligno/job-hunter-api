"""Blocker detection and handling for browser automation."""

from src.automation.blockers.detector import BlockerDetector, DetectedBlocker
from src.automation.blockers.handler import BlockerHandler, BlockerResolution

__all__ = [
    "BlockerDetector",
    "BlockerHandler",
    "BlockerResolution",
    "DetectedBlocker",
]
