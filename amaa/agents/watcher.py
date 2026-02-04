"""
AMAA v0.4 - Watcher Agent
파일 시스템 변경 감시 에이전트

Multi-Agent System의 감시 담당
- 새 파일 생성 감지
- 파일 변경 감지
- 실시간 이벤트 큐잉
"""

import time
import queue
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Callable, Set
from dataclasses import dataclass, field
from enum import Enum

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent,
        FileMovedEvent, FileDeletedEvent, DirCreatedEvent
    )
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class FileEventType(Enum):
    """파일 이벤트 타입"""
    CREATED = "created"
    MODIFIED = "modified"
    MOVED = "moved"
    DELETED = "deleted"
    DIR_CREATED = "dir_created"


@dataclass
class FileEvent:
    """파일 이벤트 데이터"""
    event_type: FileEventType
    path: str
    timestamp: str
    old_path: Optional[str] = None  # 이동의 경우 원래 경로
    is_directory: bool = False
    
    def to_dict(self) -> dict:
        return {
            'event_type': self.event_type.value,
            'path': self.path,
            'timestamp': self.timestamp,
            'old_path': self.old_path,
            'is_directory': self.is_directory,
        }


class AMAAEventHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """AMAA 파일 시스템 이벤트 핸들러"""
    
    def __init__(self, event_queue: queue.Queue, 
                 exclude_patterns: Optional[Set[str]] = None):
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self.event_queue = event_queue
        self.exclude_patterns = exclude_patterns or {
            '.git', 'node_modules', '__pycache__', '.DS_Store', 
            'Thumbs.db', '*.tmp', '*.swp', '~$*'
        }
    
    def _should_ignore(self, path: str) -> bool:
        """제외 패턴 확인"""
        p = Path(path)
        name = p.name
        
        for pattern in self.exclude_patterns:
            if pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern or pattern in str(p):
                return True
        
        return False
    
    def _create_event(self, event_type: FileEventType, path: str,
                      old_path: Optional[str] = None,
                      is_directory: bool = False) -> FileEvent:
        """이벤트 객체 생성"""
        return FileEvent(
            event_type=event_type,
            path=path,
            timestamp=datetime.now().isoformat(),
            old_path=old_path,
            is_directory=is_directory
        )
    
    def on_created(self, event):
        if self._should_ignore(event.src_path):
            return
        
        evt_type = FileEventType.DIR_CREATED if event.is_directory else FileEventType.CREATED
        self.event_queue.put(
            self._create_event(evt_type, event.src_path, is_directory=event.is_directory)
        )
    
    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        
        self.event_queue.put(
            self._create_event(FileEventType.MODIFIED, event.src_path)
        )
    
    def on_moved(self, event):
        if self._should_ignore(event.src_path) and self._should_ignore(event.dest_path):
            return
        
        self.event_queue.put(
            self._create_event(
                FileEventType.MOVED, 
                event.dest_path, 
                old_path=event.src_path,
                is_directory=event.is_directory
            )
        )
    
    def on_deleted(self, event):
        if self._should_ignore(event.src_path):
            return
        
        self.event_queue.put(
            self._create_event(
                FileEventType.DELETED, 
                event.src_path,
                is_directory=event.is_directory
            )
        )


