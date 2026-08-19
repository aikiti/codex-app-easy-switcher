# Codex App かんたん切り替え 仕様書

## 1. 文書情報

| 項目 | 内容 |
|---|---|
| アプリ名 | Codex App かんたん切り替え |
| バージョン | 0.3.0 |
| 対象OS | arm64 macOS 12以降 / Windows版Codex Appが動作するWindows |
| 主な利用者 | ターミナルやコマンド操作に不慣れな勉強会参加者 |
| 実装 | Python / Tkinter |
| 初期Ollamaモデル | 未選択（インストール済みモデルから利用者が選択） |

## 2. 目的

ターミナルを表示せず、ボタン操作だけでCodex Appの通常GPTとOllamaモデルを切り替える。
初心者向けの分かりやすさを維持しながら、Codex Appで使用するCloudモデル・ローカルモデルを
変更できるようにする。また、将来作成するRAG・AIエージェント・自作AIアプリ向けに、
Ollamaモデルをインストール・確認できるようにする。

## 3. 対象範囲

### 3.1 対象機能

- 通常のCodex GPTでCodex Appを起動
- 選択したOllama CloudモデルまたはローカルモデルでCodex Appを起動
- インストール済みCloud／ローカルモデルをタブで分離表示
- 選択画面を開くたびにOllamaモデル一覧と機能情報を再取得
- モデル名の手入力
- 選択モデル名、種類、準備状態の表示・保存
- 未準備モデルの起動拒否とモデル管理画面への案内
- ローカルモデル選択時・起動時の警告
- 現在のCodex接続状態表示
- Ollamaの未インストール／停止中／起動中表示
- 停止中のOllamaを利用者確認後に起動し、最大15秒で接続判定
- Ollamaモデル一覧、インストール、進捗表示、中止
- Ollama接続状態でランチャーを終了するときの復元確認

### 3.2 対象外

- Ollama自体の自動インストール
- Ollamaモデルの削除
- モデルごとのCodex互換性保証
- Apple Developer ID署名・Apple公証
- Windowsコード署名証明書による署名
- アカウント作成・サインイン

## 4. UI方針

### 4.1 メイン画面

- 現在のCodex App接続状態とモデル名
- 「通常のCodex GPTで起動」
- 「選択中のOllamaモデルで起動」
- 選択中のモデル名、Cloud / ローカル種別、推奨状態、準備状態
- 「モデルを変更」
- 状態・結果表示

モデルを変更しただけではCodex Appを終了・再起動しない。

### 4.2 モデル選択画面

1. 画面を開くたびにインストール済みモデルを再取得する。
2. Cloudモデルとローカルモデルをタブで分離表示する。
3. `ollama show`のcapabilitiesとcontext lengthからCodex互換性を表示する。
4. 非対応・未確認モデルは一覧に「選択不可」と表示し、選択を拒否する。
5. インストールされていない手入力モデルは選択を拒否する。

### 4.3 Ollamaモデル管理画面

- 8GB PC用`gemma3:1b`のかんたん準備
- 16GB PC用`gemma4:e2b-it-qat`のかんたん準備
- `gemma4:e4b-it-qat`、`gemma4:12b-it-qat`、`qwen3.5:9b`、`qwen3.5:27b`の
  かんたん準備
- 各候補のメモリ目安、容量、画像対応、Codex互換性の説明
- 各候補のOllama公式ページを開くリンク
- Codex互換モデルだけを準備後に自動選択
- Ollama公式ダウンロードページへの導線
- 手入力したモデルのインストール
- モデル名または完全一致する`ollama run <モデル名>` / `ollama pull <モデル名>`からの
  安全なモデル名抽出（余分な引数は拒否）
- Cloud／ローカルを分離したモデル一覧
- Cloud / ローカル種別、モデル名、サイズ、更新情報
- インストール進捗、結果、中止

## 5. 接続切り替え仕様

### 5.1 通常のCodex GPT

```text
ollama launch codex-app --restore --yes
```

### 5.2 選択したOllamaモデル

```text
ollama launch codex-app --model <選択したモデル> --yes
```

モデル名はアプリ専用JSONから取得し、実行前に再検証する。

### 5.3 起動前処理

1. Ollamaと選択モデルの準備状態を確認する。
2. 未準備の場合は起動せず、モデル管理画面へ案内する。
3. ローカルモデルの場合は毎回警告する。
4. 現在状態と選択先が同じ場合、設定変更せずCodex Appを起動する。
5. 接続先が異なりCodex Appが起動中の場合、未送信内容が失われる可能性を警告する。
6. 承認後、macOSではAppleScript、Windowsでは固定PowerShell処理でCodex Appへ通常終了を
   依頼する。強制終了は行わない。
7. 有効なCodex設定ファイルをアプリ独自のバックアップ先へ複製する。失敗時は中止する。
8. Ollama公式コマンドで切り替え、設定状態を確認してCodex Appを起動する。

### 5.4 Windows固有処理

- Codex Appの存在確認と起動は、Windowsスタートメニューの登録情報を使用する。
- 起動状態確認は固定された`Get-Process`処理を使用する。
- 通常終了は`CloseMainWindow()`で依頼し、終了できない場合は手動終了を案内する。
- ユーザー入力をPowerShellスクリプトへ埋め込まない。
- Ollama・PowerShellなどの子プロセスはコマンド画面を表示せず起動する。

