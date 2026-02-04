"""
AMAA v0.4 - Analyzer Agent
파일 분석 및 분류 에이전트

Multi-Agent System의 분석 담당
- 파일 내용 분석
- 카테고리 결정
- 메타데이터 추출
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.perceiver import Perceiver, PerceptionResult, FileType
from ..core.mapmaker import MapMaker, FileInfo


@dataclass
class AnalysisResult:
    """분석 결과"""
    file_path: str
    file_type: str
    category: Optional[str] = None
    suggested_folder: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    confidence: float = 0.0
    is_sensitive: bool = False
    analysis_time: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'file_type': self.file_type,
            'category': self.category,
            'suggested_folder': self.suggested_folder,
            'keywords': self.keywords,
            'summary': self.summary,
            'confidence': self.confidence,
            'is_sensitive': self.is_sensitive,
            'analysis_time': self.analysis_time,
            'error': self.error,
        }


class AnalyzerAgent:
    """
    파일 분석 에이전트
    
    파일 내용을 분석하고 적절한 분류를 결정
    
    Usage:
        analyzer = AnalyzerAgent(config)
        result = analyzer.analyze("/path/to/file.pdf")
        print(result.category)
    """
    
    # 카테고리 매핑
    CATEGORY_FOLDERS = {
        'documents': 'Documents',
        'images': 'Images',
        'videos': 'Videos',
        'audio': 'Music',
        'code': 'Code',
        'data': 'Data',
        'archives': 'Archives',
        'other': 'Misc',
    }
    
    def __init__(self, config=None, directory_context: Optional[str] = None):
        """
        Args:
            config: AMAA Config 객체
            directory_context: 디렉토리 구조 컨텍스트
        """
        self.config = config
        self.perceiver = Perceiver(config=config, directory_context=directory_context)
    
    def analyze(self, file_path: str) -> AnalysisResult:
        """
        단일 파일 분석
        
        Args:
            file_path: 분석할 파일 경로
            
        Returns:
            AnalysisResult: 분석 결과
        """
        start_time = datetime.now()
        path = Path(file_path)
        
        result = AnalysisResult(
            file_path=str(path),
            file_type='unknown'
        )
        
        try:
            # Perceiver로 파일 인식
            perception = self.perceiver.perceive(file_path)
            
            # 결과 매핑
            result.file_type = perception.file_type.value
            result.category = perception.suggested_category or self._infer_category(perception)
            result.suggested_folder = self._determine_folder(result.category, perception)
            result.keywords = perception.keywords
            result.summary = perception.caption or self._generate_summary(perception)
            result.confidence = perception.confidence
            result.is_sensitive = self._check_sensitivity(perception)
            
            if perception.error:
                result.error = perception.error
                
        except Exception as e:
            result.error = str(e)
        
        result.analysis_time = (datetime.now() - start_time).total_seconds()
        return result
    
    def _infer_category(self, perception: PerceptionResult) -> str:
        """파일 타입에서 카테고리 추론"""
        type_to_category = {
            FileType.DOCUMENT: 'documents',
            FileType.IMAGE: 'images',
            FileType.VIDEO: 'videos',
            FileType.AUDIO: 'audio',
            FileType.CODE: 'code',
            FileType.DATA: 'data',
            FileType.ARCHIVE: 'archives',
        }
        return type_to_category.get(perception.file_type, 'other')
    
    def _determine_folder(self, category: str, perception: PerceptionResult) -> str:
        """대상 폴더 결정"""
        # LLM 제안이 있으면 사용
        if perception.suggested_path:
            return perception.suggested_path
        
        # 기본 카테고리 폴더
        return self.CATEGORY_FOLDERS.get(category, 'Misc')
    
    def _generate_summary(self, perception: PerceptionResult) -> str:
        """요약 생성"""
        parts = []
        
        if perception.file_type:
            parts.append(f"Type: {perception.file_type.value}")
        
        if perception.keywords:
            parts.append(f"Keywords: {', '.join(perception.keywords[:5])}")
        
        if perception.language:
            parts.append(f"Language: {perception.language}")
        
        return '; '.join(parts) if parts else None
    
    def _check_sensitivity(self, perception: PerceptionResult) -> bool:
        """민감 정보 여부 확인"""
        sensitive_keywords = {
            '기밀', 'confidential', 'secret', 'private',
            'password', '비밀번호', '개인정보'
        }
        
        text = perception.extracted_text or ''
        keywords = perception.keywords or []
        
        # 키워드 체크
        for kw in keywords:
            if kw.lower() in sensitive_keywords:
                return True
        
        # 텍스트 체크
        text_lower = text.lower()
        for sensitive in sensitive_keywords:
            if sensitive in text_lower:
                return True
        
        return False
    
    def analyze_batch(self, file_paths: List[str],
                      max_workers: int = 4,
                      progress_callback=None) -> List[AnalysisResult]:
        """
        여러 파일 일괄 분석
        
        Args:
            file_paths: 파일 경로 목록
            max_workers: 병렬 워커 수
            progress_callback: 진행 콜백 (current, total, path)
            
        Returns:
            List[AnalysisResult]: 분석 결과 목록
        """
        results = []
        total = len(file_paths)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.analyze, path): path
                for path in file_paths
            }
            
            for i, future in enumerate(as_completed(futures)):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    path = futures[future]
                    results.append(AnalysisResult(
                        file_path=path,
                        file_type='unknown',
                        error=str(e)
                    ))
                
                if progress_callback:
                    progress_callback(i + 1, total, futures[future])
        
        return results
    
    def set_context(self, directory_context: str) -> None:
        """디렉토리 컨텍스트 업데이트"""
        self.perceiver.set_directory_context(directory_context)
    
    def get_category_stats(self, results: List[AnalysisResult]) -> Dict[str, int]:
        """분석 결과에서 카테고리 통계"""
        stats = {}
        for r in results:
            cat = r.category or 'unknown'
            stats[cat] = stats.get(cat, 0) + 1
        return stats


if __name__ == "__main__":
    import sys
    
    print("🔬 AMAA Analyzer Agent Test")
    print("=" * 50)
    
    analyzer = AnalyzerAgent()
    
    if len(sys.argv) > 1:
        path = sys.argv[1]
        
        if Path(path).is_file():
            result = analyzer.analyze(path)
            
            print(f"\n📄 File: {result.file_path}")
            print(f"📁 Type: {result.file_type}")
            print(f"🏷️ Category: {result.category}")
            print(f"📂 Suggested Folder: {result.suggested_folder}")
            print(f"🔑 Keywords: {', '.join(result.keywords[:5])}")
            print(f"📝 Summary: {result.summary}")
            print(f"🎯 Confidence: {result.confidence:.1%}")
            print(f"🔒 Sensitive: {result.is_sensitive}")
            print(f"⏱️ Time: {result.analysis_time:.2f}s")
        else:
            # 디렉토리면 전체 분석
            files = list(Path(path).rglob('*'))
            files = [str(f) for f in files if f.is_file()][:20]  # 최대 20개
            
            print(f"\n📁 Analyzing {len(files)} files...")
            
            def progress(current, total, p):
                print(f"[{current}/{total}] {Path(p).name}")
            
            results = analyzer.analyze_batch(files, progress_callback=progress)
            
            print("\n📊 Results:")
            for cat, count in analyzer.get_category_stats(results).items():
                print(f"  {cat}: {count}")
    else:
        print("Usage: python analyzer.py <file_or_directory>")
