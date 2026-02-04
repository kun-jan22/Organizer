"""
AMAA v0.4 - Desktop Auto Organizer
바탕화면 자동 정리 에이전트

Features:
- 바탕화면 실시간 모니터링
- 파일 타입별 자동 분류
- ISO 8601 날짜 프리픽스
- Google Drive 동기화
- 히스토리 기록
"""

import os
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Set
from dataclasses import dataclass
from enum import Enum

# Watchdog 임포트 (선택적)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class FileCategory(Enum):
    """파일 카테고리"""
    DOCUMENTS = "Documents"
    IMAGES = "Images"
    VIDEOS = "Videos"
    AUDIO = "Audio"
    ARCHIVES = "Archives"
    CODE = "Code"
    DATA = "Data"
    EXECUTABLES = "Executables"
    OTHERS = "Others"


# 확장자 → 카테고리 매핑
EXTENSION_MAP: Dict[str, FileCategory] = {
    # 문서
    '.pdf': FileCategory.DOCUMENTS,
    '.doc': FileCategory.DOCUMENTS,
    '.docx': FileCategory.DOCUMENTS,
    '.xls': FileCategory.DOCUMENTS,
    '.xlsx': FileCategory.DOCUMENTS,
    '.ppt': FileCategory.DOCUMENTS,
    '.pptx': FileCategory.DOCUMENTS,
    '.txt': FileCategory.DOCUMENTS,
    '.rtf': FileCategory.DOCUMENTS,
    '.odt': FileCategory.DOCUMENTS,
    '.hwp': FileCategory.DOCUMENTS,
    
    # 이미지
    '.jpg': FileCategory.IMAGES,
    '.jpeg': FileCategory.IMAGES,
    '.png': FileCategory.IMAGES,
    '.gif': FileCategory.IMAGES,
    '.bmp': FileCategory.IMAGES,
    '.svg': FileCategory.IMAGES,
    '.webp': FileCategory.IMAGES,
    '.ico': FileCategory.IMAGES,
    '.heic': FileCategory.IMAGES,
    '.tiff': FileCategory.IMAGES,
    
    # 비디오
    '.mp4': FileCategory.VIDEOS,
    '.avi': FileCategory.VIDEOS,
    '.mkv': FileCategory.VIDEOS,
    '.mov': FileCategory.VIDEOS,
    '.wmv': FileCategory.VIDEOS,
    '.flv': FileCategory.VIDEOS,
    '.webm': FileCategory.VIDEOS,
    
    # 오디오
    '.mp3': FileCategory.AUDIO,
    '.wav': FileCategory.AUDIO,
    '.flac': FileCategory.AUDIO,
    '.aac': FileCategory.AUDIO,
    '.ogg': FileCategory.AUDIO,
    '.m4a': FileCategory.AUDIO,
    
    # 압축 파일
    '.zip': FileCategory.ARCHIVES,
    '.rar': FileCategory.ARCHIVES,
    '.7z': FileCategory.ARCHIVES,
    '.tar': FileCategory.ARCHIVES,
    '.gz': FileCategory.ARCHIVES,
    '.bz2': FileCategory.ARCHIVES,
    
    # 코드
    '.py': FileCategory.CODE,
    '.js': FileCategory.CODE,
    '.ts': FileCategory.CODE,
    '.jsx': FileCategory.CODE,
    '.tsx': FileCategory.CODE,
    '.html': FileCategory.CODE,
    '.css': FileCategory.CODE,
    '.java': FileCategory.CODE,
    '.cpp': FileCategory.CODE,
    '.c': FileCategory.CODE,
    '.h': FileCategory.CODE,
    '.go': FileCategory.CODE,
    '.rs': FileCategory.CODE,
    '.swift': FileCategory.CODE,
    '.kt': FileCategory.CODE,
    '.rb': FileCategory.CODE,
    '.php': FileCategory.CODE,
    '.sh': FileCategory.CODE,
    '.bat': FileCategory.CODE,
    '.ps1': FileCategory.CODE,
    
    # 데이터
    '.json': FileCategory.DATA,
    '.xml': FileCategory.DATA,
    '.csv': FileCategory.DATA,
    '.yaml': FileCategory.DATA,
    '.yml': FileCategory.DATA,
    '.sql': FileCategory.DATA,
    '.db': FileCategory.DATA,
    '.sqlite': FileCategory.DATA,
    
    # 실행 파일
    '.exe': FileCategory.EXECUTABLES,
    '.msi': FileCategory.EXECUTABLES,
    '.dmg': FileCategory.EXECUTABLES,
    '.app': FileCategory.EXECUTABLES,
    '.deb': FileCategory.EXECUTABLES,
    '.rpm': FileCategory.EXECUTABLES,
}


