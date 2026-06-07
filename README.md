# Codex App かんたん切り替え

![Codex App かんたん切り替え アイコン](assets/app_icon_source.png)

ターミナルを使ったことがない人でも、ボタン操作だけでCodex Appの接続先を切り替え、
将来使うOllamaモデルを管理できるmacOS向けGUIアプリです。

Python標準ライブラリのTkinterだけで動作します。

## 配布物と文書

- 配布用アプリ: `dist/Codex App かんたん切り替え.app`
- 配布用ZIP: `dist/Codex-App-Easy-Switcher-macOS.zip`
- [仕様書（Markdown）](docs/SPECIFICATION.md)
- [操作マニュアル（Markdown）](docs/USER_MANUAL.md)
- `docs/Codex_App_かんたん切り替え_仕様書.docx`
- `docs/Codex_App_かんたん切り替え_操作マニュアル.docx`
- [セキュリティ方針](SECURITY.md)

## 主な機能

### Codex App かんたん切り替え

- 通常のCodex GPTでCodex Appを起動
- Ollama Cloudの `gpt-oss:120b-cloud` でCodex Appを起動
- 現在の接続状態を大きく表示
- Codex App起動中は、入力途中の内容が失われる可能性を切り替え前に警告
- Ollama接続状態でランチャーを終了するとき、通常のCodexへ戻すか確認

内部ではOllama公式の次の機能だけを使用します。ターミナルは表示しません。

```text
ollama launch codex-app --model gpt-oss:120b-cloud --yes
ollama launch codex-app --restore --yes
```

このアプリ自身はCodex設定を書き換えません。現在状態を表示するために
`~/.codex/config.toml` を読み取ります。実際の設定変更・バックアップ・復元は
Ollama Launchに任せます。Ollamaのバックアップは通常
`~/.ollama/backup/codex-app/` に保存されます。

### Ollamaモデル管理

将来作成するRAGアプリ、AIエージェント、自作アプリなどで使うモデルを管理します。

- インストール済みモデルの一覧表示
- Cloudモデルとローカルモデルの区別表示
- 手入力したモデル名をボタンでインストール
- インストール中の進捗表示と中止
- 大容量通信・ディスク使用の可能性を開始前に警告

モデルの削除機能はありません。また、モデル管理画面でインストールしたモデルは
Codex Appの切り替え候補には自動追加されません。

## 必要なもの

- macOS
- Python 3（Tkinterを含む）
- Codex App
- Ollama v0.24.0以降

Ollamaが見つからない場合、アプリ内のボタンから公式ダウンロードページを開けます。
Ollama自体の自動インストールは行いません。

## 起動方法

参加者はFinderで次のアプリをダブルクリックします。ターミナルは表示されません。

```text
Codex App かんたん切り替え.app
```

初回起動時にmacOSの警告が表示された場合は、アプリを右クリックして「開く」を選択します。
初めてCodex Appの接続先を切り替えるとき、macOSからCodex Appを制御する許可を求められる
場合があります。その場合は許可してください。

開発者は次のコマンドでも起動できます。

```bash
python3 app.py
```

## 基本操作

### 通常のCodex GPTを使う

「通常のCodex GPTで起動」を押します。Ollama Launchが保存したバックアップから
通常のCodex設定へ復元し、Codex Appを起動します。

### gpt-oss:120b-cloudを使う

「gpt-oss:120b-cloudで起動」を押します。Ollama Cloud経由に切り替えてCodex Appを
起動します。Cloudモデルなので、ローカルPC上で120Bモデルを動かすわけではありません。

### 新しいモデルをインストールする

「Ollama モデル管理」タブで、Ollama公式ライブラリに掲載されているモデル名を入力し、
「モデルをインストール」を押します。

例:

```text
qwen2.5-coder:7b
gemma3:4b
gpt-oss:20b
```

ローカルモデルは数GB以上の通信とディスク容量を使用する場合があります。

## 安全設計

- ターミナル・コマンドプロンプトを表示しない
- subprocessは引数リスト形式で実行し、`shell=True` を使用しない
- 危険な文字を含むモデル名は拒否
- 切り替え前にCodex Appを安全に終了
- Ollama公式の切り替え・復元機能だけを使用
- ランチャー終了時にOllama接続を戻し忘れないよう警告
- モデルの自動削除やOllamaの自動インストールは行わない

## 公開・配布時の注意

ソースコードの公開にあたり、APIキーや認証情報、個人用パスは含めていません。
アプリはプロンプトやプロジェクト内容を収集・送信しません。

ただし、接続切り替え時にはCodex Appが終了・再起動され、Ollama公式機能が
`~/.codex/config.toml`を変更・復元します。未送信内容が失われる可能性があるため、
切り替え前の確認画面を必ず読んでください。

現在の配布アプリはarm64 macOS向けのアドホック署名版で、Apple公証は未実施です。
初回起動時はmacOSの警告が表示される場合があります。

## トラブルシューティング

- Ollamaが見つからない: 公式ページからインストールし、Ollamaを起動して再確認します。
- モデル一覧を取得できない: Ollamaアプリが起動しているか確認します。
- `unknown integration: codex-app`: Ollamaをv0.24.0以降へ更新します。
- Cloudモデルを使えない: Ollamaへのサインイン状態を確認します。
- 切り替えに失敗する: Codex Appを手動で終了してから再試行します。
- 通常のCodexへ戻せない: `~/.ollama/backup/codex-app/` にバックアップがあるか確認します。

## 開発者向けテスト

重要: Codex App内のCodexから開発・検証している間は、実際の切り替えボタンや
`ollama launch codex-app --restore` を実行しないでください。Codex Appが終了・再起動され、
作業中のセッションも終了します。切り替え処理はモックを使った自動テストで確認してください。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 app.py --smoke-test
```

## macOS配布アプリのビルド

PyInstallerをインストール後、次を実行します。

```bash
scripts/build_icon.sh
scripts/build_macos_app.sh
```

ビルド結果は`dist/`に作成されます。GitHubへはソースコードと文書を公開し、
配布ZIPはRelease添付ファイルとして公開する想定です。

Windows版は、macOS版の完成後に別途作成する予定です。
