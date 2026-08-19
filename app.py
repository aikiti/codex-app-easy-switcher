from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from tkinter import messagebox, ttk

from codex_model_launcher.core import (
    OLLAMA_DOWNLOAD_URL,
    WORKSHOP_MODEL_16GB,
    WORKSHOP_MODEL_32GB,
    WORKSHOP_MODEL_8GB,
    WORKSHOP_MODEL_GEMMA4_12B,
    WORKSHOP_MODEL_GEMMA4_E4B,
    WORKSHOP_MODEL_QWEN_9B,
    AppSettings,
    CodexState,
    OllamaModel,
    backup_codex_config,
    codex_app_is_running,
    detect_ollama,
    format_checks,
    is_cloud_model,
    is_codex_compatible_model,
    is_valid_model,
    launch_codex_app,
    list_ollama_models,
    load_settings,
    model_kind,
    normalize_model_input,
    ollama_model_library_url,
    quit_codex_app,
    read_codex_state,
    remove_legacy_profile_from_config,
    run_checks,
    save_settings,
    state_matches_target,
    subprocess_window_options,
    switch_codex_connection,
)


SWITCH_WARNING = (
    "Codex Appをいったん終了して、接続先を切り替えます。\n"
    "入力途中の内容がある場合は失われる可能性があります。続けますか？"
)

LOCAL_MODEL_WARNING = (
    "このローカルモデルでは、Codex Appのファイル編集やエージェント機能が"
    "正常に動作しない可能性があります。\n\n"
    "問題が発生した場合は、通常のCodex GPTに戻してください。\n\n"
    "このモデルでCodex Appを起動しますか？"
)


class ModelSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        models: list[OllamaModel],
        current_model: str,
    ) -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.models = models
        self.manual_model_var = tk.StringVar(value=current_model)

        self.title("Codex Appで使うモデルを変更")
        self.geometry("780x720")
        self.minsize(720, 640)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(
            outer,
            text="Codex Appで使うOllamaモデルを選びます",
            font=("", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text=(
                "モデルを選ぶだけではCodex Appは再起動しません。"
                " Cloudモデルとローカルモデルをタブで表示します。"
            ),
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        self.model_tabs = ttk.Notebook(outer)
        self.model_tabs.grid(row=2, column=0, sticky="nsew")

        self.cloud_frame = ttk.Frame(self.model_tabs, padding=10)
        self.model_tabs.add(self.cloud_frame, text="Cloudモデル")
        self.cloud_frame.columnconfigure(0, weight=1)
        self.cloud_frame.rowconfigure(0, weight=1)
        self.cloud_tree = self._create_model_tree(self.cloud_frame)
        self.cloud_tree.grid(row=0, column=0, sticky="nsew")
        self.cloud_tree.bind("<Double-1>", lambda _event: self._choose_from_tree(self.cloud_tree))
        ttk.Button(
            self.cloud_frame,
            text="選択したCloudモデルを使う",
            command=lambda: self._choose_from_tree(self.cloud_tree),
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        self.advanced_frame = ttk.Frame(self.model_tabs, padding=10)
        self.model_tabs.add(self.advanced_frame, text="インストール済みローカルモデル")
        self.advanced_frame.columnconfigure(0, weight=1)
        self.advanced_frame.rowconfigure(1, weight=1)
        ttk.Label(
            self.advanced_frame,
            text=(
                "Codex対応モデルだけ選択できます。非対応モデルは"
                "Ollamaアプリでの体験用として表示します。"
            ),
            foreground="#a33b20",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.local_tree = self._create_model_tree(self.advanced_frame)
        self.local_tree.grid(row=1, column=0, sticky="nsew")
        self.local_tree.bind("<Double-1>", lambda _event: self._choose_from_tree(self.local_tree))
        ttk.Button(
            self.advanced_frame,
            text="選択したローカルモデルを使う",
            command=lambda: self._choose_from_tree(self.local_tree),
        ).grid(row=2, column=0, sticky="e", pady=(6, 10))
        manual = ttk.Frame(self.advanced_frame)
        manual.grid(row=3, column=0, sticky="ew")
        manual.columnconfigure(1, weight=1)
        ttk.Label(manual, text="モデル名を手動入力").grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(manual, textvariable=self.manual_model_var).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Button(manual, text="入力したモデルを選ぶ", command=self._choose_manual).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Button(outer, text="キャンセル", command=self.destroy).grid(
            row=3, column=0, sticky="e", pady=(14, 0)
        )
        self._populate_trees()
        if any(not is_cloud_model(model.name) for model in self.models):
            self.model_tabs.select(self.advanced_frame)

    @staticmethod
    def _create_model_tree(parent: ttk.Frame) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent,
            columns=("name", "status", "size"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        tree.heading("name", text="モデル名")
        tree.heading("status", text="用途")
        tree.heading("size", text="サイズ")
        tree.column("name", width=410)
        tree.column("status", width=120, stretch=False)
        tree.column("size", width=100, stretch=False)
        return tree

    def _populate_trees(self) -> None:
        cloud_models = sorted(
            (
                model
                for model in self.models
                if is_cloud_model(model.name)
            ),
            key=lambda model: model.name.lower(),
        )
        local_models = sorted(
            (model for model in self.models if not is_cloud_model(model.name)),
            key=lambda model: model.name.lower(),
        )
        for tree, items in ((self.cloud_tree, cloud_models), (self.local_tree, local_models)):
            for model in items:
                tree.insert(
                    "", "end", values=(model.name, model.codex_status, model.size)
                )

    def _choose_from_tree(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(
                "モデルを選択してください",
                "一覧から使用するモデルを選択してください。",
                parent=self,
            )
            return
        values = tree.item(selection[0], "values")
        if values:
            self._choose(str(values[0]))

    def _choose_manual(self) -> None:
        model = normalize_model_input(self.manual_model_var.get())
        if model is None:
            messagebox.showerror(
                "モデル名を確認してください",
                (
                    "モデル名、またはOllama公式ページの「ollama run モデル名」を"
                    "貼り付けてください。"
                ),
                parent=self,
            )
            return
        self.manual_model_var.set(model)
        self._choose(model)

    def _choose(self, model: str) -> None:
        installed = next((item for item in self.models if item.name == model), None)
        if installed and not is_codex_compatible_model(installed):
            messagebox.showerror(
                "Codexでは使用できません",
                (
                    f"{model} はCodexに必要なthinking・tools・64K以上の"
                    "コンテキスト条件を満たしていません。\n\n"
                    "OllamaアプリでのローカルLLM体験に使用してください。"
                ),
                parent=self,
            )
            return
        if not is_cloud_model(model) and not messagebox.askyesno(
            "ローカルモデルを選択します",
            LOCAL_MODEL_WARNING.replace(
                "このモデルでCodex Appを起動しますか？",
                "このモデルを選択しますか？",
            ),
            parent=self,
        ):
            return
        self.result = model
        self.destroy()


class ExitChoiceDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.result = "cancel"
        self.title("終了前の確認")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Codex AppはOllama接続の状態です。", font=("", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            frame,
            text=(
                "通常のCodexへ戻す場合は、Codex Appをいったん終了して復元します。\n"
                "入力途中の内容がある場合は失われる可能性があります。"
            ),
            justify="left",
        ).pack(anchor="w", pady=(8, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(
            buttons,
            text="通常のCodexに戻して終了",
            command=lambda: self._choose("restore"),
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Ollama状態のまま終了",
            command=lambda: self._choose("keep"),
        ).pack(side="left", padx=8)
        ttk.Button(buttons, text="キャンセル", command=lambda: self._choose("cancel")).pack(
            side="right"
        )
        self.protocol("WM_DELETE_WINDOW", lambda: self._choose("cancel"))
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _choose(self, result: str) -> None:
        self.result = result
        self.destroy()


class CodexAppLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = load_settings()
        self.install_model_var = tk.StringVar(value=self.settings.install_model)
        self.selected_model_var = tk.StringVar(value=self.settings.codex_model)
        self.selected_model_detail_var = tk.StringVar(value="")
        self.state_var = tk.StringVar(value="現在の状態を確認しています...")
        self.state_detail_var = tk.StringVar(value="")
        self.model_summary_var = tk.StringVar(value="モデル一覧を確認していません。")
        self.busy = False
        self.pull_response = None
        self.pull_cancel_event = threading.Event()
        self.pull_in_progress = False
        self.select_model_after_pull: str | None = None
        self.models: list[OllamaModel] = []

        self._configure_window()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._start_checks)

    def _configure_window(self) -> None:
        self.root.title("Codex App かんたん切り替え")
        self.root.geometry(self.settings.window_geometry)
        self.root.minsize(860, 700)
        style = ttk.Style(self.root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        style.configure("Title.TLabel", font=("", 19, "bold"))
        style.configure("State.TLabel", font=("", 17, "bold"))
        style.configure("Primary.TButton", font=("", 13, "bold"), padding=(14, 13))
        style.configure("Secondary.TButton", font=("", 13, "bold"), padding=(14, 13))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Codex App かんたん切り替え", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="ターミナルを使わず、Codex Appの接続先とOllamaモデルを管理します。",
        ).pack(anchor="w", pady=(2, 12))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self.switch_tab = ttk.Frame(self.tabs, padding=16)
        self.models_tab = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(self.switch_tab, text="Codex App かんたん切り替え")
        self.tabs.add(self.models_tab, text="Ollama モデル管理")
        self._build_switch_tab()
        self._build_models_tab()

    def _build_switch_tab(self) -> None:
        tab = self.switch_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

        state_frame = ttk.LabelFrame(tab, text=" 現在のCodex App ", padding=16)
        state_frame.grid(row=0, column=0, sticky="ew")
        state_frame.columnconfigure(0, weight=1)
        self.state_label = ttk.Label(
            state_frame, textvariable=self.state_var, style="State.TLabel", justify="left"
        )
        self.state_label.grid(row=0, column=0, sticky="w")
        ttk.Label(state_frame, textvariable=self.state_detail_var, justify="left").grid(
            row=1, column=0, sticky="w", pady=(5, 0)
        )
        self.refresh_button = ttk.Button(
            state_frame, text="状態を再確認", command=self._start_checks
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, padx=(16, 0))

        action_frame = ttk.LabelFrame(tab, text=" 接続先を選んで起動 ", padding=16)
        action_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        action_frame.columnconfigure((0, 1), weight=1)
        self.normal_button = ttk.Button(
            action_frame,
            text="通常のCodex GPTで起動",
            style="Primary.TButton",
            command=lambda: self._request_switch("normal"),
        )
        self.normal_button.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.ollama_button = ttk.Button(
            action_frame,
            text="選択中のOllamaモデルで起動",
            style="Secondary.TButton",
            command=lambda: self._request_switch("ollama"),
        )
        self.ollama_button.grid(row=0, column=1, sticky="ew", padx=(7, 0))

        selected_frame = ttk.Frame(action_frame, padding=(0, 12, 0, 0))
        selected_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        selected_frame.columnconfigure(0, weight=1)
        ttk.Label(selected_frame, text="選択中のOllamaモデル", font=("", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            selected_frame,
            textvariable=self.selected_model_var,
            font=("", 16, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Label(selected_frame, textvariable=self.selected_model_detail_var).grid(
            row=2, column=0, sticky="w", pady=(2, 0)
        )
        selected_buttons = ttk.Frame(selected_frame)
        selected_buttons.grid(row=0, column=1, rowspan=3, padx=(12, 0))
        self.change_model_button = ttk.Button(
            selected_buttons,
            text="モデルを変更",
            command=self._choose_codex_model,
        )
        self.change_model_button.pack(side="left")

        ttk.Label(
            action_frame,
            text=(
                "通常のCodex GPTと選択したOllamaモデルを使い分けます。"
                " 切り替えはOllama公式機能で行います。"
            ),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.ollama_missing = ttk.Frame(tab)
        ttk.Label(
            self.ollama_missing,
            text="Ollamaが見つかりません。インストール後に状態を再確認してください。",
            foreground="#a33b20",
        ).pack(side="left")
        ttk.Button(
            self.ollama_missing,
            text="Ollama公式ダウンロードページを開く",
            command=lambda: webbrowser.open(OLLAMA_DOWNLOAD_URL),
        ).pack(side="right")

        ttk.Label(tab, text="状態・結果", font=("", 12, "bold")).grid(
            row=3, column=0, sticky="w", pady=(16, 4)
        )
        self.switch_log = tk.Text(tab, height=12, wrap="word")
        self.switch_log.grid(row=4, column=0, sticky="nsew")
        self._replace_text(self.switch_log, "準備しています...")

    def _build_models_tab(self) -> None:
        tab = self.models_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        workshop_frame = ttk.LabelFrame(
            tab, text=" 勉強会向け・PC容量別かんたん準備 ", padding=12
        )
        workshop_frame.grid(row=0, column=0, sticky="ew")
        workshop_frame.columnconfigure((0, 1), weight=1)
        ttk.Label(
            workshop_frame,
            text=(
                "自分のPCに合うボタンを1つだけ押してください。"
                " メモリ容量は目安です（GPU・コンテキスト設定で変動します）。"
            ),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        def add_model_card(
            row: int,
            column: int,
            title: str,
            model: str,
            detail: str,
        ) -> ttk.Button:
            card = ttk.LabelFrame(workshop_frame, text=f" {title} ", padding=8)
            card.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0, 6) if column == 0 else (6, 0),
                pady=(6, 0),
            )
            card.columnconfigure(0, weight=1)
            install = ttk.Button(
                card,
                text=f"{model}\n{detail}",
                command=lambda value=model: self._request_workshop_model(value),
            )
            install.grid(row=0, column=0, sticky="ew")
            ttk.Button(
                card,
                text="Ollama公式ページ（コマンドをコピー）",
                command=lambda value=model: self._open_model_page(value),
            ).grid(row=1, column=0, sticky="ew", pady=(5, 0))
            return install

        self.workshop_8gb_button = add_model_card(
            1,
            0,
            "メモリ8GB目安・Ollama体験用",
            WORKSHOP_MODEL_8GB,
            "約815MB／テキスト専用／Codex不可",
        )
        self.workshop_16gb_button = add_model_card(
            1,
            1,
            "メモリ16GB目安・Codex軽量",
            WORKSHOP_MODEL_16GB,
            "約4.3GB／画像対応／推論: 低推奨",
        )
        self.workshop_gemma4_e4b_button = add_model_card(
            2,
            0,
            "メモリ16～24GB目安・Gemma 4",
            WORKSHOP_MODEL_GEMMA4_E4B,
            "約6.1GB／画像対応／Codex対応",
        )
        self.workshop_gemma4_12b_button = add_model_card(
            2,
            1,
            "メモリ24GB以上目安・Gemma 4",
            WORKSHOP_MODEL_GEMMA4_12B,
            "約7.2GB／画像対応／Codex対応",
        )
        self.workshop_qwen9_button = add_model_card(
            3,
            0,
            "メモリ16～24GB目安・Qwen推奨",
            WORKSHOP_MODEL_QWEN_9B,
            "約6.6GB／画像対応／推論: 低推奨",
        )
        self.workshop_32gb_button = add_model_card(
            3,
            1,
            "メモリ32GB以上目安・Qwen高性能",
            WORKSHOP_MODEL_32GB,
            "約17GB／画像対応／Codex対応",
        )
        ttk.Label(
            workshop_frame,
            text=(
                "注意: Gemma 3 1BはOllamaアプリでの体験専用です。"
                " 推論レベルを低にしてもCodexでは使用できません。"
            ),
            foreground="#a33b20",
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Button(
            workshop_frame,
            text="Ollama公式ダウンロード",
            command=lambda: webbrowser.open(OLLAMA_DOWNLOAD_URL),
        ).grid(row=4, column=1, sticky="e", padx=6, pady=(8, 0))

        install_frame = ttk.LabelFrame(tab, text=" 新しいモデルをインストール ", padding=12)
        install_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        install_frame.columnconfigure(1, weight=1)
        ttk.Label(install_frame, text="モデル名 / 公式コマンド").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.install_entry = ttk.Entry(install_frame, textvariable=self.install_model_var)
        self.install_entry.grid(row=0, column=1, sticky="ew")
        self.install_button = ttk.Button(
            install_frame, text="モデルをインストール", command=self._request_pull
        )
        self.install_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(
            install_frame,
            text=(
                "RAG・AIエージェント・自作アプリなど、将来の用途向けです。"
                " 公式ページの「ollama run ...」をそのまま貼り付けられます。"
            ),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(14, 6))
        ttk.Label(toolbar, textvariable=self.model_summary_var, font=("", 12, "bold")).pack(
            side="left"
        )
        self.models_refresh_button = ttk.Button(
            toolbar, text="モデル一覧を更新", command=self._start_model_refresh
        )
        self.models_refresh_button.pack(side="right")

        columns = ("kind", "name", "codex", "size", "modified")
        self.model_tree = ttk.Treeview(tab, columns=columns, show="headings", height=7)
        self.model_tree.heading("kind", text="種類")
        self.model_tree.heading("name", text="モデル名")
        self.model_tree.heading("codex", text="用途")
        self.model_tree.heading("size", text="サイズ")
        self.model_tree.heading("modified", text="更新")
        self.model_tree.column("kind", width=90, stretch=False)
        self.model_tree.column("name", width=260)
        self.model_tree.column("codex", width=120, stretch=False)
        self.model_tree.column("size", width=100, stretch=False)
        self.model_tree.column("modified", width=180)
        self.model_tree.grid(row=3, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.model_tree.yview)
        scrollbar.grid(row=3, column=1, sticky="ns")
        self.model_tree.configure(yscrollcommand=scrollbar.set)

        progress_frame = ttk.LabelFrame(tab, text=" インストール状況 ", padding=10)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.pull_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100, value=0
        )
        self.pull_progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cancel_pull_button = ttk.Button(
            progress_frame, text="中止", command=self._cancel_pull, state="disabled"
        )
        self.cancel_pull_button.grid(row=0, column=1)
        self.pull_status_var = tk.StringVar(value="待機中（0%）")
        ttk.Label(progress_frame, textvariable=self.pull_status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(7, 0)
        )
        self.pull_log = tk.Text(progress_frame, height=5, wrap="word")
        self.pull_log.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._replace_text(self.pull_log, "モデル名を入力してインストールできます。")

    @staticmethod
    def _replace_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _append_pull_log(self, text: str) -> None:
        clean = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text).strip()
        if not clean:
            return
        self.pull_log.configure(state="normal")
        self.pull_log.insert("end", clean + "\n")
        line_count = int(self.pull_log.index("end-1c").split(".")[0])
        if line_count > 120:
            self.pull_log.delete("1.0", f"{line_count - 100}.0")
        self.pull_log.see("end")
        self.pull_log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.normal_button,
            self.ollama_button,
            self.refresh_button,
            self.models_refresh_button,
            self.install_button,
            self.workshop_8gb_button,
            self.workshop_16gb_button,
            self.workshop_gemma4_e4b_button,
            self.workshop_gemma4_12b_button,
            self.workshop_qwen9_button,
            self.workshop_32gb_button,
            self.change_model_button,
        ):
            widget.configure(state=state)

    def _start_checks(self) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self._replace_text(self.switch_log, "Codex AppとOllamaの状態を確認しています...")
        threading.Thread(target=self._checks_worker, daemon=True).start()

    def _checks_worker(self) -> None:
        results, models, state = run_checks()
        self.root.after(0, lambda: self._finish_checks(results, models, state))

    def _finish_checks(self, results: list, models: list[OllamaModel], state: CodexState) -> None:
        self._show_state(state)
        self._show_models(models)
        self._replace_text(self.switch_log, format_checks(results))
        if detect_ollama():
            self.ollama_missing.grid_forget()
        else:
            self.ollama_missing.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._set_busy(False)

    def _show_state(self, state: CodexState) -> None:
        if state.mode == "normal":
            self.state_var.set("通常のCodex GPT")
            self.state_detail_var.set(f"モデル: {state.model or 'デフォルト'}")
        elif state.mode == "ollama":
            self.state_var.set("Ollama経由")
            self.state_detail_var.set(f"モデル: {state.model or '不明'}")
        else:
            self.state_var.set("状態を確認できません")
            self.state_detail_var.set(state.detail)

    def _refresh_selected_model_display(self) -> None:
        model = self.settings.codex_model
        if not model:
            self.selected_model_var.set("未選択")
            self.selected_model_detail_var.set("「モデルを変更」から選択してください")
            return
        self.selected_model_var.set(model)
        kind = model_kind(model)
        installed = next((item for item in self.models if item.name == model), None)
        status = (
            installed.codex_status
            if installed is not None
            else "未準備・モデル管理でインストールしてください"
        )
        self.selected_model_detail_var.set(f"{kind} / {status}")

    def _choose_codex_model(self) -> None:
        if self.busy:
            return
        ollama_path = detect_ollama()
        if not ollama_path:
            messagebox.showerror(
                "Ollamaが見つかりません",
                "Ollamaをインストールしてからモデルを選択してください。",
                parent=self.root,
            )
            return
        self._set_busy(True)
        self._replace_text(self.switch_log, "インストール済みモデルを再取得しています...")
        threading.Thread(
            target=self._choose_model_refresh_worker,
            args=(ollama_path,),
            daemon=True,
        ).start()

    def _choose_model_refresh_worker(self, ollama_path: str) -> None:
        ok, models, output = list_ollama_models(ollama_path)
        self.root.after(
            0,
            lambda: self._finish_choose_model_refresh(ok, models, output),
        )

    def _finish_choose_model_refresh(
        self, ok: bool, models: list[OllamaModel], output: str
    ) -> None:
        self._set_busy(False)
        if not ok:
            messagebox.showerror("モデル一覧取得エラー", output, parent=self.root)
            return
        self._show_models(models)
        dialog = ModelSelectionDialog(self.root, self.models, self.settings.codex_model)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        self.settings.codex_model = dialog.result
        self._save_settings()
        self._refresh_selected_model_display()
        self._replace_text(
            self.switch_log,
            (
                f"Codex App用モデルを {dialog.result} に変更しました。\n"
                "まだCodex Appの接続先は切り替えていません。"
            ),
        )

    def _request_switch(self, mode: str) -> None:
        if self.busy:
            return
        ollama_path = detect_ollama()
        current_state = read_codex_state()
        selected_model = self.settings.codex_model
        if mode == "ollama" and not selected_model:
            messagebox.showinfo(
                "モデルを選択してください",
                "先に「モデルを変更」からCodexで使うモデルを選択してください。",
                parent=self.root,
            )
            self._choose_codex_model()
            return
        if mode == "ollama" and not ollama_path:
            messagebox.showerror(
                "Ollamaが見つかりません",
                "Ollamaをインストールしてから、状態を再確認してください。",
                parent=self.root,
            )
            return
        installed_model = next(
            (model for model in self.models if model.name == selected_model), None
        )
        if mode == "ollama" and installed_model is None:
            self.install_model_var.set(selected_model)
            self.tabs.select(self.models_tab)
            messagebox.showwarning(
                "モデルの準備が必要です",
                (
                    f"{selected_model} がモデル一覧にありません。\n"
                    "モデル管理タブで内容を確認し、「モデルをインストール」を押してください。"
                ),
                parent=self.root,
            )
            return
        if (
            mode == "ollama"
            and installed_model is not None
            and not is_codex_compatible_model(installed_model)
        ):
            messagebox.showerror(
                "Codex非対応モデルです",
                (
                    f"{selected_model} はCodexに必要なthinking・tools・64K以上の"
                    "コンテキスト条件を満たしていません。\n\n"
                    "OllamaアプリでのローカルLLM体験に使用してください。"
                ),
                parent=self.root,
            )
            return
        if mode == "ollama" and not is_cloud_model(selected_model) and not messagebox.askyesno(
            "ローカルモデルで起動します",
            LOCAL_MODEL_WARNING,
            parent=self.root,
        ):
            return
        if state_matches_target(current_state, mode, selected_model) and (
            mode == "normal" or ollama_path is not None
        ):
            ok, message = launch_codex_app()
            self._show_state(current_state)
            self._replace_text(
                self.switch_log,
                (
                    "すでに選択した接続先になっています。\n"
                    + message
                    if ok
                    else "Codex Appを起動できませんでした。\n" + message
                ),
            )
            if not ok:
                messagebox.showerror("Codex App起動エラー", message, parent=self.root)
            return
        if not ollama_path:
            messagebox.showerror(
                "Ollamaが見つかりません",
                "Ollamaをインストールしてから、状態を再確認してください。",
                parent=self.root,
            )
            return
        if codex_app_is_running() and not messagebox.askyesno(
            "Codex Appを切り替えます", SWITCH_WARNING, parent=self.root
        ):
            return
        label = "通常のCodex GPT" if mode == "normal" else selected_model
        self._set_busy(True)
        self._replace_text(self.switch_log, f"{label}へ切り替えています。しばらくお待ちください...")
        threading.Thread(
            target=self._switch_worker,
            args=(ollama_path, mode, selected_model, False),
            daemon=True,
        ).start()

    def _switch_worker(
        self,
        ollama_path: str,
        mode: str,
        model: str,
        close_after: bool,
    ) -> None:
        quit_ok, quit_message = quit_codex_app()
        if not quit_ok:
            self.root.after(
                0, lambda: self._finish_switch(False, quit_message, close_after)
            )
            return
        try:
            backup_path = backup_codex_config()
        except OSError as exc:
            self.root.after(
                0,
                lambda error=str(exc): self._finish_switch(
                    False,
                    "安全のため切り替えを中止しました。\n"
                    f"Codex設定の自動バックアップを作成できません: {error}",
                    close_after,
                ),
            )
            return
        ok, output = switch_codex_connection(ollama_path, mode, model)
        output = f"自動バックアップ: {backup_path}\n" + output
        if ok and mode == "ollama":
            # 新しい Codex が拒否するレガシーな profile 行を取り除く（互換処理）。
            remove_legacy_profile_from_config()
        if ok and not close_after and not codex_app_is_running():
            launch_codex_app()
        state = read_codex_state()
        if ok and not state_matches_target(state, mode, model):
            ok = False
            output = (
                (output + "\n") if output else ""
            ) + f"切り替え後の状態を確認できませんでした: {state.detail}"
        message = output or ("切り替えが完了しました。" if ok else "切り替えに失敗しました。")
        self.root.after(0, lambda: self._finish_switch(ok, message, close_after))

    def _finish_switch(self, ok: bool, message: str, close_after: bool) -> None:
        if close_after and ok:
            self._save_and_destroy()
            return
        self._set_busy(False)
        state = read_codex_state()
        self._show_state(state)
        self._replace_text(
            self.switch_log,
            ("切り替えが完了しました。\n" if ok else "切り替えに失敗しました。\n") + message,
        )
        if not ok:
            messagebox.showerror("切り替えエラー", message, parent=self.root)

    def _start_model_refresh(self) -> None:
        if self.busy:
            return
        ollama_path = detect_ollama()
        if not ollama_path:
            messagebox.showerror("Ollamaが見つかりません", "Ollamaをインストールしてください。")
            return
        self._set_busy(True)
        self.model_summary_var.set("モデル一覧を更新しています...")
        threading.Thread(target=self._model_refresh_worker, args=(ollama_path,), daemon=True).start()

    def _model_refresh_worker(self, ollama_path: str) -> None:
        ok, models, output = list_ollama_models(ollama_path)
        self.root.after(0, lambda: self._finish_model_refresh(ok, models, output))

    def _finish_model_refresh(self, ok: bool, models: list[OllamaModel], output: str) -> None:
        self._set_busy(False)
        if ok:
            self._show_models(models)
        else:
            self.model_summary_var.set("モデル一覧を取得できませんでした。")
            messagebox.showerror("Ollama接続エラー", output, parent=self.root)

    def _show_models(self, models: list[OllamaModel]) -> None:
        self.models = sorted(
            models,
            key=lambda model: (not is_cloud_model(model.name), model.name.lower()),
        )
        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        for model in self.models:
            self.model_tree.insert(
                "",
                "end",
                values=(
                    model.kind,
                    model.name,
                    model.codex_status,
                    model.size,
                    model.modified,
                ),
            )
        cloud_count = sum(model.kind == "Cloud" for model in self.models)
        self.model_summary_var.set(
            f"インストール済み: {len(self.models)}件"
            f"（Cloud {cloud_count}件 / ローカル {len(self.models) - cloud_count}件）"
        )
        self._refresh_selected_model_display()

    @staticmethod
    def _open_model_page(model: str) -> None:
        webbrowser.open(ollama_model_library_url(model))

    def _request_workshop_model(self, model: str) -> None:
        if self.busy:
            return
        self.install_model_var.set(model)
        installed = next((item for item in self.models if item.name == model), None)
        if installed is not None:
            if is_codex_compatible_model(installed):
                self.settings.codex_model = model
                self._save_settings()
                self._refresh_selected_model_display()
                self.tabs.select(self.switch_tab)
                detail = "Codex Appで使うOllamaモデルとして選択しました。"
                guidance = "「選択中のOllamaモデルで起動」を押すと切り替えられます。"
            else:
                detail = "OllamaアプリでのローカルLLM体験に使用できます。"
                guidance = "このモデルはCodex用には選択されません。"
            self._replace_text(
                self.switch_log,
                f"{model} はインストール済みです。\n{detail}",
            )
            messagebox.showinfo(
                "モデルの準備ができています",
                f"{model} はインストール済みです。\n\n{guidance}",
                parent=self.root,
            )
            return
        self._request_pull(select_after=model != WORKSHOP_MODEL_8GB)

    def _request_pull(self, select_after: bool = False) -> None:
        model = normalize_model_input(self.install_model_var.get())
        if model is None:
            messagebox.showerror(
                "モデル名を確認してください",
                (
                    "モデル名、またはOllama公式ページの「ollama run モデル名」を"
                    "貼り付けてください。"
                ),
                parent=self.root,
            )
            return
        self.install_model_var.set(model)
        ollama_path = detect_ollama()
        if not ollama_path:
            messagebox.showerror("Ollamaが見つかりません", "Ollamaをインストールしてください。")
            return
        kind = model_kind(model)
        prompt = (
            f"次の{kind}をインストールします。\n\n"
            f"モデル名: {model}\n\n"
            "ローカルモデルは大容量の通信とディスク容量を使用する場合があります。\n"
            "完了するまでPCを閉じないでください。開始しますか？"
        )
        if not messagebox.askyesno("モデルをインストール", prompt, parent=self.root):
            return
        self.select_model_after_pull = model if select_after else None
        self.settings.install_model = model
        self._save_settings()
        self._set_busy(True)
        self.pull_in_progress = True
        self.pull_cancel_event.clear()
        self.pull_progress.configure(value=0)
        self.pull_status_var.set("Ollamaへ接続しています（0%）")
        self.cancel_pull_button.configure(state="normal")
        self._replace_text(self.pull_log, f"{model} のインストールを開始します...")
        threading.Thread(target=self._pull_worker, args=(ollama_path, model), daemon=True).start()

    def _pull_worker(self, ollama_path: str, model: str) -> None:
        del ollama_path  # Ollamaの公式ローカルAPIを使用する。
        cancelled = False
        try:
            body = json.dumps({"model": model, "stream": True}).encode("utf-8")
            request = urllib.request.Request(
                "http://127.0.0.1:11434/api/pull",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # Fixed loopback Ollama endpoint; no user-controlled URL or scheme.
            with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
                self.pull_response = response
                succeeded = False
                for raw_line in response:
                    if self.pull_cancel_event.is_set():
                        cancelled = True
                        break
                    if not raw_line.strip():
                        continue
                    update = json.loads(raw_line.decode("utf-8"))
                    if update.get("error"):
                        raise RuntimeError(str(update["error"]))
                    status = str(update.get("status", "処理中"))
                    total = int(update.get("total") or 0)
                    completed = int(update.get("completed") or 0)
                    percent = min(100, round(completed * 100 / total)) if total else None
                    self.root.after(
                        0,
                        lambda s=status, p=percent: self._update_pull_progress(s, p),
                    )
                    succeeded = status.lower() == "success"
            cancelled = cancelled or self.pull_cancel_event.is_set()
            self.root.after(
                0,
                lambda: self._finish_pull(succeeded and not cancelled, cancelled, model),
            )
        except (
            OSError,
            ValueError,
            urllib.error.URLError,
            json.JSONDecodeError,
            RuntimeError,
        ) as exc:
            was_cancelled = cancelled or self.pull_cancel_event.is_set()
            self.root.after(
                0,
                lambda error=str(exc), was_cancelled=was_cancelled: self._finish_pull(
                    False, was_cancelled, model, error
                ),
            )
        finally:
            self.pull_response = None

    def _update_pull_progress(self, status: str, percent: int | None) -> None:
        if percent is None:
            self.pull_status_var.set(status)
            return
        self.pull_progress.configure(value=percent)
        self.pull_status_var.set(f"{status}（{percent}%）")

    def _finish_pull(
        self, ok: bool, cancelled: bool, model: str, error: str = ""
    ) -> None:
        self.pull_in_progress = False
        self.cancel_pull_button.configure(state="disabled")
        self._set_busy(False)
        if ok:
            self.pull_progress.configure(value=100)
            self.pull_status_var.set(f"完了: {model}（100%）")
            self._append_pull_log(f"{model} のインストールが完了しました。")
            if self.select_model_after_pull == model:
                self.settings.codex_model = model
                self._save_settings()
                self._append_pull_log(
                    "Codex Appで使うOllamaモデルとして自動選択しました。"
                )
            messagebox.showinfo(
                "インストール完了",
                f"{model} のインストールが完了しました。",
                parent=self.root,
            )
            self._start_model_refresh()
        elif cancelled:
            self.pull_status_var.set("インストールを中止しました。")
            self._append_pull_log("インストールを中止しました。")
        else:
            self.pull_status_var.set("インストールに失敗しました。")
            message = error or "インストールに失敗しました。表示内容を確認してください。"
            self._append_pull_log(message)
            messagebox.showerror("インストールエラー", message, parent=self.root)
        self.select_model_after_pull = None

    def _cancel_pull(self) -> None:
        if self.busy and messagebox.askyesno(
            "インストールを中止",
            "モデルのインストールを中止しますか？",
            parent=self.root,
        ):
            self.pull_cancel_event.set()
            response = self.pull_response
            if response is not None:
                response.close()

    def _save_settings(self) -> None:
        self.settings.install_model = self.install_model_var.get().strip()
        self.settings.window_geometry = self.root.geometry()
        save_settings(self.settings)

    def _on_close(self) -> None:
        if self.pull_in_progress:
            messagebox.showwarning(
                "インストール中です",
                "モデルのインストール中です。中止してから終了してください。",
                parent=self.root,
            )
            return
        if self.busy:
            messagebox.showwarning(
                "処理中です",
                "状態確認または切り替え処理が完了してから終了してください。",
                parent=self.root,
            )
            return
        state = read_codex_state()
        if state.mode != "ollama":
            self._save_and_destroy()
            return
        dialog = ExitChoiceDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result == "cancel":
            return
        if dialog.result == "keep":
            self._save_and_destroy()
            return
        ollama_path = detect_ollama()
        if not ollama_path:
            messagebox.showerror(
                "通常のCodexへ戻せません",
                "Ollamaが見つからないため復元できません。ランチャーは終了しません。",
                parent=self.root,
            )
            return
        self._set_busy(True)
        self._replace_text(self.switch_log, "通常のCodexへ戻しています...")
        threading.Thread(
            target=self._switch_worker,
            args=(ollama_path, "normal", self.settings.codex_model, True),
            daemon=True,
        ).start()

    def _save_and_destroy(self) -> None:
        try:
            self._save_settings()
        finally:
            self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex App かんたん切り替え")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    CodexAppLauncher(root)
    if args.smoke_test:
        root.after(1300, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