@dataclass
class OrganizeResult:
    """정리 결과"""
    success: bool
    original_path: str
    new_path: str
    original_name: str
    new_name: str
    category: str
    error: Optional[str] = None


class DesktopOrganizer:
    """
    바탕화면 자동 정리기
    
    바탕화면에 생성/저장되는 파일을 자동으로
    적절한 폴더로 이동합니다.
    
    Usage:
        organizer = DesktopOrganizer(
            desktop_path="~/Desktop",
            output_base="~/Documents/Organized"
        )
        organizer.start()  # 실시간 모니터링
        
        # 또는 수동 정리
        results = organizer.organize_all()
    """
    
    def __init__(self,
                 desktop_path: Optional[str] = None,
                 output_base: str = "~/Documents/Organized",
                 gdrive_sync = None,
                 gdrive_folder_id: Optional[str] = None,
                 history_tracker = None,
                 add_date_prefix: bool = True,
                 delay_seconds: int = 5,
                 excluded_extensions: Optional[Set[str]] = None,
                 excluded_patterns: Optional[List[str]] = None):
        """
        Args:
            desktop_path: 바탕화면 경로 (None이면 자동 감지)
            output_base: 정리된 파일 저장 기본 경로
            gdrive_sync: GoogleDriveSync 인스턴스
            gdrive_folder_id: Drive 폴더 ID
            history_tracker: HistoryTracker 인스턴스
            add_date_prefix: ISO 8601 날짜 프리픽스 추가 여부
            delay_seconds: 파일 생성 후 처리 대기 시간
            excluded_extensions: 제외할 확장자
            excluded_patterns: 제외할 파일명 패턴
        """
        # 바탕화면 경로 자동 감지
        if desktop_path:
            self.desktop_path = Path(desktop_path).expanduser()
        else:
            self.desktop_path = self._detect_desktop()
        
        self.output_base = Path(output_base).expanduser()
        self.gdrive_sync = gdrive_sync
        self.gdrive_folder_id = gdrive_folder_id
        self.history_tracker = history_tracker
        self.add_date_prefix = add_date_prefix
        self.delay_seconds = delay_seconds
        
        self.excluded_extensions = excluded_extensions or {'.lnk', '.url', '.ini'}
        self.excluded_patterns = excluded_patterns or ['desktop.ini', '.DS_Store', 'Thumbs.db']
        
        # 폴더 생성
        self.output_base.mkdir(parents=True, exist_ok=True)
        for category in FileCategory:
            (self.output_base / category.value).mkdir(exist_ok=True)
        
        self._observer = None
        self._is_running = False
        self._pending_files: Dict[str, float] = {}  # path -> creation_time
    
    def _detect_desktop(self) -> Path:
        """바탕화면 경로 자동 감지"""
        import platform
        
        system = platform.system()
        home = Path.home()
        
        if system == "Windows":
            # Windows
            desktop = home / "Desktop"
            if not desktop.exists():
                desktop = home / "바탕 화면"  # Korean
            if not desktop.exists():
                desktop = home / "OneDrive" / "Desktop"
            if not desktop.exists():
                desktop = home / "OneDrive" / "바탕 화면"
        elif system == "Darwin":
            # macOS
            desktop = home / "Desktop"
        else:
            # Linux
            desktop = home / "Desktop"
            if not desktop.exists():
                desktop = home / "바탕화면"
        
        return desktop
    
    def get_category(self, file_path: Path) -> FileCategory:
        """파일 카테고리 결정"""
        suffix = file_path.suffix.lower()
        return EXTENSION_MAP.get(suffix, FileCategory.OTHERS)
    
    def should_skip(self, file_path: Path) -> bool:
        """파일 스킵 여부 결정"""
        # 확장자 제외
        if file_path.suffix.lower() in self.excluded_extensions:
            return True
        
        # 패턴 제외
        for pattern in self.excluded_patterns:
            if pattern.lower() in file_path.name.lower():
                return True
        
        # 숨김 파일
        if file_path.name.startswith('.'):
            return True
        
        # 폴더는 스킵
        if file_path.is_dir():
            return True
        
        return False
    
    def generate_new_name(self, original_name: str) -> str:
        """새 파일명 생성 (날짜 프리픽스)"""
        if not self.add_date_prefix:
            return original_name
        
        # 이미 날짜 프리픽스가 있는지 확인
        import re
        if re.match(r'^\d{4}-\d{2}-\d{2}_', original_name):
            return original_name
        
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        return f"{date_prefix}_{original_name}"
    
    def get_unique_path(self, path: Path) -> Path:
        """중복 없는 경로 생성"""
        if not path.exists():
            return path
        
        counter = 1
        stem = path.stem
        suffix = path.suffix
        
        while True:
            new_path = path.parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
    
    def organize_file(self, file_path: Path) -> OrganizeResult:
        """단일 파일 정리"""
        if self.should_skip(file_path):
            return OrganizeResult(
                success=False,
                original_path=str(file_path),
                new_path="",
                original_name=file_path.name,
                new_name="",
                category="",
                error="Skipped"
            )
        
        if not file_path.exists():
            return OrganizeResult(
                success=False,
                original_path=str(file_path),
                new_path="",
                original_name=file_path.name,
                new_name="",
                category="",
                error="File not found"
            )
        
        try:
            # 카테고리 결정
            category = self.get_category(file_path)
            
            # 새 이름 생성
            new_name = self.generate_new_name(file_path.name)
            
            # 대상 경로
            target_dir = self.output_base / category.value
            target_path = target_dir / new_name
            target_path = self.get_unique_path(target_path)
            
            # 파일 이동
            shutil.move(str(file_path), str(target_path))
            
            print(f"📁 정리됨: {file_path.name} → {category.value}/{target_path.name}")
            
            # Google Drive 업로드
            if self.gdrive_sync and self.gdrive_folder_id:
                self.gdrive_sync.upload_file(
                    str(target_path),
                    self.gdrive_folder_id
                )
            
            # 히스토리 기록
            if self.history_tracker:
                self.history_tracker.record_desktop_organize(
                    original_path=str(file_path),
                    new_path=str(target_path),
                    category=category.value
                )
            
            return OrganizeResult(
                success=True,
                original_path=str(file_path),
                new_path=str(target_path),
                original_name=file_path.name,
                new_name=target_path.name,
                category=category.value
            )
            
        except Exception as e:
            return OrganizeResult(
                success=False,
                original_path=str(file_path),
                new_path="",
                original_name=file_path.name,
                new_name="",
                category="",
                error=str(e)
            )
    
    def organize_all(self) -> List[OrganizeResult]:
        """바탕화면 전체 정리"""
        results = []
        
        if not self.desktop_path.exists():
            print(f"❌ 바탕화면 경로를 찾을 수 없습니다: {self.desktop_path}")
            return results
        
        print(f"🧹 바탕화면 정리 시작: {self.desktop_path}")
        
        for item in self.desktop_path.iterdir():
            if item.is_file():
                result = self.organize_file(item)
                results.append(result)
        
        success_count = sum(1 for r in results if r.success)
        print(f"✅ 정리 완료: {success_count}/{len(results)} 파일")
        
        return results
    
    def start(self):
        """실시간 모니터링 시작"""
        if not WATCHDOG_AVAILABLE:
            print("⚠️ watchdog 미설치. 수동 모드로 전환합니다.")
            print("   pip install watchdog")
            self._start_polling()
            return
        
        self._start_watchdog()
    
    def _start_watchdog(self):
        """Watchdog 기반 모니터링"""
        
        class DesktopHandler(FileSystemEventHandler):
            def __init__(self, organizer):
                self.organizer = organizer
            
            def on_created(self, event):
                if event.is_directory:
                    return
                
                file_path = Path(event.src_path)
                
                # 지연 처리 (파일 쓰기 완료 대기)
                self.organizer._pending_files[str(file_path)] = time.time()
            
            def on_moved(self, event):
                if event.is_directory:
                    return
                
                # 바탕화면으로 이동된 파일
                dest_path = Path(event.dest_path)
                if dest_path.parent == self.organizer.desktop_path:
                    self.organizer._pending_files[str(dest_path)] = time.time()
        
        handler = DesktopHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.desktop_path), recursive=False)
        self._observer.start()
        
        self._is_running = True
        
        print(f"👁️ 바탕화면 모니터링 시작: {self.desktop_path}")
        print(f"   저장 위치: {self.output_base}")
        print("   중지하려면 Ctrl+C")
        
        try:
            while self._is_running:
                self._process_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def _start_polling(self):
        """폴링 기반 모니터링 (fallback)"""
        self._is_running = True
        known_files: Set[str] = set()
        
        print(f"👁️ 바탕화면 폴링 모니터링 시작: {self.desktop_path}")
        
        try:
            while self._is_running:
                current_files = set()
                
                for item in self.desktop_path.iterdir():
                    if item.is_file():
                        current_files.add(str(item))
                
                # 새 파일 감지
                new_files = current_files - known_files
                for file_path in new_files:
                    self._pending_files[file_path] = time.time()
                
                known_files = current_files
                
                self._process_pending()
                time.sleep(2)
                
        except KeyboardInterrupt:
            self.stop()
    
    def _process_pending(self):
        """대기 중인 파일 처리"""
        now = time.time()
        to_process = []
        
        for file_path, created_time in list(self._pending_files.items()):
            if now - created_time >= self.delay_seconds:
                to_process.append(file_path)
        
        for file_path in to_process:
            del self._pending_files[file_path]
            path = Path(file_path)
            if path.exists():
                self.organize_file(path)
    
    def stop(self):
        """모니터링 중지"""
        self._is_running = False
        
        if self._observer:
            self._observer.stop()
            self._observer.join()
        
        print("\n👁️ 바탕화면 모니터링 중지됨")


if __name__ == "__main__":
    import sys
    
    print("🖥️ AMAA Desktop Organizer Test")
    print("=" * 50)
    
    organizer = DesktopOrganizer()
    
    print(f"바탕화면: {organizer.desktop_path}")
    print(f"저장 위치: {organizer.output_base}")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        organizer.start()
    else:
        print("\n현재 파일 스캔 중...")
        
        files = list(organizer.desktop_path.iterdir())
        files = [f for f in files if f.is_file() and not organizer.should_skip(f)]
        
        print(f"정리 대상: {len(files)}개 파일")
        
        for f in files[:10]:
            cat = organizer.get_category(f)
            print(f"  {f.name} → {cat.value}/")
        
        print("\n실제 정리하려면: python -m amaa desktop --execute")
        print("실시간 모니터링: python desktop_organizer.py --watch")
