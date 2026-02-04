"""
AMAA v0.4 - Gmail Attachment Watcher
이메일 첨부파일 자동 감지 및 저장

Features:
- Gmail API를 통한 새 이메일 감지
- 첨부파일 자동 다운로드
- Google Drive + 로컬 동시 저장
- 히스토리 기록
"""

import os
import base64
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field


@dataclass
class AttachmentInfo:
    """첨부파일 정보"""
    message_id: str
    attachment_id: str
    filename: str
    mime_type: str
    size: int
    sender: str
    subject: str
    received_at: str
    local_path: Optional[str] = None
    gdrive_path: Optional[str] = None
    gdrive_id: Optional[str] = None


class GmailWatcher:
    """
    Gmail 첨부파일 감시자
    
    Gmail API를 사용하여 새 이메일의 첨부파일을 감지하고
    로컬 및 Google Drive에 자동 저장합니다.
    
    Usage:
        watcher = GmailWatcher(
            credentials_path="credentials.json",
            local_save_path="~/Downloads/EmailAttachments",
            gdrive_folder_id="your_folder_id"
        )
        watcher.start()
    """
    
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
    ]
    
    def __init__(self, 
                 credentials_path: str = "credentials.json",
                 token_path: str = "~/.amaa/gmail_token.json",
                 local_save_path: str = "~/Downloads/EmailAttachments",
                 gdrive_folder_id: Optional[str] = None,
                 history_callback: Optional[Callable] = None,
                 check_interval: int = 60):
        """
        Args:
            credentials_path: Google OAuth credentials.json 경로
            token_path: 저장된 토큰 경로
            local_save_path: 로컬 저장 경로
            gdrive_folder_id: Google Drive 폴더 ID
            history_callback: 히스토리 기록 콜백
            check_interval: 확인 간격 (초)
        """
        self.credentials_path = Path(credentials_path).expanduser()
        self.token_path = Path(token_path).expanduser()
        self.local_save_path = Path(local_save_path).expanduser()
        self.gdrive_folder_id = gdrive_folder_id
        self.history_callback = history_callback
        self.check_interval = check_interval
        
        # 로컬 저장 폴더 생성
        self.local_save_path.mkdir(parents=True, exist_ok=True)
        
        # API 클라이언트
        self._gmail_service = None
        self._gdrive_sync = None
        self._is_running = False
        
        # 처리된 메시지 ID 추적
        self._processed_ids_file = self.token_path.parent / "processed_emails.json"
        self._processed_ids = self._load_processed_ids()
    
    def _load_processed_ids(self) -> set:
        """처리된 이메일 ID 로드"""
        if self._processed_ids_file.exists():
            try:
                with open(self._processed_ids_file, 'r') as f:
                    return set(json.load(f))
            except:
                pass
        return set()
    
    def _save_processed_ids(self):
        """처리된 이메일 ID 저장"""
        self._processed_ids_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._processed_ids_file, 'w') as f:
            json.dump(list(self._processed_ids), f)
    
    def authenticate(self) -> bool:
        """
        Gmail API 인증
        
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
            
            # Gmail 서비스 빌드
            self._gmail_service = build('gmail', 'v1', credentials=creds)
            print("✅ Gmail API 인증 성공")
            return True
            
        except ImportError:
            print("❌ Google API 라이브러리가 설치되지 않았습니다.")
            print("   pip install google-api-python-client google-auth-oauthlib")
            return False
        except Exception as e:
            print(f"❌ Gmail 인증 실패: {e}")
            return False
    
    def get_unread_with_attachments(self, max_results: int = 10) -> List[Dict]:
        """
        첨부파일이 있는 읽지 않은 이메일 조회
        
        Args:
            max_results: 최대 결과 수
            
        Returns:
            List[Dict]: 이메일 목록
        """
        if not self._gmail_service:
            return []
        
        try:
            # 읽지 않은 이메일 + 첨부파일 있는 것만
            results = self._gmail_service.users().messages().list(
                userId='me',
                q='is:unread has:attachment',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            return messages
            
        except Exception as e:
            print(f"❌ 이메일 조회 실패: {e}")
            return []
    
    def get_message_details(self, message_id: str) -> Optional[Dict]:
        """메시지 상세 정보 조회"""
        if not self._gmail_service:
            return None
        
        try:
            message = self._gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            return message
        except Exception as e:
            print(f"❌ 메시지 상세 조회 실패: {e}")
            return None
    
    def download_attachment(self, message_id: str, 
                           attachment_id: str,
                           filename: str) -> Optional[bytes]:
        """첨부파일 다운로드"""
        if not self._gmail_service:
            return None
        
        try:
            attachment = self._gmail_service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()
            
            data = attachment.get('data', '')
            file_data = base64.urlsafe_b64decode(data)
            return file_data
            
        except Exception as e:
            print(f"❌ 첨부파일 다운로드 실패: {e}")
            return None
    
    def process_message(self, message_id: str) -> List[AttachmentInfo]:
        """
        이메일 처리 및 첨부파일 저장
        
        Args:
            message_id: Gmail 메시지 ID
            
        Returns:
            List[AttachmentInfo]: 저장된 첨부파일 목록
        """
        if message_id in self._processed_ids:
            return []
        
        message = self.get_message_details(message_id)
        if not message:
            return []
        
        # 헤더에서 정보 추출
        headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
        sender = headers.get('From', 'Unknown')
        subject = headers.get('Subject', 'No Subject')
        date = headers.get('Date', datetime.now().isoformat())
        
        attachments = []
        parts = message['payload'].get('parts', [])
        
        for part in parts:
            filename = part.get('filename', '')
            if not filename:
                continue
            
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            
            if not attachment_id:
                continue
            
            # 첨부파일 다운로드
            file_data = self.download_attachment(message_id, attachment_id, filename)
            if not file_data:
                continue
            
            # 날짜 프리픽스 추가 (ISO 8601)
            date_prefix = datetime.now().strftime("%Y-%m-%d")
            safe_filename = self._sanitize_filename(filename)
            final_filename = f"{date_prefix}_{safe_filename}"
            
            # 로컬 저장
            local_path = self.local_save_path / final_filename
            local_path = self._get_unique_path(local_path)
            
            with open(local_path, 'wb') as f:
                f.write(file_data)
            
            print(f"📎 저장됨: {local_path.name}")
            
            # Google Drive 저장
            gdrive_id = None
            gdrive_path = None
            
            if self._gdrive_sync and self.gdrive_folder_id:
                result = self._gdrive_sync.upload_file(
                    str(local_path),
                    self.gdrive_folder_id
                )
                if result:
                    gdrive_id = result.get('id')
                    gdrive_path = result.get('webViewLink')
                    print(f"☁️ Drive 업로드 완료: {gdrive_id}")
            
            # AttachmentInfo 생성
            info = AttachmentInfo(
                message_id=message_id,
                attachment_id=attachment_id,
                filename=filename,
                mime_type=part.get('mimeType', 'application/octet-stream'),
                size=body.get('size', 0),
                sender=sender,
                subject=subject,
                received_at=date,
                local_path=str(local_path),
                gdrive_path=gdrive_path,
                gdrive_id=gdrive_id
            )
            attachments.append(info)
            
            # 히스토리 콜백
            if self.history_callback:
                self.history_callback({
                    'action': 'EMAIL_ATTACHMENT_SAVED',
                    'source': f"email:{sender}",
                    'destination': str(local_path),
                    'original_name': filename,
                    'new_name': final_filename,
                    'gdrive_id': gdrive_id,
                    'metadata': {
                        'subject': subject,
                        'sender': sender,
                        'size': body.get('size', 0)
                    }
                })
        
        # 처리 완료 표시
        self._processed_ids.add(message_id)
        self._save_processed_ids()
        
        return attachments
    
    def _sanitize_filename(self, filename: str) -> str:
        """파일명 정리"""
        # 위험한 문자 제거
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    def _get_unique_path(self, path: Path) -> Path:
        """중복 없는 경로 생성"""
        if not path.exists():
            return path
        
        counter = 1
        stem = path.stem
        suffix = path.suffix
        
        while True:
            new_path = path.parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
    
    def set_gdrive_sync(self, gdrive_sync):
        """Google Drive 동기화 객체 설정"""
        self._gdrive_sync = gdrive_sync
    
    def check_and_process(self) -> List[AttachmentInfo]:
        """새 이메일 확인 및 처리"""
        all_attachments = []
        
        messages = self.get_unread_with_attachments()
        
        for msg in messages:
            attachments = self.process_message(msg['id'])
            all_attachments.extend(attachments)
        
        return all_attachments
    
    def start(self):
        """실시간 감시 시작"""
        import time
        
        if not self.authenticate():
            return
        
        self._is_running = True
        print(f"📧 Gmail 첨부파일 감시 시작...")
        print(f"   저장 경로: {self.local_save_path}")
        print(f"   확인 간격: {self.check_interval}초")
        
        try:
            while self._is_running:
                attachments = self.check_and_process()
                
                if attachments:
                    print(f"✅ {len(attachments)}개 첨부파일 처리됨")
                
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n📧 Gmail 감시 중지")
    
    def stop(self):
        """감시 중지"""
        self._is_running = False


if __name__ == "__main__":
    import sys
    
    print("📧 AMAA Gmail Watcher Test")
    print("=" * 50)
    
    watcher = GmailWatcher(
        local_save_path="~/Downloads/EmailAttachments"
    )
    
    if watcher.authenticate():
        print("\n최근 첨부파일 이메일 확인 중...")
        attachments = watcher.check_and_process()
        
        for att in attachments:
            print(f"\n📎 {att.filename}")
            print(f"   발신자: {att.sender}")
            print(f"   제목: {att.subject}")
            print(f"   로컬: {att.local_path}")
