# AMAA v0.4 - Autonomous Multi-Agent Architecture

> 🗂️ AI 기반 자율형 파일 조직화 시스템 (100% 오픈소스, 무료 API)

## 🎯 Overview

AMAA는 **Ollama + LlamaIndex**를 활용하여 로컬에서 완전히 동작하는 지능형 파일 관리 시스템입니다.
유료 API 없이 개인정보 보호와 보안을 최우선으로 설계되었습니다.

## ✨ Key Features

### 🤖 Multi-Agent System (MAS)
- **Watcher Agent**: 파일 시스템 변경 감시 (watchdog)
- **Analyzer Agent**: 파일 내용 분석 및 분류 (Ollama LLM)
- **Organizer Agent**: 지능형 파일 이동 및 정리
- **Reviewer Agent**: 조직화 결과 검토 및 피드백

### 🧠 Local Intelligence
- **Ollama**: 로컬 LLM으로 파일 분류 결정
- **LLaVA**: 이미지/비디오 시맨틱 분석
- **LlamaIndex**: 자연어 파일 검색 (RAG)

### 🔒 Security First
- **Dry Run**: 모든 변경 사항 미리보기
- **Undo System**: 완전한 실행 취소 지원
- **DLP**: 기밀 데이터 자동 감지 및 보호

### ⚡ Performance
- Python 3.11+ 비동기 처리
- 멀티코어 병렬 스캔
- 제네레이터 기반 대용량 파일 처리

## 📦 Installation

```bash
# 1. Clone repository
git clone https://github.com/kun-jan22/Organizer.git
cd Organizer

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Ollama (https://ollama.ai)
# Then pull required models:
ollama pull llama3.2
ollama pull llava
```

## 🚀 Quick Start

```bash
# 1. Scan directory and build taxonomy map
amaa scan ~/Documents

# 2. Analyze files (dry run by default)
amaa analyze ~/Downloads

# 3. Preview changes before execution
amaa preview

# 4. Execute organization (with confirmation)
amaa execute

# 5. Undo last action if needed
amaa undo
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AMAA v0.4 Architecture                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Watcher   │───▶│  Analyzer   │───▶│  Organizer  │     │
│  │   Agent     │    │   Agent     │    │   Agent     │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Reviewer Agent                      │   │
│  │            (Feedback & Learning Loop)                │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                 │
│  ┌───────────────────────┴───────────────────────┐         │
│  │                 Core Services                  │         │
│  ├───────────────────────────────────────────────┤         │
│  │  MapMaker │ Perceiver │ UndoManager │ DLP     │         │
│  └───────────────────────────────────────────────┘         │
│                           │                                 │
│  ┌───────────────────────┴───────────────────────┐         │
│  │              Storage Layer                     │         │
│  │  SQLite (History) │ JSON (Config) │ Index     │         │
│  └───────────────────────────────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
Organizer/
├── amaa/
│   ├── __init__.py
│   ├── agents/           # Multi-Agent System
│   │   ├── watcher.py    # File system monitoring
│   │   ├── analyzer.py   # Content analysis
│   │   ├── organizer.py  # File organization
│   │   └── reviewer.py   # Quality review
│   ├── core/             # Core modules
│   │   ├── mapmaker.py   # Directory indexer
│   │   ├── perceiver.py  # Multimodal extraction
│   │   ├── orchestrator.py # Workflow control
│   │   └── undo.py       # Undo system
│   ├── security/         # Security features
│   │   ├── dlp.py        # Data Loss Prevention
│   │   └── permissions.py # OS permission checks
│   ├── storage/          # Data persistence
│   │   ├── database.py   # SQLite operations
│   │   └── indexer.py    # LlamaIndex integration
│   └── utils/            # Utilities
│       ├── config.py     # Configuration
│       ├── logger.py     # Logging
│       └── fileops.py    # File operations
├── cli.py                # Command-line interface
├── gui.py                # GUI interface (Tkinter)
├── config.yaml           # Configuration file
├── requirements.txt      # Dependencies
└── tests/                # Unit tests
```

## ⚙️ Configuration

```yaml
# config.yaml
amaa:
  # Ollama settings
  ollama:
    base_url: "http://localhost:11434"
    model: "llama3.2"
    vision_model: "llava"
  
  # File naming convention
  naming:
    date_prefix: true  # ISO 8601 (YYYY-MM-DD)
    separator: "_"
  
  # Safety settings
  safety:
    dry_run_default: true
    confirm_before_execute: true
    max_files_per_batch: 100
  
  # DLP settings
  dlp:
    enabled: true
    keywords: ["기밀", "confidential", "secret", "private"]
    action: "tag"  # tag, quarantine, alert
```

## 🔧 CLI Commands

| Command | Description |
|---------|-------------|
| `amaa scan <path>` | 디렉토리 스캔 및 구조 분석 |
| `amaa analyze <path>` | 파일 분석 및 분류 제안 |
| `amaa preview` | 변경 사항 미리보기 |
| `amaa execute` | 파일 이동 실행 |
| `amaa undo` | 마지막 작업 취소 |
| `amaa search <query>` | 자연어 파일 검색 |
| `amaa status` | 현재 상태 확인 |
| `amaa config` | 설정 관리 |

## 🛡️ Security Features

### DLP (Data Loss Prevention)
- 기밀 키워드 자동 감지
- 민감 파일 태그 및 격리
- 암호화 옵션 지원

### Permission Checks
- Windows PowerShell 실행 정책 확인
- macOS TCC 권한 체크
- Linux 파일 권한 검증

## 📊 Supported File Types

| Category | Extensions |
|----------|------------|
| Documents | `.pdf`, `.docx`, `.txt`, `.md`, `.xlsx` |
| Images | `.jpg`, `.png`, `.gif`, `.webp`, `.heic` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv` |
| Audio | `.mp3`, `.wav`, `.flac`, `.m4a` |
| Code | `.py`, `.js`, `.ts`, `.java`, `.cpp` |
| Archives | `.zip`, `.tar`, `.gz`, `.7z` |

## 🔄 Roadmap

- [x] v0.1 - Basic directory indexer
- [x] v0.2 - Ollama integration
- [x] v0.3 - Undo system
- [x] v0.4 - Multi-agent architecture
- [ ] v0.5 - GUI interface
- [ ] v0.6 - Cloud sync support
- [ ] v1.0 - Production release

## 📝 License

MIT License - See [LICENSE](LICENSE)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

**Made with ❤️ for organized files**
