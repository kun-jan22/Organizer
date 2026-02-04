"""
AMAA v0.4 - Perceiver (Multimodal Data Extractor)
멀티모달 데이터 추출 및 Ollama 연동 모듈

Step 2: 멀티모달 데이터 추출 및 Ollama 연동
- PyMuPDF로 문서 텍스트 추출
- Pillow + Ollama(LLaVA)로 이미지 시맨틱 캡션 생성
- 계층적 추론으로 최적 경로 결정
"""

import base64
import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import mimetypes
import httpx


class FileType(Enum):
    """파일 타입 열거형"""
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CODE = "code"
    DATA = "data"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


@dataclass
class PerceptionResult:
    """인식 결과 데이터 클래스"""
    file_path: str
    file_type: FileType
    extracted_text: Optional[str] = None
    caption: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    language: Optional[str] = None
    suggested_category: Optional[str] = None
    suggested_path: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'file_type': self.file_type.value,
            'extracted_text': self.extracted_text[:500] if self.extracted_text else None,
            'caption': self.caption,
            'keywords': self.keywords,
            'entities': self.entities,
            'language': self.language,
            'suggested_category': self.suggested_category,
            'suggested_path': self.suggested_path,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'processing_time': self.processing_time,
            'error': self.error,
        }


class OllamaClient:
    """
    Ollama API 클라이언트
    
    로컬 LLM과 통신하여 텍스트/이미지 분석 수행
    """
    
    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "llama3.2",
                 vision_model: str = "llava",
                 timeout: int = 60):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.vision_model = vision_model
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    
    def is_available(self) -> bool:
        """Ollama 서버 사용 가능 여부 확인"""
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> List[str]:
        """사용 가능한 모델 목록"""
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m['name'] for m in data.get('models', [])]
        except Exception:
            pass
        return []
    
    def generate(self, prompt: str, model: Optional[str] = None,
                 system: Optional[str] = None,
                 stream: bool = False) -> str:
        """
        텍스트 생성
        
        Args:
            prompt: 사용자 프롬프트
            model: 사용할 모델 (기본값: self.model)
            system: 시스템 프롬프트
            stream: 스트리밍 여부
            
        Returns:
            str: 생성된 텍스트
        """
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": stream,
        }
        
        if system:
            payload["system"] = system
        
        try:
            response = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', '')
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def generate_with_image(self, prompt: str, image_path: str,
                           model: Optional[str] = None) -> str:
        """
        이미지와 함께 텍스트 생성 (LLaVA 등 비전 모델용)
        
        Args:
            prompt: 프롬프트
            image_path: 이미지 파일 경로
            model: 비전 모델 (기본값: self.vision_model)
            
        Returns:
            str: 생성된 텍스트 (캡션 등)
        """
        # 이미지를 base64로 인코딩
        path = Path(image_path)
        if not path.exists():
            return f"Error: Image not found: {image_path}"
        
        with open(path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        payload = {
            "model": model or self.vision_model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
        }
        
        try:
            response = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('response', '')
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def chat(self, messages: List[Dict[str, str]], 
             model: Optional[str] = None) -> str:
        """
        채팅 형식의 대화
        
        Args:
            messages: [{"role": "user/assistant/system", "content": "..."}]
            model: 사용할 모델
            
        Returns:
            str: 응답 메시지
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
        }
        
        try:
            response = self._client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('message', {}).get('content', '')
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def close(self):
        """클라이언트 종료"""
        self._client.close()


class Perceiver:
    """
    멀티모달 데이터 인식 엔진
    
    다양한 파일 타입에서 의미 있는 정보를 추출하고,
    Ollama를 통해 지능형 분류를 수행
    
    Usage:
        perceiver = Perceiver(config, directory_tree)
        result = perceiver.perceive("/path/to/file.pdf")
        print(result.suggested_path)
    """
    
    # 파일 확장자 → FileType 매핑
    EXTENSION_MAP = {
        # Documents
        '.pdf': FileType.DOCUMENT,
        '.docx': FileType.DOCUMENT,
        '.doc': FileType.DOCUMENT,
        '.txt': FileType.DOCUMENT,
        '.md': FileType.DOCUMENT,
        '.xlsx': FileType.DOCUMENT,
        '.xls': FileType.DOCUMENT,
        '.pptx': FileType.DOCUMENT,
        '.rtf': FileType.DOCUMENT,
        
        # Images
        '.jpg': FileType.IMAGE,
        '.jpeg': FileType.IMAGE,
        '.png': FileType.IMAGE,
        '.gif': FileType.IMAGE,
        '.webp': FileType.IMAGE,
        '.heic': FileType.IMAGE,
        '.bmp': FileType.IMAGE,
        '.svg': FileType.IMAGE,
        
        # Videos
        '.mp4': FileType.VIDEO,
        '.mov': FileType.VIDEO,
        '.avi': FileType.VIDEO,
        '.mkv': FileType.VIDEO,
        '.webm': FileType.VIDEO,
        
        # Audio
        '.mp3': FileType.AUDIO,
        '.wav': FileType.AUDIO,
        '.flac': FileType.AUDIO,
        '.m4a': FileType.AUDIO,
        '.aac': FileType.AUDIO,
        
        # Code
        '.py': FileType.CODE,
        '.js': FileType.CODE,
        '.ts': FileType.CODE,
        '.java': FileType.CODE,
        '.cpp': FileType.CODE,
        '.c': FileType.CODE,
        '.go': FileType.CODE,
        '.rs': FileType.CODE,
        '.html': FileType.CODE,
        '.css': FileType.CODE,
        
        # Data
        '.json': FileType.DATA,
        '.xml': FileType.DATA,
        '.csv': FileType.DATA,
        '.yaml': FileType.DATA,
        '.yml': FileType.DATA,
        '.sql': FileType.DATA,
        
        # Archives
        '.zip': FileType.ARCHIVE,
        '.tar': FileType.ARCHIVE,
        '.gz': FileType.ARCHIVE,
        '.7z': FileType.ARCHIVE,
        '.rar': FileType.ARCHIVE,
    }
    
    def __init__(self, config=None, directory_context: Optional[str] = None):
        """
        Args:
            config: AMAA Config 객체
            directory_context: 현재 디렉토리 구조 컨텍스트 (LLM용)
        """
        self.config = config
        self.directory_context = directory_context
        
        # Ollama 클라이언트 초기화
        if config:
            self.ollama = OllamaClient(
                base_url=config.ollama.base_url,
                model=config.ollama.model,
                vision_model=config.ollama.vision_model,
                timeout=config.ollama.timeout
            )
        else:
            self.ollama = OllamaClient()
        
        # 시스템 프롬프트
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """LLM 시스템 프롬프트 생성"""
        return """당신은 파일 분류 전문가입니다. 
파일의 내용을 분석하여 가장 적합한 저장 경로를 결정합니다.

규칙:
1. ISO 8601 날짜 형식(YYYY-MM-DD)을 파일명 접두어로 사용
2. 카테고리(documents, images, projects 등)에 따라 폴더 구분
3. 기존 디렉토리 구조를 존중하여 일관성 유지
4. 프로젝트 관련 파일은 프로젝트 폴더에 그룹화

응답 형식:
- suggested_path: 제안하는 절대 경로
- category: 파일 카테고리
- confidence: 신뢰도 (0.0 ~ 1.0)
- reasoning: 결정 이유 (간단히)"""
    
    def perceive(self, file_path: str) -> PerceptionResult:
        """
        파일 인식 및 분석 수행
        
        Args:
            file_path: 분석할 파일 경로
            
        Returns:
            PerceptionResult: 인식 결과
        """
        start_time = datetime.now()
        path = Path(file_path).expanduser().resolve()
        
        if not path.exists():
            return PerceptionResult(
                file_path=str(path),
                file_type=FileType.UNKNOWN,
                error=f"File not found: {file_path}"
            )
        
        # 파일 타입 결정
        file_type = self._detect_file_type(path)
        
        # 기본 결과 초기화
        result = PerceptionResult(
            file_path=str(path),
            file_type=file_type,
            metadata=self._extract_metadata(path)
        )
        
        try:
            # 파일 타입별 처리
            if file_type == FileType.DOCUMENT:
                result = self._perceive_document(path, result)
            elif file_type == FileType.IMAGE:
                result = self._perceive_image(path, result)
            elif file_type == FileType.VIDEO:
                result = self._perceive_video(path, result)
            elif file_type == FileType.CODE:
                result = self._perceive_code(path, result)
            elif file_type == FileType.DATA:
                result = self._perceive_data(path, result)
            else:
                result = self._perceive_generic(path, result)
            
            # LLM을 통한 경로 제안
            if self.ollama.is_available():
                result = self._suggest_path_with_llm(result)
            
        except Exception as e:
            result.error = str(e)
        
        result.processing_time = (datetime.now() - start_time).total_seconds()
        return result
    
    def _detect_file_type(self, path: Path) -> FileType:
        """파일 타입 감지"""
        ext = path.suffix.lower()
        
        if ext in self.EXTENSION_MAP:
            return self.EXTENSION_MAP[ext]
        
        # MIME 타입으로 추측
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            if mime_type.startswith('image/'):
                return FileType.IMAGE
            elif mime_type.startswith('video/'):
                return FileType.VIDEO
            elif mime_type.startswith('audio/'):
                return FileType.AUDIO
            elif mime_type.startswith('text/'):
                return FileType.DOCUMENT
        
        return FileType.UNKNOWN
    
    def _extract_metadata(self, path: Path) -> dict:
        """기본 메타데이터 추출"""
        stat = path.stat()
        return {
            'name': path.name,
            'extension': path.suffix.lower(),
            'size': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'mime_type': mimetypes.guess_type(str(path))[0],
        }
    
    def _perceive_document(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """문서 파일 분석"""
        ext = path.suffix.lower()
        
        if ext == '.pdf':
            result.extracted_text = self._extract_pdf_text(path)
        elif ext == '.txt':
            result.extracted_text = self._extract_text_file(path)
        elif ext == '.md':
            result.extracted_text = self._extract_text_file(path)
        elif ext in ['.docx', '.doc']:
            result.extracted_text = self._extract_docx_text(path)
        
        # 텍스트에서 키워드/엔티티 추출
        if result.extracted_text:
            result.keywords = self._extract_keywords(result.extracted_text)
            result.entities = self._extract_entities(result.extracted_text)
            result.language = self._detect_language(result.extracted_text)
        
        return result
    
    def _perceive_image(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """이미지 파일 분석 (LLaVA 사용)"""
        
        # EXIF 메타데이터 추출
        result.metadata.update(self._extract_image_metadata(path))
        
        # LLaVA로 이미지 캡션 생성
        if self.ollama.is_available():
            prompt = """이 이미지를 분석해주세요:
1. 주요 내용 설명 (한 문장)
2. 키워드 3-5개
3. 적합한 분류 카테고리 (사진, 스크린샷, 문서스캔, 그래픽, 기타)

JSON 형식으로 응답:
{"caption": "...", "keywords": [...], "category": "..."}"""
            
            response = self.ollama.generate_with_image(prompt, str(path))
            
            try:
                # JSON 파싱 시도
                data = json.loads(response)
                result.caption = data.get('caption', '')
                result.keywords = data.get('keywords', [])
                result.suggested_category = data.get('category', '')
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 텍스트로 저장
                result.caption = response
        
        return result
    
    def _perceive_video(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """비디오 파일 분석"""
        
        # 썸네일 추출 후 이미지 분석
        thumbnail = self._extract_video_thumbnail(path)
        
        if thumbnail and self.ollama.is_available():
            prompt = "이 비디오 프레임을 분석하여 비디오 내용을 설명해주세요."
            result.caption = self.ollama.generate_with_image(prompt, thumbnail)
            
            # 임시 썸네일 삭제
            try:
                Path(thumbnail).unlink()
            except:
                pass
        
        # 비디오 메타데이터
        result.metadata.update(self._extract_video_metadata(path))
        
        return result
    
    def _perceive_code(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """코드 파일 분석"""
        
        result.extracted_text = self._extract_text_file(path)
        
        if result.extracted_text:
            # 언어 감지
            result.language = path.suffix.replace('.', '')
            
            # 코드에서 키워드 추출 (클래스명, 함수명 등)
            result.keywords = self._extract_code_symbols(result.extracted_text, result.language)
            
            # 프로젝트 관련 정보 추출
            result.entities = self._extract_imports(result.extracted_text, result.language)
        
        return result
    
    def _perceive_data(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """데이터 파일 분석"""
        ext = path.suffix.lower()
        
        if ext == '.json':
            result.metadata.update(self._analyze_json(path))
        elif ext == '.csv':
            result.metadata.update(self._analyze_csv(path))
        elif ext in ['.yaml', '.yml']:
            result.extracted_text = self._extract_text_file(path)
        
        return result
    
    def _perceive_generic(self, path: Path, result: PerceptionResult) -> PerceptionResult:
        """일반 파일 분석"""
        # 파일명에서 정보 추출
        result.keywords = self._extract_from_filename(path.stem)
        return result
    
    def _suggest_path_with_llm(self, result: PerceptionResult) -> PerceptionResult:
        """
        LLM을 통한 계층적 추론으로 최적 경로 제안
        
        디렉토리 컨텍스트와 파일 정보를 함께 전달하여
        기존 분류 체계에 맞는 경로를 제안받음
        """
        
        # 프롬프트 구성
        file_info = f"""
파일 정보:
- 이름: {result.metadata.get('name', '')}
- 타입: {result.file_type.value}
- 크기: {result.metadata.get('size', 0)} bytes
- 수정일: {result.metadata.get('modified', '')}
"""
        
        if result.extracted_text:
            file_info += f"- 내용 요약: {result.extracted_text[:500]}...\n"
        
        if result.caption:
            file_info += f"- 이미지 캡션: {result.caption}\n"
        
        if result.keywords:
            file_info += f"- 키워드: {', '.join(result.keywords)}\n"
        
        # 디렉토리 컨텍스트 추가
        context = ""
        if self.directory_context:
            context = f"""
현재 디렉토리 구조:
{self.directory_context}
"""
        
        prompt = f"""{file_info}
{context}

이 파일에 가장 적합한 저장 경로를 JSON으로 제안해주세요:
{{"suggested_path": "/path/to/store", "category": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""
        
        response = self.ollama.generate(prompt, system=self.system_prompt)
        
        try:
            # JSON 추출 시도
            json_match = re.search(r'\{[^{}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                result.suggested_path = data.get('suggested_path')
                result.suggested_category = data.get('category')
                result.confidence = float(data.get('confidence', 0.5))
        except (json.JSONDecodeError, ValueError):
            # 파싱 실패 시 기본값 유지
            pass
        
        return result
    
    # ============================================================
    # 텍스트 추출 메서드들
    # ============================================================
    
    def _extract_pdf_text(self, path: Path) -> str:
        """PDF에서 텍스트 추출 (PyMuPDF)"""
        try:
            import fitz  # PyMuPDF
            
            text_parts = []
            with fitz.open(str(path)) as doc:
                for page in doc:
                    text_parts.append(page.get_text())
            
            return '\n'.join(text_parts)
        except ImportError:
            return "[PyMuPDF not installed]"
        except Exception as e:
            return f"[Error extracting PDF: {e}]"
    
    def _extract_text_file(self, path: Path, max_size: int = 1_000_000) -> str:
        """텍스트 파일 읽기"""
        try:
            # 인코딩 감지
            import chardet
            
            with open(path, 'rb') as f:
                raw = f.read(min(max_size, path.stat().st_size))
            
            detected = chardet.detect(raw)
            encoding = detected.get('encoding', 'utf-8')
            
            return raw.decode(encoding, errors='replace')
        except ImportError:
            # chardet 없으면 utf-8로 시도
            try:
                return path.read_text(encoding='utf-8')
            except:
                return path.read_text(encoding='latin-1', errors='replace')
        except Exception as e:
            return f"[Error reading file: {e}]"
    
    def _extract_docx_text(self, path: Path) -> str:
        """DOCX에서 텍스트 추출"""
        try:
            from zipfile import ZipFile
            from xml.etree import ElementTree
            
            with ZipFile(str(path)) as docx:
                content = docx.read('word/document.xml')
            
            tree = ElementTree.fromstring(content)
            
            # Word XML 네임스페이스
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            texts = []
            for para in tree.findall('.//w:p', ns):
                para_text = ''.join(
                    node.text for node in para.findall('.//w:t', ns) if node.text
                )
                texts.append(para_text)
            
            return '\n'.join(texts)
        except Exception as e:
            return f"[Error extracting DOCX: {e}]"
    
    # ============================================================
    # 이미지/비디오 처리 메서드들
    # ============================================================
    
    def _extract_image_metadata(self, path: Path) -> dict:
        """이미지 EXIF 메타데이터 추출"""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            
            with Image.open(str(path)) as img:
                metadata = {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                }
                
                # EXIF 데이터
                exif = img._getexif()
                if exif:
                    for tag_id, value in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if isinstance(value, (str, int, float)):
                            metadata[f'exif_{tag}'] = value
                
                return metadata
        except ImportError:
            return {'error': 'Pillow not installed'}
        except Exception as e:
            return {'error': str(e)}
    
    def _extract_video_thumbnail(self, path: Path) -> Optional[str]:
        """비디오에서 썸네일 추출"""
        try:
            import cv2
            
            cap = cv2.VideoCapture(str(path))
            
            # 첫 프레임 또는 중간 프레임
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(30, total_frames // 2))
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                thumb_path = path.parent / f".thumb_{path.stem}.jpg"
                cv2.imwrite(str(thumb_path), frame)
                return str(thumb_path)
        except ImportError:
            pass
        except Exception:
            pass
        
        return None
    
    def _extract_video_metadata(self, path: Path) -> dict:
        """비디오 메타데이터 추출"""
        try:
            import cv2
            
            cap = cv2.VideoCapture(str(path))
            
            metadata = {
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'duration': cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1),
            }
            
            cap.release()
            return metadata
        except ImportError:
            return {'error': 'OpenCV not installed'}
        except Exception as e:
            return {'error': str(e)}
    
    # ============================================================
    # 텍스트 분석 메서드들
    # ============================================================
    
    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """텍스트에서 키워드 추출 (간단한 TF 기반)"""
        import re
        from collections import Counter
        
        # 단어 추출 (한글, 영문 모두)
        words = re.findall(r'[\w가-힣]{2,}', text.lower())
        
        # 불용어 제거
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                    '이', '그', '저', '것', '수', '등', '및', '의', '를', '을', '에'}
        words = [w for w in words if w not in stopwords and len(w) > 2]
        
        # 빈도수 기반 상위 키워드
        counter = Counter(words)
        return [word for word, _ in counter.most_common(top_n)]
    
    def _extract_entities(self, text: str) -> List[str]:
        """텍스트에서 엔티티(고유명사 등) 추출"""
        import re
        
        entities = []
        
        # 이메일
        emails = re.findall(r'[\w.-]+@[\w.-]+\.\w+', text)
        entities.extend(emails)
        
        # URL
        urls = re.findall(r'https?://[^\s]+', text)
        entities.extend(urls)
        
        # 날짜
        dates = re.findall(r'\d{4}[-/]\d{2}[-/]\d{2}', text)
        entities.extend(dates)
        
        # 대문자로 시작하는 단어 (고유명사 추정)
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities.extend(proper_nouns[:10])
        
        return list(set(entities))[:20]
    
    def _detect_language(self, text: str) -> str:
        """텍스트 언어 감지 (간단한 휴리스틱)"""
        # 한글 비율 체크
        korean_chars = len(re.findall(r'[가-힣]', text))
        total_chars = len(text)
        
        if total_chars > 0 and korean_chars / total_chars > 0.3:
            return 'ko'
        
        # 일본어 체크
        japanese_chars = len(re.findall(r'[\u3040-\u30ff]', text))
        if total_chars > 0 and japanese_chars / total_chars > 0.1:
            return 'ja'
        
        # 중국어 체크
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        if total_chars > 0 and chinese_chars / total_chars > 0.1:
            return 'zh'
        
        return 'en'
    
    def _extract_code_symbols(self, code: str, language: str) -> List[str]:
        """코드에서 심볼(클래스, 함수명 등) 추출"""
        import re
        
        symbols = []
        
        if language in ['py', 'python']:
            # Python 클래스/함수
            classes = re.findall(r'class\s+(\w+)', code)
            functions = re.findall(r'def\s+(\w+)', code)
            symbols.extend(classes)
            symbols.extend(functions)
        
        elif language in ['js', 'ts', 'javascript', 'typescript']:
            # JS/TS 함수/클래스
            classes = re.findall(r'class\s+(\w+)', code)
            functions = re.findall(r'function\s+(\w+)', code)
            arrow_funcs = re.findall(r'const\s+(\w+)\s*=\s*(?:\([^)]*\)|[^=])\s*=>', code)
            symbols.extend(classes)
            symbols.extend(functions)
            symbols.extend(arrow_funcs)
        
        elif language in ['java', 'cpp', 'c', 'c++']:
            # Java/C++ 클래스/메서드
            classes = re.findall(r'class\s+(\w+)', code)
            symbols.extend(classes)
        
        return list(set(symbols))[:20]
    
    def _extract_imports(self, code: str, language: str) -> List[str]:
        """코드에서 import 문 추출"""
        import re
        
        imports = []
        
        if language in ['py', 'python']:
            # Python imports
            imports.extend(re.findall(r'^import\s+(\w+)', code, re.MULTILINE))
            imports.extend(re.findall(r'^from\s+(\w+)', code, re.MULTILINE))
        
        elif language in ['js', 'ts', 'javascript', 'typescript']:
            # JS/TS imports
            imports.extend(re.findall(r"import\s+.*from\s+['\"]([^'\"]+)['\"]", code))
            imports.extend(re.findall(r"require\(['\"]([^'\"]+)['\"]\)", code))
        
        elif language == 'java':
            imports.extend(re.findall(r'^import\s+([\w.]+)', code, re.MULTILINE))
        
        return list(set(imports))
    
    def _extract_from_filename(self, filename: str) -> List[str]:
        """파일명에서 키워드 추출"""
        import re
        
        # 구분자로 분리
        parts = re.split(r'[-_\s.]+', filename)
        
        # 날짜 제거
        keywords = [p for p in parts if not re.match(r'^\d{4,8}$', p)]
        
        return [k for k in keywords if len(k) > 2]
    
    def _analyze_json(self, path: Path) -> dict:
        """JSON 파일 분석"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return {
                'json_type': type(data).__name__,
                'json_keys': list(data.keys())[:10] if isinstance(data, dict) else None,
                'json_length': len(data) if isinstance(data, (list, dict)) else None,
            }
        except:
            return {}
    
    def _analyze_csv(self, path: Path) -> dict:
        """CSV 파일 분석"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                first_lines = [f.readline() for _ in range(5)]
            
            # 헤더 추출
            header = first_lines[0].strip().split(',') if first_lines else []
            
            return {
                'csv_columns': header[:10],
                'csv_preview_rows': len([l for l in first_lines if l.strip()]) - 1,
            }
        except:
            return {}
    
    def set_directory_context(self, context: str) -> None:
        """디렉토리 컨텍스트 업데이트"""
        self.directory_context = context
    
    def batch_perceive(self, file_paths: List[str], 
                       progress_callback=None) -> List[PerceptionResult]:
        """여러 파일 일괄 분석"""
        results = []
        total = len(file_paths)
        
        for i, path in enumerate(file_paths):
            result = self.perceive(path)
            results.append(result)
            
            if progress_callback:
                progress_callback(i + 1, total, path)
        
        return results


if __name__ == "__main__":
    import sys
    
    # Ollama 연결 테스트
    print("🔍 Testing Ollama connection...")
    ollama = OllamaClient()
    
    if ollama.is_available():
        print("✅ Ollama is available")
        print(f"📋 Available models: {ollama.list_models()}")
    else:
        print("❌ Ollama is not available")
        print("   Please start Ollama: ollama serve")
    
    # 파일 분석 테스트
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"\n🔍 Analyzing: {test_file}")
        
        perceiver = Perceiver()
        result = perceiver.perceive(test_file)
        
        print(f"\n📊 Results:")
        print(f"  File Type: {result.file_type.value}")
        print(f"  Keywords: {result.keywords}")
        print(f"  Suggested Category: {result.suggested_category}")
        print(f"  Suggested Path: {result.suggested_path}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Processing Time: {result.processing_time:.2f}s")
