"""
AMAA v0.4 - File Indexer
LlamaIndex 기반 파일 인덱서 (자연어 검색 지원)
"""

from pathlib import Path
from typing import Optional, List, Dict, Any


class FileIndexer:
    """
    LlamaIndex 기반 파일 인덱서
    
    정리된 파일들을 인덱싱하여 자연어 검색 지원
    
    Usage:
        indexer = FileIndexer(index_path="~/.amaa/index")
        indexer.index_directory("/path/to/organized")
        results = indexer.search("프로젝트 관련 PDF 문서")
    """
    
    def __init__(self, index_path: str = "~/.amaa/index"):
        self.index_path = Path(index_path).expanduser()
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        self._index = None
        self._llama_available = self._check_llama_index()
    
    def _check_llama_index(self) -> bool:
        """LlamaIndex 사용 가능 여부 확인"""
        try:
            from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
            return True
        except ImportError:
            return False
    
    def index_directory(self, dir_path: str, 
                        recursive: bool = True) -> Dict[str, Any]:
        """
        디렉토리 인덱싱
        
        Args:
            dir_path: 인덱싱할 디렉토리
            recursive: 재귀 여부
            
        Returns:
            Dict: 인덱싱 결과
        """
        if not self._llama_available:
            return {
                'status': 'error',
                'message': 'LlamaIndex not installed. Run: pip install llama-index'
            }
        
        try:
            from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
            from llama_index.core import Settings
            
            # 문서 로드
            reader = SimpleDirectoryReader(
                input_dir=dir_path,
                recursive=recursive,
                exclude_hidden=True
            )
            documents = reader.load_data()
            
            # 인덱스 생성
            self._index = VectorStoreIndex.from_documents(documents)
            
            # 인덱스 저장
            self._index.storage_context.persist(str(self.index_path))
            
            return {
                'status': 'success',
                'documents_indexed': len(documents),
                'index_path': str(self.index_path)
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def load_index(self) -> bool:
        """저장된 인덱스 로드"""
        if not self._llama_available:
            return False
        
        try:
            from llama_index.core import StorageContext, load_index_from_storage
            
            storage_context = StorageContext.from_defaults(
                persist_dir=str(self.index_path)
            )
            self._index = load_index_from_storage(storage_context)
            return True
            
        except Exception:
            return False
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        자연어 검색
        
        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            
        Returns:
            List[Dict]: 검색 결과
        """
        if not self._llama_available:
            return [{'error': 'LlamaIndex not installed'}]
        
        if self._index is None:
            if not self.load_index():
                return [{'error': 'No index available'}]
        
        try:
            query_engine = self._index.as_query_engine(similarity_top_k=top_k)
            response = query_engine.query(query)
            
            results = []
            for node in response.source_nodes:
                results.append({
                    'content': node.text[:500],
                    'score': node.score,
                    'metadata': node.metadata
                })
            
            return results
            
        except Exception as e:
            return [{'error': str(e)}]
    
    def is_available(self) -> bool:
        """인덱서 사용 가능 여부"""
        return self._llama_available


if __name__ == "__main__":
    import sys
    
    print("📚 AMAA File Indexer Test")
    print("=" * 50)
    
    indexer = FileIndexer()
    
    if not indexer.is_available():
        print("⚠️ LlamaIndex not installed")
        print("   Run: pip install llama-index llama-index-embeddings-huggingface")
    else:
        print("✅ LlamaIndex available")
        
        if len(sys.argv) > 1:
            path = sys.argv[1]
            print(f"\n📁 Indexing: {path}")
            result = indexer.index_directory(path)
            print(f"Result: {result}")
