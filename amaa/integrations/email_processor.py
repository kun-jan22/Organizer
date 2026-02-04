"""
AMAA v0.4.2 - Email Processor
과거/현재 이메일 처리 + AI 요약 + Google Sheets 연동

Features:
- 과거 이메일 일괄 처리 (날짜 범위 지정)
- Gemini/Ollama AI로 이메일 요약
- Task/Request/Deadline 자동 추출
- Google Sheets에 자동 기록
- 첨부파일 저장 (로컬 + Drive)
"""

import os
import base64
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict, field
from email.utils import parsedate_to_datetime
import json

# 환경변수 로드
from dotenv import load_dotenv
load_dotenv()


@dataclass
class EmailSummary:
    """이메일 요약 데이터"""
    message_id: str
    date: str
    sender: str
    recipients: str
    subject: str
    body_preview: str  # 원문 일부
    summary: str  # AI 요약
    tasks: List[str] = field(default_factory=list)  # Task 목록
    requests: List[str] = field(default_factory=list)  # Request 목록
    deadlines: List[str] = field(default_factory=list)  # Deadline 목록
    attachments: List[str] = field(default_factory=list)  # 첨부파일 목록
    attachment_paths: List[str] = field(default_factory=list)  # 저장 경로
    labels: List[str] = field(default_factory=list)  # Gmail 라벨
    is_important: bool = False
    needs_action: bool = False




class OllamaClient:
    """Ollama AI 클라이언트 (로컬 LLM)"""
    
    def __init__(self, model: str = "llama3.2"):
        self.model = model
        self.base_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self._available = None
    
    def is_available(self) -> bool:
        """Ollama 서버 가용성 확인"""
        if self._available is not None:
            return self._available
        
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            self._available = response.status_code == 200
            return self._available
        except:
            self._available = False
            return False
    
    def summarize_email(self, subject: str, body: str, sender: str) -> Dict[str, Any]:
        """Ollama로 이메일 요약"""
        if not self.is_available():
            return None
        
        import requests
        
        prompt = f"""다음 이메일을 분석해주세요.

발신자: {sender}
제목: {subject}

본문:
{body[:2000]}

다음 JSON 형식으로만 응답해주세요:
{{"summary": "이메일 핵심 내용 2-3문장 요약 (한국어)", "tasks": ["해야 할 일"], "requests": ["요청 사항"], "deadlines": ["마감일"], "is_important": true/false, "needs_action": true/false}}

JSON만 응답하세요, 다른 텍스트 없이."""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=60
            )
            
            if response.status_code == 200:
                text = response.json().get('response', '').strip()
                
                # JSON 추출
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0]
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0]
                
                # JSON 파싱 시도
                import json
                return json.loads(text)
        except Exception as e:
            print(f"⚠️ Ollama 요약 실패: {e}")
        
        return None


class GeminiClient:
    """Gemini AI 클라이언트"""
    
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        self._model = None
    
    def _init_model(self):
        if self._model:
            return True
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel('gemini-2.0-flash')
            return True
        except ImportError:
            print("⚠️ google-generativeai 설치 필요: pip install google-generativeai")
            return False
        except Exception as e:
            print(f"❌ Gemini 초기화 실패: {e}")
            return False
    
    def summarize_email(self, subject: str, body: str, 
                        sender: str) -> Dict[str, Any]:
        """이메일 요약 및 태스크 추출"""
        if not self._init_model():
            return self._fallback_summary(subject, body)
        
        prompt = f"""다음 이메일을 분석해주세요.

발신자: {sender}
제목: {subject}

본문:
{body[:3000]}  # 최대 3000자

다음 JSON 형식으로 응답해주세요:
{{
    "summary": "이메일 핵심 내용 2-3문장 요약 (한국어)",
    "tasks": ["해야 할 일 목록"],
    "requests": ["요청 사항 목록"],
    "deadlines": ["마감일/기한 목록 (날짜 포함)"],
    "is_important": true/false,
    "needs_action": true/false
}}

JSON만 응답하세요."""
        
        try:
            response = self._model.generate_content(prompt)
            text = response.text.strip()
            
            # JSON 추출
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            return json.loads(text)
            
        except Exception as e:
            print(f"⚠️ Gemini 요약 실패: {e}")
            # Ollama fallback 시도
            ollama_result = self._try_ollama(subject, body, sender)
            if ollama_result:
                print("  ✓ Ollama fallback 성공")
                return ollama_result
            return self._fallback_summary(subject, body)
    
    def _try_ollama(self, subject: str, body: str, sender: str) -> Optional[Dict[str, Any]]:
        """Ollama로 fallback 시도"""
        try:
            ollama = OllamaClient(model="llama3.2")
            if ollama.is_available():
                return ollama.summarize_email(subject, body, sender)
        except:
            pass
        return None

    def _fallback_summary(self, subject: str, body: str) -> Dict[str, Any]:
        """Gemini 실패 시 기본 추출"""
        # 간단한 키워드 기반 추출
        deadlines = []
        tasks = []
        requests = []
        
        # 날짜 패턴
        date_patterns = [
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',
            r'\d{1,2}월\s*\d{1,2}일',
            r'(today|tomorrow|next week|다음주|내일|오늘)',
        ]
        for pattern in date_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            deadlines.extend(matches[:3])
        
        # 요청 패턴
        request_patterns = [
            r'(please|요청|부탁|확인.*주세요|검토.*주세요)',
        ]
        for pattern in request_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                requests.append("요청 사항 있음")
                break
        
        return {
            'summary': f"제목: {subject[:100]}",
            'tasks': tasks,
            'requests': requests,
            'deadlines': deadlines,
            'is_important': '긴급' in subject or 'urgent' in subject.lower(),
            'needs_action': len(requests) > 0 or len(deadlines) > 0
        }


