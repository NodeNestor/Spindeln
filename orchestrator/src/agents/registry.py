"""Agent registry — discover and instantiate agents by name or category."""

from __future__ import annotations

import logging
from typing import Type

from src.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type[BaseAgent]] = {}


def register_agent(name: str):
    """Decorator: register an agent class under a name.

    Usage:
        @register_agent("ratsit")
        class RatsitAgent(BaseAgent):
            ...
    """
    def wrapper(cls: Type[BaseAgent]) -> Type[BaseAgent]:
        _REGISTRY[name] = cls
        logger.debug("Registered agent: %s", name)
        return cls
    return wrapper


def get_agent(name: str) -> BaseAgent:
    """Instantiate an agent by name."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown agent: {name}. Available: {list(_REGISTRY.keys())}")
    return cls()


def get_all_agents() -> list[BaseAgent]:
    """Instantiate all registered agents."""
    return [cls() for cls in _REGISTRY.values()]


def get_agents_by_category(category: str) -> list[BaseAgent]:
    """Get agents whose module path contains a category name.

    Categories: public_records, social_media, breach, web, analysis
    """
    results = []
    for name, cls in _REGISTRY.items():
        module = cls.__module__ or ""
        if category in module:
            results.append(cls())
    return results


def list_agents() -> list[dict]:
    """List all registered agents with metadata."""
    return [
        {
            "name": name,
            "source_type": cls().source_type.value if hasattr(cls(), "source_type") else "",
            "description": cls().description if hasattr(cls(), "description") else "",
            "module": cls.__module__ or "",
        }
        for name, cls in _REGISTRY.items()
    ]


def agent_names() -> list[str]:
    """List all registered agent names."""
    return list(_REGISTRY.keys())
