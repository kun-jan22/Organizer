"""
AMAA v0.4 - Reviewer Agent
조직화 결과 검토 및 피드백 에이전트

Multi-Agent System의 검토 담당
- 조직화 결과 품질 평가
- 개선 제안 생성
- 학습 피드백 수집
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ..core.perceiver import OllamaClient


@dataclass
class ReviewItem:
    """검토 항목"""
    file_path: str
    original_path: str
    action_taken: str
    is_correct: Optional[bool] = None
    user_feedback: Optional[str] = None
    suggested_correction: Optional[str] = None
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'original_path': self.original_path,
            'action_taken': self.action_taken,
            'is_correct': self.is_correct,
            'user_feedback': self.user_feedback,
            'suggested_correction': self.suggested_correction,
            'timestamp': self.timestamp,
        }


@dataclass
class ReviewReport:
    """검토 보고서"""
    session_id: str
    reviewed_at: str
    total_items: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    pending_count: int = 0
    accuracy_rate: float = 0.0
    items: List[ReviewItem] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'reviewed_at': self.reviewed_at,
            'total_items': self.total_items,
            'correct_count': self.correct_count,
            'incorrect_count': self.incorrect_count,
            'pending_count': self.pending_count,
            'accuracy_rate': self.accuracy_rate,
            'items': [i.to_dict() for i in self.items],
            'recommendations': self.recommendations,
        }


class ReviewerAgent:
    """
    조직화 결과 검토 에이전트
    
    실행된 조직화 결과를 평가하고 피드백 수집
    
    Usage:
        reviewer = ReviewerAgent(config)
        report = reviewer.create_review(session)
        
        # 사용자 피드백 수집
        reviewer.mark_correct(report.items[0])
        reviewer.mark_incorrect(report.items[1], "Should be in Projects folder")
        
        # 보고서 생성
        summary = reviewer.generate_summary(report)
    """
    
    def __init__(self, config=None):
        """
        Args:
            config: AMAA Config 객체
        """
        self.config = config
        
        # LLM 클라이언트 (피드백 분석용)
        if config:
            self.ollama = OllamaClient(
                base_url=config.ollama.base_url,
                model=config.ollama.model
            )
        else:
            self.ollama = OllamaClient()
        
        # 피드백 저장소
        self._feedback_history: List[ReviewItem] = []
    
    def create_review(self, session_data: Dict[str, Any]) -> ReviewReport:
        """
        세션 결과로부터 검토 보고서 생성
        
        Args:
            session_data: 조직화 세션 데이터
            
        Returns:
            ReviewReport: 검토 보고서
        """
        report = ReviewReport(
            session_id=session_data.get('session_id', 'unknown'),
            reviewed_at=datetime.now().isoformat()
        )
        
        changes = session_data.get('changes', [])
        
        for change in changes:
            if change.get('executed'):
                item = ReviewItem(
                    file_path=change.get('destination_path', ''),
                    original_path=change.get('source_path', ''),
                    action_taken=change.get('action', 'unknown'),
                    timestamp=datetime.now().isoformat()
                )
                report.items.append(item)
                report.total_items += 1
                report.pending_count += 1
        
        return report
    
    def mark_correct(self, item: ReviewItem) -> None:
        """항목을 올바름으로 표시"""
        item.is_correct = True
        self._feedback_history.append(item)
    
    def mark_incorrect(self, item: ReviewItem, 
                       feedback: str,
                       correction: Optional[str] = None) -> None:
        """항목을 잘못됨으로 표시"""
        item.is_correct = False
        item.user_feedback = feedback
        item.suggested_correction = correction
        self._feedback_history.append(item)
    
    def update_report_stats(self, report: ReviewReport) -> ReviewReport:
        """보고서 통계 업데이트"""
        report.correct_count = sum(1 for i in report.items if i.is_correct is True)
        report.incorrect_count = sum(1 for i in report.items if i.is_correct is False)
        report.pending_count = sum(1 for i in report.items if i.is_correct is None)
        
        reviewed = report.correct_count + report.incorrect_count
        if reviewed > 0:
            report.accuracy_rate = report.correct_count / reviewed
        
        return report
    
    def generate_summary(self, report: ReviewReport) -> str:
        """검토 요약 생성"""
        lines = [
            "=" * 50,
            f"📊 AMAA Review Report",
            f"Session: {report.session_id}",
            f"Reviewed: {report.reviewed_at}",
            "=" * 50,
            "",
            "📈 Statistics:",
            f"  Total Items: {report.total_items}",
            f"  Correct: {report.correct_count} ✅",
            f"  Incorrect: {report.incorrect_count} ❌",
            f"  Pending: {report.pending_count} ⏳",
            f"  Accuracy: {report.accuracy_rate:.1%}",
            "",
        ]
        
        # 잘못된 항목 상세
        incorrect_items = [i for i in report.items if i.is_correct is False]
        if incorrect_items:
            lines.append("❌ Incorrect Items:")
            for item in incorrect_items[:10]:
                lines.append(f"  - {Path(item.file_path).name}")
                lines.append(f"    From: {item.original_path}")
                if item.user_feedback:
                    lines.append(f"    Feedback: {item.user_feedback}")
            lines.append("")
        
        # 추천사항
        if report.recommendations:
            lines.append("💡 Recommendations:")
            for rec in report.recommendations:
                lines.append(f"  - {rec}")
        
        return '\n'.join(lines)
    
    def analyze_patterns(self, report: ReviewReport) -> List[str]:
        """
        피드백 패턴 분석 및 개선 제안 생성
        
        Args:
            report: 검토 보고서
            
        Returns:
            List[str]: 개선 제안 목록
        """
        recommendations = []
        
        # 정확도 기반 제안
        if report.accuracy_rate < 0.8:
            recommendations.append(
                "Consider reviewing the category rules - accuracy is below 80%"
            )
        
        # 잘못된 항목 분석
        incorrect_items = [i for i in report.items if i.is_correct is False]
        
        if incorrect_items:
            # 피드백에서 공통 패턴 찾기
            feedbacks = [i.user_feedback for i in incorrect_items if i.user_feedback]
            
            # 폴더 관련 피드백
            folder_issues = [f for f in feedbacks if 'folder' in f.lower()]
            if len(folder_issues) > 2:
                recommendations.append(
                    f"Folder classification needs improvement - {len(folder_issues)} issues reported"
                )
            
            # 카테고리 관련 피드백
            category_issues = [f for f in feedbacks if 'category' in f.lower()]
            if len(category_issues) > 2:
                recommendations.append(
                    f"Category detection needs tuning - {len(category_issues)} issues reported"
                )
        
        # LLM으로 추가 분석
        if incorrect_items and self.ollama.is_available():
            llm_suggestions = self._get_llm_suggestions(incorrect_items)
            recommendations.extend(llm_suggestions)
        
        report.recommendations = recommendations
        return recommendations
    
    def _get_llm_suggestions(self, incorrect_items: List[ReviewItem]) -> List[str]:
        """LLM을 통한 개선 제안"""
        try:
            # 피드백 요약
            feedbacks = [
                f"- {Path(i.file_path).name}: {i.user_feedback}"
                for i in incorrect_items[:10]
                if i.user_feedback
            ]
            
            if not feedbacks:
                return []
            
            prompt = f"""다음은 파일 조직화 시스템에서 잘못 분류된 파일들의 피드백입니다:

