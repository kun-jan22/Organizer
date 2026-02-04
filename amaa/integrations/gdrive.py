"""
AMAA v0.4 - Google Drive Sync
Google Drive 동기화 모듈

Features:
- 파일 업로드/다운로드
- 폴더 생성 및 관리
- 로컬 ↔ Drive 양방향 동기화
"""

import os
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable


class GoogleDriveSync:
    """
    Google Drive 동기화
    
    로컬 파일을 Google Drive에 업로드하고
    폴더 구조를 동기화합니다.
    
    Usage:
        sync = GoogleDriveSync(credentials_path="credentials.json")
        sync.authenticate()
        
        # 파일 업로드
        result = sync.upload_file("local_file.pdf", "folder_id")
        
        # 폴더 생성
        folder_id = sync.create_folder("AMAA_Attachments")
    """
    
    SCOPES = [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive.metadata.readonly',
    ]
    
    def __init__(self,
                 credentials_path: str = "credentials.json",
                 token_path: str = "~/.amaa/gdrive_token.json"):
        """
        Args:
            credentials_path: Google OAuth credentials.json 경로
            token_path: 저장된 토큰 경로
        """
        self.credentials_path = Path(credentials_path).expanduser()
        self.token_path = Path(token_path).expanduser()
        
        self._service = None
        self._folder_cache: Dict[str, str] = {}  # name -> id 캐시
    
    def authenticate(self) -> bool:
        """
        Google Drive API 인증
        
        Returns:
            bool: 인증 성공 여부
        """
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            
            creds = None
            
            # 저장된 토큰 로드
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), self.SCOPES
                )
            
            # 토큰 갱신 또는 새 인증
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path.exists():
                        print(f"❌ credentials.json not found: {self.credentials_path}")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                
                # 토큰 저장
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
            
            # Drive 서비스 빌드
            self._service = build('drive', 'v3', credentials=creds)
            print("✅ Google Drive API 인증 성공")
            return True
            
        except ImportError:
            print("❌ Google API 라이브러리가 설치되지 않았습니다.")
            print("   pip install google-api-python-client google-auth-oauthlib")
            return False
        except Exception as e:
            print(f"❌ Drive 인증 실패: {e}")
            return False
    
    def create_folder(self, name: str, 
                      parent_id: Optional[str] = None) -> Optional[str]:
        """
        Google Drive에 폴더 생성
        
        Args:
            name: 폴더 이름
            parent_id: 부모 폴더 ID (None이면 루트)
            
        Returns:
            str: 생성된 폴더 ID
        """
        if not self._service:
            return None
        
        # 캐시 확인
        cache_key = f"{parent_id or 'root'}:{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]
        
        try:
            # 기존 폴더 확인
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self._service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            if files:
                folder_id = files[0]['id']
                self._folder_cache[cache_key] = folder_id
                return folder_id
            
            # 새 폴더 생성
            file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            folder = self._service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            self._folder_cache[cache_key] = folder_id
            
            print(f"📁 Drive 폴더 생성: {name} ({folder_id})")
            return folder_id
            
        except Exception as e:
            print(f"❌ 폴더 생성 실패: {e}")
            return None
    
    def upload_file(self, local_path: str,
                    parent_folder_id: Optional[str] = None,
                    custom_name: Optional[str] = None) -> Optional[Dict]:
        """
        파일을 Google Drive에 업로드
        
        Args:
            local_path: 로컬 파일 경로
            parent_folder_id: 업로드할 폴더 ID
            custom_name: 커스텀 파일명 (None이면 원본 이름)
            
        Returns:
            Dict: 업로드된 파일 정보 (id, name, webViewLink)
        """
        if not self._service:
            return None
        
        try:
            from googleapiclient.http import MediaFileUpload
            
            path = Path(local_path)
            if not path.exists():
                print(f"❌ 파일 없음: {local_path}")
                return None
            
            filename = custom_name or path.name
            
            # MIME 타입 추측
            mime_type = self._guess_mime_type(path.suffix)
            
            file_metadata = {'name': filename}
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]
            
            media = MediaFileUpload(
                str(path),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self._service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink, size'
            ).execute()
            
            print(f"☁️ Drive 업로드: {filename}")
            
            return {
                'id': file.get('id'),
                'name': file.get('name'),
                'webViewLink': file.get('webViewLink'),
                'size': file.get('size')
            }
            
        except Exception as e:
            print(f"❌ 업로드 실패: {e}")
            return None
    
    def _guess_mime_type(self, suffix: str) -> str:
        """확장자로 MIME 타입 추측"""
        mime_map = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.zip': 'application/zip',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
        }
        return mime_map.get(suffix.lower(), 'application/octet-stream')
    
    def list_files(self, folder_id: Optional[str] = None,
                   max_results: int = 100) -> List[Dict]:
        """
        폴더 내 파일 목록 조회
        
        Args:
            folder_id: 폴더 ID (None이면 루트)
            max_results: 최대 결과 수
            
        Returns:
            List[Dict]: 파일 목록
        """
        if not self._service:
            return []
        
        try:
            query = "trashed=false"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            results = self._service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, mimeType, size, modifiedTime, webViewLink)"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            print(f"❌ 파일 목록 조회 실패: {e}")
            return []
    
    def download_file(self, file_id: str, 
                      local_path: str) -> bool:
        """
        Google Drive에서 파일 다운로드
        
        Args:
            file_id: 파일 ID
            local_path: 저장할 로컬 경로
            
        Returns:
            bool: 성공 여부
        """
        if not self._service:
            return False
        
        try:
            from googleapiclient.http import MediaIoBaseDownload
            
            request = self._service.files().get_media(fileId=file_id)
            
            path = Path(local_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            print(f"⬇️ 다운로드 완료: {path.name}")
            return True
            
        except Exception as e:
            print(f"❌ 다운로드 실패: {e}")
            return False
    
    def create_folder_structure(self, structure: Dict[str, Any],
                                parent_id: Optional[str] = None) -> Dict[str, str]:
        """
        폴더 구조 일괄 생성
        
        Args:
            structure: 폴더 구조 딕셔너리
                {"Documents": {"Work": {}, "Personal": {}}, "Images": {}}
            parent_id: 부모 폴더 ID
            
        Returns:
            Dict[str, str]: 폴더 이름 -> ID 매핑
        """
        result = {}
        
        for name, children in structure.items():
            folder_id = self.create_folder(name, parent_id)
            if folder_id:
                result[name] = folder_id
                
                if children:
                    child_result = self.create_folder_structure(children, folder_id)
                    for child_name, child_id in child_result.items():
                        result[f"{name}/{child_name}"] = child_id
        
        return result
    
    def setup_amaa_folders(self) -> Dict[str, str]:
        """
        AMAA 기본 폴더 구조 생성
        
        Returns:
            Dict[str, str]: 폴더 이름 -> ID 매핑
        """
        structure = {
            "AMAA_Files": {
                "EmailAttachments": {},
                "Documents": {
                    "PDF": {},
                    "Word": {},
                    "Excel": {},
                    "Presentations": {}
                },
                "Images": {
                    "Screenshots": {},
                    "Photos": {}
                },
                "Archives": {},
                "Others": {}
            }
        }
        
        print("📁 AMAA Drive 폴더 구조 생성 중...")
        result = self.create_folder_structure(structure)
        print(f"✅ {len(result)}개 폴더 생성 완료")
        
        return result


if __name__ == "__main__":
    print("☁️ AMAA Google Drive Sync Test")
    print("=" * 50)
    
    sync = GoogleDriveSync()
    
    if sync.authenticate():
        # AMAA 폴더 구조 생성
        folders = sync.setup_amaa_folders()
        
        for name, folder_id in folders.items():
            print(f"  📁 {name}: {folder_id}")
