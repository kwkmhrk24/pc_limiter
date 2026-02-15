> [!NOTE]
> 本プロジェクトのコード・ドキュメントは、AI アシスタント **Claude Opus 4.6 (Thinking)** を活用して作成されました。

# 🛡️ PC Limiter — 使いすぎ防止アプリ

WSL2 (Ubuntu) 上で動作し、Windows ホスト側のアプリ使用を監視・制限するアプリケーション。

## 特徴

- **プロセス監視** — `tasklist.exe` / `powershell.exe` 経由で Windows のプロセスを監視
- **ブラックリスト** — 禁止アプリ検出時に `taskkill.exe` で強制終了
- **使用時間制限** — アプリごとの累積使用時間を SQLite に記録し、閾値超過で制限発動
- **深夜帯制限 (カーフュー)** — 設定した時間帯は PC 利用を制限
- **全画面オーバーレイ** — 制限発動時に 5 秒カウントダウン付きのロック画面を表示
- **AI 説教機能** — Ollama (ローカル LLM) が使用状況に基づいた叱責メッセージを生成
- **自動起動** — Windows タスクスケジューラで PC 起動時にバックグラウンド実行

## 技術スタック

| 項目 | 技術 |
|---|---|
| 実行環境 | WSL2 (Ubuntu) / Python 3.10+ |
| GUI | PySide6 (WSLg 経由で表示) |
| LLM | Ollama (ローカル API) |
| DB | SQLite |
| Windows 連携 | subprocess → tasklist.exe / taskkill.exe / powershell.exe |

## ファイル構成

```
pc_limiter/
├── main.py              # メインループ・設定・制限判定
├── monitor.py           # Windowsプロセス監視 + SQLite使用時間記録
├── overlay.py           # PySide6 全画面オーバーレイ
├── llm_client.py        # Ollama API クライアント
├── requirements.txt     # 依存パッケージ
├── scripts/
│   ├── start_limiter.bat            # 手動起動用バッチ
│   ├── start_limiter_hidden.vbs     # 非表示起動用VBS
│   ├── register_task.ps1            # タスクスケジューラ登録
│   └── unregister_task.ps1          # タスクスケジューラ解除
└── docs/
    └── pc_limiter/
        ├── task.md
        ├── implementation_plan.md
        └── walkthrough.md
```

## セットアップ

### 前提条件

- Windows 10/11 + WSL2 (Ubuntu)
- WSLg が有効 (`echo $DISPLAY` で `:0` が返ること)
- Python 3.10+

### インストール

```bash
cd ~/Portfolio/pc_limiter
pip install -r requirements.txt
```

#### システムライブラリ (初回のみ)

```bash
sudo apt-get install -y libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 \
  libxcb-xkb1
```

### 実行

```bash
python3 main.py
```

### 自動起動の設定 (オプション)

Windows 側の PowerShell で以下を実行:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\<ユーザー名>\pc_limiter_scripts\register_task.ps1"
```

## 設定

`main.py` 内の `AppConfig` を編集:

```python
config = AppConfig(
    blacklist=["chrome.exe", "discord.exe", "steam.exe"],   # 禁止アプリ
    curfew_start=time(1, 0),    # 深夜制限 01:00〜
    curfew_end=time(6, 0),      #         〜06:00
    max_usage_seconds=7200,     # アプリごと2時間上限
    poll_interval=5,            # 監視間隔 (秒)
    ollama_model="phi3",        # LLMモデル
)
```

## 注意事項

- Ollama サーバーが未起動でもフォールバックメッセージで動作します
- 使用ログは `usage_log.db` (SQLite) に自動保存されます
- 終了は `Ctrl+C` で行えます
