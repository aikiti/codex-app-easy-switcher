# Codex App かんたん切り替え 仕様書

## 1. 文書情報

| 項目 | 内容 |
|---|---|
| アプリ名 | Codex App かんたん切り替え |
| バージョン | 0.1.0 |
| 対象OS | macOS 12以降（初版） |
| 主な利用者 | ターミナルやコマンド操作に不慣れな勉強会参加者 |
| 実装 | Python / Tkinter |
| 既定のOllama接続モデル | `gpt-oss:120b-cloud` |

## 2. 目的

ターミナルを表示せず、ボタン操作だけでCodex Appの接続先を切り替える。
また、将来作成するRAGアプリ、AIエージェント、自作AIアプリ向けに、
Ollamaモデルをインストール・確認できるようにする。

## 3. 対象範囲

### 3.1 対象機能

- 通常のCodex GPTでCodex Appを起動
- Ollama Cloudの`gpt-oss:120b-cloud`でCodex Appを起動
- 現在のCodex接続状態を表示
- Codex App起動中の安全な終了・再起動
- Ollama未導入・未起動・旧バージョンの案内
- インストール済みOllamaモデルの一覧表示
- Cloudモデルとローカルモデルの区別
- 手入力したモデルのインストール、進捗表示、中止
- Ollama接続状態でランチャーを終了するときの復元確認

### 3.2 対象外

- Windows対応
- Ollama自体の自動インストール
- Ollamaモデルの削除
- Codex Appで使用するモデルの自由選択
- Apple Developer ID署名・Apple公証
- OllamaまたはCodex Appのアカウント作成・サインイン

## 4. 画面構成

### 4.1 Codex App かんたん切り替えタブ

- 現在の接続状態
- 現在のモデル名
- 「通常のCodex GPTで起動」ボタン
- 「gpt-oss:120b-cloudで起動」ボタン
- 「状態を再確認」ボタン
- 状態・結果表示欄
- Ollama未導入時の公式ダウンロードページボタン

### 4.2 Ollama モデル管理タブ

- モデル名入力欄
- 「モデルをインストール」ボタン
- インストール済みモデル一覧
- Cloud / ローカル種別、モデル名、サイズ、更新情報
- インストール進捗、結果、中止ボタン

## 5. 接続切り替え仕様

### 5.1 通常のCodex GPT

Ollama公式機能を次の引数リストで実行する。

```text
ollama launch codex-app --restore --yes
```

### 5.2 Ollama Cloud

Ollama公式機能を次の引数リストで実行する。

```text
ollama launch codex-app --model gpt-oss:120b-cloud --yes
```

### 5.3 切り替え前処理

1. 選択済み接続先と現在状態が同じ場合、設定変更は行わずCodex Appを起動する。
2. 接続先が異なりCodex Appが起動中の場合、入力途中の内容が失われる可能性を警告する。
3. 利用者が承認した場合のみ、AppleScriptでCodex Appを通常終了する。
4. Ollama公式コマンドで切り替える。
5. 設定状態を読み取り確認し、Codex Appを起動する。

## 6. モデル管理仕様

- モデル名は英数字と`. _ : / -`のみ許可し、最大200文字とする。
- インストールは`ollama pull <モデル名>`を引数リスト形式で実行する。
- 実行前に大容量通信・ディスク使用の可能性を表示し、確認を求める。
- インストール中は進捗を表示し、中止操作を提供する。
- `:cloud`または`-cloud`で終わるモデルをCloudモデルとして表示する。
- `gpt-oss:120b-cloud`が未導入の場合、切り替えを実行せずモデル管理タブへ案内する。

## 7. 設定・データ

### 7.1 アプリ専用設定

保存先:

```text
~/Library/Application Support/CodexModelLauncher/settings.json
```

保存項目:

- 最後に入力したインストール対象モデル名
- ウィンドウ位置・サイズ

### 7.2 Codex設定

- 状態表示のため`~/.codex/config.toml`を読み取る。
- アプリ自身はCodex設定を直接編集しない。
- 設定変更、バックアップ、復元はOllama公式の`ollama launch codex-app`へ委譲する。

## 8. 安全・セキュリティ仕様

- `shell=True`、`os.system`、`eval`、`exec`を使用しない。
- 外部コマンドは固定の実行ファイルと検証済み引数のリストで起動する。
- モデル名の危険文字を拒否する。
- ターミナルを表示しない。
- Codex Appを終了する前に利用者へ警告する。
- Ollama接続状態で終了するとき、復元・維持・キャンセルを選択できる。
- モデルの削除、Ollamaの自動インストール、無確認の大容量ダウンロードを行わない。
- APIキー、認証情報、プロンプト、Codexプロジェクト内容を収集・送信しない。

## 9. 配布仕様

- PyInstallerのwindowedアプリとしてarm64 macOS向けにビルドする。
- アプリ名: `Codex App かんたん切り替え.app`
- 配布ZIP: `Codex-App-Easy-Switcher-macOS.zip`
- 専用アイコンを組み込む。
- 現在はアドホック署名であり、Apple公証は未実施。

## 10. 既知の制約

- Codex Appの切り替えはCodex Appを終了・再起動するため、未送信内容が失われる可能性がある。
- Ollama公式機能がCodex設定を書き換える。復元用バックアップは通常
  `~/.ollama/backup/codex-app/`に作成される。
- Apple公証がないため、初回起動時にmacOSの警告が表示される場合がある。
- OllamaおよびCodex Appの将来の仕様変更により、連携方法が変わる可能性がある。

## 11. 受入基準

- ターミナルを表示せずアプリを起動できる。
- 通常Codexと`gpt-oss:120b-cloud`の切り替え引数が正しい。
- 同じ接続先では不要な切り替えを実行しない。
- Ollamaモデル一覧をCloud / ローカルに分類できる。
- 危険なモデル名を拒否できる。
- モデルインストールを確認後に開始し、中止できる。
- Ollama状態で終了すると復元確認が表示される。
- 自動テストがすべて成功する。