class WatcherAgent:
    """
    파일 시스템 감시 에이전트
    
    지정된 디렉토리를 모니터링하고 변경사항을 큐에 추가
    
    Usage:
        watcher = WatcherAgent()
        watcher.add_watch("/path/to/watch")
        watcher.start()
        
        # 이벤트 처리
        while True:
            event = watcher.get_event(timeout=1.0)
            if event:
                process_event(event)
        
        watcher.stop()
    """
    
    def __init__(self, config=None):
        """
        Args:
            config: AMAA Config 객체
        """
        self.config = config
        
        # 이벤트 큐
        self._event_queue: queue.Queue = queue.Queue()
        
        # 감시 대상 경로
        self._watch_paths: Set[str] = set()
        
        # Observer (watchdog)
        self._observer: Optional[Observer] = None
        self._running = False
        
        # 콜백
        self._event_callbacks: List[Callable[[FileEvent], None]] = []
        
        # 제외 패턴
        if config:
            exclude_dirs = set(config.exclude.get('directories', []))
            exclude_files = set(config.exclude.get('files', []))
            exclude_patterns = set(config.exclude.get('patterns', []))
            self._exclude_patterns = exclude_dirs | exclude_files | exclude_patterns
        else:
            self._exclude_patterns = {'.git', 'node_modules', '__pycache__'}
    
    def add_watch(self, path: str, recursive: bool = True) -> bool:
        """
        감시 경로 추가
        
        Args:
            path: 감시할 경로
            recursive: 하위 디렉토리 포함 여부
            
        Returns:
            bool: 성공 여부
        """
        if not WATCHDOG_AVAILABLE:
            print("⚠️ watchdog 패키지가 설치되지 않았습니다. pip install watchdog")
            return False
        
        p = Path(path).expanduser().resolve()
        
        if not p.exists() or not p.is_dir():
            print(f"❌ Invalid path: {path}")
            return False
        
        self._watch_paths.add((str(p), recursive))
        
        # 이미 실행 중이면 즉시 추가
        if self._running and self._observer:
            handler = AMAAEventHandler(self._event_queue, self._exclude_patterns)
            self._observer.schedule(handler, str(p), recursive=recursive)
        
        return True
    
    def remove_watch(self, path: str) -> bool:
        """감시 경로 제거"""
        p = Path(path).expanduser().resolve()
        
        for watched in list(self._watch_paths):
            if watched[0] == str(p):
                self._watch_paths.discard(watched)
                return True
        
        return False
    
    def start(self) -> bool:
        """감시 시작"""
        if not WATCHDOG_AVAILABLE:
            print("⚠️ watchdog 패키지가 필요합니다.")
            return False
        
        if self._running:
            return True
        
        if not self._watch_paths:
            print("⚠️ 감시할 경로가 없습니다. add_watch()를 먼저 호출하세요.")
            return False
        
        self._observer = Observer()
        handler = AMAAEventHandler(self._event_queue, self._exclude_patterns)
        
        for path, recursive in self._watch_paths:
            self._observer.schedule(handler, path, recursive=recursive)
        
        self._observer.start()
        self._running = True
        
        # 콜백 처리 스레드 시작
        if self._event_callbacks:
            self._start_callback_thread()
        
        return True
    
    def stop(self) -> None:
        """감시 중지"""
        self._running = False
        
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
    
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._running
    
    def get_event(self, timeout: Optional[float] = None) -> Optional[FileEvent]:
        """
        이벤트 가져오기 (블로킹)
        
        Args:
            timeout: 타임아웃 (초)
            
        Returns:
            FileEvent: 이벤트 또는 None
        """
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_events(self, max_events: int = 100) -> List[FileEvent]:
        """
        대기 중인 모든 이벤트 가져오기 (논블로킹)
        
        Args:
            max_events: 최대 이벤트 수
            
        Returns:
            List[FileEvent]: 이벤트 목록
        """
        events = []
        
        for _ in range(max_events):
            try:
                event = self._event_queue.get_nowait()
                events.append(event)
            except queue.Empty:
                break
        
        return events
    
    def add_callback(self, callback: Callable[[FileEvent], None]) -> None:
        """
        이벤트 콜백 추가
        
        Args:
            callback: 이벤트 처리 함수
        """
        self._event_callbacks.append(callback)
    
    def _start_callback_thread(self) -> None:
        """콜백 처리 스레드 시작"""
        def callback_worker():
            while self._running:
                event = self.get_event(timeout=0.5)
                if event:
                    for callback in self._event_callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            print(f"Callback error: {e}")
        
        thread = threading.Thread(target=callback_worker, daemon=True)
        thread.start()
    
    def get_pending_count(self) -> int:
        """대기 중인 이벤트 수"""
        return self._event_queue.qsize()
    
    def clear_queue(self) -> int:
        """이벤트 큐 비우기"""
        count = 0
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count


