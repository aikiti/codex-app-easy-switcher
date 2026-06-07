from __future__ import annotations

import argparse
import re
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from codex_model_launcher.core import (
    DEFAULT_CODEX_OLLAMA_MODEL,
    OLLAMA_DOWNLOAD_URL,
    AppSettings,
    CodexState,
    OllamaModel,
    build_pull_args,
    codex_app_is_running,
    detect_ollama,
    format_checks,
    is_cloud_model,
    is_valid_model,
    launch_codex_app,
    list_ollama_models,
    load_settings,
    model_kind,
    quit_codex_app,
    read_codex_state,
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
    f"問題が発生した場合は、推奨モデル {DEFAULT_CODEX_OLLAMA_MODEL} に戻してください。\n\n"
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
        self.show_advanced_var = tk.BooleanVar(value=False)

        self.title("Codex Appで使うモデルを変更")
        self.geometry("720x620")
        self.minsize(680, 560)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(
            outer,
            text="Codex Appで使うOllamaモデルを選びます",
            font=("", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text=(
                "モデルを選ぶだけではCodex Appは再起動しません。"
                " Cloudモデルを優先して表示しています。"
            ),
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        recommended = ttk.LabelFrame(outer, text=" 推奨・動作確認済み ", padding=12)
        recommended.grid(row=2, column=0, sticky="ew")
        recommended.columnconfigure(0, weight=1)
        ttk.Label(
            recommended,
            text=DEFAULT_CODEX_OLLAMA_MODEL,
            font=("", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            recommended,
            text="Ollama Cloudモデル。初めて使う方におすすめです。",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(
            recommended,
            text="推奨モデルを選ぶ",
            command=lambda: self._choose(DEFAULT_CODEX_OLLAMA_MODEL),
        ).grid(row=0, column=1, rowspan=2, padx=(12, 0))

        self.cloud_frame = ttk.LabelFrame(outer, text=" その他のCloudモデル ", padding=10)
        self.cloud_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
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

        ttk.Checkbutton(
            outer,
            text="詳細設定を表示（ローカルモデル・モデル名の手入力）",
            variable=self.show_advanced_var,
            command=self._toggle_advanced,
        ).grid(row=4, column=0, sticky="w", pady=(12, 0))

        self.advanced_frame = ttk.LabelFrame(outer, text=" 詳細設定・上級者向け ", padding=10)
        self.advanced_frame.columnconfigure(0, weight=1)
        self.advanced_frame.rowconfigure(1, weight=1)
        ttk.Label(
            self.advanced_frame,
            text=(
                "ローカルモデルでは、Codex Appのエージェント機能が"
                "正常に動作しない場合があります。"
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
            row=6, column=0, sticky="e", pady=(14, 0)
        )
        self._populate_trees()

    @staticmethod
    def _create_model_tree(parent: ttk.Frame) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent,
            columns=("name", "size"),
            show="headings",
            height=6,
            selectmode="browse",
        )
        tree.heading("name", text="モデル名")
        tree.heading("size", text="サイズ")
        tree.column("name", width=470)
        tree.column("size", width=100, stretch=False)
        return tree

    def _populate_trees(self) -> None:
        cloud_models = sorted(
            (
                model
                for model in self.models
                if is_cloud_model(model.name)
                and model.name != DEFAULT_CODEX_OLLAMA_MODEL
            ),
            key=lambda model: model.name.lower(),
        )
        local_models = sorted(
            (model for model in self.models if not is_cloud_model(model.name)),
            key=lambda model: model.name.lower(),
        )
        for tree, items in ((self.cloud_tree, cloud_models), (self.local_tree, local_models)):
            for model in items:
                tree.insert("", "end", values=(model.name, model.size))

    def _toggle_advanced(self) -> None:
        if self.show_advanced_var.get():
            self.cloud_frame.grid_forget()
            self.advanced_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
            self.geometry("720x680")
        else:
            self.advanced_frame.grid_forget()
            self.cloud_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
            self.geometry("720x620")

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
        model = self.manual_model_var.get().strip()
        if not is_valid_model(model):
            messagebox.showerror(
                "モデル名を確認してください",
                "モデル名には英数字と . _ : / - のみ使用できます（200文字以内）。",
                parent=self,
            )
            return
        self._choose(model)

    def _choose(self, model: str) -> None:
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
        self.pull_process: subprocess.Popen[str] | None = None
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
            font=("", 13, "bold"),
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
        self.reset_model_button = ttk.Button(
            selected_buttons,
            text="推奨モデルに戻す",
            command=self._reset_recommended_model,
        )
        self.reset_model_button.pack(side="left", padx=(8, 0))

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
        tab.rowconfigure(2, weight=1)

        install_frame = ttk.LabelFrame(tab, text=" 新しいモデルをインストール ", padding=12)
        install_frame.grid(row=0, column=0, sticky="ew")
        install_frame.columnconfigure(1, weight=1)
        ttk.Label(install_frame, text="モデル名").grid(row=0, column=0, sticky="w", padx=(0, 8))
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
                " モデル名はOllama公式ライブラリで確認して入力してください。"
            ),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        ttk.Label(toolbar, textvariable=self.model_summary_var, font=("", 12, "bold")).pack(
            side="left"
        )
        self.models_refresh_button = ttk.Button(
            toolbar, text="モデル一覧を更新", command=self._start_model_refresh
        )
        self.models_refresh_button.pack(side="right")

        columns = ("kind", "name", "size", "modified")
        self.model_tree = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        self.model_tree.heading("kind", text="種類")
        self.model_tree.heading("name", text="モデル名")
        self.model_tree.heading("size", text="サイズ")
        self.model_tree.heading("modified", text="更新")
        self.model_tree.column("kind", width=90, stretch=False)
        self.model_tree.column("name", width=300)
        self.model_tree.column("size", width=100, stretch=False)
        self.model_tree.column("modified", width=180)
        self.model_tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.model_tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.model_tree.configure(yscrollcommand=scrollbar.set)

        progress_frame = ttk.LabelFrame(tab, text=" インストール状況 ", padding=10)
        progress_frame.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.pull_progress = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.pull_progress.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cancel_pull_button = ttk.Button(
            progress_frame, text="中止", command=self._cancel_pull, state="disabled"
        )
        self.cancel_pull_button.grid(row=0, column=1)
        self.pull_log = tk.Text(progress_frame, height=5, wrap="word")
        self.pull_log.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
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
            self.change_model_button,
            self.reset_model_button,
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
        self.selected_model_var.set(model)
        kind = model_kind(model)
        available = any(item.name == model for item in self.models)
        status = "利用可能" if available else "未準備・モデル管理でインストールしてください"
        recommendation = " / 推奨" if model == DEFAULT_CODEX_OLLAMA_MODEL else ""
        self.selected_model_detail_var.set(f"{kind}{recommendation} / {status}")

    def _choose_codex_model(self) -> None:
        if self.busy:
            return
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

    def _reset_recommended_model(self) -> None:
        if self.busy:
            return
        self.settings.codex_model = DEFAULT_CODEX_OLLAMA_MODEL
        self._save_settings()
        self._refresh_selected_model_display()
        self._replace_text(
            self.switch_log,
            (
                f"Codex App用モデルを推奨モデル {DEFAULT_CODEX_OLLAMA_MODEL} に戻しました。\n"
                "まだCodex Appの接続先は切り替えていません。"
            ),
        )

    def _request_switch(self, mode: str) -> None:
        if self.busy:
            return
        ollama_path = detect_ollama()
        current_state = read_codex_state()
        selected_model = self.settings.codex_model
        if mode == "ollama" and not ollama_path:
            messagebox.showerror(
                "Ollamaが見つかりません",
                "Ollamaをインストールしてから、状態を再確認してください。",
                parent=self.root,
            )
            return
        if mode == "ollama" and not any(
            model.name == selected_model for model in self.models
        ):
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
        ok, output = switch_codex_connection(ollama_path, mode, model)
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
                "", "end", values=(model.kind, model.name, model.size, model.modified)
            )
        cloud_count = sum(model.kind == "Cloud" for model in self.models)
        self.model_summary_var.set(
            f"インストール済み: {len(self.models)}件"
            f"（Cloud {cloud_count}件 / ローカル {len(self.models) - cloud_count}件）"
        )
        self._refresh_selected_model_display()

    def _request_pull(self) -> None:
        model = self.install_model_var.get().strip()
        if not is_valid_model(model):
            messagebox.showerror(
                "モデル名を確認してください",
                "モデル名には英数字と . _ : / - のみ使用できます（200文字以内）。",
                parent=self.root,
            )
            return
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
        self.settings.install_model = model
        self._save_settings()
        self._set_busy(True)
        self.pull_progress.start(12)
        self.cancel_pull_button.configure(state="normal")
        self._replace_text(self.pull_log, f"{model} のインストールを開始します...")
        threading.Thread(target=self._pull_worker, args=(ollama_path, model), daemon=True).start()

    def _pull_worker(self, ollama_path: str, model: str) -> None:
        try:
            self.pull_process = subprocess.Popen(
                build_pull_args(ollama_path, model),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                shell=False,
                **subprocess_window_options(),
            )
            assert self.pull_process.stdout is not None
            buffer = ""
            last_update = 0.0
            while True:
                char = self.pull_process.stdout.read(1)
                if char == "" and self.pull_process.poll() is not None:
                    break
                if char in ("\r", "\n"):
                    if buffer.strip():
                        now = time.monotonic()
                        if char == "\n" or now - last_update >= 0.15:
                            line = buffer
                            self.root.after(0, lambda value=line: self._append_pull_log(value))
                            last_update = now
                    buffer = ""
                else:
                    buffer += char
            if buffer.strip():
                self.root.after(0, lambda value=buffer: self._append_pull_log(value))
            returncode = self.pull_process.wait()
            cancelled = returncode < 0
            self.root.after(0, lambda: self._finish_pull(returncode == 0, cancelled, model))
        except OSError as exc:
            self.root.after(0, lambda: self._finish_pull(False, False, model, str(exc)))
        finally:
            self.pull_process = None

    def _finish_pull(
        self, ok: bool, cancelled: bool, model: str, error: str = ""
    ) -> None:
        self.pull_progress.stop()
        self.cancel_pull_button.configure(state="disabled")
        self._set_busy(False)
        if ok:
            self._append_pull_log(f"{model} のインストールが完了しました。")
            self._start_model_refresh()
        elif cancelled:
            self._append_pull_log("インストールを中止しました。")
        else:
            message = error or "インストールに失敗しました。表示内容を確認してください。"
            self._append_pull_log(message)
            messagebox.showerror("インストールエラー", message, parent=self.root)

    def _cancel_pull(self) -> None:
        process = self.pull_process
        if process and process.poll() is None:
            if messagebox.askyesno(
                "インストールを中止",
                "モデルのインストールを中止しますか？",
                parent=self.root,
            ):
                process.terminate()

    def _save_settings(self) -> None:
        self.settings.install_model = self.install_model_var.get().strip()
        self.settings.window_geometry = self.root.geometry()
        save_settings(self.settings)

    def _on_close(self) -> None:
        if self.pull_process and self.pull_process.poll() is None:
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
