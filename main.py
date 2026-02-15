"""
main.py - PC使いすぎ防止アプリのメインモジュール

全コンポーネント（monitor, overlay, llm_client）を統合し、
ポーリングベースの監視ループを実行する。
"""

import logging
import signal
import sys
from datetime import datetime, time
from dataclasses import dataclass, field
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QAction

from monitor import WindowsProcessMonitor, UsageTracker
from overlay import FullScreenOverlay
from llm_client import OllamaClient

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pc_limiter.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ==============================================================================
# 設定 (Configuration)
# ==============================================================================

@dataclass
class AppConfig:
    """アプリケーション設定。"""

    # 禁止アプリのリスト (プロセス名, 小文字で比較)
    blacklist: list[str] = field(default_factory=lambda: [
        "chrome.exe",
        "discord.exe",
        "vlc.exe",
        "steam.exe",
        "steamwebhelper.exe",
    ])

    # 深夜帯制限 (カーフュー)
    curfew_start: time = field(default_factory=lambda: time(1, 0))   # 01:00
    curfew_end: time = field(default_factory=lambda: time(6, 0))     # 06:00

    # アプリごとの使用時間上限（秒）
    max_usage_seconds: int = 7200  # 2時間

    # ポーリング間隔（秒）
    poll_interval: int = 5

    # Ollama設定
    ollama_model: str = "phi3"
    ollama_base_url: str = "http://localhost:11434"

    # カーフュー中に全アプリを制限するか
    curfew_blocks_all: bool = True


# ==============================================================================
# PCLimiterApp - メインアプリケーション
# ==============================================================================

class PCLimiterApp:
    """
    PC使いすぎ防止アプリのメインクラス。

    QTimerでポーリングし、以下の制限判定を行う:
    1. カーフュー時間帯かどうか
    2. ブラックリストアプリが起動しているか
    3. アプリの使用時間が閾値を超えているか
    """

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig()
        self._overlay_active = False
        self._last_intervention_time: datetime | None = None
        # 連続介入を防ぐクールダウン（秒）
        self._intervention_cooldown = 60

        # コンポーネント初期化
        self.monitor = WindowsProcessMonitor()
        self.tracker = UsageTracker()
        self.llm = OllamaClient(
            model=self.config.ollama_model,
            base_url=self.config.ollama_base_url,
        )
        self.overlay: FullScreenOverlay | None = None

        logger.info("PCLimiterApp initialized")
        logger.info("Blacklist: %s", self.config.blacklist)
        logger.info("Curfew: %s - %s", self.config.curfew_start, self.config.curfew_end)
        logger.info("Max usage per app: %d seconds", self.config.max_usage_seconds)

    def start(self, app: QApplication):
        """アプリケーションを開始する。"""
        self.app = app

        # オーバーレイを作成
        self.overlay = FullScreenOverlay()
        self.overlay.overlay_closed.connect(self._on_overlay_closed)

        # ポーリングタイマーを開始
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(self.config.poll_interval * 1000)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        # 初回即時実行
        QTimer.singleShot(1000, self._poll)

        logger.info("Monitoring started (interval: %ds)", self.config.poll_interval)

    def _poll(self):
        """ポーリング処理: プロセスを監視し、制限を判定する。"""
        if self._overlay_active:
            return  # オーバーレイ表示中はスキップ

        try:
            # 1. アクティブウィンドウを取得して使用時間を記録
            active = self.monitor.get_active_window()
            if active and active.process_name and active.process_name != "Unknown":
                self.tracker.record_usage(
                    process_name=active.process_name,
                    window_title=active.window_title,
                    duration_sec=self.config.poll_interval,
                )

            # 2. 制限判定
            violation = self._check_violations()
            if violation:
                self._trigger_intervention(violation)

        except Exception as e:
            logger.error("Error during poll: %s", e)

    def _check_violations(self) -> str | None:
        """
        制限違反をチェックする。

        Returns:
            違反理由の文字列。違反なしの場合はNone。
        """
        now = datetime.now()

        # クールダウンチェック
        if self._last_intervention_time:
            elapsed = (now - self._last_intervention_time).total_seconds()
            if elapsed < self._intervention_cooldown:
                return None

        # --- チェック1: カーフュー時間帯 ---
        if self._is_curfew_time(now.time()):
            if self.config.curfew_blocks_all:
                return f"深夜帯（{self.config.curfew_start.strftime('%H:%M')} - {self.config.curfew_end.strftime('%H:%M')}）です。PCを使うのをやめましょう。"

        # --- チェック2: ブラックリストアプリ起動チェック ---
        processes = self.monitor.get_running_processes()
        running_names = {p.name.lower() for p in processes}

        for app_name in self.config.blacklist:
            if app_name.lower() in running_names:
                # 強制終了
                self.monitor.kill_process(app_name)
                return f"禁止アプリ「{app_name}」が起動されたため、強制終了しました。"

        # --- チェック3: 使用時間超過 ---
        active = self.monitor.get_active_window()
        if active and active.process_name:
            usage = self.tracker.get_usage_today(active.process_name)
            if usage > self.config.max_usage_seconds:
                hours = usage // 3600
                minutes = (usage % 3600) // 60
                return (
                    f"「{active.process_name}」の使用時間が{hours}時間{minutes}分に達しました。"
                    f"上限の{self.config.max_usage_seconds // 3600}時間を超えています。"
                )

        return None

    def _is_curfew_time(self, current: time) -> bool:
        """現在時刻がカーフュー時間帯かどうかを判定する。"""
        start = self.config.curfew_start
        end = self.config.curfew_end

        if start <= end:
            # 通常: 例 09:00 - 17:00
            return start <= current <= end
        else:
            # 日跨ぎ: 例 23:00 - 06:00
            return current >= start or current <= end

    def _trigger_intervention(self, violation_reason: str):
        """
        制限を発動し、オーバーレイを表示する。

        Args:
            violation_reason: 違反理由のテキスト
        """
        self._overlay_active = True
        self._last_intervention_time = datetime.now()

        logger.warning("INTERVENTION: %s", violation_reason)

        # 使用状況サマリーを取得
        summary = self.tracker.get_formatted_summary()
        usage_context = f"{violation_reason}\n\n{summary}"

        # LLMから説教メッセージを生成
        scolding = self.llm.generate_scolding(usage_context)

        # オーバーレイを表示
        display_text = f"⚡ {violation_reason}\n\n💬 {scolding}"
        if self.overlay:
            self.overlay.show_message(display_text)

    def _on_overlay_closed(self):
        """オーバーレイが閉じられた時のコールバック。"""
        self._overlay_active = False
        logger.info("Overlay closed, monitoring resumed")


