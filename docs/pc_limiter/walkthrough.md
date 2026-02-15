# PC使いすぎ防止アプリ — ウォークスルー

## 実装したファイル

| ファイル | 行数 | 役割 |
|---|---|---|
| [monitor.py](file:///\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\monitor.py) | ~310行 | WSLからWindows監視 + SQLite使用時間記録 |
| [llm_client.py](file:///\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\llm_client.py) | ~110行 | Ollama API連携 (説教メッセージ生成) |
| [overlay.py](file:///\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\overlay.py) | ~180行 | PySide6全画面オーバーレイ (5秒カウントダウン) |
| [main.py](file:///\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\main.py) | ~260行 | ブラックリスト/カーフュー/使用量制限の統括 |
| [requirements.txt](file:///\\wsl.localhost\Ubuntu-20.04\home\hiroki\Portfolio\pc_limiter\requirements.txt) | 2行 | PySide6, ollama |

## 検証結果

| テスト | 結果 |
|---|---|
| `monitor.py` — `tasklist.exe` 経由でプロセス取得 | ✅ 319プロセス取得成功 |
| `llm_client.py` — Ollamaサーバー不通時のフォールバック | ✅ 正常動作 |
| PySide6 インポート | ✅ 成功 |
| 全モジュールのインポート統合テスト | ✅ 成功 |

## 使い方

```bash
cd ~/Portfolio/pc_limiter
python3 main.py
```

### 設定のカスタマイズ

`main.py` 内の `AppConfig` を編集して、ブラックリストや制限時間を変更できます:

```python
config = AppConfig(
    blacklist=["chrome.exe", "discord.exe", "vlc.exe"],  # 禁止アプリ
    curfew_start=time(1, 0),   # 深夜制限開始 01:00
    curfew_end=time(6, 0),     # 深夜制限終了 06:00
    max_usage_seconds=7200,     # 2時間/アプリ
    poll_interval=5,            # 5秒ごとに監視
)
```

> [!NOTE]
> - Ollamaサーバーが停止中でもフォールバックメッセージで動作します
> - WSLg (`$DISPLAY=:0`) が有効な環境で全画面オーバーレイが表示されます
> - 使用ログは `usage_log.db` (SQLite) に自動保存されます
