"""
AMAA v0.4 - Configuration Manager
설정 관리 모듈
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class OllamaConfig:
    """Ollama 설정"""
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    vision_model: str = "llava"
    timeout: int = 60
    max_retries: int = 3


@dataclass
class NamingConfig:
    """파일 명명 규칙 설정"""
    date_prefix: bool = True
    date_format: str = "%Y-%m-%d"
    separator: str = "_"
    lowercase: bool = False
    max_length: int = 255


@dataclass
class SafetyConfig:
    """안전 설정"""
    dry_run_default: bool = True
    confirm_before_execute: bool = True
    max_files_per_batch: int = 100
    backup_before_move: bool = True
    preserve_timestamps: bool = True


@dataclass
class UndoConfig:
    """Undo 시스템 설정"""
    enabled: bool = True
    max_history: int = 1000
    retention_days: int = 30


@dataclass
class DLPConfig:
    """DLP (Data Loss Prevention) 설정"""
    enabled: bool = True
    keywords: list = field(default_factory=lambda: [
        "기밀", "confidential", "secret", "private",
        "password", "비밀번호", "개인정보", "주민등록번호"
    ])
    action: str = "tag"  # tag, quarantine, alert, block
    quarantine_path: str = "~/.amaa/quarantine"


@dataclass
class PerformanceConfig:
    """성능 설정"""
    parallel_workers: int = 4
    chunk_size: int = 1000
    cache_enabled: bool = True
    cache_ttl: int = 3600


@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = "INFO"
    file: str = "~/.amaa/logs/amaa.log"
    max_size: str = "10MB"
    backup_count: int = 5


@dataclass  
class StorageConfig:
    """저장소 설정"""
    database_path: str = "~/.amaa/amaa.db"
    index_path: str = "~/.amaa/index"
    config_path: str = "~/.amaa/config"


class Config:
    """
    AMAA 설정 관리자 (Singleton)
    
    Usage:
        config = Config.load("config.yaml")
        print(config.ollama.model)
    """
    
    _instance: Optional['Config'] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: Optional[str] = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._initialized = True
        self._config_path = config_path
        self._raw_config: dict = {}
        
        # Initialize with defaults
        self.ollama = OllamaConfig()
        self.naming = NamingConfig()
        self.safety = SafetyConfig()
        self.undo = UndoConfig()
        self.dlp = DLPConfig()
        self.performance = PerformanceConfig()
        self.logging = LoggingConfig()
        self.storage = StorageConfig()
        
        # File type configurations
        self.file_types: dict = {}
        self.exclude: dict = {}
        
        if config_path:
            self.load(config_path)
    
    @classmethod
    def load(cls, config_path: str) -> 'Config':
        """설정 파일 로드"""
        instance = cls(config_path)
        
        path = Path(config_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)
        
        instance._raw_config = raw
        amaa_config = raw.get('amaa', {})
        
        # Load each section
        if 'ollama' in amaa_config:
            instance.ollama = OllamaConfig(**amaa_config['ollama'])
        
        if 'naming' in amaa_config:
            instance.naming = NamingConfig(**amaa_config['naming'])
        
        if 'safety' in amaa_config:
            instance.safety = SafetyConfig(**amaa_config['safety'])
        
        if 'undo' in amaa_config:
            instance.undo = UndoConfig(**amaa_config['undo'])
        
        if 'dlp' in amaa_config:
            instance.dlp = DLPConfig(**amaa_config['dlp'])
        
        if 'performance' in amaa_config:
            instance.performance = PerformanceConfig(**amaa_config['performance'])
        
        if 'logging' in amaa_config:
            instance.logging = LoggingConfig(**amaa_config['logging'])
        
        if 'storage' in amaa_config:
            instance.storage = StorageConfig(**amaa_config['storage'])
        
        instance.file_types = amaa_config.get('file_types', {})
        instance.exclude = amaa_config.get('exclude', {})
        
        return instance
    
    def save(self, config_path: Optional[str] = None) -> None:
        """설정 파일 저장"""
        path = Path(config_path or self._config_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        config_dict = {
            'amaa': {
                'version': '0.4.0',
                'ollama': self.ollama.__dict__,
                'naming': self.naming.__dict__,
                'safety': self.safety.__dict__,
                'undo': self.undo.__dict__,
                'dlp': self.dlp.__dict__,
                'performance': self.performance.__dict__,
                'logging': self.logging.__dict__,
                'storage': self.storage.__dict__,
                'file_types': self.file_types,
                'exclude': self.exclude,
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """점 표기법으로 설정값 가져오기 (e.g., 'ollama.model')"""
        keys = key.split('.')
        value = self._raw_config.get('amaa', {})
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        
        return value
    
    def expand_path(self, path: str) -> Path:
        """경로 확장 (~, 환경변수 등)"""
        return Path(os.path.expandvars(path)).expanduser().resolve()
    
    @property
    def database_path(self) -> Path:
        """데이터베이스 경로"""
        return self.expand_path(self.storage.database_path)
    
    @property
    def index_path(self) -> Path:
        """인덱스 경로"""
        return self.expand_path(self.storage.index_path)
    
    @property
    def log_path(self) -> Path:
        """로그 파일 경로"""
        return self.expand_path(self.logging.file)
    
    def is_excluded(self, path: Path) -> bool:
        """경로가 제외 대상인지 확인"""
        name = path.name
        
        # 디렉토리 제외
        if path.is_dir() and name in self.exclude.get('directories', []):
            return True
        
        # 파일 제외
        if name in self.exclude.get('files', []):
            return True
        
        # 패턴 제외
        import fnmatch
        for pattern in self.exclude.get('patterns', []):
            if fnmatch.fnmatch(name, pattern):
                return True
        
        return False
    
    def get_file_category(self, path: Path) -> Optional[str]:
        """파일 확장자로 카테고리 결정"""
        ext = path.suffix.lower()
        
        for category, info in self.file_types.items():
            if ext in info.get('extensions', []):
                return category
        
        return None
    
    @classmethod
    def reset(cls) -> None:
        """싱글톤 인스턴스 리셋 (테스트용)"""
        cls._instance = None


def get_default_config() -> Config:
    """기본 설정 반환"""
    config = Config()
    return config


if __name__ == "__main__":
    # Test configuration
    config = Config.load("config.yaml")
    print(f"Ollama Model: {config.ollama.model}")
    print(f"DLP Keywords: {config.dlp.keywords}")
    print(f"Database Path: {config.database_path}")