class GoogleSheetsClient:
    """Google Sheets 클라이언트"""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, credentials_path: str = "./credentials.json",
                 token_path: str = "~/.amaa/sheets_token.json"):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path).expanduser()
        self._service = None
    
    def authenticate(self) -> bool:
        """Google Sheets API 인증"""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            
            creds = None
            
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), self.SCOPES
                )
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
            
            self._service = build('sheets', 'v4', credentials=creds)
            print("✅ Google Sheets API 인증 성공")
            return True
            
        except ImportError:
            print("❌ Google API 라이브러리 필요")
            return False
        except Exception as e:
            print(f"❌ Sheets 인증 실패: {e}")
            return False
    
    def create_email_sheet(self, title: str = "AMAA Email Summary") -> Optional[str]:
        """이메일 요약용 스프레드시트 생성"""
        if not self._service:
            return None
        
        try:
            spreadsheet = {
                'properties': {'title': title},
                'sheets': [{
                    'properties': {
                        'title': 'Emails',
                        'gridProperties': {'frozenRowCount': 1}
                    }
                }]
            }
            
            result = self._service.spreadsheets().create(
                body=spreadsheet
            ).execute()
            
            spreadsheet_id = result['spreadsheetId']
            sheet_id = result['sheets'][0]['properties']['sheetId']
            
            # 헤더 추가
            headers = [
                ['날짜', '발신자', '수신자', '제목', '원문 미리보기', 
                 'AI 요약', 'Tasks', 'Requests', 'Deadlines', 
                 '첨부파일', '중요', '조치필요', '라벨']
            ]
            
            self._service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Emails!A1:M1',
                valueInputOption='RAW',
                body={'values': headers}
            ).execute()
            
            # 서식 적용 (헤더 굵게)
            requests = [{
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 1
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {'red': 0.2, 'green': 0.5, 'blue': 0.8},
                            'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                }
            }]
            
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            print(f"✅ 스프레드시트 생성됨: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
            return spreadsheet_id
            
        except Exception as e:
            print(f"❌ 스프레드시트 생성 실패: {e}")
            return None
    
    def append_email_summary(self, spreadsheet_id: str, 
                             summary: EmailSummary) -> bool:
        """이메일 요약 추가"""
        if not self._service:
            return False
        
        try:
            row = [
                summary.date,
                summary.sender,
                summary.recipients,
                summary.subject,
                summary.body_preview[:500],  # 미리보기 500자 제한
                summary.summary,
                '\n'.join(summary.tasks),
                '\n'.join(summary.requests),
                '\n'.join(summary.deadlines),
                '\n'.join(summary.attachments),
                '✅' if summary.is_important else '',
                '⚠️' if summary.needs_action else '',
                ', '.join(summary.labels)
            ]
            
            self._service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='Emails!A:M',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            
            return True
            
        except Exception as e:
            print(f"❌ 시트 추가 실패: {e}")
            return False
    
    def batch_append(self, spreadsheet_id: str, 
                     summaries: List[EmailSummary]) -> int:
        """여러 이메일 일괄 추가"""
        if not self._service:
            return 0
        
        rows = []
        for s in summaries:
            rows.append([
                s.date,
                s.sender,
                s.recipients,
                s.subject,
                s.body_preview[:500],
                s.summary,
                '\n'.join(s.tasks),
                '\n'.join(s.requests),
                '\n'.join(s.deadlines),
                '\n'.join(s.attachments),
                '✅' if s.is_important else '',
                '⚠️' if s.needs_action else '',
                ', '.join(s.labels)
            ])
        
        try:
            self._service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='Emails!A:M',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
            
            return len(rows)
            
        except Exception as e:
            print(f"❌ 일괄 추가 실패: {e}")
            return 0


class EmailProcessor:
    """
    이메일 처리기
    
    과거/현재 이메일을 처리하고 Google Sheets에 기록합니다.
    
    Usage:
        processor = EmailProcessor()
        processor.authenticate()
        
        # 과거 7일 이메일 처리
        processor.process_past_emails(days=7)
        
        # 특정 날짜 범위
        processor.process_date_range("2025-01-01", "2025-02-01")
    """
    
    GMAIL_SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify',
    ]
    
    def __init__(self,
                 credentials_path: str = "./credentials.json",
                 local_save_path: str = "~/Downloads/EmailAttachments",
                 spreadsheet_id: Optional[str] = None):
        self.credentials_path = Path(credentials_path)
        self.local_save_path = Path(local_save_path).expanduser()
        self.spreadsheet_id = spreadsheet_id
        
        self.local_save_path.mkdir(parents=True, exist_ok=True)
        
        self._gmail_service = None
        self._gemini = GeminiClient()
        self._sheets = GoogleSheetsClient(str(credentials_path))
        self._gdrive = None
    
    def authenticate(self) -> bool:
        """모든 API 인증"""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            
            # Gmail + Sheets 통합 스코프
            combined_scopes = self.GMAIL_SCOPES + self._sheets.SCOPES
            
            token_path = Path("~/.amaa/gmail_sheets_token.json").expanduser()
            creds = None
            
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(token_path), combined_scopes
                )
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), combined_scopes
                    )
                    creds = flow.run_local_server(port=0)
                
                token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            
            # 서비스 빌드
            self._gmail_service = build('gmail', 'v1', credentials=creds)
            self._sheets._service = build('sheets', 'v4', credentials=creds)
            
            print("✅ Gmail + Sheets API 인증 성공")
            return True
            
        except Exception as e:
            print(f"❌ 인증 실패: {e}")
            return False
    
    def setup_spreadsheet(self, title: str = None) -> str:
        """스프레드시트 설정 (없으면 생성)"""
        if self.spreadsheet_id:
            return self.spreadsheet_id
        
        title = title or f"AMAA Email Summary - {datetime.now().strftime('%Y-%m')}"
        self.spreadsheet_id = self._sheets.create_email_sheet(title)
        
        return self.spreadsheet_id
    
    def get_emails(self, query: str = "", 
                   max_results: int = 100) -> List[Dict]:
        """이메일 목록 조회"""
        if not self._gmail_service:
            return []
        
        try:
            results = self._gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            return results.get('messages', [])
            
        except Exception as e:
            print(f"❌ 이메일 조회 실패: {e}")
            return []
    
    def get_message_detail(self, message_id: str) -> Optional[Dict]:
        """메시지 상세 조회"""
        if not self._gmail_service:
            return None
        
        try:
            return self._gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
        except Exception as e:
            print(f"❌ 메시지 조회 실패: {e}")
            return None
    
    def parse_message(self, message: Dict) -> EmailSummary:
        """메시지 파싱"""
        headers = {h['name'].lower(): h['value'] 
                   for h in message['payload'].get('headers', [])}
        
        # 기본 정보
        message_id = message['id']
        subject = headers.get('subject', '(제목 없음)')
        sender = headers.get('from', 'Unknown')
        recipients = headers.get('to', '')
        date_str = headers.get('date', '')
        
        # 날짜 파싱
        try:
            date_obj = parsedate_to_datetime(date_str)
            date = date_obj.strftime('%Y-%m-%d %H:%M')
        except:
            date = date_str[:19] if date_str else ''
        
        # 본문 추출
        body = self._extract_body(message['payload'])
        
        # 첨부파일 목록
        attachments = []
        parts = message['payload'].get('parts', [])
        for part in parts:
            filename = part.get('filename', '')
            if filename:
                attachments.append(filename)
        
        # 라벨
        labels = message.get('labelIds', [])
        
        # AI 요약
        ai_result = self._gemini.summarize_email(subject, body, sender)
        
        return EmailSummary(
            message_id=message_id,
            date=date,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body_preview=body[:1000],
            summary=ai_result.get('summary', ''),
            tasks=ai_result.get('tasks', []),
            requests=ai_result.get('requests', []),
            deadlines=ai_result.get('deadlines', []),
            attachments=attachments,
            labels=labels,
            is_important=ai_result.get('is_important', False),
            needs_action=ai_result.get('needs_action', False)
        )
    
    def _extract_body(self, payload: Dict) -> str:
        """이메일 본문 추출"""
        body = ""
        
        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8', errors='ignore')
        
        if not body and 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if part['body'].get('data'):
                        body = base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8', errors='ignore')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if part['body'].get('data'):
                        html = base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8', errors='ignore')
                        # HTML 태그 제거
                        body = re.sub(r'<[^>]+>', '', html)
        
        return body.strip()
    
    def download_attachments(self, message_id: str, 
                             message: Dict) -> List[str]:
        """첨부파일 다운로드"""
        saved_paths = []
        parts = message['payload'].get('parts', [])
        
        for part in parts:
            filename = part.get('filename', '')
            if not filename:
                continue
            
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            
            if not attachment_id:
                continue
            
            try:
                attachment = self._gmail_service.users().messages().attachments().get(
                    userId='me',
                    messageId=message_id,
                    id=attachment_id
                ).execute()
                
                data = base64.urlsafe_b64decode(attachment['data'])
                
                # 날짜 프리픽스
                date_prefix = datetime.now().strftime("%Y-%m-%d")
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                final_filename = f"{date_prefix}_{safe_filename}"
                
                save_path = self.local_save_path / final_filename
                
                # 중복 방지
                counter = 1
                while save_path.exists():
                    save_path = self.local_save_path / f"{date_prefix}_{counter}_{safe_filename}"
                    counter += 1
                
                with open(save_path, 'wb') as f:
                    f.write(data)
                
                saved_paths.append(str(save_path))
                print(f"📎 저장: {save_path.name}")
                
            except Exception as e:
                print(f"⚠️ 첨부파일 다운로드 실패 ({filename}): {e}")
        
        return saved_paths
    
    def process_past_emails(self, days: int = 7, 
                            include_attachments: bool = True,
                            save_to_sheets: bool = True) -> List[EmailSummary]:
        """
        과거 이메일 처리
        
        Args:
            days: 처리할 일수
            include_attachments: 첨부파일 다운로드 여부
            save_to_sheets: Google Sheets 저장 여부
        """
        # 날짜 쿼리
        after_date = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
        query = f"after:{after_date}"
        
        return self._process_emails(query, include_attachments, save_to_sheets)
    
    def process_date_range(self, start_date: str, end_date: str,
                           include_attachments: bool = True,
                           save_to_sheets: bool = True) -> List[EmailSummary]:
        """
        날짜 범위 이메일 처리
        
        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
        """
        # Gmail 날짜 형식 변환
        start = start_date.replace('-', '/')
        end = end_date.replace('-', '/')
        query = f"after:{start} before:{end}"
        
        return self._process_emails(query, include_attachments, save_to_sheets)
    
    def process_with_query(self, query: str,
                           include_attachments: bool = True,
                           save_to_sheets: bool = True) -> List[EmailSummary]:
        """
        커스텀 쿼리로 이메일 처리
        
        Args:
            query: Gmail 검색 쿼리
                예: "from:someone@example.com"
                    "has:attachment"
                    "is:unread"
                    "subject:invoice"
        """
        return self._process_emails(query, include_attachments, save_to_sheets)
    
    def _process_emails(self, query: str,
                        include_attachments: bool,
                        save_to_sheets: bool) -> List[EmailSummary]:
        """이메일 처리 내부 로직"""
        print(f"📧 이메일 검색 중... (쿼리: {query})")
        
        messages = self.get_emails(query, max_results=100)
        print(f"   {len(messages)}개 이메일 발견")
        
        if not messages:
            return []
        
        # 스프레드시트 설정
        if save_to_sheets:
            self.setup_spreadsheet()
        
        summaries = []
        
        for i, msg in enumerate(messages):
            print(f"   [{i+1}/{len(messages)}] 처리 중...")
            
            detail = self.get_message_detail(msg['id'])
            if not detail:
                continue
            
            # 파싱 및 요약
            summary = self.parse_message(detail)
            
            # 첨부파일 다운로드
            if include_attachments and summary.attachments:
                saved = self.download_attachments(msg['id'], detail)
                summary.attachment_paths = saved
            
            summaries.append(summary)
        
        # Sheets에 저장
        if save_to_sheets and self.spreadsheet_id:
            count = self._sheets.batch_append(self.spreadsheet_id, summaries)
            print(f"✅ {count}개 이메일 시트에 저장됨")
            print(f"   https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}")
        
        print(f"✅ 총 {len(summaries)}개 이메일 처리 완료")
        
        return summaries


if __name__ == "__main__":
    import sys
    
    print("📧 AMAA Email Processor Test")
    print("=" * 50)
    
    processor = EmailProcessor()
    
    if processor.authenticate():
        # 테스트: 최근 3일 이메일
        if len(sys.argv) > 1:
            days = int(sys.argv[1])
        else:
            days = 3
        
        print(f"\n최근 {days}일 이메일 처리 중...")
        summaries = processor.process_past_emails(days=days)
        
        print(f"\n📊 결과:")
        for s in summaries[:5]:
            print(f"\n  📩 {s.subject[:50]}")
            print(f"     발신: {s.sender[:30]}")
            print(f"     요약: {s.summary[:100]}")
            if s.tasks:
                print(f"     Tasks: {s.tasks}")
            if s.deadlines:
                print(f"     Deadlines: {s.deadlines}")
