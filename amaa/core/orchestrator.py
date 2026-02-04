"""
AMAA v0.4 - Orchestrator (Workflow Controller)
파일 조직화 워크플로우 제어 및 미리보기 시스템

Step 3: 지능형 오케스트레이터
- shutil.move 실행 전 미리보기
- 사용자 승인 후 실행
- 배치 작업 관리
"""

import shutil
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from .undo import UndoManager, ActionType, BatchContext
from .mapmaker import MapMaker, FileInfo
from .perceiver import Perceiver, PerceptionResult


class OrganizeAction(Enum):
    """조직화 액션 타입"""
    MOVE = "move"
    COPY = "copy"
    RENAME = "rename"
    CREATE_DIR = "create_dir"
    TAG = "tag"
    SKIP = "skip"


@dataclass
class ProposedChange:
    """제안된 변경 사항"""
    action: OrganizeAction
    source_path: str
    destination_path: str
    reason: str
    confidence: float = 0.0
    new_filename: Optional[str] = None
    category: Optional[str] = None
    approved: bool = False
    executed: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'action': self.action.value,
            'source_path': self.source_path,
            'destination_path': self.destination_path,
            'reason': self.reason,
            'confidence': self.confidence,
            'new_filename': self.new_filename,
            'category': self.category,
            'approved': self.approved,
            'executed': self.executed,
            'error': self.error,
        }


@dataclass
class OrganizeSession:
    """조직화 세션"""
    session_id: str
    root_path: str
    created_at: str
    changes: List[ProposedChange] = field(default_factory=list)
    executed: bool = False
    batch_id: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'root_path': self.root_path,
            'created_at': self.created_at,
            'changes': [c.to_dict() for c in self.changes],
            'executed': self.executed,
            'batch_id': self.batch_id,
            'stats': self.stats,
        }


