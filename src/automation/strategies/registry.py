"""Registry for ATS strategies."""

import logging
import re
from typing import TypeVar

from src.automation.strategies.base import ATSStrategy

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=ATSStrategy)


class ATSStrategyRegistry:
    """Registry for ATS strategies.

    Provides:
    - Registration of strategy classes via decorator
    - Auto-detection of ATS from URL/content
    - Retrieval of strategy instances by name

    Usage:
        # Register a strategy
        @ATSStrategyRegistry.register
        class BreezyStrategy(ATSStrategy):
            ...

        # Get strategy by name
        strategy = ATSStrategyRegistry.get_strategy("breezy")

        # Auto-detect strategy
        strategy = await ATSStrategyRegistry.detect_ats(page_html, page_url)
    """

    _strategies: dict[str, type[ATSStrategy]] = {}

    @classmethod
    def register(cls, strategy_class: type[T]) -> type[T]:
        """Register a strategy class.

        Use as a decorator:
            @ATSStrategyRegistry.register
            class MyStrategy(ATSStrategy):
                ...

        Args:
            strategy_class: Strategy class to register

        Returns:
            The registered class (for decorator pattern)
        """
        # Create a temporary instance to get the name
        try:
            # For abstract properties, we need to instantiate to get the name
            instance = strategy_class()
            name = instance.ats_name
        except Exception:
            # Fallback: derive name from class name
            name = strategy_class.__name__.lower().replace("strategy", "")

        cls._strategies[name] = strategy_class
        logger.info(f"Registered ATS strategy: {name}")
        return strategy_class

    @classmethod
    def get_strategy(cls, ats_name: str) -> ATSStrategy | None:
        """Get strategy instance by name.

        Args:
            ats_name: ATS identifier (e.g., 'breezy', 'workable')

        Returns:
            ATSStrategy instance or None if not found
        """
        strategy_class = cls._strategies.get(ats_name.lower())
        if strategy_class:
            return strategy_class()
        return None

    @classmethod
    async def detect_ats(
        cls,
        page_html: str,
        page_url: str,
    ) -> ATSStrategy | None:
        """Auto-detect ATS from page and return appropriate strategy.

        Tries each registered strategy's detect() method in order.

        Args:
            page_html: Page HTML content
            page_url: Page URL

        Returns:
            Matching ATSStrategy instance or None
        """
        # First, try URL pattern matching (faster)
        for name, strategy_class in cls._strategies.items():
            try:
                instance = strategy_class()
                for pattern in instance.url_patterns:
                    if re.search(pattern, page_url, re.IGNORECASE):
                        logger.info(f"Detected ATS by URL pattern: {name}")
                        return instance
            except Exception as e:
                logger.warning(f"Error checking URL patterns for {name}: {e}")

        # Then, try content-based detection
        for name, strategy_class in cls._strategies.items():
            try:
                instance = strategy_class()
                if await instance.detect(page_html, page_url):
                    logger.info(f"Detected ATS by content: {name}")
                    return instance
            except Exception as e:
                logger.warning(f"Error detecting ATS {name}: {e}")

        # Fall back to generic strategy if registered
        generic = cls.get_strategy("generic")
        if generic:
            logger.info("Using generic strategy (no specific ATS detected)")
            return generic

        logger.warning("No ATS strategy matched - returning None")
        return None

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategy names.

        Returns:
            List of registered strategy names
        """
        return list(cls._strategies.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies (for testing)."""
        cls._strategies.clear()
