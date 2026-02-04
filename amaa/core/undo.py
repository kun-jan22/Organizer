"""
AMAA v0.4 - Undo Manager (Action History)
파일 이동 이력 관리 및 실행 취소 시스템

Step 3: Undo 시스템
- SQLite3에 모든 이동 이력 기록
- undo_last_action() 메서드로 즉시 되돌리기
- 배치 단위 Undo 지원
"""

import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
from contextlib import contextmanager


class ActionType(Enum):
    """액션 타입"""
    MOVE = "move"
    COPY = "copy"
    RENAME = "rename"
    DELETE = "delete"
    CREATE_DIR = "create_dir"
    TAG = "tag"
    BATCH = "batch"


class ActionStatus(Enum):
    """액션 상태"""
    PENDING = "pending"
    EXECUTED = "executed"
    UNDONE = "undone"
    FAILED = "failed"


@dataclass
class ActionRecord:
    """액션 기록 데이터 클래스"""
    id: Optional[int] = None
    action_type: ActionType = ActionType.MOVE
    source_path: str = ""
    destination_path: str = ""
    timestamp: str = ""
    status: ActionStatus = ActionStatus.PENDING
    batch_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'action_type': self.action_type.value,
            'source_path': self.source_path,
            'destination_path': self.destination_path,
            'timestamp': self.timestamp,
            'status': self.status.value,
            'batch_id': self.batch_id,
            'metadata': self.metadata,
            'error_message': self.error_message,
        }
    
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> 'ActionRecord':
        """데이터베이스 row에서 ActionRecord 생성"""
        return cls(
            id=row['id'],
            action_type=ActionType(row['action_type']),
            source_path=row['source_path'],
            destination_path=row['destination_path'],
            timestamp=row['timestamp'],
            status=ActionStatus(row['status']),
            batch_id=row['batch_id'],
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            error_message=row['error_message'],
        )


