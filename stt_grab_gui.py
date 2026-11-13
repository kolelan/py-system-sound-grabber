#!/usr/bin/env python3
"""
GUI: локальный STT (GigaAM / Whisper / Vosk) → текст → опционально LLM.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from llm_rewrite import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LlmError,
    LlmSettings,
    api_key_from_env,
    rewrite_text,
)
from stt_base import SttError, SttRecognizer
from stt_catalog import all_models, download, is_installed, list_installed, open_recognizer


class SttGrabGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("STT — локальные модели + LLM")
        self.root.geometry("980x860")
        self.root.minsize(780, 680)

        self.asr: SttRecognizer | None = None
        self._asr_id: str | None = None
        self._busy = False
        self._download_buttons: list[ttk.Button] = []
        self._label_to_id: dict[str, str] = {}

        self.audio_var = tk.StringVar()
        self.model_label_var = tk.StringVar()
        self.punct_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Готов")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.api_key_var = tk.StringVar(value=api_key_from_env())
        self.show_api_key_var = tk.BooleanVar(value=False)
        self.api_base_var = tk.StringVar(value=DEFAULT_BASE_URL)
        self.api_model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.prompt_var = tk.StringVar(
            value="Исправь ошибки распознавания, расставь знаки препинания, сделай текст читаемым."
        )

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def _build_ui(self) -> None:
        ttk.Label(self.root, text="Речь → текст → LLM", font=("Segoe UI", 14, "bold")).pack(
            pady=(10, 4)
        )

        src = ttk.LabelFrame(self.root, text="Аудио")
        src.pack(fill="x", padx=12, pady=4)
        ttk.Entry(src, textvariable=self.audio_var).pack(
            side=tk.LEFT, fill="x", expand=True, padx=6, pady=6
        )
        ttk.Button(src, text="Файл…", command=self.choose_audio).pack(side=tk.LEFT, padx=4)
        ttk.Button(src, text="Папка записей…", command=self.choose_from_captures).pack(
            side=tk.LEFT, padx=4
        )

        model = ttk.LabelFrame(self.root, text="Модель распознавания")
        model.pack(fill="x", padx=12, pady=4)
        pick = ttk.Frame(model)
        pick.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(pick, text="Установленные:").pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(
            pick, textvariable=self.model_label_var, state="readonly", width=36
        )
        self.model_combo.pack(side=tk.LEFT, fill="x", expand=True, padx=6)
        ttk.Button(pick, text="Обновить список", command=self.refresh_models).pack(side=tk.LEFT)
        ttk.Checkbutton(pick, text="Пунктуация (Silero)", variable=self.punct_var).pack(
            side=tk.LEFT, padx=6
        )
        downloads = ttk.Frame(model)
        downloads.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(downloads, text="Скачать:").pack(side=tk.LEFT)
        for spec in all_models():
            button = ttk.Button(
                downloads,
                text=spec.button,
                command=lambda model_id=spec.id: self.start_download(model_id),
            )
            button.pack(side=tk.LEFT, padx=4)
            self._download_buttons.append(button)
        self.refresh_models()

        controls = ttk.Frame(self.root)
        controls.pack(pady=6)
        self.recognize_btn = ttk.Button(controls, text="▶ Распознать", command=self.start_recognize)
        self.recognize_btn.pack(side=tk.LEFT, padx=4)

        ttk.Label(self.root, textvariable=self.status_var).pack()
        self.progress = ttk.Progressbar(self.root, maximum=100, variable=self.progress_var)
        self.progress.pack(fill="x", padx=12, pady=4)

        # Две панели текста всегда видны — раньше результат LLM уезжал за край окна.
        self.paned = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        self.paned.pack(fill="both", expand=True, padx=12, pady=4)

        asr_frame = ttk.Frame(self.paned)
        asr_hdr = ttk.Frame(asr_frame)
        asr_hdr.pack(fill="x")
        ttk.Label(asr_hdr, text="Распознанный текст (можно править)").pack(side=tk.LEFT)
        ttk.Button(
            asr_hdr, text="Копировать", command=lambda: self.copy_widget_text(self.text)
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            asr_hdr,
            text="Сохранить…",
            command=lambda: self.save_widget_text(self.text, "распознанный", "распознано"),
        ).pack(side=tk.RIGHT)
        self.text = tk.Text(asr_frame, height=10, wrap="word", undo=True, maxundo=-1)
        self.text.pack(fill="both", expand=True, pady=(2, 0))
        self._bind_text_editing(self.text)
        self.paned.add(asr_frame, weight=3)

        llm_pane = ttk.Frame(self.paned)
        llm = ttk.LabelFrame(llm_pane, text="Переработка в LLM (DeepSeek / совместимый API)")
        llm.pack(fill="x", pady=(0, 6))

        ttk.Label(llm, text="API key:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        key_row = ttk.Frame(llm)
        key_row.grid(row=0, column=1, sticky="we", padx=6, pady=4)
        self.api_key_entry = ttk.Entry(key_row, textvariable=self.api_key_var, show="•")
        self.api_key_entry.pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Checkbutton(
            key_row,
            text="Показать",
            variable=self.show_api_key_var,
            command=self._toggle_api_key_visibility,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(key_row, text="Вставить", command=self.paste_api_key).pack(side=tk.LEFT, padx=(4, 0))
        self._bind_api_key_clipboard(self.api_key_entry)

        ttk.Label(llm, text="Base URL:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(llm, textvariable=self.api_base_var).grid(
            row=1, column=1, sticky="we", padx=6, pady=4
        )
        ttk.Label(llm, text="Model:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            llm,
            textvariable=self.api_model_var,
            values=["deepseek-chat", "deepseek-flash", "deepseek-v4-pro"],
        ).grid(row=2, column=1, sticky="we", padx=6, pady=4)
        ttk.Label(llm, text="Промпт:").grid(row=3, column=0, sticky="nw", padx=6, pady=4)
        self.prompt_box = tk.Text(llm, height=3, wrap="word", undo=True, maxundo=-1)
        self.prompt_box.grid(row=3, column=1, sticky="we", padx=6, pady=4)
        self.prompt_box.insert("1.0", self.prompt_var.get())
        self._bind_text_editing(self.prompt_box)
        prompt_actions = ttk.Frame(llm)
        prompt_actions.grid(row=4, column=1, sticky="e", padx=6, pady=6)
        ttk.Button(prompt_actions, text="Загрузить промпт…", command=self.load_prompt).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(
            prompt_actions,
            text="Сохранить промпт…",
            command=lambda: self.save_widget_text(self.prompt_box, "промпт", "промпт"),
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(prompt_actions, text="Отправить в LLM", command=self.start_rewrite).pack(
            side=tk.LEFT
        )
        llm.columnconfigure(1, weight=1)

        llm_hdr = ttk.Frame(llm_pane)
        llm_hdr.pack(fill="x")
        ttk.Label(llm_hdr, text="Результат LLM (можно править)").pack(side=tk.LEFT)
        ttk.Button(
            llm_hdr, text="Копировать", command=lambda: self.copy_widget_text(self.llm_text)
        ).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(
            llm_hdr,
            text="Сохранить…",
            command=lambda: self.save_widget_text(self.llm_text, "LLM", "обработано"),
        ).pack(side=tk.RIGHT)
        self.llm_text = tk.Text(llm_pane, height=8, wrap="word", undo=True, maxundo=-1)
        self.llm_text.pack(fill="both", expand=True, pady=(2, 4))
        self._bind_text_editing(self.llm_text)
        self.paned.add(llm_pane, weight=2)

        self.root.after(50, self._set_initial_sash)

    def _set_initial_sash(self) -> None:
        try:
            height = max(self.paned.winfo_height(), 1)
            # Чуть больше места распознанному тексту, результат LLM остаётся на экране.
            self.paned.sashpos(0, int(height * 0.45))
        except tk.TclError:
            pass

    def _toggle_api_key_visibility(self) -> None:
        self.api_key_entry.configure(show="" if self.show_api_key_var.get() else "•")

    def paste_api_key(self) -> None:
        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Буфер", "Буфер обмена пуст")
            return
        key = (clip or "").strip()
        if not key:
            messagebox.showwarning("Буфер", "В буфере нет текста")
            return
        self.api_key_var.set(key)
        self.api_key_entry.icursor(tk.END)
        self.status_var.set("API key вставлен из буфера")

    def _bind_api_key_clipboard(self, entry: ttk.Entry) -> None:
        def do_paste(_event: tk.Event | None = None) -> str:
            self.paste_api_key()
            return "break"

        def do_copy(_event: tk.Event | None = None) -> str:
            try:
                if entry.selection_present():
                    self.root.clipboard_clear()
                    self.root.clipboard_append(entry.selection_get())
            except tk.TclError:
                pass
            return "break"

        def do_cut(_event: tk.Event | None = None) -> str:
            try:
                if entry.selection_present():
                    self.root.clipboard_clear()
                    self.root.clipboard_append(entry.selection_get())
                    entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass
            return "break"

        for seq in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            entry.bind(seq, do_paste)
        for seq in ("<Control-c>", "<Control-C>"):
            entry.bind(seq, do_copy)
        for seq in ("<Control-x>", "<Control-X>"):
            entry.bind(seq, do_cut)

        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Вставить", command=self.paste_api_key)
        menu.add_command(label="Копировать", command=lambda: do_copy())
        menu.add_command(label="Вырезать", command=lambda: do_cut())
        menu.add_separator()
        menu.add_command(label="Очистить", command=lambda: self.api_key_var.set(""))

        def show_menu(event: tk.Event) -> None:
            menu.tk_popup(event.x_root, event.y_root)

        entry.bind("<Button-3>", show_menu)

    def _bind_text_editing(self, widget: tk.Text) -> None:
        """Ctrl+A/C/V/X и ПКМ; keycode — чтобы работало и на русской раскладке Windows."""

        def select_all(_event: tk.Event | None = None) -> str:
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"

        def copy_sel(_event: tk.Event | None = None) -> str:
            try:
                if widget.tag_ranges(tk.SEL):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(widget.get(tk.SEL_FIRST, tk.SEL_LAST))
            except tk.TclError:
                pass
            return "break"

        def cut_sel(_event: tk.Event | None = None) -> str:
            try:
                if widget.tag_ranges(tk.SEL):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(widget.get(tk.SEL_FIRST, tk.SEL_LAST))
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass
            return "break"

        def paste_clip(_event: tk.Event | None = None) -> str:
            try:
                clip = self.root.clipboard_get()
            except tk.TclError:
                return "break"
            try:
                if widget.tag_ranges(tk.SEL):
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass
            widget.insert(tk.INSERT, clip)
            return "break"

        def on_ctrl_key(event: tk.Event) -> str | None:
            # Windows: keycode не зависит от раскладки (A=65, C=67, V=86, X=88).
            # Один обработчик — без двойной вставки на EN + поддержка RU.
            code = getattr(event, "keycode", None)
            if code == 65:
                return select_all(event)
            if code == 67:
                return copy_sel(event)
            if code == 86:
                return paste_clip(event)
            if code == 88:
                return cut_sel(event)
            return None

        widget.bind("<Control-KeyPress>", on_ctrl_key)
        widget.bind("<Shift-Insert>", paste_clip)

        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Выделить всё", command=select_all)
        menu.add_command(label="Копировать", command=copy_sel)
        menu.add_command(label="Вырезать", command=cut_sel)
        menu.add_command(label="Вставить", command=paste_clip)

        def show_menu(event: tk.Event) -> None:
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)

    def copy_widget_text(self, widget: tk.Text) -> None:
        content = widget.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Буфер", "Нечего копировать")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update_idletasks()
        self.status_var.set("Текст скопирован в буфер")

    def _suggested_save_name(self, marker: str) -> tuple[str, str | None]:
        """Имя для диалога: «<аудио> распознано|обработано ГГГГММДД_ЧЧ-ММ-СС.txt»."""
        stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
        audio = self.audio_var.get().strip()
        stem = Path(audio).stem if audio else ""
        filename = f"{stem} {marker} {stamp}.txt" if stem else f"{marker} {stamp}.txt"
        initialdir = None
        if audio:
            parent = Path(audio).expanduser().parent
            if parent.is_dir():
                initialdir = str(parent)
        return filename, initialdir

    def save_widget_text(self, widget: tk.Text, label: str, marker: str) -> None:
        content = widget.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("Текст", f"Нечего сохранять ({label})")
            return
        initialfile, initialdir = self._suggested_save_name(marker)
        # На Windows initialfile+initialdir часто даёт пустое имя — передаём полный путь.
        suggested = str(Path(initialdir) / initialfile) if initialdir else initialfile
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=suggested,
        )
        if path:
            Path(path).write_text(content + "\n", encoding="utf-8")
            self.status_var.set(f"Сохранено: {Path(path).name}")

    def load_prompt(self) -> None:
        _, initialdir = self._suggested_save_name("промпт")
        dialog_kwargs: dict = {
            "filetypes": [("Text", "*.txt"), ("All", "*.*")],
        }
        if initialdir:
            dialog_kwargs["initialdir"] = initialdir
        path = filedialog.askopenfilename(**dialog_kwargs)
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Промпт", f"Не удалось прочитать файл:\n{exc}")
            return
        self.prompt_box.delete("1.0", tk.END)
        self.prompt_box.insert("1.0", content.strip())
        self.status_var.set(f"Промпт загружен: {Path(path).name}")

    def choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Audio", "*.wav *.flac *.ogg *.mp3 *.m4a"),
                ("All", "*.*"),
            ]
        )
        if path:
            self.audio_var.set(path)

    def choose_from_captures(self) -> None:
        initial = Path("conference_captures")
        if not initial.is_dir():
            initial = Path(".")
        path = filedialog.askopenfilename(
            initialdir=str(initial.resolve()),
            filetypes=[("Audio", "*.wav *.flac *.ogg *.mp3"), ("All", "*.*")],
        )
        if path:
            self.audio_var.set(path)

    def refresh_models(self, select_id: str | None = None) -> None:
        installed = list_installed()
        self._label_to_id = {spec.title: spec.id for spec in installed}
        labels = list(self._label_to_id)
        self.model_combo["values"] = labels
        if select_id:
            for label, model_id in self._label_to_id.items():
                if model_id == select_id:
                    self.model_label_var.set(label)
                    return
        current = self.model_label_var.get()
        if current in self._label_to_id:
            return
        self.model_label_var.set(labels[0] if labels else "")
        if not labels:
            self.status_var.set("Нет моделей — скачайте GigaAM, Whisper или Vosk")

    def _selected_model_id(self) -> str | None:
        return self._label_to_id.get(self.model_label_var.get())

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.recognize_btn.config(state=state)
        for button in self._download_buttons:
            button.config(state=state)

    def start_download(self, model_id: str) -> None:
        if self._busy:
            return
        spec = next(item for item in all_models() if item.id == model_id)
        if is_installed(spec):
            self.refresh_models(select_id=model_id)
            self.status_var.set(f"Уже установлена: {spec.title}")
            return

        self._set_busy(True)
        self.progress_var.set(0)
        self.status_var.set(f"Скачивание: {spec.title}")

        def worker() -> None:
            try:
                def on_progress(frac: float, message: str) -> None:
                    self.root.after(0, lambda f=frac, m=message: self._on_download_progress(f, m))

                download(model_id, on_progress)
                self.root.after(0, lambda: self._on_downloaded(model_id))
            except SttError as exc:
                self.root.after(0, lambda m=str(exc): self._on_fail(m))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda m=str(exc): self._on_fail(m))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_progress(self, frac: float, message: str) -> None:
        self.progress_var.set(frac * 100)
        self.status_var.set(message)

    def _on_downloaded(self, model_id: str) -> None:
        self._set_busy(False)
        self.progress_var.set(100)
        self.refresh_models(select_id=model_id)
        self.status_var.set("Модель скачана и выбрана")

    def start_recognize(self) -> None:
        if self._busy:
            return
        audio = self.audio_var.get().strip()
        if not audio or not Path(audio).is_file():
            messagebox.showerror("Ошибка", "Выберите аудиофайл")
            return
        model_id = self._selected_model_id()
        if not model_id:
            messagebox.showerror("Модель", "Скачайте и выберите модель распознавания")
            return

        self._set_busy(True)
        self.status_var.set("Распознавание…")
        self.progress_var.set(0)
        self.text.delete("1.0", tk.END)

        def worker() -> None:
            try:
                if self.asr is None or self._asr_id != model_id:
                    self.asr = open_recognizer(model_id)
                    self._asr_id = model_id

                def on_progress(p: float) -> None:
                    self.root.after(0, lambda value=p: self.progress_var.set(value * 100))

                result = self.asr.transcribe(
                    audio,
                    punctuate=bool(self.punct_var.get()),
                    on_progress=on_progress,
                )
                self.root.after(0, lambda text=result: self._on_recognized(text))
            except SttError as exc:
                self.root.after(0, lambda message=str(exc): self._on_fail(message))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda message=str(exc): self._on_fail(message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_recognized(self, result: str) -> None:
        self._set_busy(False)
        self.progress_var.set(100)
        self.status_var.set("Готово")
        self.text.insert("1.0", result)

    def _on_fail(self, message: str) -> None:
        self._set_busy(False)
        self.status_var.set("Ошибка")
        messagebox.showerror("Ошибка", message)

    def start_rewrite(self) -> None:
        if self._busy:
            return
        src = self.text.get("1.0", tk.END).strip()
        prompt = self.prompt_box.get("1.0", tk.END).strip()
        if not src:
            messagebox.showwarning("LLM", "Сначала распознайте текст")
            return
        if not prompt:
            messagebox.showwarning("LLM", "Укажите уточняющий промпт")
            return
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("LLM", "Укажите API key")
            return

        self._set_busy(True)
        self.status_var.set("LLM…")
        self.llm_text.delete("1.0", tk.END)

        settings = LlmSettings(
            api_key=key,
            base_url=self.api_base_var.get().strip() or DEFAULT_BASE_URL,
            model=self.api_model_var.get().strip() or DEFAULT_MODEL,
        )

        def worker() -> None:
            try:
                out = rewrite_text(src, prompt, settings)
                self.root.after(0, lambda: self._on_rewritten(out))
            except LlmError as exc:
                self.root.after(0, lambda: self._on_fail(str(exc)))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._on_fail(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_rewritten(self, result: str) -> None:
        self._set_busy(False)
        self.status_var.set("LLM готово")
        self.llm_text.insert("1.0", result or "")
        self.llm_text.see("1.0")
        self.llm_text.focus_set()
        # Подтянуть нижнюю панель, если окно сжато.
        try:
            height = max(self.paned.winfo_height(), 1)
            if self.paned.sashpos(0) > int(height * 0.7):
                self.paned.sashpos(0, int(height * 0.45))
        except tk.TclError:
            pass
        if not (result or "").strip():
            messagebox.showwarning("LLM", "API вернул пустой ответ")


def main() -> None:
    root = tk.Tk()
    SttGrabGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