# ==============================================================================
# System Tray Icon (Optional)
# ==============================================================================

def create_tray_icon(app: QApplication, limiter: PCLimiterApp) -> QSystemTrayIcon | None:
    """システムトレイアイコンを作成する（利用可能な場合）。"""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.info("System tray not available")
        return None

    tray = QSystemTrayIcon(app)

    menu = QMenu()
    status_action = QAction("📊 使用状況を表示", app)
    status_action.triggered.connect(lambda: _show_status(limiter))
    menu.addAction(status_action)

    menu.addSeparator()

    quit_action = QAction("❌ 終了", app)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.setToolTip("PC Limiter - 使いすぎ防止")
    tray.show()

    return tray


def _show_status(limiter: PCLimiterApp):
    """使用状況を表示する。"""
    summary = limiter.tracker.get_formatted_summary()
    logger.info("\n%s", summary)
    print(summary)


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    """メインエントリーポイント。"""
    print("=" * 50)
    print("  🛡️  PC Limiter - 使いすぎ防止アプリ")
    print("=" * 50)
    print()

    # QApplication を作成
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # トレイで動作し続ける

    # --- Ctrl+C で安全に終了するためのハンドラ ---
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    # Qtイベントループ中にPythonのシグナルが処理されるよう、
    # 定期的にPythonコードを実行するタイマーを設定
    sigint_timer = QTimer()
    sigint_timer.timeout.connect(lambda: None)  # Pythonに制御を返す
    sigint_timer.start(200)

    # 設定（必要に応じてカスタマイズ）
    config = AppConfig(
        blacklist=[
            "chrome.exe",
            "discord.exe",
            "vlc.exe",
            "steam.exe",
            "steamwebhelper.exe",
        ],
        curfew_start=time(1, 0),
        curfew_end=time(6, 0),
        max_usage_seconds=7200,  # 2時間
        poll_interval=5,
    )

    # アプリを初期化して開始
    limiter = PCLimiterApp(config)
    limiter.start(app)

    # トレイアイコン
    tray = create_tray_icon(app, limiter)

    print("✅ 監視を開始しました。")
    print(f"   ブラックリスト: {config.blacklist}")
    print(f"   カーフュー: {config.curfew_start.strftime('%H:%M')} - {config.curfew_end.strftime('%H:%M')}")
    print(f"   使用時間上限: {config.max_usage_seconds // 3600}時間/アプリ")
    print(f"   ポーリング間隔: {config.poll_interval}秒")
    print()
    print("終了するには Ctrl+C を押してください。")

    # イベントループ開始
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