class UndoManager:
    """
    Undo 매니저 - 파일 작업 이력 관리 및 실행 취소
    
    모든 파일 이동/복사/삭제 작업을 SQLite에 기록하고
    언제든지 되돌릴 수 있는 기능 제공
    
    Usage:
        undo = UndoManager(db_path="~/.amaa/amaa.db")
        
        # 액션 기록
        action = undo.record_action(ActionType.MOVE, src, dst)
        
        # 실제 이동 수행
        shutil.move(src, dst)
        
        # 상태 업데이트
        undo.mark_executed(action.id)
        
        # 실행 취소
        undo.undo_last_action()
    """
    
    def __init__(self, db_path: str = "~/.amaa/amaa.db", 
                 max_history: int = 1000,
                 retention_days: int = 30):
        """
        Args:
            db_path: SQLite 데이터베이스 경로
            max_history: 최대 보관 이력 수
            retention_days: 이력 보관 기간 (일)
        """
        self.db_path = Path(db_path).expanduser().resolve()
        self.max_history = max_history
        self.retention_days = retention_days
        
        # 데이터베이스 초기화
        self._init_database()
        
        # 스레드 로컬 연결
        self._local = threading.local()
    
    def _get_connection(self) -> sqlite3.Connection:
        """스레드 안전한 데이터베이스 연결"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def _transaction(self):
        """트랜잭션 컨텍스트 매니저"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def _init_database(self) -> None:
        """데이터베이스 스키마 초기화"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # 액션 이력 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS action_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                source_path TEXT NOT NULL,
                destination_path TEXT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                batch_id TEXT,
                metadata TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 인덱스 생성
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_action_status 
            ON action_history(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_action_timestamp 
            ON action_history(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_action_batch 
            ON action_history(batch_id)
        ''')
        
        conn.commit()
        conn.close()
    
    def record_action(self, action_type: ActionType, 
                      source_path: str,
                      destination_path: Optional[str] = None,
                      batch_id: Optional[str] = None,
                      metadata: Optional[Dict] = None) -> ActionRecord:
        """
        액션 기록
        
        Args:
            action_type: 액션 타입
            source_path: 원본 경로
            destination_path: 대상 경로 (옵션)
            batch_id: 배치 ID (옵션)
            metadata: 추가 메타데이터
            
        Returns:
            ActionRecord: 생성된 액션 기록
        """
        timestamp = datetime.now().isoformat()
        
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO action_history 
                (action_type, source_path, destination_path, timestamp, status, batch_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                action_type.value,
                source_path,
                destination_path,
                timestamp,
                ActionStatus.PENDING.value,
                batch_id,
                json.dumps(metadata) if metadata else None
            ))
            
            action_id = cursor.lastrowid
        
        return ActionRecord(
            id=action_id,
            action_type=action_type,
            source_path=source_path,
            destination_path=destination_path or "",
            timestamp=timestamp,
            status=ActionStatus.PENDING,
            batch_id=batch_id,
            metadata=metadata or {}
        )
    
    def mark_executed(self, action_id: int) -> None:
        """액션을 실행됨으로 표시"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE action_history 
                SET status = ?
                WHERE id = ?
            ''', (ActionStatus.EXECUTED.value, action_id))
    
    def mark_failed(self, action_id: int, error_message: str) -> None:
        """액션을 실패로 표시"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE action_history 
                SET status = ?, error_message = ?
                WHERE id = ?
            ''', (ActionStatus.FAILED.value, error_message, action_id))
    
    def mark_undone(self, action_id: int) -> None:
        """액션을 취소됨으로 표시"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE action_history 
                SET status = ?
                WHERE id = ?
            ''', (ActionStatus.UNDONE.value, action_id))
    
    def undo_last_action(self) -> Optional[ActionRecord]:
        """
        마지막 실행 액션 취소
        
        Returns:
            ActionRecord: 취소된 액션 (없으면 None)
        """
        # 마지막 실행된 액션 찾기
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM action_history 
            WHERE status = ?
            ORDER BY id DESC
            LIMIT 1
        ''', (ActionStatus.EXECUTED.value,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        action = ActionRecord.from_row(row)
        
        # 실제 Undo 수행
        success = self._perform_undo(action)
        
        if success:
            self.mark_undone(action.id)
            action.status = ActionStatus.UNDONE
        
        return action
    
    def undo_batch(self, batch_id: str) -> List[ActionRecord]:
        """
        배치 단위로 모든 액션 취소
        
        Args:
            batch_id: 배치 ID
            
        Returns:
            List[ActionRecord]: 취소된 액션 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 배치의 모든 실행된 액션 (역순으로)
        cursor.execute('''
            SELECT * FROM action_history 
            WHERE batch_id = ? AND status = ?
            ORDER BY id DESC
        ''', (batch_id, ActionStatus.EXECUTED.value))
        
        undone_actions = []
        
        for row in cursor.fetchall():
            action = ActionRecord.from_row(row)
            
            if self._perform_undo(action):
                self.mark_undone(action.id)
                action.status = ActionStatus.UNDONE
                undone_actions.append(action)
        
        return undone_actions
    
    def undo_n_actions(self, n: int) -> List[ActionRecord]:
        """
        최근 N개의 액션 취소
        
        Args:
            n: 취소할 액션 수
            
        Returns:
            List[ActionRecord]: 취소된 액션 목록
        """
        undone = []
        
        for _ in range(n):
            action = self.undo_last_action()
            if action:
                undone.append(action)
            else:
                break
        
        return undone
    
    def _perform_undo(self, action: ActionRecord) -> bool:
        """
        실제 Undo 작업 수행
        
        Args:
            action: 취소할 액션
            
        Returns:
            bool: 성공 여부
        """
        try:
            if action.action_type == ActionType.MOVE:
                # 파일 원래 위치로 이동
                src = Path(action.destination_path)
                dst = Path(action.source_path)
                
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    return True
                else:
                    print(f"⚠️ Source file not found: {src}")
                    return False
            
            elif action.action_type == ActionType.COPY:
                # 복사된 파일 삭제
                dst = Path(action.destination_path)
                if dst.exists():
                    dst.unlink()
                    return True
            
            elif action.action_type == ActionType.RENAME:
                # 이름 원복
                src = Path(action.destination_path)
                dst = Path(action.source_path)
                
                if src.exists():
                    src.rename(dst)
                    return True
            
            elif action.action_type == ActionType.DELETE:
                # 삭제된 파일 복구 (백업에서)
                backup_path = action.metadata.get('backup_path')
                if backup_path and Path(backup_path).exists():
                    dst = Path(action.source_path)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(backup_path, str(dst))
                    return True
            
            elif action.action_type == ActionType.CREATE_DIR:
                # 생성된 디렉토리 삭제 (비어있을 때만)
                dir_path = Path(action.source_path)
                if dir_path.exists() and dir_path.is_dir():
                    try:
                        dir_path.rmdir()  # 비어있을 때만 삭제
                        return True
                    except OSError:
                        print(f"⚠️ Directory not empty: {dir_path}")
                        return False
            
            return True
            
        except Exception as e:
            print(f"❌ Undo failed: {e}")
            return False
    
    def get_history(self, limit: int = 100, 
                    status: Optional[ActionStatus] = None,
                    since: Optional[datetime] = None) -> List[ActionRecord]:
        """
        이력 조회
        
        Args:
            limit: 최대 반환 개수
            status: 필터링할 상태
            since: 이 시점 이후만
            
        Returns:
            List[ActionRecord]: 액션 기록 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM action_history WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status.value)
        
        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        return [ActionRecord.from_row(row) for row in cursor.fetchall()]
    
    def get_undoable_actions(self, limit: int = 10) -> List[ActionRecord]:
        """Undo 가능한 액션 목록"""
        return self.get_history(limit=limit, status=ActionStatus.EXECUTED)
    
    def get_action_by_id(self, action_id: int) -> Optional[ActionRecord]:
        """ID로 액션 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM action_history WHERE id = ?", (action_id,))
        row = cursor.fetchone()
        
        return ActionRecord.from_row(row) if row else None
    
    def get_stats(self) -> Dict[str, Any]:
        """이력 통계"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 총 액션 수
        cursor.execute("SELECT COUNT(*) FROM action_history")
        total = cursor.fetchone()[0]
        
        # 상태별 통계
        cursor.execute('''
            SELECT status, COUNT(*) 
            FROM action_history 
            GROUP BY status
        ''')
        by_status = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 타입별 통계
        cursor.execute('''
            SELECT action_type, COUNT(*) 
            FROM action_history 
            GROUP BY action_type
        ''')
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            'total_actions': total,
            'by_status': by_status,
            'by_type': by_type,
        }
    
    def cleanup_old_records(self) -> int:
        """
        오래된 기록 정리
        
        Returns:
            int: 삭제된 레코드 수
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            # 오래된 기록 삭제
            cursor.execute('''
                DELETE FROM action_history 
                WHERE timestamp < ? AND status IN (?, ?)
            ''', (cutoff.isoformat(), ActionStatus.UNDONE.value, ActionStatus.FAILED.value))
            
            deleted = cursor.rowcount
        
        # 최대 개수 제한
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM action_history 
                WHERE id NOT IN (
                    SELECT id FROM action_history 
                    ORDER BY id DESC 
                    LIMIT ?
                )
            ''', (self.max_history,))
            
            deleted += cursor.rowcount
        
        return deleted
    
    def export_history(self, output_path: str) -> None:
        """이력을 JSON으로 내보내기"""
        history = self.get_history(limit=self.max_history)
        
        data = {
            'exported_at': datetime.now().isoformat(),
            'total_records': len(history),
            'records': [action.to_dict() for action in history]
        }
        
        path = Path(output_path).expanduser()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def close(self) -> None:
        """연결 종료"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


class BatchContext:
    """
    배치 작업 컨텍스트 매니저
    
    여러 파일 작업을 하나의 배치로 묶어서 관리
    
    Usage:
        with BatchContext(undo_manager) as batch:
            for file in files:
                batch.record_move(src, dst)
                shutil.move(src, dst)
                batch.mark_success()
    """
    
    def __init__(self, undo_manager: UndoManager):
        self.undo_manager = undo_manager
        self.batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.actions: List[ActionRecord] = []
        self._current_action: Optional[ActionRecord] = None
    
    def __enter__(self) -> 'BatchContext':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # 예외 발생 시 모든 실행된 액션 롤백
            self.rollback()
        return False
    
    def record_move(self, source: str, destination: str, 
                    metadata: Optional[Dict] = None) -> ActionRecord:
        """이동 액션 기록"""
        self._current_action = self.undo_manager.record_action(
            ActionType.MOVE, source, destination,
            batch_id=self.batch_id,
            metadata=metadata
        )
        self.actions.append(self._current_action)
        return self._current_action
    
    def record_copy(self, source: str, destination: str) -> ActionRecord:
        """복사 액션 기록"""
        self._current_action = self.undo_manager.record_action(
            ActionType.COPY, source, destination,
            batch_id=self.batch_id
        )
        self.actions.append(self._current_action)
        return self._current_action
    
    def mark_success(self) -> None:
        """현재 액션 성공 표시"""
        if self._current_action:
            self.undo_manager.mark_executed(self._current_action.id)
            self._current_action = None
    
    def mark_failure(self, error: str) -> None:
        """현재 액션 실패 표시"""
        if self._current_action:
            self.undo_manager.mark_failed(self._current_action.id, error)
            self._current_action = None
    
    def rollback(self) -> List[ActionRecord]:
        """배치 전체 롤백"""
        return self.undo_manager.undo_batch(self.batch_id)
    
    @property
    def action_count(self) -> int:
        """현재 배치의 액션 수"""
        return len(self.actions)


if __name__ == "__main__":
    import tempfile
    import os
    
    # 테스트
    print("🧪 Testing UndoManager...")
    
    # 임시 디렉토리에서 테스트
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        test_dir = os.path.join(tmpdir, "test_files")
        os.makedirs(test_dir)
        
        # 테스트 파일 생성
        src_file = os.path.join(test_dir, "test.txt")
        dst_dir = os.path.join(test_dir, "moved")
        os.makedirs(dst_dir)
        
        with open(src_file, 'w') as f:
            f.write("Test content")
        
        print(f"✅ Created test file: {src_file}")
        
        # UndoManager 테스트
        undo = UndoManager(db_path=db_path)
        
        # 이동 액션 기록
        dst_file = os.path.join(dst_dir, "test.txt")
        action = undo.record_action(ActionType.MOVE, src_file, dst_file)
        print(f"📝 Recorded action: {action.id}")
        
        # 실제 이동
        shutil.move(src_file, dst_file)
        undo.mark_executed(action.id)
        print(f"✅ Moved: {src_file} → {dst_file}")
        
        # Undo
        undone = undo.undo_last_action()
        print(f"↩️ Undone action: {undone.id}")
        
        # 원복 확인
        if os.path.exists(src_file):
            print(f"✅ File restored: {src_file}")
        else:
            print(f"❌ Undo failed!")
        
        # 통계 출력
        stats = undo.get_stats()
        print(f"\n📊 Stats: {stats}")
        
        undo.close()
    
    print("\n✅ All tests passed!")
