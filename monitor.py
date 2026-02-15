"""
monitor.py - WSLからWindowsプロセスを監視するモジュール

WSL2環境から subprocess 経由で tasklist.exe / powershell.exe を呼び出し、
Windowsホスト側のプロセス情報を取得・管理する。
"""

import csv
import io
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- Constants ---
SUBPROCESS_TIMEOUT = 5  # seconds
DB_PATH = Path(__file__).parent / "usage_log.db"

# tasklist.exe / taskkill.exe のパス候補
# WSLからは /mnt/c/Windows/System32/ 経由でアクセスできる
_SYSTEM32_CANDIDATES = [
    "/mnt/c/Windows/System32",
    "/mnt/c/WINDOWS/system32",
    "/mnt/c/Windows/system32",
]


def _find_system32() -> str:
    """System32ディレクトリのWSLパスを検出する。"""
    for candidate in _SYSTEM32_CANDIDATES:
        if os.path.isdir(candidate):
            return candidate
    # フォールバック: 直接コマンド名で呼ぶ（PATHに通っている前提）
    return ""


def _build_cmd(exe_name: str) -> str:
    """実行ファイルのフルパスを構築する。"""
    sys32 = _find_system32()
    if sys32:
        full_path = os.path.join(sys32, exe_name)
        if os.path.isfile(full_path):
            return full_path
    # PATHから探す
    return exe_name


# --- Data Classes ---

@dataclass
class ProcessInfo:
    """Windowsプロセスの情報を表すデータクラス。"""
    name: str
    pid: int
    session_name: str = ""
    session_num: int = 0
    mem_usage_kb: int = 0


@dataclass
class ActiveWindowInfo:
    """アクティブウィンドウの情報を表すデータクラス。"""
    process_name: str
    window_title: str
    pid: int = 0


# ==============================================================================
# WindowsProcessMonitor - Windowsプロセスの監視・制御
# ==============================================================================

