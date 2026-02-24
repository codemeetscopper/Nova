from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from nova.core.config import ConfigManager
from nova.core.style import StyleManager
from nova.core.icons import IconManager

_log = logging.getLogger(__name__)

@dataclass
class NovaContext:
    """
    Central context object for Nova, holding core services.
    Replaces the 'QtPop' dependency injection container.
    """
    config: ConfigManager
    style: StyleManager
    icons: IconManager
    data: Any = None # Placeholder if needed for data layer interaction
    
    # Optional helper for logging if app components expect it
    @property
    def log(self):
        return _log
