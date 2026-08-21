# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""可选插件的中立 contracts 与 host registry。"""

from miloco.plugins.contracts import HostPluginContribution
from miloco.plugins.registry import (
    HostPluginRegistry,
    PluginFactory,
    PluginFailure,
    PluginFailureCode,
    PluginLifecycleStage,
    PluginRegistryActivationError,
)

__all__ = [
    "HostPluginContribution",
    "HostPluginRegistry",
    "PluginFactory",
    "PluginFailure",
    "PluginFailureCode",
    "PluginLifecycleStage",
    "PluginRegistryActivationError",
]
