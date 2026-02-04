"""
AMAA v0.4 - History Tracker
파일 이동/이름변경 히스토리 추적

Features:
- 모든 파일 작업 기록
- 원본 위치/이름 추적
- 변경 전/후 이름 기록
- 검색 및 필터링
- 보고서 생성
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from enum import Enum


class ActionType(Enum):
    """작업 유형"""
    MOVE = "MOVE"
    RENAME = "RENAME"
    COPY = "COPY"
    DELETE = "DELETE"
    CREATE = "CREATE"
    EMAIL_ATTACHMENT = "EMAIL_ATTACHMENT"
    DESKTOP_AUTO_ORGANIZE = "DESKTOP_AUTO_ORGANIZE"


@dataclass
class HistoryRecord:
    """히스토리 레코드"""
    id: Optional[int] = None
    timestamp: str = ""
    action_type: str = ""
    
    # 원본 정보
    original_path: str = ""
    original_name: str = ""
    original_folder: str = ""
    
    # 변경 후 정보
    new_path: str = ""
    new_name: str = ""
    new_folder: str = ""
    
    # 메타데이터
    file_size: int = 0
    file_type: str = ""
    source: str = ""  # "desktop", "email", "manual"
    
    # 추가 정보
    metadata: str = "{}"  # JSON
    
    # 상태
    is_undone: bool = False
    undone_at: Optional[str] = None


class HistoryTracker:
    """
    파일 히스토리 추적기
    
    모든 파일 작업을 기록하고 검색할 수 있습니다.
    
    Usage:
        tracker = HistoryTracker()
        
        # 기록
        tracker.record_move(
            original_path="/Users/Desktop/report.pdf",
            new_path="/Users/Documents/2025-02/report.pdf"
        )
        
        # 검색
        records = tracker.search("report")
        
        # 히스토리 조회
        history = tracker.get_history(days=7)
    """
    
    def __init__(self, db_path: str = "~/.amaa/history.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    @contextmanager
    def _connection(self):
        """데이터베이스 연결"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_schema(self):
        """스키마 초기화"""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    
                    original_path TEXT,
                    original_name TEXT,
                    original_folder TEXT,
                    
                    new_path TEXT,
                    new_name TEXT,
                    new_folder TEXT,
                    
                    file_size INTEGER DEFAULT 0,
                    file_type TEXT,
                    source TEXT,
                    
                    metadata TEXT DEFAULT '{}',
                    
                    is_undone INTEGER DEFAULT 0,
                    undone_at TEXT
                )
            ''')
            
            # 인덱스
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON history(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_action_type ON history(action_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_original_name ON history(original_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_new_name ON history(new_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON history(source)')
    
    def record(self, record: HistoryRecord) -> int:
        """히스토리 기록"""
        if not record.timestamp:
            record.timestamp = datetime.now().isoformat()
        
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO history (
                    timestamp, action_type,
                    original_path, original_name, original_folder,
                    new_path, new_name, new_folder,
                    file_size, file_type, source,
                    metadata, is_undone, undone_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.timestamp, record.action_type,
                record.original_path, record.original_name, record.original_folder,
                record.new_path, record.new_name, record.new_folder,
                record.file_size, record.file_type, record.source,
                record.metadata, int(record.is_undone), record.undone_at
            ))
            return cursor.lastrowid
    
    def record_move(self, original_path: str, new_path: str,
                    source: str = "manual",
                    metadata: Optional[Dict] = None) -> int:
        """파일 이동 기록"""
        orig = Path(original_path)
        new = Path(new_path)
        
        record = HistoryRecord(
            action_type=ActionType.MOVE.value,
            original_path=str(orig),
            original_name=orig.name,
            original_folder=str(orig.parent),
            new_path=str(new),
            new_name=new.name,
            new_folder=str(new.parent),
            file_type=orig.suffix.lower(),
            source=source,
            metadata=json.dumps(metadata or {})
        )
        
        # 파일 크기
        if new.exists():
            record.file_size = new.stat().st_size
        
        return self.record(record)
    
    def record_rename(self, original_path: str, new_name: str,
                      source: str = "manual",
                      metadata: Optional[Dict] = None) -> int:
        """이름 변경 기록"""
        orig = Path(original_path)
        new = orig.parent / new_name
        
        record = HistoryRecord(
            action_type=ActionType.RENAME.value,
            original_path=str(orig),
            original_name=orig.name,
            original_folder=str(orig.parent),
            new_path=str(new),
            new_name=new_name,
            new_folder=str(orig.parent),
            file_type=orig.suffix.lower(),
            source=source,
            metadata=json.dumps(metadata or {})
        )
        
        return self.record(record)
    
    def record_email_attachment(self, sender: str, subject: str,
                                 original_filename: str, saved_path: str,
                                 gdrive_id: Optional[str] = None) -> int:
        """이메일 첨부파일 저장 기록"""
        saved = Path(saved_path)
        
        record = HistoryRecord(
            action_type=ActionType.EMAIL_ATTACHMENT.value,
            original_path=f"email:{sender}",
            original_name=original_filename,
            original_folder="email",
            new_path=str(saved),
            new_name=saved.name,
            new_folder=str(saved.parent),
            file_type=saved.suffix.lower(),
            source="email",
            metadata=json.dumps({
                'sender': sender,
                'subject': subject,
                'gdrive_id': gdrive_id
            })
        )
        
        if saved.exists():
            record.file_size = saved.stat().st_size
        
        return self.record(record)
    
    def record_desktop_organize(self, original_path: str, new_path: str,
                                 category: str,
                                 metadata: Optional[Dict] = None) -> int:
        """바탕화면 자동 정리 기록"""
        orig = Path(original_path)
        new = Path(new_path)
        
        meta = metadata or {}
        meta['category'] = category
        
        record = HistoryRecord(
            action_type=ActionType.DESKTOP_AUTO_ORGANIZE.value,
            original_path=str(orig),
            original_name=orig.name,
            original_folder=str(orig.parent),
            new_path=str(new),
            new_name=new.name,
            new_folder=str(new.parent),
            file_type=orig.suffix.lower(),
            source="desktop",
            metadata=json.dumps(meta)
        )
        
        if new.exists():
            record.file_size = new.stat().st_size
        
        return self.record(record)
    
    def get_history(self, days: Optional[int] = None,
                    action_type: Optional[str] = None,
                    source: Optional[str] = None,
                    limit: int = 100) -> List[HistoryRecord]:
        """히스토리 조회"""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            sql = "SELECT * FROM history WHERE 1=1"
            params = []
            
            if days:
                from_date = datetime.now().replace(
                    hour=0, minute=0, second=0
                )
                from_date = from_date.isoformat()
                sql += f" AND timestamp >= ?"
                params.append(from_date)
            
            if action_type:
                sql += " AND action_type = ?"
                params.append(action_type)
            
            if source:
                sql += " AND source = ?"
                params.append(source)
            
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            
            records = []
            for row in cursor.fetchall():
                records.append(HistoryRecord(
                    id=row['id'],
                    timestamp=row['timestamp'],
                    action_type=row['action_type'],
                    original_path=row['original_path'],
                    original_name=row['original_name'],
                    original_folder=row['original_folder'],
                    new_path=row['new_path'],
                    new_name=row['new_name'],
                    new_folder=row['new_folder'],
                    file_size=row['file_size'],
                    file_type=row['file_type'],
                    source=row['source'],
                    metadata=row['metadata'],
                    is_undone=bool(row['is_undone']),
                    undone_at=row['undone_at']
                ))
            
            return records
    
    def search(self, query: str, limit: int = 50) -> List[HistoryRecord]:
        """파일명으로 검색"""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM history 
                WHERE original_name LIKE ? OR new_name LIKE ? OR original_path LIKE ? OR new_path LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit))
            
            records = []
            for row in cursor.fetchall():
                records.append(HistoryRecord(
                    id=row['id'],
                    timestamp=row['timestamp'],
                    action_type=row['action_type'],
                    original_path=row['original_path'],
                    original_name=row['original_name'],
                    original_folder=row['original_folder'],
                    new_path=row['new_path'],
                    new_name=row['new_name'],
                    new_folder=row['new_folder'],
                    file_size=row['file_size'],
                    file_type=row['file_type'],
                    source=row['source'],
                    metadata=row['metadata'],
                    is_undone=bool(row['is_undone']),
                    undone_at=row['undone_at']
                ))
            
            return records
    
    def get_file_history(self, filename: str) -> List[HistoryRecord]:
        """특정 파일의 전체 이력 조회"""
        return self.search(filename, limit=100)
    
    def mark_undone(self, record_id: int):
        """작업 취소 표시"""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE history 
                SET is_undone = 1, undone_at = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), record_id))
    
    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """통계 조회"""
        with self._connection() as conn:
            cursor = conn.cursor()
            
            from_date = datetime.now().replace(
                hour=0, minute=0, second=0
            )
            
            # 전체 카운트
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(file_size) as total_size
                FROM history
            ''')
            row = cursor.fetchone()
            total = row['total']
            total_size = row['total_size'] or 0
            
            # 액션 타입별
            cursor.execute('''
                SELECT action_type, COUNT(*) as count
                FROM history
                GROUP BY action_type
            ''')
            by_action = {row['action_type']: row['count'] for row in cursor.fetchall()}
            
            # 소스별
            cursor.execute('''
                SELECT source, COUNT(*) as count
                FROM history
                GROUP BY source
            ''')
            by_source = {row['source']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total_records': total,
                'total_size_bytes': total_size,
                'total_size_formatted': self._format_size(total_size),
                'by_action_type': by_action,
                'by_source': by_source
            }
    
    def _format_size(self, size: int) -> str:
        """파일 크기 포맷팅"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def export_report(self, output_path: str,
                      days: Optional[int] = None,
                      format: str = "json") -> str:
        """히스토리 보고서 내보내기"""
        records = self.get_history(days=days, limit=10000)
        
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "json":
            data = [asdict(r) for r in records]
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == "csv":
            import csv
            with open(output, 'w', encoding='utf-8', newline='') as f:
                if records:
                    writer = csv.DictWriter(f, fieldnames=asdict(records[0]).keys())
                    writer.writeheader()
                    for r in records:
                        writer.writerow(asdict(r))
        
        elif format == "md":
            with open(output, 'w', encoding='utf-8') as f:
                f.write("# AMAA File History Report\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n")
                f.write(f"Total Records: {len(records)}\n\n")
                
                f.write("## Recent Activity\n\n")
                f.write("| Time | Action | Original | New | Source |\n")
                f.write("|------|--------|----------|-----|--------|\n")
                
                for r in records[:100]:
                    time_str = r.timestamp[:16] if r.timestamp else ""
                    f.write(f"| {time_str} | {r.action_type} | {r.original_name} | {r.new_name} | {r.source} |\n")
        
        return str(output)


# 전역 트래커 인스턴스
_tracker: Optional[HistoryTracker] = None


def get_tracker() -> HistoryTracker:
    """전역 트래커 가져오기"""
    global _tracker
    if _tracker is None:
        _tracker = HistoryTracker()
    return _tracker


if __name__ == "__main__":
    print("📜 AMAA History Tracker Test")
    print("=" * 50)
    
    tracker = HistoryTracker()
    
    # 테스트 기록
    tracker.record_move(
        "/Users/Desktop/test.pdf",
        "/Users/Documents/2025-02/test.pdf",
        source="desktop"
    )
    
    tracker.record_email_attachment(
        sender="sender@example.com",
        subject="Test Email",
        original_filename="attachment.pdf",
        saved_path="/Users/Downloads/EmailAttachments/2025-02-04_attachment.pdf"
    )
    
    # 히스토리 조회
    history = tracker.get_history(limit=10)
    
    print(f"\n최근 기록 ({len(history)}개):")
    for h in history:
        print(f"  [{h.action_type}] {h.original_name} → {h.new_name}")
    
    # 통계
    stats = tracker.get_statistics()
    print(f"\n📊 통계:")
    print(f"  총 기록: {stats['total_records']}")
    print(f"  총 크기: {stats['total_size_formatted']}")