class WindowsProcessMonitor:
    """
    WSL2からWindowsプロセスを監視・制御するクラス。

    subprocess経由でtasklist.exe / powershell.exeを呼び出し、
    プロセス一覧の取得、アクティブウィンドウの検出、プロセスの強制終了を行う。
    """

    def __init__(self):
        self._tasklist_cmd = _build_cmd("tasklist.exe")
        self._taskkill_cmd = _build_cmd("taskkill.exe")
        self._powershell_cmd = _build_cmd("powershell.exe")
        logger.info(
            "WindowsProcessMonitor initialized: tasklist=%s, taskkill=%s, powershell=%s",
            self._tasklist_cmd, self._taskkill_cmd, self._powershell_cmd,
        )

    def get_running_processes(self) -> list[ProcessInfo]:
        """
        Windowsで実行中のプロセス一覧を取得する。

        tasklist.exe /FO CSV /NH を実行し、CSV形式の出力をパースする。

        Returns:
            ProcessInfoのリスト。取得失敗時は空リスト。
        """
        try:
            result = subprocess.run(
                [self._tasklist_cmd, "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                logger.warning(
                    "tasklist.exe returned non-zero exit code: %d, stderr: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return []

            return self._parse_tasklist_csv(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error("tasklist.exe timed out after %d seconds", SUBPROCESS_TIMEOUT)
            return []
        except FileNotFoundError:
            logger.error(
                "tasklist.exe not found at '%s'. "
                "Ensure WSL can access Windows System32 directory.",
                self._tasklist_cmd,
            )
            return []
        except Exception as e:
            logger.error("Unexpected error running tasklist.exe: %s", e)
            return []

    def _parse_tasklist_csv(self, csv_text: str) -> list[ProcessInfo]:
        """
        tasklist.exe /FO CSV /NH の出力をパースする。

        出力例:
        "chrome.exe","12345","Console","1","150,000 K"
        """
        processes = []
        reader = csv.reader(io.StringIO(csv_text))

        for line_num, row in enumerate(reader, 1):
            try:
                if len(row) < 5:
                    continue

                name = row[0].strip('"').strip()
                pid_str = row[1].strip('"').strip()
                session_name = row[2].strip('"').strip()
                session_num_str = row[3].strip('"').strip()
                mem_str = row[4].strip('"').strip()

                if not name or not pid_str:
                    continue

                pid = int(pid_str)
                session_num = int(session_num_str) if session_num_str.isdigit() else 0

                # メモリ使用量: "150,000 K" → 150000
                mem_kb = 0
                mem_clean = mem_str.replace(",", "").replace(".", "").split()
                if mem_clean and mem_clean[0].isdigit():
                    mem_kb = int(mem_clean[0])

                processes.append(ProcessInfo(
                    name=name,
                    pid=pid,
                    session_name=session_name,
                    session_num=session_num,
                    mem_usage_kb=mem_kb,
                ))

            except (ValueError, IndexError) as e:
                logger.debug("Skipping malformed tasklist row %d: %s (error: %s)", line_num, row, e)
                continue

        logger.debug("Parsed %d processes from tasklist output", len(processes))
        return processes

    def get_active_window(self) -> Optional[ActiveWindowInfo]:
        """
        現在アクティブな（フォアグラウンドの）ウィンドウ情報を取得する。

        PowerShellを使用してWin32 APIを呼び出し、フォアグラウンドウィンドウの
        タイトルとプロセス情報を取得する。

        Returns:
            ActiveWindowInfo、または取得失敗時はNone。
        """
        ps_script = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

$hwnd = [Win32]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[Win32]::GetWindowText($hwnd, $sb, 256) | Out-Null
$title = $sb.ToString()

$pid = 0
[Win32]::GetWindowThreadProcessId($hwnd, [ref]$pid) | Out-Null

if ($pid -gt 0) {
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
    Write-Output "$procName`t$title`t$pid"
} else {
    Write-Output "Unknown`tUnknown`t0"
}
"""

        try:
            result = subprocess.run(
                [self._powershell_cmd, "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT * 2,  # PowerShellは起動が遅い
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                logger.warning(
                    "PowerShell returned non-zero exit code: %d, stderr: %s",
                    result.returncode,
                    result.stderr.strip()[:200],
                )
                return None

            output = result.stdout.strip()
            if not output:
                return None

            parts = output.split("\t")
            if len(parts) >= 3:
                return ActiveWindowInfo(
                    process_name=parts[0].strip(),
                    window_title=parts[1].strip(),
                    pid=int(parts[2].strip()) if parts[2].strip().isdigit() else 0,
                )
            elif len(parts) >= 2:
                return ActiveWindowInfo(
                    process_name=parts[0].strip(),
                    window_title=parts[1].strip(),
                )

            logger.warning("Unexpected PowerShell output format: %s", output[:100])
            return None

        except subprocess.TimeoutExpired:
            logger.error("PowerShell timed out getting active window")
            return None
        except FileNotFoundError:
            logger.error("powershell.exe not found at '%s'", self._powershell_cmd)
            return None
        except Exception as e:
            logger.error("Unexpected error getting active window: %s", e)
            return None

    def kill_process(self, process_name: str) -> bool:
        """
        指定されたプロセス名のプロセスを強制終了する。

        taskkill.exe /F /IM <process_name> を実行する。

        Args:
            process_name: 終了対象のプロセス名（例: "chrome.exe"）

        Returns:
            成功時True、失敗時False。
        """
        if not process_name or not process_name.strip():
            logger.warning("Empty process name provided to kill_process")
            return False

        # 安全チェック: 重要なシステムプロセスは終了させない
        protected = {"csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
                      "svchost.exe", "explorer.exe", "dwm.exe", "winlogon.exe",
                      "smss.exe", "system"}
        if process_name.lower() in protected:
            logger.warning("Attempted to kill protected system process: %s", process_name)
            return False

        try:
            result = subprocess.run(
                [self._taskkill_cmd, "/F", "/IM", process_name],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                logger.info("Successfully killed process: %s", process_name)
                return True
            else:
                logger.warning(
                    "taskkill.exe failed for '%s': %s",
                    process_name,
                    result.stderr.strip() or result.stdout.strip(),
                )
                return False

        except subprocess.TimeoutExpired:
            logger.error("taskkill.exe timed out for process: %s", process_name)
            return False
        except FileNotFoundError:
            logger.error("taskkill.exe not found at '%s'", self._taskkill_cmd)
            return False
        except Exception as e:
            logger.error("Unexpected error killing process '%s': %s", process_name, e)
            return False

    def is_process_running(self, process_name: str) -> bool:
        """指定プロセス名が現在実行中かチェックする。"""
        processes = self.get_running_processes()
        return any(p.name.lower() == process_name.lower() for p in processes)


# ==============================================================================
# UsageTracker - アプリ使用時間の計測・記録
# ==============================================================================

class UsageTracker:
    """
    アプリケーションごとの使用時間をSQLiteで記録・管理するクラス。
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        """データベースとテーブルを初期化する。"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS usage_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        process_name TEXT NOT NULL,
                        window_title TEXT DEFAULT '',
                        duration_sec INTEGER NOT NULL,
                        recorded_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_date_process
                    ON usage_log(date, process_name)
                """)
                conn.commit()
            logger.info("Database initialized at %s", self.db_path)
        except sqlite3.Error as e:
            logger.error("Failed to initialize database: %s", e)
            raise

    def record_usage(self, process_name: str, window_title: str = "", duration_sec: int = 5):
        """
        アプリ使用ログを記録する。

        Args:
            process_name: プロセス名 (例: "chrome.exe")
            window_title: ウィンドウタイトル
            duration_sec: 使用時間（秒）。ポーリング間隔に相当。
        """
        try:
            today = date.today().isoformat()
            now = datetime.now().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO usage_log (date, process_name, window_title, duration_sec, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (today, process_name, window_title, duration_sec, now),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to record usage for '%s': %s", process_name, e)

    def get_usage_today(self, process_name: str) -> int:
        """
        当日の指定プロセスの累積使用時間（秒）を取得する。

        Args:
            process_name: プロセス名

        Returns:
            累積使用秒数。
        """
        try:
            today = date.today().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "SELECT COALESCE(SUM(duration_sec), 0) FROM usage_log "
                    "WHERE date = ? AND LOWER(process_name) = LOWER(?)",
                    (today, process_name),
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except sqlite3.Error as e:
            logger.error("Failed to get usage for '%s': %s", process_name, e)
            return 0

    def get_usage_summary(self) -> list[dict]:
        """
        当日の全アプリの使用時間サマリーを取得する。

        Returns:
            [{"process_name": str, "total_seconds": int, "hours": float}, ...] のリスト。
        """
        try:
            today = date.today().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "SELECT process_name, SUM(duration_sec) as total "
                    "FROM usage_log WHERE date = ? "
                    "GROUP BY LOWER(process_name) "
                    "ORDER BY total DESC",
                    (today,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "process_name": row[0],
                        "total_seconds": row[1],
                        "hours": round(row[1] / 3600, 2),
                    }
                    for row in rows
                ]
        except sqlite3.Error as e:
            logger.error("Failed to get usage summary: %s", e)
            return []

    def get_formatted_summary(self) -> str:
        """使用時間サマリーを人間が読める文字列として返す。"""
        summary = self.get_usage_summary()
        if not summary:
            return "本日の使用ログはまだありません。"

        lines = ["== 本日のPC使用状況 =="]
        for item in summary:
            total = item["total_seconds"]
            hours = total // 3600
            minutes = (total % 3600) // 60
            lines.append(f"  {item['process_name']}: {hours}時間{minutes}分")
        return "\n".join(lines)
