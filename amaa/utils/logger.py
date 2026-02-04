"""
AMAA v0.4 - Logger
로깅 유틸리티
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class Logger:
    """AMAA 로거"""
    
    EMOJI = {
        'DEBUG': '🔍',
        'INFO': '📝',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }
    
    def __init__(self, name: str = "amaa", 
                 level: str = "INFO",
                 log_file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self._get_formatter(use_emoji=True))
        self.logger.addHandler(console_handler)
        
        # 파일 핸들러
        if log_file:
            log_path = Path(log_file).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(str(log_path), encoding='utf-8')
            file_handler.setFormatter(self._get_formatter(use_emoji=False))
            self.logger.addHandler(file_handler)
    
    def _get_formatter(self, use_emoji: bool = True) -> logging.Formatter:
        if use_emoji:
            return logging.Formatter(
                '%(asctime)s │ %(levelname)-8s │ %(message)s',
                datefmt='%H:%M:%S'
            )
        return logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    def debug(self, msg: str) -> None:
        self.logger.debug(f"{self.EMOJI['DEBUG']} {msg}")
    
    def info(self, msg: str) -> None:
        self.logger.info(f"{self.EMOJI['INFO']} {msg}")
    
    def warning(self, msg: str) -> None:
        self.logger.warning(f"{self.EMOJI['WARNING']} {msg}")
    
    def error(self, msg: str) -> None:
        self.logger.error(f"{self.EMOJI['ERROR']} {msg}")
    
    def critical(self, msg: str) -> None:
        self.logger.critical(f"{self.EMOJI['CRITICAL']} {msg}")
    
    def success(self, msg: str) -> None:
        self.logger.info(f"✅ {msg}")
    
    def progress(self, current: int, total: int, msg: str = "") -> None:
        pct = (current / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        self.logger.info(f"⏳ [{bar}] {pct:.0f}% {msg}")


_default_logger: Optional[Logger] = None


def get_logger(name: str = "amaa", 
               level: str = "INFO",
               log_file: Optional[str] = None) -> Logger:
    """로거 인스턴스 가져오기"""
    global _default_logger
    
    if _default_logger is None:
        _default_logger = Logger(name, level, log_file)
    
    return _default_logger
