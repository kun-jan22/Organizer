"""
AMAA v0.4 - Autonomous Multi-Agent Architecture
자율형 파일 조직화 시스템 (100% 오픈소스)

Usage:
    # CLI
    python -m amaa scan ~/Downloads
    python -m amaa preview ~/Downloads
    python -m amaa execute ~/Downloads
    
    # Python API
    from amaa import Orchestrator
    orch = Orchestrator()
    results = orch.scan_and_analyze("/path/to/folder")
"""

__version__ = "0.4.0"
__author__ = "kun-jan22"

# Core exports
from .core.config import Config, get_default_config
from .core.mapmaker import MapMaker
from .core.perceiver import Perceiver, OllamaClient
from .core.orchestrator import Orchestrator
from .core.undo import UndoManager

# Agent exports
from .agents.watcher import WatcherAgent
from .agents.analyzer import AnalyzerAgent
from .agents.organizer import OrganizerAgent
from .agents.reviewer import ReviewerAgent

# Security exports
from .security.dlp import DLPScanner
from .security.permissions import PermissionChecker

# Storage exports
from .storage.database import Database
from .storage.indexer import FileIndexer

__all__ = [
    # Version
    "__version__",
    # Core
    "Config",
    
     
    "get_default_config",
    "MapMaker",
    "Perceiver",
    "OllamaClient",
    "Orchestrator",
    "UndoManager",
    # Agents
    "WatcherAgent",
    "AnalyzerAgent",
    "OrganizerAgent",
    "ReviewerAgent",
    # Security
    "DLPScanner",
    "PermissionChecker",
    # Storage
    "Database",
    "FileIndexer",
]
