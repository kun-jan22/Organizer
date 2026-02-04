"""
AMAA v0.4 - Organizer Agent
파일 조직화 실행 에이전트

Multi-Agent System의 조직화 담당
- 파일 이동/복사 실행
- 폴더 구조 생성
- 파일명 규칙 적용
"""

import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from ..core.undo import UndoManager, ActionType, BatchContext


@dataclass
class OrganizeTask:
    """조직화 작업"""
    source: str
    destination: str
    action: str = "move"  # move, copy, rename
    new_name: Optional[str] = None
    reason: str = ""
    approved: bool = False
    executed: bool = False
    error: Optional[str] = None


class OrganizerAgent:
    """
    파일 조직화 실행 에이전트
    
    분석 결과에 따라 파일을 이동/정리
    
    Usage:
        organizer = OrganizerAgent(db_path="~/.amaa/amaa.db")
        task = OrganizeTask(source="/path/file.txt", destination="/new/path/")
        organizer.execute_task(task)
    """
    
    def __init__(self, config=None, db_path: str = "~/.amaa/amaa.db"):
        """
        Args:
            config: AMAA Config 객체
            db_path: Undo 데이터베이스 경로
        """
        self.config = config
        self.undo_manager = UndoManager(db_path=db_path)
        
        # 파일명 규칙
        self.date_prefix = True
        self.date_format = "%Y-%m-%d"
        self.separator = "_"
        
        if config:
            self.date_prefix = config.naming.date_prefix
            self.date_format = config.naming.date_format
            self.separator = config.naming.separator
    
    def execute_task(self, task: OrganizeTask, 
                     dry_run: bool = False) -> OrganizeTask:
        """
        단일 작업 실행
        
        Args:
            task: 실행할 작업
            dry_run: 미리보기 모드
            
        Returns:
            OrganizeTask: 업데이트된 작업
        """
        try:
            src = Path(task.source)
            dst = Path(task.destination)
            
            if not src.exists():
                task.error = f"Source not found: {task.source}"
                return task
            
            # 새 파일명 결정
            if task.new_name:
                final_name = task.new_name
            else:
                final_name = self._generate_filename(src)
            
            # 대상 경로 결정
            if dst.suffix:  # 파일 경로로 지정된 경우
                final_path = dst
            else:  # 디렉토리로 지정된 경우
                final_path = dst / final_name
            
            # 중복 처리
            final_path = self._handle_duplicate(final_path)
            
            if dry_run:
                task.destination = str(final_path)
                return task
            
            # 대상 디렉토리 생성
            final_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 실행
            if task.action == "move":
                action = self.undo_manager.record_action(
                    ActionType.MOVE, str(src), str(final_path)
                )
                shutil.move(str(src), str(final_path))
                self.undo_manager.mark_executed(action.id)
                
            elif task.action == "copy":
                action = self.undo_manager.record_action(
                    ActionType.COPY, str(src), str(final_path)
                )
                shutil.copy2(str(src), str(final_path))
                self.undo_manager.mark_executed(action.id)
                
            elif task.action == "rename":
                action = self.undo_manager.record_action(
                    ActionType.RENAME, str(src), str(final_path)
                )
                src.rename(final_path)
                self.undo_manager.mark_executed(action.id)
            
            task.destination = str(final_path)
            task.executed = True
            
        except Exception as e:
            task.error = str(e)
        
        return task
    
    def execute_batch(self, tasks: List[OrganizeTask],
                      dry_run: bool = False,
                      progress_callback=None) -> List[OrganizeTask]:
        """
        여러 작업 일괄 실행
        
        Args:
            tasks: 작업 목록
            dry_run: 미리보기 모드
            progress_callback: 진행 콜백
            
        Returns:
            List[OrganizeTask]: 업데이트된 작업 목록
        """
        results = []
        total = len(tasks)
        
        if not dry_run:
            batch = BatchContext(self.undo_manager)
        
        try:
            for i, task in enumerate(tasks):
                if progress_callback:
                    progress_callback(i + 1, total, task.source)
                
                if task.approved:
                    result = self.execute_task(task, dry_run=dry_run)
                else:
                    task.error = "Not approved"
                    result = task
                
                results.append(result)
        except Exception as e:
            # 에러 발생 시 롤백
            if not dry_run:
                batch.rollback()
            raise
        
        return results
    
    def _generate_filename(self, source: Path) -> str:
        """파일명 생성 (날짜 접두어 포함)"""
        original_name = source.stem
        extension = source.suffix
        
        # 이미 날짜 접두어가 있는지 확인
        date_pattern = r'^\d{4}-\d{2}-\d{2}'
        if re.match(date_pattern, original_name):
            return source.name
        
        # 날짜 접두어 추가
        if self.date_prefix:
            date_str = datetime.now().strftime(self.date_format)
            return f"{date_str}{self.separator}{original_name}{extension}"
        
        return source.name
    
    def _handle_duplicate(self, path: Path) -> Path:
        """중복 파일 처리"""
        if not path.exists():
            return path
        
        counter = 1
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        
        while True:
            new_name = f"{stem}{self.separator}{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1
            
            if counter > 999:  # 안전장치
                raise ValueError(f"Too many duplicates: {path}")
    
    def create_folder_structure(self, base_path: str,
                                structure: Dict[str, List[str]]) -> List[str]:
        """
        폴더 구조 생성
        
        Args:
            base_path: 기본 경로
            structure: {'category': ['subfolder1', 'subfolder2']}
            
        Returns:
            List[str]: 생성된 폴더 경로들
        """
        created = []
        base = Path(base_path)
        
        for category, subfolders in structure.items():
            category_path = base / category
            category_path.mkdir(parents=True, exist_ok=True)
            created.append(str(category_path))
            
            for subfolder in subfolders:
                sub_path = category_path / subfolder
                sub_path.mkdir(exist_ok=True)
                created.append(str(sub_path))
        
        return created
    
    def undo_last(self) -> Optional[Dict]:
        """마지막 작업 취소"""
        action = self.undo_manager.undo_last_action()
        return action.to_dict() if action else None
    
    def undo_n(self, n: int) -> List[Dict]:
        """N개 작업 취소"""
        actions = self.undo_manager.undo_n_actions(n)
        return [a.to_dict() for a in actions]
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        """작업 이력 조회"""
        history = self.undo_manager.get_history(limit=limit)
        return [h.to_dict() for h in history]
    
    def close(self):
        """리소스 정리"""
        self.undo_manager.close()


if __name__ == "__main__":
    import sys
    
    print("📦 AMAA Organizer Agent Test")
    print("=" * 50)
    
    organizer = OrganizerAgent()
    
    # 테스트 작업
    if len(sys.argv) > 2:
        src = sys.argv[1]
        dst = sys.argv[2]
        
        task = OrganizeTask(
            source=src,
            destination=dst,
            action="move",
            approved=True
        )
        
        print(f"\n📄 Source: {src}")
        print(f"📁 Destination: {dst}")
        
        # Dry run 먼저
        print("\n🔍 Dry Run:")
        result = organizer.execute_task(task, dry_run=True)
        print(f"  → {result.destination}")
        
        # 실제 실행 여부 확인
        confirm = input("\n Execute? (y/n): ")
        if confirm.lower() == 'y':
            result = organizer.execute_task(task, dry_run=False)
            if result.executed:
                print(f"✅ Moved to: {result.destination}")
            else:
                print(f"❌ Error: {result.error}")
    else:
        print("Usage: python organizer.py <source> <destination>")
    
    organizer.close()
