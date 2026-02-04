#!/usr/bin/env python3
"""
AMAA v0.4 - Command Line Interface
멀티 에이전트 자율 파일 정리 시스템

Usage:
    amaa scan <path>           # 디렉토리 스캔
    amaa analyze <path>        # 파일 분석
    amaa preview <path>        # 정리 미리보기 (Dry Run)
    amaa execute <path>        # 실제 정리 실행
    amaa undo                  # 마지막 작업 취소
    amaa search <query>        # 파일 검색
    amaa watch <path>          # 실시간 모니터링
    amaa status                # 시스템 상태
    amaa config                # 설정 관리
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Rich 임포트 (fallback 포함)
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.tree import Tree
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Click 임포트 (fallback 포함)
try:
    import click
    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False


# ======================== 콘솔 헬퍼 ========================

class SimpleConsole:
    """Rich 없을 때 사용하는 심플 콘솔"""
    
    def print(self, msg: str, style: str = None):
        print(msg)
    
    def rule(self, title: str = ""):
        print(f"\n{'='*50} {title} {'='*50}\n")

console = Console() if RICH_AVAILABLE else SimpleConsole()


def print_banner():
    """AMAA 배너 출력"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║     🤖 AMAA v0.4 - Autonomous Multi-Agent Architecture    ║
    ║           자율형 파일 정리 시스템 (100% 오픈소스)            ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    if RICH_AVAILABLE:
        console.print(Panel(banner, style="bold blue"))
    else:
        print(banner)


def print_error(msg: str):
    if RICH_AVAILABLE:
        console.print(f"[red]❌ Error:[/red] {msg}")
    else:
        print(f"❌ Error: {msg}")


def print_success(msg: str):
    if RICH_AVAILABLE:
        console.print(f"[green]✅[/green] {msg}")
    else:
        print(f"✅ {msg}")


def print_info(msg: str):
    if RICH_AVAILABLE:
        console.print(f"[blue]ℹ️[/blue] {msg}")
    else:
        print(f"ℹ️ {msg}")


def print_warning(msg: str):
    if RICH_AVAILABLE:
        console.print(f"[yellow]⚠️[/yellow] {msg}")
    else:
        print(f"⚠️ {msg}")


# ======================== Click 기반 CLI ========================

