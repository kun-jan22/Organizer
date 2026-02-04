"""
AMAA v0.4 - Database
SQLite 데이터베이스 관리
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class Database:
    """AMAA 데이터베이스 매니저"""
    
    def __init__(self, db_path: str = "~/.amaa/amaa.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    @contextmanager
    def connection(self):
        """데이터베이스 연결 컨텍스트"""
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
        with self.connection() as conn:
            cursor = conn.cursor()
            
            # 파일 인덱스 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_index (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT,
                    size INTEGER,
                    category TEXT,
                    keywords TEXT,
                    indexed_at TEXT,
                    modified_at TEXT
                )
            ''')
            
            # 설정 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            ''')
            
            # 인덱스
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_category ON file_index(category)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_extension ON file_index(extension)')
    
    def index_file(self, file_info: Dict[str, Any]) -> int:
        """파일 인덱싱"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO file_index 
                (path, name, extension, size, category, keywords, indexed_at, modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_info.get('path'),
                file_info.get('name'),
                file_info.get('extension'),
                file_info.get('size'),
                file_info.get('category'),
                json.dumps(file_info.get('keywords', [])),
                datetime.now().isoformat(),
                file_info.get('modified_at')
            ))
            return cursor.lastrowid
    
    def search_files(self, query: str, category: Optional[str] = None,
                     limit: int = 100) -> List[Dict]:
        """파일 검색"""
        with self.connection() as conn:
            cursor = conn.cursor()
            
            sql = "SELECT * FROM file_index WHERE (name LIKE ? OR keywords LIKE ?)"
            params = [f"%{query}%", f"%{query}%"]
            
            if category:
                sql += " AND category = ?"
                params.append(category)
            
            sql += " ORDER BY modified_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """설정 조회"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except:
                    return row['value']
            return default
    
    def set_setting(self, key: str, value: Any) -> None:
        """설정 저장"""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, json.dumps(value), datetime.now().isoformat()))