class SimpleWatcher:
    """
    간단한 폴링 기반 감시자 (watchdog 없이 동작)
    
    watchdog을 설치할 수 없는 환경용 폴백
    """
    
    def __init__(self, interval: float = 2.0):
        """
        Args:
            interval: 폴링 간격 (초)
        """
        self.interval = interval
        self._paths: Set[str] = set()
        self._file_states: Dict[str, float] = {}  # path -> mtime
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_queue: queue.Queue = queue.Queue()
    
    def add_watch(self, path: str) -> None:
        """감시 경로 추가"""
        p = Path(path).expanduser().resolve()
        if p.exists():
            self._paths.add(str(p))
            self._scan_path(str(p))
    
    def _scan_path(self, root: str) -> None:
        """경로 스캔하여 상태 저장"""
        for path in Path(root).rglob('*'):
            if path.is_file():
                try:
                    self._file_states[str(path)] = path.stat().st_mtime
                except:
                    pass
    
    def start(self) -> None:
        """감시 시작"""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """감시 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
    
    def _poll_loop(self) -> None:
        """폴링 루프"""
        while self._running:
            for root in self._paths:
                self._check_changes(root)
            time.sleep(self.interval)
    
    def _check_changes(self, root: str) -> None:
        """변경사항 확인"""
        current_files = set()
        
        for path in Path(root).rglob('*'):
            if not path.is_file():
                continue
            
            path_str = str(path)
            current_files.add(path_str)
            
            try:
                mtime = path.stat().st_mtime
            except:
                continue
            
            if path_str not in self._file_states:
                # 새 파일
                self._event_queue.put(FileEvent(
                    event_type=FileEventType.CREATED,
                    path=path_str,
                    timestamp=datetime.now().isoformat()
                ))
                self._file_states[path_str] = mtime
            
            elif self._file_states[path_str] != mtime:
                # 수정된 파일
                self._event_queue.put(FileEvent(
                    event_type=FileEventType.MODIFIED,
                    path=path_str,
                    timestamp=datetime.now().isoformat()
                ))
                self._file_states[path_str] = mtime
        
        # 삭제된 파일
        for path_str in list(self._file_states.keys()):
            if path_str.startswith(root) and path_str not in current_files:
                self._event_queue.put(FileEvent(
                    event_type=FileEventType.DELETED,
                    path=path_str,
                    timestamp=datetime.now().isoformat()
                ))
                del self._file_states[path_str]
    
    def get_event(self, timeout: Optional[float] = None) -> Optional[FileEvent]:
        """이벤트 가져오기"""
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None


if __name__ == "__main__":
    import sys
    
    print("👁️ AMAA Watcher Agent Test")
    print("=" * 50)
    
    if not WATCHDOG_AVAILABLE:
        print("⚠️ watchdog not installed. Using simple poller.")
        watcher_class = SimpleWatcher
    else:
        print("✅ watchdog available")
        watcher_class = WatcherAgent
    
    # 감시 경로
    watch_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print(f"\n📁 Watching: {watch_path}")
    print("Press Ctrl+C to stop\n")
    
    if watcher_class == WatcherAgent:
        watcher = WatcherAgent()
        watcher.add_watch(watch_path)
        watcher.start()
    else:
        watcher = SimpleWatcher()
        watcher.add_watch(watch_path)
        watcher.start()
    
    try:
        while True:
            event = watcher.get_event(timeout=1.0)
            if event:
                icon = {
                    FileEventType.CREATED: "✨",
                    FileEventType.MODIFIED: "📝",
                    FileEventType.DELETED: "🗑️",
                    FileEventType.MOVED: "📦",
                    FileEventType.DIR_CREATED: "📁",
                }.get(event.event_type, "❓")
                
                print(f"{icon} [{event.event_type.value}] {event.path}")
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping...")
        watcher.stop()
        print("✅ Done")