if CLICK_AVAILABLE:
    
    @click.group()
    @click.version_option(version='0.4.0', prog_name='AMAA')
    def cli():
        """
        🤖 AMAA v0.4 - Autonomous Multi-Agent Architecture
        
        자율형 파일 정리 시스템 (100% 오픈소스)
        """
        pass
    
    
    @cli.command()
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--depth', '-d', default=5, help='스캔 깊이')
    @click.option('--output', '-o', default=None, help='결과 저장 경로')
    def scan(path: str, depth: int, output: str):
        """📁 디렉토리 구조 스캔"""
        print_banner()
        
        try:
            from amaa.core.mapmaker import MapMaker
            
            print_info(f"스캔 시작: {path}")
            mapmaker = MapMaker(root_path=path, max_depth=depth)
            
            if RICH_AVAILABLE:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("스캔 중...", total=None)
                    tree = mapmaker.scan()
                    progress.update(task, description="완료!")
            else:
                tree = mapmaker.scan()
            
            # 통계 출력
            stats = tree.get('statistics', {})
            print_success(f"스캔 완료!")
            print_info(f"  총 디렉토리: {stats.get('total_directories', 0)}")
            print_info(f"  총 파일: {stats.get('total_files', 0)}")
            print_info(f"  총 크기: {stats.get('total_size_formatted', 'N/A')}")
            
            # 결과 저장
            if output:
                import json
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(tree, f, ensure_ascii=False, indent=2)
                print_success(f"결과 저장: {output}")
            
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--recursive', '-r', is_flag=True, help='하위 폴더 포함')
    @click.option('--verbose', '-v', is_flag=True, help='상세 출력')
    def analyze(path: str, recursive: bool, verbose: bool):
        """🔬 파일 분석 (AI 기반)"""
        print_banner()
        
        try:
            from amaa.agents.analyzer import AnalyzerAgent
            
            print_info(f"분석 시작: {path}")
            analyzer = AnalyzerAgent()
            
            path_obj = Path(path)
            
            if path_obj.is_file():
                result = analyzer.analyze(str(path_obj))
                _display_analysis_result(result, verbose)
            else:
                files = list(path_obj.glob('**/*' if recursive else '*'))
                files = [f for f in files if f.is_file()]
                
                print_info(f"분석할 파일: {len(files)}개")
                
                if RICH_AVAILABLE:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console
                    ) as progress:
                        task = progress.add_task("분석 중...", total=len(files))
                        
                        for f in files[:50]:  # 최대 50개
                            result = analyzer.analyze(str(f))
                            progress.update(task, advance=1, 
                                          description=f"분석: {f.name[:30]}...")
                            if verbose:
                                _display_analysis_result(result, verbose)
                else:
                    for i, f in enumerate(files[:50]):
                        result = analyzer.analyze(str(f))
                        print(f"[{i+1}/{len(files)}] {f.name}")
            
            print_success("분석 완료!")
            
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    def _display_analysis_result(result: dict, verbose: bool):
        """분석 결과 표시"""
        if RICH_AVAILABLE:
            table = Table(title="📊 분석 결과")
            table.add_column("항목", style="cyan")
            table.add_column("값", style="white")
            
            table.add_row("파일명", result.get('name', 'N/A'))
            table.add_row("카테고리", result.get('category', 'N/A'))
            table.add_row("신뢰도", f"{result.get('confidence', 0):.0%}")
            
            if verbose:
                keywords = result.get('keywords', [])
                table.add_row("키워드", ', '.join(keywords[:5]))
                table.add_row("추천 경로", result.get('suggested_path', 'N/A'))
            
            console.print(table)
        else:
            print(f"  파일: {result.get('name')}")
            print(f"  카테고리: {result.get('category')}")
            print(f"  신뢰도: {result.get('confidence', 0):.0%}")
    
    
    @cli.command()
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--output', '-o', default='.', help='정리 대상 폴더')
    def preview(path: str, output: str):
        """👁️ 정리 미리보기 (Dry Run)"""
        print_banner()
        
        try:
            from amaa.core.orchestrator import Orchestrator
            
            print_info(f"Dry Run 모드 - 실제 파일은 이동되지 않습니다")
            print_info(f"소스: {path}")
            print_info(f"대상: {output}")
            
            orchestrator = Orchestrator()
            orchestrator.dry_run = True
            
            results = orchestrator.scan_and_analyze(path)
            
            if RICH_AVAILABLE:
                table = Table(title="📋 정리 미리보기")
                table.add_column("원본", style="yellow", width=40)
                table.add_column("→", style="dim")
                table.add_column("대상", style="green", width=40)
                table.add_column("카테고리", style="cyan")
                
                for item in results:
                    table.add_row(
                        item['source'][-40:] if len(item['source']) > 40 else item['source'],
                        "→",
                        item.get('suggested_path', 'N/A')[-40:],
                        item.get('category', 'Unknown')
                    )
                
                console.print(table)
            else:
                for item in results:
                    print(f"  {item['source']} → {item.get('suggested_path', 'N/A')}")
            
            print_info(f"총 {len(results)}개 파일이 정리됩니다")
            print_warning("실제 실행하려면: amaa execute <path>")
            
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--output', '-o', default='.', help='정리 대상 폴더')
    @click.option('--yes', '-y', is_flag=True, help='확인 없이 실행')
    def execute(path: str, output: str, yes: bool):
        """🚀 실제 파일 정리 실행"""
        print_banner()
        
        try:
            from amaa.core.orchestrator import Orchestrator
            from amaa.agents.organizer import OrganizerAgent
            
            print_warning("⚠️ 이 명령은 실제로 파일을 이동합니다!")
            
            if not yes:
                confirm = click.confirm("계속하시겠습니까?", default=False)
                if not confirm:
                    print_info("취소되었습니다")
                    return
            
            orchestrator = Orchestrator()
            orchestrator.dry_run = False
            
            # 분석
            print_info("파일 분석 중...")
            results = orchestrator.scan_and_analyze(path)
            
            # 실행
            organizer = OrganizerAgent(base_output_path=output)
            
            print_info(f"파일 정리 중... ({len(results)}개)")
            
            success_count = 0
            for item in results:
                if item.get('suggested_path'):
                    success, _ = organizer.execute_move(
                        item['source'],
                        item['suggested_path']
                    )
                    if success:
                        success_count += 1
            
            print_success(f"완료! {success_count}/{len(results)} 파일 정리됨")
            print_info("실행 취소하려면: amaa undo")
            
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    @click.option('--batch', '-b', default=None, help='특정 배치 ID 취소')
    @click.option('--all', 'undo_all', is_flag=True, help='전체 취소')
    def undo(batch: str, undo_all: bool):
        """↩️ 작업 취소 (Undo)"""
        print_banner()
        
        try:
            from amaa.core.undo import UndoManager
            
            manager = UndoManager()
            
            if batch:
                results = manager.undo_batch(batch)
            elif undo_all:
                print_warning("전체 작업을 취소합니다!")
                confirm = click.confirm("계속하시겠습니까?", default=False)
                if not confirm:
                    return
                results = manager.undo_all()
            else:
                result = manager.undo_last()
                results = [result] if result else []
            
            if results:
                print_success(f"{len(results)}개 작업 취소됨")
                for r in results:
                    if r.get('success'):
                        print_info(f"  ✓ {r.get('action')}: {r.get('source')}")
            else:
                print_info("취소할 작업이 없습니다")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    @click.argument('query')
    @click.option('--category', '-c', default=None, help='카테고리 필터')
    @click.option('--limit', '-l', default=20, help='결과 수 제한')
    def search(query: str, category: str, limit: int):
        """🔍 파일 검색"""
        print_banner()
        
        try:
            from amaa.storage.database import Database
            
            db = Database()
            results = db.search_files(query, category=category, limit=limit)
            
            if results:
                if RICH_AVAILABLE:
                    table = Table(title=f"🔍 검색 결과: '{query}'")
                    table.add_column("파일명", style="cyan")
                    table.add_column("카테고리", style="yellow")
                    table.add_column("경로", style="dim")
                    
                    for r in results:
                        table.add_row(
                            r.get('name', 'N/A'),
                            r.get('category', 'N/A'),
                            r.get('path', 'N/A')[:50]
                        )
                    
                    console.print(table)
                else:
                    for r in results:
                        print(f"  {r.get('name')} [{r.get('category')}] - {r.get('path')}")
                
                print_info(f"총 {len(results)}개 결과")
            else:
                print_info("검색 결과가 없습니다")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    @click.argument('path', type=click.Path(exists=True))
    @click.option('--auto', '-a', is_flag=True, help='자동 정리 모드')
    def watch(path: str, auto: bool):
        """👁️ 실시간 폴더 모니터링"""
        print_banner()
        
        try:
            from amaa.agents.watcher import WatcherAgent
            
            print_info(f"모니터링 시작: {path}")
            print_info("중지하려면 Ctrl+C")
            
            if auto:
                print_warning("자동 정리 모드 활성화")
            
            def on_change(event_type, file_path):
                timestamp = datetime.now().strftime("%H:%M:%S")
                print_info(f"[{timestamp}] {event_type}: {file_path}")
            
            watcher = WatcherAgent(
                watch_paths=[path],
                callback=on_change if not auto else None
            )
            
            watcher.start()
            
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                watcher.stop()
                print_info("\n모니터링 중지됨")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    @cli.command()
    def status():
        """📊 시스템 상태 확인"""
        print_banner()
        
        # 모듈 상태 체크
        modules = {
            'Core - MapMaker': 'amaa.core.mapmaker',
            'Core - Perceiver': 'amaa.core.perceiver',
            'Core - Orchestrator': 'amaa.core.orchestrator',
            'Core - Undo': 'amaa.core.undo',
            'Security - DLP': 'amaa.security.dlp',
            'Agent - Watcher': 'amaa.agents.watcher',
            'Agent - Analyzer': 'amaa.agents.analyzer',
            'Agent - Organizer': 'amaa.agents.organizer',
            'Agent - Reviewer': 'amaa.agents.reviewer',
            'Storage - Database': 'amaa.storage.database',
            'Storage - Indexer': 'amaa.storage.indexer',
        }
        
        if RICH_AVAILABLE:
            table = Table(title="🔧 AMAA 모듈 상태")
            table.add_column("모듈", style="cyan")
            table.add_column("상태", justify="center")
            
            for name, module in modules.items():
                try:
                    __import__(module)
                    table.add_row(name, "[green]✅ OK[/green]")
                except ImportError as e:
                    table.add_row(name, f"[red]❌ {str(e)[:20]}[/red]")
            
            console.print(table)
        else:
            print("모듈 상태:")
            for name, module in modules.items():
                try:
                    __import__(module)
                    print(f"  ✅ {name}")
                except ImportError:
                    print(f"  ❌ {name}")
        
        # Ollama 상태
        print()
        print_info("Ollama 상태 확인 중...")
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get('models', [])
                print_success(f"Ollama 연결됨 - {len(models)}개 모델")
                for m in models[:5]:
                    print_info(f"  • {m.get('name')}")
            else:
                print_warning("Ollama 응답 없음")
        except:
            print_error("Ollama 연결 실패 - ollama serve 실행 필요")
    
    
    @cli.command()
    @click.option('--show', '-s', is_flag=True, help='현재 설정 표시')
    @click.option('--set', 'set_val', nargs=2, help='설정 변경 (key value)')
    def config(show: bool, set_val: tuple):
        """⚙️ 설정 관리"""
        print_banner()
        
        try:
            from amaa.core.config import ConfigManager, load_config
            
            if show:
                cfg = load_config()
                print_info("현재 설정:")
                print(f"  output_base: {cfg.output_base}")
                print(f"  ollama_host: {cfg.ollama_host}")
                print(f"  ollama_model: {cfg.ollama_model}")
                print(f"  dry_run: {cfg.dry_run}")
                print(f"  max_depth: {cfg.max_depth}")
            
            elif set_val:
                key, value = set_val
                from amaa.storage.database import Database
                db = Database()
                db.set_setting(key, value)
                print_success(f"설정 저장됨: {key} = {value}")
            
            else:
                print_info("사용법:")
                print("  amaa config --show        현재 설정 표시")
                print("  amaa config --set KEY VAL 설정 변경")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    # ======================== 새 명령어: 바탕화면 자동 정리 ========================
    
    @cli.command()
    @click.option('--watch', '-w', is_flag=True, help='실시간 모니터링 모드')
    @click.option('--execute', '-e', is_flag=True, help='현재 파일 정리 실행')
    @click.option('--output', '-o', default='~/Documents/Organized', help='정리된 파일 저장 위치')
    def desktop(watch: bool, execute: bool, output: str):
        """🖥️ 바탕화면 자동 정리"""
        print_banner()
        
        try:
            from amaa.agents.desktop_organizer import DesktopOrganizer
            from amaa.core.history import get_tracker
            
            tracker = get_tracker()
            organizer = DesktopOrganizer(
                output_base=output,
                history_tracker=tracker
            )
            
            print_info(f"바탕화면: {organizer.desktop_path}")
            print_info(f"저장 위치: {organizer.output_base}")
            
            if watch:
                print_info("실시간 모니터링 모드")
                organizer.start()
            elif execute:
                results = organizer.organize_all()
                success = sum(1 for r in results if r.success)
                print_success(f"정리 완료: {success}/{len(results)} 파일")
            else:
                # 미리보기
                files = list(organizer.desktop_path.iterdir())
                files = [f for f in files if f.is_file() and not organizer.should_skip(f)]
                
                if RICH_AVAILABLE:
                    table = Table(title="🖥️ 바탕화면 파일 미리보기")
                    table.add_column("파일명", style="cyan")
                    table.add_column("→")
                    table.add_column("카테고리", style="green")
                    
                    for f in files[:20]:
                        cat = organizer.get_category(f)
                        table.add_row(f.name[:40], "→", cat.value)
                    
                    console.print(table)
                else:
                    for f in files[:20]:
                        cat = organizer.get_category(f)
                        print(f"  {f.name} → {cat.value}/")
                
                print_info(f"총 {len(files)}개 파일")
                print_info("실행하려면: amaa desktop --execute")
                print_info("모니터링: amaa desktop --watch")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    # ======================== 새 명령어: Gmail 첨부파일 ========================
    
    @cli.command()
    @click.option('--start', '-s', is_flag=True, help='Gmail 모니터링 시작')
    @click.option('--check', '-c', is_flag=True, help='한 번만 확인')
    @click.option('--output', '-o', default='~/Downloads/EmailAttachments', help='저장 경로')
    def gmail(start: bool, check: bool, output: str):
        """📧 Gmail 첨부파일 자동 저장"""
        print_banner()
        
        try:
            from amaa.integrations.gmail import GmailWatcher
            from amaa.integrations.gdrive import GoogleDriveSync
            from amaa.core.history import get_tracker
            
            tracker = get_tracker()
            
            def history_callback(data):
                tracker.record_email_attachment(
                    sender=data.get('metadata', {}).get('sender', 'unknown'),
                    subject=data.get('metadata', {}).get('subject', ''),
                    original_filename=data.get('original_name', ''),
                    saved_path=data.get('destination', ''),
                    gdrive_id=data.get('gdrive_id')
                )
            
            watcher = GmailWatcher(
                local_save_path=output,
                history_callback=history_callback
            )
            
            if start:
                print_info("Gmail 모니터링 시작...")
                print_info("credentials.json 파일이 필요합니다")
                watcher.start()
            elif check:
                if watcher.authenticate():
                    print_info("새 첨부파일 확인 중...")
                    attachments = watcher.check_and_process()
                    print_success(f"{len(attachments)}개 첨부파일 처리됨")
            else:
                print_info("사용법:")
                print("  amaa gmail --check    한 번 확인")
                print("  amaa gmail --start    실시간 모니터링")
                print()
                print("⚠️ 필요한 설정:")
                print("  1. Google Cloud Console에서 OAuth 자격 증명 생성")
                print("  2. credentials.json 다운로드")
                print("  3. Gmail API 활성화")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
            print_info("pip install google-api-python-client google-auth-oauthlib")
        except Exception as e:
            print_error(str(e))
    
    
    # ======================== 새 명령어: 히스토리 ========================
    
    @cli.command()
    @click.option('--days', '-d', default=7, help='조회 기간 (일)')
    @click.option('--search', '-s', default=None, help='파일명 검색')
    @click.option('--export', '-e', default=None, help='내보내기 경로')
    @click.option('--format', '-f', default='json', type=click.Choice(['json', 'csv', 'md']), help='내보내기 형식')
    def history(days: int, search: str, export: str, format: str):
        """📜 파일 이동/변경 히스토리"""
        print_banner()
        
        try:
            from amaa.core.history import HistoryTracker
            
            tracker = HistoryTracker()
            
            if export:
                output_path = tracker.export_report(export, days=days, format=format)
                print_success(f"히스토리 내보내기 완료: {output_path}")
                return
            
            if search:
                records = tracker.search(search)
                title = f"🔍 검색 결과: '{search}'"
            else:
                records = tracker.get_history(days=days, limit=50)
                title = f"📜 최근 {days}일 히스토리"
            
            if RICH_AVAILABLE:
                table = Table(title=title)
                table.add_column("시간", style="dim", width=16)
                table.add_column("작업", style="cyan", width=10)
                table.add_column("원본 이름", style="yellow", width=25)
                table.add_column("→")
                table.add_column("새 이름", style="green", width=25)
                table.add_column("출처", style="dim", width=8)
                
                for r in records:
                    time_str = r.timestamp[:16] if r.timestamp else ""
                    table.add_row(
                        time_str,
                        r.action_type[:10],
                        (r.original_name or "")[:25],
                        "→",
                        (r.new_name or "")[:25],
                        (r.source or "")[:8]
                    )
                
                console.print(table)
            else:
                print(title)
                print("-" * 80)
                for r in records:
                    print(f"[{r.timestamp[:16]}] {r.action_type}: {r.original_name} → {r.new_name}")
            
            # 통계
            stats = tracker.get_statistics()
            print()
            print_info(f"총 기록: {stats['total_records']}")
            print_info(f"총 크기: {stats['total_size_formatted']}")
            
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
        except Exception as e:
            print_error(str(e))
    
    
    # ======================== 새 명령어: Google Drive 설정 ========================
    
    @cli.command()
    @click.option('--setup', '-s', is_flag=True, help='AMAA 폴더 구조 생성')
    @click.option('--list', '-l', 'list_files', is_flag=True, help='파일 목록')
    @click.option('--upload', '-u', default=None, help='파일 업로드')
    def gdrive(setup: bool, list_files: bool, upload: str):
        """☁️ Google Drive 연동"""
        print_banner()
        
        try:
            from amaa.integrations.gdrive import GoogleDriveSync
            
            sync = GoogleDriveSync()
            
            if not sync.authenticate():
                print_error("Google Drive 인증 실패")
                print_info("credentials.json 파일이 필요합니다")
                return
            
            if setup:
                print_info("AMAA 폴더 구조 생성 중...")
                folders = sync.setup_amaa_folders()
                
                print_success(f"{len(folders)}개 폴더 생성 완료")
                for name, folder_id in list(folders.items())[:10]:
                    print_info(f"  📁 {name}: {folder_id}")
                    
            elif list_files:
                files = sync.list_files(max_results=20)
                
                if RICH_AVAILABLE:
                    table = Table(title="☁️ Google Drive 파일")
                    table.add_column("이름", style="cyan")
                    table.add_column("타입", style="dim")
                    table.add_column("수정일", style="dim")
                    
                    for f in files:
                        table.add_row(
                            f.get('name', '')[:40],
                            f.get('mimeType', '').split('.')[-1][:15],
                            f.get('modifiedTime', '')[:10]
                        )
                    
                    console.print(table)
                else:
                    for f in files:
                        print(f"  {f.get('name')}")
                        
            elif upload:
                result = sync.upload_file(upload)
                if result:
                    print_success(f"업로드 완료: {result.get('name')}")
                    print_info(f"  ID: {result.get('id')}")
                    print_info(f"  Link: {result.get('webViewLink')}")
                else:
                    print_error("업로드 실패")
            else:
                print_info("사용법:")
                print("  amaa gdrive --setup     AMAA 폴더 구조 생성")
                print("  amaa gdrive --list      파일 목록")
                print("  amaa gdrive --upload    파일 업로드")
                
        except ImportError as e:
            print_error(f"모듈 로드 실패: {e}")
            print_info("pip install google-api-python-client google-auth-oauthlib")
        except Exception as e:
            print_error(str(e))


