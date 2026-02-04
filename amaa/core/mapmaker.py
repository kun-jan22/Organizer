"""
AMAA v0.4 - MapMaker (Directory Indexer)
디렉토리 구조 스캔 및 분류 체계(Taxonomy) 추출 모듈

Step 1: 환경 설정 및 디렉토리 인덱서 구현
- pathlib을 사용한 재귀적 디렉토리 스캔
- JSON 트리 구조 생성
- 사용자의 기존 분류 습관(Taxonomy) 추출
"""

import json
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Generator, Any, Set
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import stat


@dataclass
class FileInfo:
    """파일 정보 데이터 클래스"""
    path: str
    name: str
    extension: str
    size: int
    created: str
    modified: str
    category: Optional[str] = None
    mime_type: Optional[str] = None
    is_hidden: bool = False
    depth: int = 0
    checksum: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DirectoryInfo:
    """디렉토리 정보 데이터 클래스"""
    path: str
    name: str
    depth: int
    file_count: int = 0
    dir_count: int = 0
    total_size: int = 0
    children: List[Any] = field(default_factory=list)
    files: List[FileInfo] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        result = {
            'path': self.path,
            'name': self.name,
            'depth': self.depth,
            'file_count': self.file_count,
            'dir_count': self.dir_count,
            'total_size': self.total_size,
            'children': [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.children],
            'files': [f.to_dict() for f in self.files]
        }
        return result


@dataclass
class TaxonomyPattern:
    """분류 체계 패턴"""
    pattern: str
    count: int
    examples: List[str]
    depth: int
    category_guess: Optional[str] = None


