"""
AMAA v0.4 - DLP (Data Loss Prevention)
민감 데이터 감지 및 보호 모듈

Step 4: 보안 가드레일
- 기밀 키워드 자동 감지
- 메타데이터 태그 삽입
- 민감 파일 격리(Quarantine)
"""

import re
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed


class DLPAction(Enum):
    """DLP 액션 타입"""
    TAG = "tag"           # 메타데이터 태그 추가
    QUARANTINE = "quarantine"  # 격리 폴더로 이동
    ALERT = "alert"       # 알림만
    BLOCK = "block"       # 이동 차단
    ENCRYPT = "encrypt"   # 암호화


class DLPSeverity(Enum):
    """민감도 레벨"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DLPMatch:
    """키워드 매치 결과"""
    keyword: str
    line_number: int
    context: str
    severity: DLPSeverity = DLPSeverity.MEDIUM
    
    def to_dict(self) -> dict:
        return {
            'keyword': self.keyword,
            'line_number': self.line_number,
            'context': self.context[:100],  # 컨텍스트 일부만
            'severity': self.severity.value,
        }


@dataclass
class DLPResult:
    """DLP 스캔 결과"""
    file_path: str
    is_sensitive: bool = False
    matches: List[DLPMatch] = field(default_factory=list)
    action_taken: Optional[DLPAction] = None
    severity: DLPSeverity = DLPSeverity.LOW
    tags_applied: List[str] = field(default_factory=list)
    quarantine_path: Optional[str] = None
    error: Optional[str] = None
    scan_time: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'is_sensitive': self.is_sensitive,
            'matches': [m.to_dict() for m in self.matches],
            'action_taken': self.action_taken.value if self.action_taken else None,
            'severity': self.severity.value,
            'tags_applied': self.tags_applied,
            'quarantine_path': self.quarantine_path,
            'error': self.error,
            'scan_time': self.scan_time,
        }


class DLPScanner:
    """
    DLP (Data Loss Prevention) 스캐너
    
    파일 내용에서 민감 정보를 탐지하고 적절한 조치 수행
    
    Usage:
        dlp = DLPScanner(config)
        result = dlp.scan_file("/path/to/file.txt")
        
        if result.is_sensitive:
            dlp.apply_action(result, DLPAction.TAG)
    """
    
    # 기본 키워드 (한국어/영어)
    DEFAULT_KEYWORDS = {
        DLPSeverity.CRITICAL: [
            "주민등록번호", "주민번호",
            "social security number", "ssn",
            "비밀번호", "password", "passwd",
            "secret key", "api key", "apikey",
            "private key", "access token",
        ],
        DLPSeverity.HIGH: [
            "기밀", "극비", "대외비",
            "confidential", "top secret", "classified",
            "개인정보", "신용카드", "credit card",
            "계좌번호", "account number",
        ],
        DLPSeverity.MEDIUM: [
            "비공개", "내부용", "private",
            "internal only", "do not share",
            "민감", "sensitive",
        ],
        DLPSeverity.LOW: [
            "draft", "초안",
        ]
    }
    
    # 패턴 (정규식)
    DEFAULT_PATTERNS = {
        'korean_id': r'\d{6}[-\s]?[1-4]\d{6}',  # 주민등록번호
        'credit_card': r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}',  # 신용카드
        'phone': r'01[0-9][-\s]?\d{3,4}[-\s]?\d{4}',  # 휴대폰
        'email': r'[\w.-]+@[\w.-]+\.\w+',  # 이메일
        'ip_address': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',  # IP
        'api_key': r'(?:api[_-]?key|apikey)["\s:=]+["\']?[\w-]{20,}',  # API 키
        'aws_key': r'AKIA[0-9A-Z]{16}',  # AWS Access Key
        'private_key': r'-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----',  # PEM 키
    }
    
    def __init__(self, config=None,
                 quarantine_path: str = "~/.amaa/quarantine"):
        """
        Args:
            config: AMAA Config 객체
            quarantine_path: 격리 폴더 경로
        """
        self.config = config
        self.quarantine_path = Path(quarantine_path).expanduser()
        
        # 키워드 설정
        if config and config.dlp:
            self.keywords = self._build_keyword_map(config.dlp.keywords)
            self.default_action = DLPAction(config.dlp.action)
        else:
            self.keywords = self.DEFAULT_KEYWORDS
            self.default_action = DLPAction.TAG
        
        # 패턴 컴파일
        self.patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.DEFAULT_PATTERNS.items()
        }
        
        # 지원 파일 확장자
        self.scannable_extensions = {
            '.txt', '.md', '.csv', '.json', '.xml', '.yaml', '.yml',
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h',
            '.html', '.css', '.sql', '.log', '.conf', '.config',
            '.env', '.ini',
        }
    
    def _build_keyword_map(self, keywords: List[str]) -> Dict[DLPSeverity, List[str]]:
        """설정 키워드를 심각도별로 분류"""
        # 기본적으로 모두 HIGH로 분류
        return {
            DLPSeverity.HIGH: keywords,
            **{s: kw for s, kw in self.DEFAULT_KEYWORDS.items() if s != DLPSeverity.HIGH}
        }
    
    def scan_file(self, file_path: str) -> DLPResult:
        """
        단일 파일 DLP 스캔
        
        Args:
            file_path: 스캔할 파일 경로
            
        Returns:
            DLPResult: 스캔 결과
        """
        start_time = datetime.now()
        path = Path(file_path)
        
        result = DLPResult(file_path=str(path))
        
        # 파일 존재 확인
        if not path.exists():
            result.error = "File not found"
            return result
        
        # 지원 파일 타입 확인
        if path.suffix.lower() not in self.scannable_extensions:
            result.error = f"Unsupported file type: {path.suffix}"
            return result
        
        try:
            # 파일 내용 읽기
            content = self._read_file_safely(path)
            if content is None:
                result.error = "Could not read file"
                return result
            
            # 키워드 검사
            keyword_matches = self._scan_keywords(content)
            result.matches.extend(keyword_matches)
            
            # 패턴 검사
            pattern_matches = self._scan_patterns(content)
            result.matches.extend(pattern_matches)
            
            # 민감도 판정
            if result.matches:
                result.is_sensitive = True
                result.severity = max(
                    (m.severity for m in result.matches),
                    key=lambda s: list(DLPSeverity).index(s)
                )
            
        except Exception as e:
            result.error = str(e)
        
        result.scan_time = (datetime.now() - start_time).total_seconds()
        return result
    
    def _read_file_safely(self, path: Path, max_size: int = 10_000_000) -> Optional[str]:
        """안전하게 파일 읽기 (인코딩 자동 감지)"""
        try:
            # 파일 크기 체크
            if path.stat().st_size > max_size:
                return None
            
            # 인코딩 감지
            try:
                import chardet
                with open(path, 'rb') as f:
                    raw = f.read()
                detected = chardet.detect(raw)
                encoding = detected.get('encoding', 'utf-8')
                return raw.decode(encoding, errors='replace')
            except ImportError:
                # chardet 없으면 utf-8 시도
                try:
                    return path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    return path.read_text(encoding='latin-1', errors='replace')
                    
        except Exception:
            return None
    
    def _scan_keywords(self, content: str) -> List[DLPMatch]:
        """키워드 검사"""
        matches = []
        lines = content.split('\n')
        
        for severity, keywords in self.keywords.items():
            for keyword in keywords:
                # 대소문자 무시 검색
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                
                for line_num, line in enumerate(lines, 1):
                    if pattern.search(line):
                        matches.append(DLPMatch(
                            keyword=keyword,
                            line_number=line_num,
                            context=line.strip(),
                            severity=severity
                        ))
        
        return matches
    
    def _scan_patterns(self, content: str) -> List[DLPMatch]:
        """정규식 패턴 검사"""
        matches = []
        lines = content.split('\n')
        
        for pattern_name, pattern in self.patterns.items():
            for line_num, line in enumerate(lines, 1):
                for match in pattern.finditer(line):
                    # 패턴 이름으로 심각도 결정
                    severity = DLPSeverity.HIGH
                    if pattern_name in ['email', 'ip_address']:
                        severity = DLPSeverity.MEDIUM
                    elif pattern_name in ['korean_id', 'credit_card', 'private_key', 'aws_key']:
                        severity = DLPSeverity.CRITICAL
                    
                    # 매치된 값 마스킹
                    masked_value = self._mask_sensitive(match.group())
                    
                    matches.append(DLPMatch(
                        keyword=f"[{pattern_name}]: {masked_value}",
                        line_number=line_num,
                        context=line.strip(),
                        severity=severity
                    ))
        
        return matches
    
    def _mask_sensitive(self, value: str) -> str:
        """민감 정보 마스킹"""
        if len(value) <= 4:
            return '*' * len(value)
        return value[:2] + '*' * (len(value) - 4) + value[-2:]
    
    def apply_action(self, result: DLPResult, 
                     action: Optional[DLPAction] = None) -> DLPResult:
        """
        DLP 액션 적용
        
        Args:
            result: DLP 스캔 결과
            action: 적용할 액션 (None이면 기본값)
            
        Returns:
            DLPResult: 업데이트된 결과
        """
        action = action or self.default_action
        
        if not result.is_sensitive:
            return result
        
        try:
            if action == DLPAction.TAG:
                result = self._apply_tag(result)
            elif action == DLPAction.QUARANTINE:
                result = self._apply_quarantine(result)
            elif action == DLPAction.ALERT:
                result = self._apply_alert(result)
            elif action == DLPAction.BLOCK:
                result = self._apply_block(result)
            
            result.action_taken = action
            
        except Exception as e:
            result.error = f"Failed to apply action: {e}"
        
        return result
    
    def _apply_tag(self, result: DLPResult) -> DLPResult:
        """메타데이터 태그 적용"""
        path = Path(result.file_path)
        
        # 사이드카 JSON 파일에 태그 저장
        tag_file = path.parent / f".{path.name}.dlp.json"
        
        tags = {
            'dlp_scanned': datetime.now().isoformat(),
            'severity': result.severity.value,
            'is_sensitive': True,
            'match_count': len(result.matches),
            'keywords_found': list(set(m.keyword for m in result.matches)),
        }
        
        with open(tag_file, 'w', encoding='utf-8') as f:
            json.dump(tags, f, indent=2, ensure_ascii=False)
        
        result.tags_applied = list(tags.keys())
        return result
    
    def _apply_quarantine(self, result: DLPResult) -> DLPResult:
        """격리 폴더로 이동"""
        path = Path(result.file_path)
        
        # 격리 폴더 생성
        self.quarantine_path.mkdir(parents=True, exist_ok=True)
        
        # 고유 이름 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        quarantine_name = f"{timestamp}_{path.name}"
        quarantine_dest = self.quarantine_path / quarantine_name
        
        # 이동
        shutil.move(str(path), str(quarantine_dest))
        
        # 로그 파일 생성
        log_file = self.quarantine_path / f"{quarantine_name}.log"
        log_data = {
            'original_path': str(path),
            'quarantine_time': datetime.now().isoformat(),
            'severity': result.severity.value,
            'matches': [m.to_dict() for m in result.matches],
        }
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        result.quarantine_path = str(quarantine_dest)
        return result
    
    def _apply_alert(self, result: DLPResult) -> DLPResult:
        """알림 생성 (로그 기록)"""
        alert_log = self.quarantine_path.parent / "dlp_alerts.log"
        alert_log.parent.mkdir(parents=True, exist_ok=True)
        
        alert_entry = {
            'timestamp': datetime.now().isoformat(),
            'file': result.file_path,
            'severity': result.severity.value,
            'keywords': [m.keyword for m in result.matches[:5]],
        }
        
        with open(alert_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert_entry, ensure_ascii=False) + '\n')
        
        return result
    
    def _apply_block(self, result: DLPResult) -> DLPResult:
        """이동 차단 (플래그만 설정)"""
        # 실제 차단은 Orchestrator에서 처리
        result.tags_applied.append('BLOCKED')
        return result
    
    def scan_directory(self, dir_path: str,
                       max_workers: int = 4) -> List[DLPResult]:
        """
        디렉토리 전체 DLP 스캔 (병렬)
        
        Args:
            dir_path: 스캔할 디렉토리
            max_workers: 병렬 워커 수
            
        Returns:
            List[DLPResult]: 스캔 결과 목록
        """
        path = Path(dir_path)
        if not path.is_dir():
            return []
        
        # 스캔 대상 파일 수집
        files_to_scan = [
            f for f in path.rglob('*')
            if f.is_file() and f.suffix.lower() in self.scannable_extensions
        ]
        
        results = []
        
        # 병렬 스캔
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.scan_file, str(f)): f
                for f in files_to_scan
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.is_sensitive:
                        results.append(result)
                except Exception as e:
                    print(f"Error scanning: {e}")
        
        return results
    
    def restore_from_quarantine(self, quarantine_file: str,
                                restore_path: Optional[str] = None) -> bool:
        """
        격리된 파일 복원
        
        Args:
            quarantine_file: 격리된 파일 경로
            restore_path: 복원할 경로 (None이면 원래 위치)
            
        Returns:
            bool: 성공 여부
        """
        q_path = Path(quarantine_file)
        
        if not q_path.exists():
            return False
        
        # 로그 파일에서 원래 경로 확인
        log_file = q_path.parent / f"{q_path.name}.log"
        
        if restore_path is None and log_file.exists():
            with open(log_file, 'r') as f:
                log_data = json.load(f)
                restore_path = log_data.get('original_path')
        
        if restore_path is None:
            return False
        
        # 복원
        restore = Path(restore_path)
        restore.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.move(str(q_path), str(restore))
        
        # 로그 파일 삭제
        if log_file.exists():
            log_file.unlink()
        
        return True
    
    def get_quarantine_list(self) -> List[Dict]:
        """격리된 파일 목록"""
        if not self.quarantine_path.exists():
            return []
        
        quarantined = []
        
        for log_file in self.quarantine_path.glob("*.log"):
            try:
                with open(log_file, 'r') as f:
                    log_data = json.load(f)
                
                file_name = log_file.stem  # .log 제거
                file_path = self.quarantine_path / file_name
                
                quarantined.append({
                    'file_name': file_name,
                    'quarantine_path': str(file_path),
                    'original_path': log_data.get('original_path'),
                    'quarantine_time': log_data.get('quarantine_time'),
                    'severity': log_data.get('severity'),
                    'exists': file_path.exists(),
                })
            except:
                continue
        
        return quarantined


if __name__ == "__main__":
    import sys
    
    print("🔒 DLP Scanner Test")
    print("=" * 50)
    
    dlp = DLPScanner()
    
    if len(sys.argv) > 1:
        target = sys.argv[1]
        
        if Path(target).is_file():
            # 단일 파일 스캔
            result = dlp.scan_file(target)
            
            print(f"\n📄 File: {result.file_path}")
            print(f"🔍 Sensitive: {result.is_sensitive}")
            print(f"⚠️ Severity: {result.severity.value}")
            
            if result.matches:
                print("\n📋 Matches:")
                for m in result.matches[:10]:
                    print(f"  [{m.severity.value}] {m.keyword} (line {m.line_number})")
        else:
            # 디렉토리 스캔
            results = dlp.scan_directory(target)
            
            print(f"\n📁 Scanned directory: {target}")
            print(f"🔍 Sensitive files found: {len(results)}")
            
            for r in results[:10]:
                print(f"\n  [{r.severity.value}] {r.file_path}")
                print(f"    Matches: {len(r.matches)}")
    else:
        print("Usage: python dlp.py <file_or_directory>")
