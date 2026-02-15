"""
llm_client.py - Ollama APIと通信して「説教メッセージ」を生成するモジュール

ローカルで動作するOllamaサーバーへリクエストを送り、
ユーザーのPC使用状況に基づいた叱責・アドバイスメッセージを生成する。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_MODEL = "phi3"
DEFAULT_BASE_URL = "http://localhost:11434"

SYSTEM_PROMPT = (
    "あなたは厳しいが愛のある指導者です。"
    "ユーザーのPC使用時間の浪費について、短く辛辣に、しかし論理的に叱ってください。"
    "100文字以内で簡潔に。日本語で回答してください。"
    "最後に、具体的な改善案を一つだけ提案してください。"
)

FALLBACK_MESSAGES = [
    "⏰ PCの前で無駄な時間を過ごしていませんか？立ち上がって深呼吸しましょう。",
    "🚫 また同じアプリを開いていますね。本当にそれは今必要ですか？",
    "📚 その時間があれば、本を1章読めたはずです。優先順位を見直しましょう。",
    "🧘 集中力は有限です。一度リセットして、本当にやるべきことに取り組みましょう。",
    "⚡ 時間は取り戻せません。今この瞬間を、未来の自分のために使いましょう。",
]


class OllamaClient:
    """
    Ollama APIクライアント。

    ollamaパッケージを使用してローカルLLMと通信し、
    ユーザーの使用状況に基づいた説教メッセージを生成する。
    """

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        """
        Args:
            model: 使用するOllamaモデル名 (例: "phi3", "gemma2")
            base_url: OllamaサーバーのベースURL
        """
        self.model = model
        self.base_url = base_url
        self._fallback_index = 0

        try:
            import ollama
            self._client = ollama.Client(host=base_url)
            logger.info("OllamaClient initialized: model=%s, url=%s", model, base_url)
        except ImportError:
            logger.warning("ollama package not installed. Using fallback messages only.")
            self._client = None

    def is_available(self) -> bool:
        """
        Ollamaサーバーが利用可能かチェックする。

        Returns:
            サーバーが応答すればTrue。
        """
        if self._client is None:
            return False

        try:
            self._client.list()
            return True
        except Exception as e:
            logger.warning("Ollama server not available: %s", e)
            return False

    def generate_scolding(self, usage_log: str) -> str:
        """
        使用ログに基づいて説教メッセージを生成する。

        Args:
            usage_log: ユーザーの使用状況を表すテキスト
                       (例: "YouTubeを3時間視聴しました")

        Returns:
            生成された説教メッセージ。サーバー不通時はフォールバックメッセージ。
        """
        if self._client is None:
            return self._get_fallback()

        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"以下はユーザーのPC使用状況です:\n{usage_log}\n\nこのユーザーを叱ってください。"},
                ],
                options={
                    "temperature": 0.8,
                    "num_predict": 200,
                },
            )

            message = response.message.content.strip()
            if message:
                logger.info("Generated scolding message (%d chars)", len(message))
                return message
            else:
                logger.warning("Empty response from Ollama")
                return self._get_fallback()

        except Exception as e:
            logger.error("Failed to generate scolding message: %s", e)
            return self._get_fallback()

    def _get_fallback(self) -> str:
        """フォールバックメッセージをローテーションで返す。"""
        msg = FALLBACK_MESSAGES[self._fallback_index % len(FALLBACK_MESSAGES)]
        self._fallback_index += 1
        return msg