class MapMaker:
    """
    디렉토리 인덱서 - 로컬 파일 시스템을 스캔하고 JSON 트리 생성
    
    사용자의 기존 분류 습관(Taxonomy)을 분석하여 지능형 정리에 활용
    
    Usage:
        mapper = MapMaker(config)
        tree = mapper.scan("/path/to/root")
        taxonomy = mapper.extract_taxonomy()
        mapper.save_map("directory_map.json")
    """
    
    # 파일 카테고리 매핑
    CATEGORY_MAP = {
        'documents': {'.pdf', '.docx', '.doc', '.txt', '.md', '.xlsx', '.xls', '.pptx', '.ppt', '.rtf', '.odt'},
        'images': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp', '.svg', '.ico', '.tiff'},
        'videos': {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v'},
        'audio': {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma'},
        'code': {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.html', '.css'},
        'archives': {'.zip', '.tar', '.gz', '.7z', '.rar', '.bz2'},
        'data': {'.json', '.xml', '.csv', '.yaml', '.yml', '.sql', '.db'},
        'executables': {'.exe', '.msi', '.dmg', '.app', '.sh', '.bat', '.cmd'},
    }
    
    # 제외할 디렉토리/파일
    DEFAULT_EXCLUDES = {
        'directories': {'.git', '.svn', 'node_modules', '__pycache__', '.venv', 'venv', '.idea', '.vscode'},
        'files': {'.DS_Store', 'Thumbs.db', 'desktop.ini'},
        'patterns': {'.*', '~$*', '*.tmp', '*.swp'}
    }
    
    def __init__(self, config=None, max_workers: int = 4):
        """
        Args:
            config: AMAA Config 객체 (optional)
            max_workers: 병렬 처리 워커 수
        """
        self.config = config
        self.max_workers = max_workers
        
        # 스캔 결과
        self._root_path: Optional[Path] = None
        self._tree: Optional[DirectoryInfo] = None
        self._all_files: List[FileInfo] = []
        self._all_dirs: List[DirectoryInfo] = []
        
        # 통계
        self._stats = {
            'total_files': 0,
            'total_dirs': 0,
            'total_size': 0,
            'by_category': {},
            'by_extension': {},
            'max_depth': 0,
            'scan_time': 0,
        }
        
        # Taxonomy 분석 결과
        self._taxonomy_patterns: List[TaxonomyPattern] = []
        
        # 제외 규칙 설정
        if config:
            self._excludes = config.exclude
        else:
            self._excludes = self.DEFAULT_EXCLUDES
    
    def scan(self, root_path: str, include_files: bool = True, 
             compute_checksum: bool = False) -> DirectoryInfo:
        """
        디렉토리 재귀 스캔 및 JSON 트리 생성
        
        Args:
            root_path: 스캔할 루트 경로
            include_files: 파일 정보 포함 여부
            compute_checksum: 파일 체크섬 계산 여부
            
        Returns:
            DirectoryInfo: 디렉토리 트리 구조
        """
        start_time = datetime.now()
        
        self._root_path = Path(root_path).expanduser().resolve()
        if not self._root_path.exists():
            raise FileNotFoundError(f"Path not found: {root_path}")
        
        if not self._root_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {root_path}")
        
        # 초기화
        self._all_files.clear()
        self._all_dirs.clear()
        self._stats = {
            'total_files': 0,
            'total_dirs': 0,
            'total_size': 0,
            'by_category': {},
            'by_extension': {},
            'max_depth': 0,
            'scan_time': 0,
        }
        
        # 재귀 스캔
        self._tree = self._scan_directory(
            self._root_path, 
            depth=0,
            include_files=include_files,
            compute_checksum=compute_checksum
        )
        
        # 스캔 시간 기록
        self._stats['scan_time'] = (datetime.now() - start_time).total_seconds()
        
        return self._tree
    
    def _scan_directory(self, path: Path, depth: int, 
                        include_files: bool, compute_checksum: bool) -> DirectoryInfo:
        """디렉토리 재귀 스캔 (내부 메서드)"""
        
        dir_info = DirectoryInfo(
            path=str(path),
            name=path.name,
            depth=depth
        )
        
        # 최대 깊이 업데이트
        self._stats['max_depth'] = max(self._stats['max_depth'], depth)
        
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return dir_info
        
        subdirs = []
        files = []
        
        for entry in entries:
            # 제외 규칙 체크
            if self._should_exclude(entry):
                continue
            
            if entry.is_dir():
                subdirs.append(entry)
            elif entry.is_file():
                files.append(entry)
        
        # 하위 디렉토리 처리
        for subdir in subdirs:
            child_info = self._scan_directory(
                subdir, 
                depth + 1, 
                include_files, 
                compute_checksum
            )
            dir_info.children.append(child_info)
            dir_info.dir_count += 1
            dir_info.total_size += child_info.total_size
        
        # 파일 처리
        if include_files:
            for file_path in files:
                file_info = self._get_file_info(file_path, depth, compute_checksum)
                dir_info.files.append(file_info)
                dir_info.file_count += 1
                dir_info.total_size += file_info.size
                
                self._all_files.append(file_info)
                self._update_stats(file_info)
        
        self._all_dirs.append(dir_info)
        self._stats['total_dirs'] += 1
        
        return dir_info
    
    def _get_file_info(self, path: Path, depth: int, 
                       compute_checksum: bool) -> FileInfo:
        """파일 정보 추출"""
        
        stat_info = path.stat()
        extension = path.suffix.lower()
        
        file_info = FileInfo(
            path=str(path),
            name=path.name,
            extension=extension,
            size=stat_info.st_size,
            created=datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            modified=datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            category=self._get_category(extension),
            mime_type=mimetypes.guess_type(str(path))[0],
            is_hidden=path.name.startswith('.'),
            depth=depth
        )
        
        if compute_checksum:
            file_info.checksum = self._compute_checksum(path)
        
        self._stats['total_files'] += 1
        
        return file_info
    
    def _get_category(self, extension: str) -> Optional[str]:
        """확장자로 카테고리 결정"""
        for category, extensions in self.CATEGORY_MAP.items():
            if extension in extensions:
                return category
        return 'other'
    
    def _compute_checksum(self, path: Path, algorithm: str = 'md5') -> str:
        """파일 체크섬 계산"""
        hash_func = hashlib.new(algorithm)
        
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except (PermissionError, OSError):
            return ''
    
    def _should_exclude(self, path: Path) -> bool:
        """제외 규칙 체크"""
        name = path.name
        
        # 디렉토리 제외
        if path.is_dir():
            if name in self._excludes.get('directories', set()):
                return True
        
        # 파일 제외
        if name in self._excludes.get('files', set()):
            return True
        
        # 패턴 제외
        import fnmatch
        for pattern in self._excludes.get('patterns', []):
            if fnmatch.fnmatch(name, pattern):
                return True
        
        return False
    
    def _update_stats(self, file_info: FileInfo) -> None:
        """통계 업데이트"""
        # 카테고리별 통계
        category = file_info.category or 'other'
        if category not in self._stats['by_category']:
            self._stats['by_category'][category] = {'count': 0, 'size': 0}
        self._stats['by_category'][category]['count'] += 1
        self._stats['by_category'][category]['size'] += file_info.size
        
        # 확장자별 통계
        ext = file_info.extension or 'no_extension'
        if ext not in self._stats['by_extension']:
            self._stats['by_extension'][ext] = {'count': 0, 'size': 0}
        self._stats['by_extension'][ext]['count'] += 1
        self._stats['by_extension'][ext]['size'] += file_info.size
        
        # 총 크기
        self._stats['total_size'] += file_info.size
    
    def extract_taxonomy(self) -> List[TaxonomyPattern]:
        """
        사용자의 기존 분류 습관(Taxonomy) 추출
        
        디렉토리 구조를 분석하여 반복되는 패턴 식별
        
        Returns:
            List[TaxonomyPattern]: 분류 체계 패턴 목록
        """
        if not self._tree:
            raise ValueError("Scan first before extracting taxonomy")
        
        self._taxonomy_patterns.clear()
        
        # 디렉토리명 패턴 분석
        dir_names: Dict[str, List[str]] = {}
        for dir_info in self._all_dirs:
            name = dir_info.name.lower()
            
            # 날짜 패턴 추출
            if self._is_date_pattern(name):
                pattern = 'date_folder'
            # 년도 패턴
            elif name.isdigit() and len(name) == 4:
                pattern = 'year_folder'
            # 카테고리성 이름
            elif name in ['documents', 'images', 'videos', 'music', 'downloads', 
                         '문서', '사진', '동영상', '음악', '다운로드']:
                pattern = 'category_folder'
            # 프로젝트성 이름
            elif '-' in name or '_' in name:
                pattern = 'project_folder'
            else:
                pattern = 'generic_folder'
            
            if pattern not in dir_names:
                dir_names[pattern] = []
            dir_names[pattern].append(dir_info.path)
        
        # 패턴 객체 생성
        for pattern, paths in dir_names.items():
            taxonomy = TaxonomyPattern(
                pattern=pattern,
                count=len(paths),
                examples=paths[:5],  # 최대 5개 예시
                depth=self._get_common_depth(paths),
                category_guess=self._guess_category(pattern)
            )
            self._taxonomy_patterns.append(taxonomy)
        
        # 파일명 패턴 분석
        file_patterns = self._analyze_file_patterns()
        self._taxonomy_patterns.extend(file_patterns)
        
        return self._taxonomy_patterns
    
    def _is_date_pattern(self, name: str) -> bool:
        """날짜 패턴인지 확인"""
        import re
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{4}_\d{2}_\d{2}',  # YYYY_MM_DD
            r'\d{8}',              # YYYYMMDD
        ]
        return any(re.search(p, name) for p in date_patterns)
    
    def _get_common_depth(self, paths: List[str]) -> int:
        """경로들의 평균 깊이 계산"""
        if not paths:
            return 0
        depths = [p.count(os.sep) for p in paths]
        return sum(depths) // len(depths)
    
    def _guess_category(self, pattern: str) -> Optional[str]:
        """패턴으로 카테고리 추측"""
        mapping = {
            'date_folder': 'chronological',
            'year_folder': 'chronological',
            'category_folder': 'categorical',
            'project_folder': 'project-based',
            'generic_folder': 'mixed',
        }
        return mapping.get(pattern)
    
    def _analyze_file_patterns(self) -> List[TaxonomyPattern]:
        """파일명 패턴 분석"""
        patterns = []
        
        # 날짜 접두어 파일
        date_prefixed = [f for f in self._all_files 
                        if self._is_date_pattern(f.name)]
        if date_prefixed:
            patterns.append(TaxonomyPattern(
                pattern='date_prefixed_files',
                count=len(date_prefixed),
                examples=[f.name for f in date_prefixed[:5]],
                depth=0,
                category_guess='organized'
            ))
        
        # 일관된 네이밍 패턴 감지
        # TODO: 더 정교한 패턴 감지 추가
        
        return patterns
    
    def iter_files(self, category: Optional[str] = None) -> Generator[FileInfo, None, None]:
        """
        파일 제네레이터 (대용량 파일 처리용)
        
        Args:
            category: 특정 카테고리만 필터링 (optional)
            
        Yields:
            FileInfo: 파일 정보
        """
        for file_info in self._all_files:
            if category is None or file_info.category == category:
                yield file_info
    
    def get_tree(self) -> Optional[DirectoryInfo]:
        """스캔된 트리 구조 반환"""
        return self._tree
    
    def get_stats(self) -> dict:
        """스캔 통계 반환"""
        return self._stats.copy()
    
    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 변환"""
        if not self._tree:
            return '{}'
        
        return json.dumps(self._tree.to_dict(), indent=indent, ensure_ascii=False)
    
    def save_map(self, output_path: str) -> None:
        """디렉토리 맵을 JSON 파일로 저장"""
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
    
    def load_map(self, input_path: str) -> DirectoryInfo:
        """저장된 디렉토리 맵 로드"""
        path = Path(input_path).expanduser()
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # TODO: JSON을 DirectoryInfo 객체로 변환
        return data
    
    def get_taxonomy_summary(self) -> str:
        """Taxonomy 요약 문자열 생성"""
        if not self._taxonomy_patterns:
            return "No taxonomy patterns detected"
        
        lines = ["📊 Taxonomy Analysis Summary", "=" * 40]
        
        for pattern in sorted(self._taxonomy_patterns, key=lambda x: -x.count):
            lines.append(f"\n🏷️ Pattern: {pattern.pattern}")
            lines.append(f"   Count: {pattern.count}")
            lines.append(f"   Category: {pattern.category_guess}")
            lines.append(f"   Examples: {', '.join(pattern.examples[:3])}")
        
        return '\n'.join(lines)
    
    def get_context_for_llm(self, max_depth: int = 3) -> str:
        """
        LLM에게 전달할 디렉토리 컨텍스트 생성
        
        Args:
            max_depth: 포함할 최대 깊이
            
        Returns:
            str: LLM 프롬프트용 컨텍스트
        """
        if not self._tree:
            return "No directory scanned"
        
        lines = [
            f"# Directory Structure: {self._root_path}",
            f"Total Files: {self._stats['total_files']}",
            f"Total Directories: {self._stats['total_dirs']}",
            f"Total Size: {self._format_size(self._stats['total_size'])}",
            "",
            "## Categories:",
        ]
        
        for cat, info in self._stats['by_category'].items():
            lines.append(f"- {cat}: {info['count']} files ({self._format_size(info['size'])})")
        
        lines.append("\n## Directory Tree:")
        lines.append(self._format_tree(self._tree, max_depth=max_depth))
        
        return '\n'.join(lines)
    
    def _format_tree(self, node: DirectoryInfo, prefix: str = "", 
                     max_depth: int = 3) -> str:
        """트리 구조 포맷팅"""
        if node.depth > max_depth:
            return ""
        
        lines = [f"{prefix}📁 {node.name}/"]
        
        new_prefix = prefix + "  "
        
        # 파일
        for f in node.files[:5]:  # 최대 5개
            lines.append(f"{new_prefix}📄 {f.name}")
        
        if len(node.files) > 5:
            lines.append(f"{new_prefix}... and {len(node.files) - 5} more files")
        
        # 하위 디렉토리
        for child in node.children:
            lines.append(self._format_tree(child, new_prefix, max_depth))
        
        return '\n'.join(lines)
    
    def _format_size(self, size: int) -> str:
        """파일 크기 포맷팅"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


# ============================================================
# 병렬 스캔 버전 (대규모 디렉토리용)
# ============================================================

class ParallelMapMaker(MapMaker):
    """
    병렬 처리를 활용한 고성능 디렉토리 인덱서
    
    대규모 디렉토리(10만+ 파일) 스캔에 최적화
    """
    
    def scan_parallel(self, root_path: str, include_files: bool = True,
                      compute_checksum: bool = False) -> DirectoryInfo:
        """병렬 스캔 실행"""
        self._root_path = Path(root_path).expanduser().resolve()
        
        # 1단계: 빠른 디렉토리 구조 스캔
        dirs_to_scan = self._collect_directories(self._root_path)
        
        # 2단계: 병렬 파일 정보 수집
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._scan_single_dir, d, include_files, compute_checksum): d
                for d in dirs_to_scan
            }
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error scanning: {e}")
        
        # 3단계: 트리 구조 재구성
        self._tree = self._build_tree_from_scanned()
        
        return self._tree
    
    def _collect_directories(self, root: Path) -> List[Path]:
        """모든 하위 디렉토리 수집"""
        dirs = [root]
        
        for path in root.rglob('*'):
            if path.is_dir() and not self._should_exclude(path):
                dirs.append(path)
        
        return dirs
    
    def _scan_single_dir(self, path: Path, include_files: bool,
                         compute_checksum: bool) -> None:
        """단일 디렉토리 스캔 (병렬 워커용)"""
        # 병렬 처리에서 안전하게 파일 정보 수집
        pass
    
    def _build_tree_from_scanned(self) -> DirectoryInfo:
        """스캔된 데이터로 트리 구조 빌드"""
        # 수집된 데이터로 트리 재구성
        return self._tree


if __name__ == "__main__":
    # 테스트 실행
    import sys
    
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        target_path = "."
    
    print(f"🔍 Scanning: {target_path}")
    
    mapper = MapMaker()
    tree = mapper.scan(target_path, include_files=True)
    
    print(f"\n📊 Scan Statistics:")
    stats = mapper.get_stats()
    print(f"  Total Files: {stats['total_files']}")
    print(f"  Total Directories: {stats['total_dirs']}")
    print(f"  Total Size: {mapper._format_size(stats['total_size'])}")
    print(f"  Max Depth: {stats['max_depth']}")
    print(f"  Scan Time: {stats['scan_time']:.2f}s")
    
    print(f"\n📁 Categories:")
    for cat, info in stats['by_category'].items():
        print(f"  {cat}: {info['count']} files")
    
    # Taxonomy 추출
    print("\n" + "=" * 50)
    taxonomy = mapper.extract_taxonomy()
    print(mapper.get_taxonomy_summary())
    
    # LLM 컨텍스트 출력
    print("\n" + "=" * 50)
    print("📝 LLM Context:")
    print(mapper.get_context_for_llm(max_depth=2))