## 6. モデル管理仕様

- モデル名は英数字と`. _ : / -`のみ許可し、最大200文字とする。
- `:cloud`または`-cloud`で終わるモデルをCloudモデルとして分類する。
- モデル一覧はCloudモデルを先に表示する。
- モデルごとに`ollama show`を実行し、tools、thinking、context lengthを取得する。
- toolsとthinkingを持ち、context lengthが65536以上ならCodex対応と判定する。
- Ollama API `/api/version`を2秒で確認し、停止中の場合のみ利用者へ起動確認する。
- 起動後は最大15秒待ち、モデル一覧と各モデルの確認は1コマンド8秒で打ち切る。
- 一覧取得に成功し、保存済み選択モデルが存在しない、またはCodex非対応の場合だけ選択を解除する。
- インストールは`ollama pull <モデル名>`を引数リスト形式で実行する。
- 実行前に通信量・ディスク使用の可能性を表示し、確認を求める。
- インストール中は進捗と中止操作を提供する。

## 7. 設定・データ

アプリ専用設定:

```text
macOS: ~/Library/Application Support/CodexModelLauncher/settings.json
Windows: %LOCALAPPDATA%\CodexModelLauncher\settings.json
```

保存項目:

- Codex Appで使用する選択中のOllamaモデル名
- 最後に入力したインストール対象モデル名
- ウィンドウ位置・サイズ

Codex設定:

- 状態表示のため、`CODEX_HOME`設定時は`$CODEX_HOME/config.toml`、未設定時は
  `~/.codex/config.toml`を読み取る。
- 切り替え直前に、アプリ独自バックアップを
  `%LOCALAPPDATA%\CodexModelLauncher\backups`（Windows）へ非上書きで作成する。
- 切り替えそのものと復元はOllama公式機能へ委譲する。
- 新しいCodexと互換性のない、Ollama Launchが追加したトップレベル`profile`行だけを
  切り替え後に原子的に除去する。その他の設定は直接編集しない。

## 8. 安全・セキュリティ仕様

- `shell=True`、`os.system`、`eval`、`exec`を使用しない。
- 外部コマンドは固定実行ファイルと検証済み引数リストで起動する。
- 選択モデルと手入力モデルの危険文字を拒否する。
- モデル選択だけではCodex AppやCodex設定を変更しない。
- 非対応・未確認モデルは選択時・起動時に警告する。
- Codex Appを終了する前に利用者へ警告する。
- Windowsでは固定PowerShell処理のみ使用し、強制終了しない。
- Windowsでは子プロセスのコマンド画面を表示しない。
- モデル削除、Ollama自動インストール、無確認の大容量ダウンロードを行わない。
- APIキー、認証情報、プロンプト、Codexプロジェクト内容を収集・送信しない。

## 9. 配布仕様

- macOSはPyInstaller windowedアプリとしてarm64向けにビルドする。
- macOSアプリ名: `Codex App かんたん切り替え.app`
- macOS配布ZIP: `Codex-App-Easy-Switcher-macOS.zip`
- WindowsはGitHub Actionsの`windows-latest`環境でPyInstaller one-file / windowed EXEを
  ビルドする。
- Windows配布EXE: `Codex-App-Easy-Switcher-Windows.exe`
- バージョンタグのpush時にWindows EXEとSHA256ファイルをGitHub Releaseへ自動添付する。
- 専用アイコンを組み込む。
- アドホック署名を行い、Apple公証は実施しない。
- Windows EXEはコード署名証明書による署名を実施しない。

## 10. 既知の制約

- Ollama一覧に表示されても、そのモデルがCodexのツール実行・ファイル編集に対応する保証はない。
- ローカルモデルは性能・メモリ・コンテキスト長により正常に動作しない場合がある。
- Cloudモデル利用にはOllamaへのサインインとインターネット接続が必要。
- 接続切り替えではCodex Appが終了・再起動され、未送信内容が失われる可能性がある。
- Ollama公式機能がCodex設定を書き換え、通常`~/.ollama/backup/codex-app/`へ保存する。
- 本アプリも切り替え前のCodex設定をアプリ専用バックアップ先へ保存する。
- Apple公証がないため、初回起動時にmacOSの警告が表示される場合がある。
- Windowsコード署名がないため、SmartScreen警告が表示される場合がある。
- Windows版はGitHub Actions上のビルド・自動テスト済みだが、Windows実機の操作確認は
  利用者による検証を待つ。

## 11. 受入基準

- 初期選択モデルは空であり、存在しないモデルを暗黙に選ばない。
- 選択画面を開くたびに最新モデル一覧を取得し、Cloud／ローカルタブへ表示する。
- 選択モデルがアプリ専用JSONへ保存される。
- モデル変更だけではCodex Appを終了・再起動しない。
- 任意の検証済みモデル名を切り替え引数へ安全に設定できる。
- 未準備モデルは起動せずモデル管理画面へ案内する。
- ローカルモデル選択時・起動時に警告する。
- 6つの候補モデルにインストールボタンとOllama公式ページリンクがある。
- macOS / WindowsのGitHub Actions自動テストがすべて成功する。
- GitHub ReleaseからMac版ZIPとWindows版EXEを直接ダウンロードできる。
