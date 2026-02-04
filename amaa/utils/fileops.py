"""
AMAA v0.4 - FileOps
파일 작업 유틸리티
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime


class FileOps:
    """파일 작업 유틸리티"""
    
    @staticmethod
    def safe_move(src: str, dst: str, 
                  create_parents: bool = True) -> Tuple[bool, str]:
        """안전한 파일 이동"""
        try:
            src_path = Path(src)
            dst_path = Path(dst)
            
            if not src_path.exists():
                return False, f"Source not found: {src}"
            
            if create_parents:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(str(src_path), str(dst_path))
            return True, str(dst_path)
            
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def safe_copy(src: str, dst: str,
                  create_parents: bool = True) -> Tuple[bool, str]:
        """안전한 파일 복사"""
        try:
            src_path = Path(src)
            dst_path = Path(dst)
            
            if not src_path.exists():
                return False, f"Source not found: {src}"
            
            if create_parents:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(str(src_path), str(dst_path))
            return True, str(dst_path)
            
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_unique_path(path: str, separator: str = "_") -> str:
        """중복 없는 고유 경로 생성"""
        p = Path(path)
        if not p.exists():
            return path
        
        counter = 1
        stem = p.stem
        suffix = p.suffix
        parent = p.parent
        
        while True:
            new_path = parent / f"{stem}{separator}{counter}{suffix}"
            if not new_path.exists():
                return str(new_path)
            counter += 1
    
    @staticmethod
    def calculate_hash(path: str, algorithm: str = "md5") -> Optional[str]:
        """파일 해시 계산"""
        try:
            hash_func = hashlib.new(algorithm)
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except:
            return None
    
    @staticmethod
    def format_size(size: int) -> str:
        """파일 크기 포맷팅"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    @staticmethod
    def get_file_info(path: str) -> dict:
        """파일 정보 수집"""
        p = Path(path)
        if not p.exists():
            return {}
        
        stat = p.stat()
        return {
            'name': p.name,
            'path': str(p),
            'size': stat.st_size,
            'size_formatted': FileOps.format_size(stat.st_size),
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'extension': p.suffix.lower(),
            'is_hidden': p.name.startswith('.'),
        }