{chr(10).join(feedbacks)}

이 피드백을 분석하여 시스템 개선을 위한 구체적인 제안 3가지를 제시해주세요.
각 제안은 한 문장으로 작성해주세요."""
            
            response = self.ollama.generate(prompt)
            
            # 응답에서 제안 추출
            suggestions = []
            for line in response.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    # 번호나 대시 제거
                    suggestion = line.lstrip('0123456789.-) ')
                    if suggestion:
                        suggestions.append(suggestion)
            
            return suggestions[:3]
            
        except Exception:
            return []
    
    def get_feedback_history(self) -> List[Dict]:
        """피드백 이력 조회"""
        return [item.to_dict() for item in self._feedback_history]
    
    def export_feedback(self, output_path: str) -> None:
        """피드백 내보내기"""
        import json
        
        data = {
            'exported_at': datetime.now().isoformat(),
            'total_feedback': len(self._feedback_history),
            'feedback': [item.to_dict() for item in self._feedback_history]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def learn_from_feedback(self) -> Dict[str, Any]:
        """
        피드백으로부터 학습 (규칙 개선 제안)
        
        Returns:
            Dict: 학습 결과 및 제안된 규칙 변경
        """
        if not self._feedback_history:
            return {'status': 'no_feedback', 'suggestions': []}
        
        # 정답/오답 분류
        correct = [i for i in self._feedback_history if i.is_correct]
        incorrect = [i for i in self._feedback_history if not i.is_correct]
        
        learning_result = {
            'status': 'analyzed',
            'total_samples': len(self._feedback_history),
            'correct_count': len(correct),
            'incorrect_count': len(incorrect),
            'accuracy': len(correct) / len(self._feedback_history) if self._feedback_history else 0,
            'suggestions': [],
            'rule_changes': []
        }
        
        # 오답 패턴 분석
        if incorrect:
            # 파일 확장자별 오류 통계
            ext_errors = {}
            for item in incorrect:
                ext = Path(item.file_path).suffix.lower()
                ext_errors[ext] = ext_errors.get(ext, 0) + 1
            
            # 자주 틀리는 확장자
            for ext, count in sorted(ext_errors.items(), key=lambda x: -x[1])[:3]:
                learning_result['suggestions'].append(
                    f"Review classification rules for '{ext}' files ({count} errors)"
                )
                learning_result['rule_changes'].append({
                    'type': 'extension_review',
                    'extension': ext,
                    'error_count': count
                })
        
        return learning_result


if __name__ == "__main__":
    print("🔍 AMAA Reviewer Agent Test")
    print("=" * 50)
    
    reviewer = ReviewerAgent()
    
    # 테스트 세션 데이터
    test_session = {
        'session_id': 'test_001',
        'changes': [
            {'source_path': '/test/file1.pdf', 'destination_path': '/Documents/file1.pdf', 'action': 'move', 'executed': True},
            {'source_path': '/test/image.jpg', 'destination_path': '/Images/image.jpg', 'action': 'move', 'executed': True},
            {'source_path': '/test/code.py', 'destination_path': '/Documents/code.py', 'action': 'move', 'executed': True},
        ]
    }
    
    # 검토 보고서 생성
    report = reviewer.create_review(test_session)
    
    # 피드백 시뮬레이션
    reviewer.mark_correct(report.items[0])
    reviewer.mark_correct(report.items[1])
    reviewer.mark_incorrect(
        report.items[2], 
        "Python file should be in Code folder, not Documents",
        "/Code/code.py"
    )
    
    # 통계 업데이트
    report = reviewer.update_report_stats(report)
    
    # 패턴 분석
    reviewer.analyze_patterns(report)
    
    # 요약 출력
    print(reviewer.generate_summary(report))