class Orchestrator:
    """
    파일 조직화 오케스트레이터
    
    분석 결과를 기반으로 파일 이동 계획을 수립하고,
    사용자 승인 후 안전하게 실행
    
    Usage:
        orchestrator = Orchestrator(config)
        
        # 1. 스캔 및 분석
        session = orchestrator.scan_and_analyze("/path/to/organize")
        
        # 2. 미리보기
        orchestrator.show_preview(session)
        
        # 3. 사용자 승인
        orchestrator.approve_all(session)
        
        # 4. 실행
        results = orchestrator.execute(session)
        
        # 5. 필요시 Undo
        orchestrator.undo_session(session)
    """
    
    def __init__(self, config=None, 
                 db_path: str = "~/.amaa/amaa.db",
                 dry_run: bool = True):
        """
        Args:
            config: AMAA Config 객체
            db_path: 데이터베이스 경로
            dry_run: 기본 Dry Run 모드 여부
        """
        self.config = config
        self.dry_run = dry_run
        
        # 컴포넌트 초기화
        self.undo_manager = UndoManager(db_path=db_path)
        self.map_maker = MapMaker(config=config)
        self.perceiver = Perceiver(config=config)
        
        # 현재 세션
        self._current_session: Optional[OrganizeSession] = None
        
        # 콜백 함수들
        self._progress_callback: Optional[Callable] = None
        self._confirm_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """진행 상황 콜백 설정"""
        self._progress_callback = callback
    
    def set_confirm_callback(self, callback: Callable[[ProposedChange], bool]) -> None:
        """확인 콜백 설정 (각 파일별 승인용)"""
        self._confirm_callback = callback
    
    def scan_and_analyze(self, root_path: str,
                         target_structure: Optional[str] = None) -> OrganizeSession:
        """
        디렉토리 스캔 및 분석 후 조직화 계획 생성
        
        Args:
            root_path: 조직화할 루트 경로
            target_structure: 목표 디렉토리 구조 (옵션)
            
        Returns:
            OrganizeSession: 조직화 세션
        """
        session = OrganizeSession(
            session_id=str(uuid.uuid4())[:8],
            root_path=root_path,
            created_at=datetime.now().isoformat(),
        )
        
        # 1. 디렉토리 스캔
        self._report_progress(0, 100, "Scanning directory...")
        tree = self.map_maker.scan(root_path, include_files=True)
        taxonomy = self.map_maker.extract_taxonomy()
        
        # LLM에게 전달할 컨텍스트
        context = self.map_maker.get_context_for_llm(max_depth=3)
        self.perceiver.set_directory_context(context)
        
        # 2. 파일별 분석 및 제안 생성
        files = list(self.map_maker.iter_files())
        total = len(files)
        
        for i, file_info in enumerate(files):
            self._report_progress(i + 1, total, f"Analyzing: {file_info.name}")
            
            # 파일 인식
            perception = self.perceiver.perceive(file_info.path)
            
            # 변경 제안 생성
            change = self._generate_proposal(file_info, perception, root_path)
            
            if change and change.action != OrganizeAction.SKIP:
                session.changes.append(change)
        
        # 3. 통계 계산
        session.stats = self._calculate_stats(session.changes)
        
        self._current_session = session
        return session
    
    def _generate_proposal(self, file_info: FileInfo, 
                          perception: PerceptionResult,
                          root_path: str) -> Optional[ProposedChange]:
        """파일에 대한 변경 제안 생성"""
        
        source = Path(file_info.path)
        
        # 이미 정리된 파일인지 확인
        if self._is_already_organized(file_info):
            return ProposedChange(
                action=OrganizeAction.SKIP,
                source_path=str(source),
                destination_path=str(source),
                reason="Already organized",
                confidence=1.0
            )
        
        # 새 경로 결정
        new_path, new_name, reason = self._determine_new_location(
            file_info, perception, root_path
        )
        
        if new_path == source:
            return None
        
        return ProposedChange(
            action=OrganizeAction.MOVE,
            source_path=str(source),
            destination_path=str(new_path),
            reason=reason,
            confidence=perception.confidence,
            new_filename=new_name,
            category=perception.suggested_category or file_info.category
        )
    
    def _is_already_organized(self, file_info: FileInfo) -> bool:
        """파일이 이미 정리되었는지 확인"""
        import re
        
        # ISO 8601 날짜 접두어가 있으면 정리된 것으로 간주
        date_pattern = r'^\d{4}-\d{2}-\d{2}'
        return bool(re.match(date_pattern, file_info.name))
    
    def _determine_new_location(self, file_info: FileInfo,
                                perception: PerceptionResult,
                                root_path: str) -> Tuple[Path, str, str]:
        """새 저장 위치 결정"""
        
        root = Path(root_path)
        source = Path(file_info.path)
        
        # 카테고리 폴더 결정
        category = perception.suggested_category or file_info.category or 'misc'
        category_folder = root / category.lower()
        
        # 날짜 접두어 추가
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        original_name = source.stem
        extension = source.suffix
        
        # 이미 날짜 접두어가 있으면 유지
        import re
        if re.match(r'^\d{4}-\d{2}-\d{2}', original_name):
            new_name = source.name
        else:
            new_name = f"{date_prefix}_{original_name}{extension}"
        
        new_path = category_folder / new_name
        
        # 중복 파일 처리
        counter = 1
        while new_path.exists():
            new_name = f"{date_prefix}_{original_name}_{counter}{extension}"
            new_path = category_folder / new_name
            counter += 1
        
        reason = f"Categorized as '{category}' based on content analysis"
        
        # LLM 제안이 있으면 사용
        if perception.suggested_path:
            try:
                llm_path = Path(perception.suggested_path)
                if llm_path.is_absolute():
                    new_path = llm_path / new_name
                    reason = f"LLM suggested: {perception.suggested_path}"
            except:
                pass
        
        return new_path, new_name, reason
    
    def _calculate_stats(self, changes: List[ProposedChange]) -> Dict[str, int]:
        """변경 통계 계산"""
        stats = {
            'total': len(changes),
            'move': 0,
            'copy': 0,
            'rename': 0,
            'skip': 0,
            'by_category': {}
        }
        
        for change in changes:
            action_key = change.action.value
            if action_key in stats:
                stats[action_key] += 1
            
            cat = change.category or 'unknown'
            if cat not in stats['by_category']:
                stats['by_category'][cat] = 0
            stats['by_category'][cat] += 1
        
        return stats
    
    def show_preview(self, session: Optional[OrganizeSession] = None) -> str:
        """
        변경 사항 미리보기 출력
        
        Returns:
            str: 미리보기 텍스트
        """
        session = session or self._current_session
        if not session:
            return "No session available. Run scan_and_analyze first."
        
        lines = [
            "=" * 60,
            f"📋 AMAA Organization Preview",
            f"Session: {session.session_id}",
            f"Root: {session.root_path}",
            f"Created: {session.created_at}",
            "=" * 60,
            "",
            f"📊 Summary:",
            f"  Total changes: {session.stats.get('total', 0)}",
            f"  Files to move: {session.stats.get('move', 0)}",
            f"  Files to skip: {session.stats.get('skip', 0)}",
            "",
            "📁 By Category:",
        ]
        
        for cat, count in session.stats.get('by_category', {}).items():
            lines.append(f"  {cat}: {count}")
        
        lines.extend(["", "📝 Proposed Changes:", "-" * 40])
        
        for i, change in enumerate(session.changes[:50], 1):  # 최대 50개
            status = "✅" if change.approved else "⏳"
            lines.append(
                f"{status} [{i}] {change.action.value.upper()}: "
                f"{Path(change.source_path).name}"
            )
            lines.append(f"     → {change.destination_path}")
            lines.append(f"     Reason: {change.reason}")
            lines.append(f"     Confidence: {change.confidence:.1%}")
            lines.append("")
        
        if len(session.changes) > 50:
            lines.append(f"... and {len(session.changes) - 50} more changes")
        
        return '\n'.join(lines)
    
    def approve_all(self, session: Optional[OrganizeSession] = None) -> int:
        """모든 변경 승인"""
        session = session or self._current_session
        if not session:
            return 0
        
        count = 0
        for change in session.changes:
            if change.action != OrganizeAction.SKIP:
                change.approved = True
                count += 1
        
        return count
    
    def approve_by_confidence(self, min_confidence: float = 0.7,
                             session: Optional[OrganizeSession] = None) -> int:
        """신뢰도 기준으로 승인"""
        session = session or self._current_session
        if not session:
            return 0
        
        count = 0
        for change in session.changes:
            if change.confidence >= min_confidence and change.action != OrganizeAction.SKIP:
                change.approved = True
                count += 1
        
        return count
    
    def approve_by_category(self, category: str,
                           session: Optional[OrganizeSession] = None) -> int:
        """카테고리별 승인"""
        session = session or self._current_session
        if not session:
            return 0
        
        count = 0
        for change in session.changes:
            if change.category == category and change.action != OrganizeAction.SKIP:
                change.approved = True
                count += 1
        
        return count
    
    def approve_single(self, index: int, 
                       session: Optional[OrganizeSession] = None) -> bool:
        """단일 변경 승인"""
        session = session or self._current_session
        if not session or index >= len(session.changes):
            return False
        
        session.changes[index].approved = True
        return True
    
    def reject_single(self, index: int,
                      session: Optional[OrganizeSession] = None) -> bool:
        """단일 변경 거부"""
        session = session or self._current_session
        if not session or index >= len(session.changes):
            return False
        
        session.changes[index].approved = False
        return True
    
    def execute(self, session: Optional[OrganizeSession] = None,
                dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """
        승인된 변경 사항 실행
        
        Args:
            session: 실행할 세션
            dry_run: Dry Run 모드 (None이면 기본값 사용)
            
        Returns:
            Dict: 실행 결과
        """
        session = session or self._current_session
        if not session:
            return {'error': 'No session available'}
        
        dry_run = dry_run if dry_run is not None else self.dry_run
        
        results = {
            'session_id': session.session_id,
            'dry_run': dry_run,
            'executed': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        # 승인된 변경만 필터링
        approved_changes = [c for c in session.changes if c.approved]
        
        if not approved_changes:
            results['error'] = 'No approved changes'
            return results
        
        # 배치 컨텍스트로 실행
        if not dry_run:
            with BatchContext(self.undo_manager) as batch:
                session.batch_id = batch.batch_id
                
                total = len(approved_changes)
                for i, change in enumerate(approved_changes):
                    self._report_progress(i + 1, total, f"Executing: {Path(change.source_path).name}")
                    
                    try:
                        success = self._execute_change(change, batch)
                        
                        if success:
                            change.executed = True
                            results['executed'] += 1
                        else:
                            results['failed'] += 1
                            
                    except Exception as e:
                        change.error = str(e)
                        results['failed'] += 1
                        results['errors'].append({
                            'file': change.source_path,
                            'error': str(e)
                        })
                        batch.mark_failure(str(e))
        else:
            # Dry Run - 실제 실행 없이 시뮬레이션
            results['executed'] = len(approved_changes)
            results['message'] = "Dry run completed. Use dry_run=False to execute."
        
        session.executed = not dry_run
        return results
    
    def _execute_change(self, change: ProposedChange, 
                        batch: BatchContext) -> bool:
        """단일 변경 실행"""
        
        if change.action == OrganizeAction.MOVE:
            src = Path(change.source_path)
            dst = Path(change.destination_path)
            
            # 대상 디렉토리 생성
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            # 액션 기록
            batch.record_move(str(src), str(dst))
            
            # 실제 이동
            shutil.move(str(src), str(dst))
            
            # 성공 표시
            batch.mark_success()
            return True
        
        elif change.action == OrganizeAction.COPY:
            src = Path(change.source_path)
            dst = Path(change.destination_path)
            
            dst.parent.mkdir(parents=True, exist_ok=True)
            batch.record_copy(str(src), str(dst))
            
            shutil.copy2(str(src), str(dst))
            
            batch.mark_success()
            return True
        
        elif change.action == OrganizeAction.RENAME:
            src = Path(change.source_path)
            dst = Path(change.destination_path)
            
            batch.record_move(str(src), str(dst))
            src.rename(dst)
            batch.mark_success()
            return True
        
        return False
    
    def undo_session(self, session: Optional[OrganizeSession] = None) -> List[Dict]:
        """세션의 모든 변경 Undo"""
        session = session or self._current_session
        
        if not session or not session.batch_id:
            return []
        
        undone = self.undo_manager.undo_batch(session.batch_id)
        
        return [action.to_dict() for action in undone]
    
    def undo_last(self) -> Optional[Dict]:
        """마지막 변경 Undo"""
        action = self.undo_manager.undo_last_action()
        return action.to_dict() if action else None
    
    def save_session(self, output_path: str,
                     session: Optional[OrganizeSession] = None) -> None:
        """세션을 JSON으로 저장"""
        session = session or self._current_session
        if not session:
            return
        
        path = Path(output_path).expanduser()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_session(self, input_path: str) -> OrganizeSession:
        """저장된 세션 로드"""
        path = Path(input_path).expanduser()
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        changes = [
            ProposedChange(
                action=OrganizeAction(c['action']),
                source_path=c['source_path'],
                destination_path=c['destination_path'],
                reason=c['reason'],
                confidence=c.get('confidence', 0),
                new_filename=c.get('new_filename'),
                category=c.get('category'),
                approved=c.get('approved', False),
                executed=c.get('executed', False),
                error=c.get('error'),
            )
            for c in data.get('changes', [])
        ]
        
        session = OrganizeSession(
            session_id=data['session_id'],
            root_path=data['root_path'],
            created_at=data['created_at'],
            changes=changes,
            executed=data.get('executed', False),
            batch_id=data.get('batch_id'),
            stats=data.get('stats', {})
        )
        
        self._current_session = session
        return session
    
    def _report_progress(self, current: int, total: int, message: str) -> None:
        """진행 상황 보고"""
        if self._progress_callback:
            self._progress_callback(current, total, message)
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        """작업 이력 조회"""
        history = self.undo_manager.get_history(limit=limit)
        return [action.to_dict() for action in history]
    
    def close(self) -> None:
        """리소스 정리"""
        self.undo_manager.close()


if __name__ == "__main__":
    import sys
    
    print("🔧 AMAA Orchestrator Test")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        target_path = "."
    
    # 오케스트레이터 생성
    orchestrator = Orchestrator(dry_run=True)
    
    # 진행 상황 콜백
    def progress(current, total, msg):
        print(f"[{current}/{total}] {msg}")
    
    orchestrator.set_progress_callback(progress)
    
    # 스캔 및 분석
    print(f"\n📂 Scanning: {target_path}")
    session = orchestrator.scan_and_analyze(target_path)
    
    # 미리보기
    print(orchestrator.show_preview())
    
    # Dry run 실행
    print("\n🏃 Executing (dry run)...")
    results = orchestrator.execute(dry_run=True)
    print(f"Results: {results}")
    
    orchestrator.close()
