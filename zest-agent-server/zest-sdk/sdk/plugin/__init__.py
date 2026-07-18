"""Plugin module for Zest sdk.

This module provides support for loading and managing plugins that bundle
skills, hooks, MCP configurations, agents, and commands together.

It also provides support for plugin marketplaces - directories that list
available plugins with their metadata and source locations.
"""

from sdk.plugin.fetch import (
    PluginFetchError,
    fetch_plugin_with_resolution,
)
from sdk.plugin.loader import load_plugins
from sdk.plugin.plugin import Plugin
from sdk.plugin.types import (
    AgentDefinition,
    CommandDefinition,
    Marketplace,
    MarketplaceMetadata,
    MarketplaceOwner,
    MarketplacePluginEntry,
    MarketplacePluginSource,
    PluginAuthor,
    PluginManifest,
    PluginSource,
    ResolvedPluginSource,
)


__all__ = [
    # Plugin classes
    "Plugin",
    "PluginFetchError",
    "PluginManifest",
    "PluginAuthor",
    "PluginSource",
    "ResolvedPluginSource",
    "AgentDefinition",
    "CommandDefinition",
    # Plugin loading
    "load_plugins",
    "fetch_plugin_with_resolution",
    # Marketplace classes
    "Marketplace",
    "MarketplaceOwner",
    "MarketplacePluginEntry",
    "MarketplacePluginSource",
    "MarketplaceMetadata",
]
