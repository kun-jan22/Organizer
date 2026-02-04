"""
AMAA v0.4 - Permission Checker
OS별 권한 확인 유틸리티

Step 4: 권한 가드레일
- Windows PowerShell 실행 정책 확인
- macOS TCC 권한 체크
- Linux 파일 권한 검증
"""

import os
import sys
import stat
import platform
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class OSType(Enum):
    """OS 타입"""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


class PermissionType(Enum):
    """권한 타입"""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    FULL_ACCESS = "full_access"


@dataclass
class PermissionResult:
    """권한 확인 결과"""
    path: str
    is_accessible: bool = False
    can_read: bool = False
    can_write: bool = False
    can_execute: bool = False
    can_delete: bool = False
    owner: Optional[str] = None
    permissions: Optional[str] = None
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'is_accessible': self.is_accessible,
            'can_read': self.can_read,
            'can_write': self.can_write,
            'can_execute': self.can_execute,
            'can_delete': self.can_delete,
            'owner': self.owner,
            'permissions': self.permissions,
            'issues': self.issues,
            'recommendations': self.recommendations,
        }


class PermissionChecker:
    """
    OS별 권한 확인 유틸리티
    
    파일 시스템 접근 권한을 확인하고 문제점 진단
    
    Usage:
        checker = PermissionChecker()
        
        # 시스템 권한 확인
        sys_result = checker.check_system_permissions()
        
        # 경로 권한 확인
        path_result = checker.check_path_permissions("/path/to/check")
    """
    
    def __init__(self):
        self.os_type = self._detect_os()
        self.is_admin = self._check_admin()
    
    def _detect_os(self) -> OSType:
        """OS 타입 감지"""
        system = platform.system().lower()
        
        if system == 'windows':
            return OSType.WINDOWS
        elif system == 'darwin':
            return OSType.MACOS
        elif system == 'linux':
            return OSType.LINUX
        else:
            return OSType.UNKNOWN
    
    def _check_admin(self) -> bool:
        """관리자/루트 권한 확인"""
        try:
            if self.os_type == OSType.WINDOWS:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except:
            return False
    
    def check_system_permissions(self) -> Dict[str, Any]:
        """
        시스템 전체 권한 상태 확인
        
        Returns:
            Dict: 시스템 권한 정보
        """
        result = {
            'os': self.os_type.value,
            'os_version': platform.version(),
            'is_admin': self.is_admin,
            'python_version': sys.version,
            'issues': [],
            'recommendations': [],
        }
        
        if self.os_type == OSType.WINDOWS:
            result.update(self._check_windows_permissions())
        elif self.os_type == OSType.MACOS:
            result.update(self._check_macos_permissions())
        elif self.os_type == OSType.LINUX:
            result.update(self._check_linux_permissions())
        
        return result
    
    def _check_windows_permissions(self) -> Dict[str, Any]:
        """Windows 권한 확인"""
        result = {
            'execution_policy': None,
            'user_profile': os.environ.get('USERPROFILE'),
            'program_files_access': False,
        }
        
        issues = []
        recommendations = []
        
        # PowerShell 실행 정책 확인
        try:
            ps_result = subprocess.run(
                ['powershell', '-Command', 'Get-ExecutionPolicy'],
                capture_output=True, text=True, timeout=10
            )
            policy = ps_result.stdout.strip()
            result['execution_policy'] = policy
            
            if policy == 'Restricted':
                issues.append("PowerShell execution policy is Restricted")
                recommendations.append(
                    "Run as Administrator: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser"
                )
        except Exception as e:
            issues.append(f"Could not check PowerShell execution policy: {e}")
        
        # Program Files 접근 확인
        try:
            pf = Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files'))
            result['program_files_access'] = os.access(str(pf), os.W_OK)
        except:
            pass
        
        # Windows Defender 제외 권장
        recommendations.append(
            "Consider adding AMAA folder to Windows Defender exclusions for better performance"
        )
        
        result['issues'] = issues
        result['recommendations'] = recommendations
        
        return result
    
    def _check_macos_permissions(self) -> Dict[str, Any]:
        """macOS 권한 확인 (TCC 포함)"""
        result = {
            'tcc_full_disk_access': None,
            'tcc_automation': None,
            'sip_enabled': None,
            'home_dir': os.path.expanduser('~'),
        }
        
        issues = []
        recommendations = []
        
        # TCC (Transparency, Consent, and Control) 확인
        # Full Disk Access
        try:
            # Desktop 폴더 접근으로 확인
            desktop = Path.home() / 'Desktop'
            if desktop.exists():
                test_file = desktop / '.amaa_permission_test'
                try:
                    test_file.touch()
                    test_file.unlink()
                    result['tcc_full_disk_access'] = True
                except PermissionError:
                    result['tcc_full_disk_access'] = False
                    issues.append("Full Disk Access permission not granted")
                    recommendations.append(
                        "Grant Full Disk Access: System Preferences > Security & Privacy > Privacy > Full Disk Access"
                    )
        except Exception as e:
            issues.append(f"Could not check TCC permissions: {e}")
        
        # SIP (System Integrity Protection) 상태
        try:
            sip_result = subprocess.run(
                ['csrutil', 'status'],
                capture_output=True, text=True, timeout=5
            )
            result['sip_enabled'] = 'enabled' in sip_result.stdout.lower()
        except:
            pass
        
        result['issues'] = issues
        result['recommendations'] = recommendations
        
        return result
    
    def _check_linux_permissions(self) -> Dict[str, Any]:
        """Linux 권한 확인"""
        result = {
            'selinux_status': None,
            'apparmor_status': None,
            'home_dir': os.path.expanduser('~'),
            'current_user': os.environ.get('USER'),
        }
        
        issues = []
        recommendations = []
        
        # SELinux 상태
        try:
            se_result = subprocess.run(
                ['getenforce'],
                capture_output=True, text=True, timeout=5
            )
            result['selinux_status'] = se_result.stdout.strip()
            
            if result['selinux_status'] == 'Enforcing':
                recommendations.append(
                    "SELinux is enforcing. You may need to set appropriate contexts for AMAA files."
                )
        except FileNotFoundError:
            result['selinux_status'] = 'Not installed'
        except:
            pass
        
        # AppArmor 상태
        try:
            aa_result = subprocess.run(
                ['aa-status', '--enabled'],
                capture_output=True, text=True, timeout=5
            )
            result['apparmor_status'] = 'enabled' if aa_result.returncode == 0 else 'disabled'
        except FileNotFoundError:
            result['apparmor_status'] = 'Not installed'
        except:
            pass
        
        result['issues'] = issues
        result['recommendations'] = recommendations
        
        return result
    
    def check_path_permissions(self, path: str) -> PermissionResult:
        """
        특정 경로의 권한 확인
        
        Args:
            path: 확인할 경로
            
        Returns:
            PermissionResult: 권한 확인 결과
        """
        p = Path(path).expanduser().resolve()
        result = PermissionResult(path=str(p))
        
        if not p.exists():
            result.issues.append("Path does not exist")
            result.recommendations.append(f"Create the directory: mkdir -p {p}")
            return result
        
        # 기본 접근 확인
        result.is_accessible = os.access(str(p), os.F_OK)
        result.can_read = os.access(str(p), os.R_OK)
        result.can_write = os.access(str(p), os.W_OK)
        result.can_execute = os.access(str(p), os.X_OK)
        
        # 삭제 권한 (부모 디렉토리 쓰기 권한)
        if p.parent.exists():
            result.can_delete = os.access(str(p.parent), os.W_OK)
        
        # 상세 권한 정보
        try:
            stat_info = p.stat()
            mode = stat_info.st_mode
            result.permissions = stat.filemode(mode)
            
            # 소유자 정보
            if self.os_type != OSType.WINDOWS:
                import pwd
                try:
                    result.owner = pwd.getpwuid(stat_info.st_uid).pw_name
                except:
                    result.owner = str(stat_info.st_uid)
        except:
            pass
        
        # 문제점 분석
        if not result.can_read:
            result.issues.append("Cannot read from this path")
            self._add_permission_recommendation(result, 'read')
        
        if not result.can_write:
            result.issues.append("Cannot write to this path")
            self._add_permission_recommendation(result, 'write')
        
        return result
    
    def _add_permission_recommendation(self, result: PermissionResult, 
                                       perm_type: str) -> None:
        """권한 수정 권장사항 추가"""
        path = result.path
        
        if self.os_type == OSType.WINDOWS:
            if perm_type == 'write':
                result.recommendations.append(
                    f"Right-click on '{path}' > Properties > Security > Edit permissions"
                )
        else:
            if perm_type == 'read':
                result.recommendations.append(f"chmod +r '{path}'")
            elif perm_type == 'write':
                result.recommendations.append(f"chmod +w '{path}'")
                result.recommendations.append(f"Or change owner: sudo chown $USER '{path}'")
    
    def check_amaa_requirements(self, 
                                target_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        AMAA 실행에 필요한 모든 권한 확인
        
        Args:
            target_dirs: 추가로 확인할 디렉토리 목록
            
        Returns:
            Dict: 종합 권한 확인 결과
        """
        result = {
            'system': self.check_system_permissions(),
            'paths': {},
            'all_ok': True,
            'critical_issues': [],
        }
        
        # 기본 경로들 확인
        default_paths = [
            Path.home() / '.amaa',
            Path.home() / 'Downloads',
            Path.home() / 'Documents',
        ]
        
        if target_dirs:
            default_paths.extend(Path(d) for d in target_dirs)
        
        for p in default_paths:
            path_result = self.check_path_permissions(str(p))
            result['paths'][str(p)] = path_result.to_dict()
            
            if not path_result.can_write:
                result['all_ok'] = False
                result['critical_issues'].append(
                    f"Cannot write to {p}: {', '.join(path_result.issues)}"
                )
        
        return result
    
    def ensure_directory(self, path: str) -> bool:
        """
        디렉토리 존재 및 권한 확보
        
        Args:
            path: 확인/생성할 디렉토리
            
        Returns:
            bool: 성공 여부
        """
        p = Path(path).expanduser()
        
        try:
            p.mkdir(parents=True, exist_ok=True)
            
            # 권한 확인
            if not os.access(str(p), os.W_OK):
                return False
            
            return True
        except Exception:
            return False
    
    def fix_permissions(self, path: str, 
                        mode: int = 0o755) -> bool:
        """
        권한 수정 시도 (Unix 계열만)
        
        Args:
            path: 대상 경로
            mode: 설정할 권한 (기본: 755)
            
        Returns:
            bool: 성공 여부
        """
        if self.os_type == OSType.WINDOWS:
            # Windows는 별도 처리 필요
            return False
        
        try:
            p = Path(path)
            p.chmod(mode)
            return True
        except Exception:
            return False
    
    def get_recommended_setup(self) -> str:
        """권장 설정 가이드 반환"""
        lines = [
            "=" * 50,
            "AMAA v0.4 - Recommended Permission Setup",
            "=" * 50,
            "",
        ]
        
        if self.os_type == OSType.WINDOWS:
            lines.extend([
                "🪟 Windows Setup:",
                "",
                "1. PowerShell Execution Policy:",
                "   Run PowerShell as Administrator and execute:",
                "   > Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser",
                "",
                "2. Folder Access:",
                "   - AMAA needs write access to: %USERPROFILE%\\.amaa",
                "   - And to any folders you want to organize",
                "",
                "3. Windows Defender:",
                "   - Consider adding exclusion for AMAA folder",
                "   - Settings > Update & Security > Windows Security > ",
                "     Virus & threat protection > Manage settings > Exclusions",
            ])
        
        elif self.os_type == OSType.MACOS:
            lines.extend([
                "🍎 macOS Setup:",
                "",
                "1. Full Disk Access (Required):",
                "   - System Preferences > Security & Privacy > Privacy",
                "   - Click '+' and add Terminal or your Python executable",
                "",
                "2. Automation (If using AppleScript features):",
                "   - Grant access when prompted",
                "",
                "3. Folder Permissions:",
                "   - AMAA needs write access to: ~/.amaa",
                "   - Run: chmod 755 ~/.amaa",
            ])
        
        elif self.os_type == OSType.LINUX:
            lines.extend([
                "🐧 Linux Setup:",
                "",
                "1. User Permissions:",
                "   - Ensure you have write access to: ~/.amaa",
                "   - Run: mkdir -p ~/.amaa && chmod 755 ~/.amaa",
                "",
                "2. SELinux (if enabled):",
                "   - May need to set appropriate contexts",
                "   - Or run: setenforce 0 (temporarily)",
                "",
                "3. AppArmor (if enabled):",
                "   - May need to create a profile for AMAA",
            ])
        
        lines.extend([
            "",
            "=" * 50,
            "Run 'amaa check-permissions' to verify your setup",
            "=" * 50,
        ])
        
        return '\n'.join(lines)


def run_permission_check():
    """권한 확인 실행"""
    print("🔐 AMAA Permission Checker")
    print("=" * 50)
    
    checker = PermissionChecker()
    
    print(f"\n📱 OS: {checker.os_type.value}")
    print(f"👤 Admin: {checker.is_admin}")
    
    # 시스템 권한 확인
    print("\n📋 System Permissions:")
    sys_perms = checker.check_system_permissions()
    
    for key, value in sys_perms.items():
        if key not in ['issues', 'recommendations']:
            print(f"  {key}: {value}")
    
    if sys_perms.get('issues'):
        print("\n⚠️ Issues:")
        for issue in sys_perms['issues']:
            print(f"  - {issue}")
    
    if sys_perms.get('recommendations'):
        print("\n💡 Recommendations:")
        for rec in sys_perms['recommendations']:
            print(f"  - {rec}")
    
    # AMAA 요구사항 확인
    print("\n📁 Path Permissions:")
    amaa_req = checker.check_amaa_requirements()
    
    for path, perms in amaa_req['paths'].items():
        status = "✅" if perms['can_write'] else "❌"
        print(f"  {status} {path}")
        if perms['issues']:
            for issue in perms['issues']:
                print(f"     └─ {issue}")
    
    # 종합 결과
    print("\n" + "=" * 50)
    if amaa_req['all_ok']:
        print("✅ All permissions OK! AMAA is ready to run.")
    else:
        print("❌ Some permissions need to be fixed:")
        for issue in amaa_req['critical_issues']:
            print(f"  - {issue}")
        
        print("\n📖 Recommended Setup Guide:")
        print(checker.get_recommended_setup())


if __name__ == "__main__":
    run_permission_check()