# ======================== Fallback CLI (Click 없을 때) ========================

def fallback_cli():
    """Click 없을 때 기본 CLI"""
    print_banner()
    
    if len(sys.argv) < 2:
        print("사용법: python cli.py <command> [options]")
        print()
        print("명령어:")
        print("  scan <path>      - 디렉토리 스캔")
        print("  analyze <path>   - 파일 분석")
        print("  preview <path>   - 정리 미리보기")
        print("  execute <path>   - 실제 정리 실행")
        print("  undo             - 작업 취소")
        print("  status           - 시스템 상태")
        print()
        print("⚠️ 더 나은 CLI를 위해 Click 설치 권장:")
        print("   pip install click rich")
        return
    
    command = sys.argv[1]
    
    if command == "status":
        print("📊 시스템 상태")
        print("=" * 40)
        print("✅ AMAA v0.4 기본 CLI 모드")
        print()
        print("전체 기능을 위해 다음 패키지 설치:")
        print("  pip install click rich")
    
    elif command == "scan" and len(sys.argv) > 2:
        path = sys.argv[2]
        print(f"📁 스캔: {path}")
        try:
            from amaa.core.mapmaker import MapMaker
            mm = MapMaker(root_path=path)
            tree = mm.scan()
            print(f"✅ 완료! {tree.get('statistics', {}).get('total_files', 0)}개 파일")
        except Exception as e:
            print(f"❌ 오류: {e}")
    
    else:
        print(f"❌ 알 수 없는 명령: {command}")


# ======================== 메인 ========================

def main():
    """메인 엔트리포인트"""
    if CLICK_AVAILABLE:
        cli()
    else:
        fallback_cli()


if __name__ == "__main__":
    main()
