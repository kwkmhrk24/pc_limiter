"""
overlay.py - PySide6を使った全画面オーバーレイモジュール

制限発動時に画面全体を覆う半透明ウィンドウを表示し、
5秒のカウントダウン（深呼吸タイム）を経てから解除可能にする。
AI説教メッセージも画面上に大きく表示する。
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QPushButton,
    QGraphicsDropShadowEffect, QApplication,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


class FullScreenOverlay(QWidget):
    """
    全画面オーバーレイウィジェット。

    - 半透明の黒い背景で画面全体を覆う
    - 最前面に固定し、カウントダウン中はキー/マウス操作をブロック
    - 5秒カウントダウン後に「閉じる」ボタンを表示
    - AI説教メッセージを画面中央に表示
    """

    # オーバーレイが閉じられた時に発火するシグナル
    overlay_closed = Signal()

    COUNTDOWN_SECONDS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._countdown = self.COUNTDOWN_SECONDS
        self._is_locked = True
        self._setup_window()
        self._setup_ui()
        self._setup_timer()

    def _setup_window(self):
        """ウィンドウフラグとスタイルを設定する。"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # タスクバーに表示しない
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("background-color: rgba(10, 10, 15, 230);")
        self.setCursor(Qt.CursorShape.WaitCursor)

    def _setup_ui(self):
        """UIコンポーネントを構築する。"""
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(30)

        # === 警告アイコン・ヘッダー ===
        self.header_label = QLabel("⚠️ 使用制限が発動しました")
        self.header_label.setFont(QFont("Segoe UI Emoji", 28, QFont.Weight.Bold))
        self.header_label.setStyleSheet("color: #FF6B6B; background: transparent;")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header_label)

        # === AI説教メッセージ ===
        self.message_label = QLabel("")
        self.message_label.setFont(QFont("Noto Sans JP", 18))
        self.message_label.setStyleSheet(
            "color: #E0E0E0; background: transparent; "
            "padding: 20px; line-height: 1.6;"
        )
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setMaximumWidth(800)

        # テキストに影を追加
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(2, 2)
        self.message_label.setGraphicsEffect(shadow)
        layout.addWidget(self.message_label)

        # === カウントダウン表示 ===
        self.countdown_label = QLabel("")
        self.countdown_label.setFont(QFont("Segoe UI", 72, QFont.Weight.Bold))
        self.countdown_label.setStyleSheet("color: #FFD93D; background: transparent;")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_label)

        # === 深呼吸メッセージ ===
        self.breathe_label = QLabel("🧘 深呼吸してください...")
        self.breathe_label.setFont(QFont("Noto Sans JP", 16))
        self.breathe_label.setStyleSheet("color: #87CEEB; background: transparent;")
        self.breathe_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.breathe_label)

        # === 閉じるボタン (カウントダウン後に表示) ===
        self.close_button = QPushButton("✅ 理解しました — 作業に戻る")
        self.close_button.setFont(QFont("Noto Sans JP", 14, QFont.Weight.Bold))
        self.close_button.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #2ECC71;
                border: none;
                border-radius: 12px;
                padding: 15px 40px;
                min-width: 300px;
            }
            QPushButton:hover {
                background-color: #27AE60;
            }
            QPushButton:pressed {
                background-color: #1E8449;
            }
        """)
        self.close_button.clicked.connect(self._on_close)
        self.close_button.setVisible(False)
        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def _setup_timer(self):
        """カウントダウンタイマーを設定する。"""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)  # 1秒
        self._timer.timeout.connect(self._tick)

    def show_message(self, scolding_text: str = ""):
        """
        オーバーレイを表示し、説教メッセージをセットする。

        Args:
            scolding_text: AI生成の説教テキスト
        """
        self._countdown = self.COUNTDOWN_SECONDS
        self._is_locked = True
        self.close_button.setVisible(False)
        self.breathe_label.setVisible(True)
        self.setCursor(Qt.CursorShape.WaitCursor)

        if scolding_text:
            self.message_label.setText(scolding_text)
        else:
            self.message_label.setText("PCの使いすぎです。少し休憩しましょう。")

        self._update_countdown_display()

        # フルスクリーン表示
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            self.setGeometry(geometry)

        self.showFullScreen()
        self._timer.start()
        logger.info("Overlay shown with countdown %d seconds", self.COUNTDOWN_SECONDS)

    def _tick(self):
        """カウントダウンの1秒ごとの更新。"""
        self._countdown -= 1
        self._update_countdown_display()

        if self._countdown <= 0:
            self._timer.stop()
            self._unlock()

    def _update_countdown_display(self):
        """カウントダウン表示を更新する。"""
        if self._countdown > 0:
            self.countdown_label.setText(str(self._countdown))
        else:
            self.countdown_label.setText("✓")

    def _unlock(self):
        """カウントダウン完了後にオーバーレイのロックを解除する。"""
        self._is_locked = False
        self.close_button.setVisible(True)
        self.close_button.setEnabled(True)
        self.close_button.raise_()  # ボタンを最前面に
        self.breathe_label.setText("🎯 さあ、集中して取り組みましょう！")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        logger.info("Overlay unlocked")

    def _on_close(self):
        """閉じるボタンが押された時の処理。"""
        logger.info("Close button clicked")
        self.hide()
        self.overlay_closed.emit()
        logger.info("Overlay closed by user")

    # --- イベントオーバーライド ---

    def keyPressEvent(self, event):
        """カウントダウン中はキー操作をブロックする。"""
        if self._is_locked:
            event.ignore()
            return
        # Escapeキーでも閉じられるようにする
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """カウントダウン中はウィンドウを閉じれないようにする。"""
        if self._is_locked:
            event.ignore()
        else:
            super().closeEvent(event)
