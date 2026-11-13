#!/usr/bin/env python3
"""
Конференция: системный звук (собеседники) + микрофон.

- continuous: один большой файл
- segments: нарезка в папку
- stereo: L=система, R=микрофон; или mono-микс
- опциональный noise gate с pre/post-roll (для segments)

Экспериментальный скрипт (*_ext), базовые grab/mic_grab не трогает.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from audio_io import (
    SUPPORTED_FORMATS,
    refresh_timestamp_in_filename,
    with_audio_extension,
)
from conference_recorder_ext import ConferenceLevel, ConferenceRecorder, ConferenceSettings
from mic_recorder import MicDevice
from recorder import LoopbackDevice, RecorderError


class ConferenceGrabExtApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Конференция — система + микрофон")
        self.root.geometry("680x720")

        self.settings = ConferenceSettings()
        self.recorder = ConferenceRecorder(
            settings=self.settings,
            on_level=self._on_level,
            on_saved=self._on_saved,
        )
        self.loopbacks: list[LoopbackDevice] = []
        self.mics: list[MicDevice] = []

        self.sys_var = tk.StringVar()
        self.mic_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="continuous")
        self.mix_var = tk.StringVar(value="stereo")
        self.format_var = tk.StringVar(value="wav")
        self.folder_var = tk.StringVar(value=str(Path("conference_captures").resolve()))
        self.file_var = tk.StringVar(value="conference.wav")
        self.full_path_var = tk.StringVar(value="")
        self.buffer_var = tk.StringVar(value="30")
        self.gate_enable_var = tk.BooleanVar(value=False)
        self.gate_var = tk.DoubleVar(value=-45.0)
        self.pre_roll_var = tk.StringVar(value="250")
        self.post_roll_var = tk.StringVar(value="400")
        self.boost_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Готов")
        self.sys_level_var = tk.StringVar(value="Система: —")
        self.mic_level_var = tk.StringVar(value="Микрофон: —")
        self.buffer_pct_var = tk.StringVar(value="Буфер: —")

        self._last_level: ConferenceLevel | None = None
        self._pending_saved: Path | None = None
        self._syncing_paths = False

        self._build_ui()
        self.refresh_devices()
        self._update_full_path()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll()

    def _build_ui(self) -> None:
        ttk.Label(self.root, text="conference_grab_ext", font=("Segoe UI", 14, "bold")).pack(
            pady=(10, 2)
        )
        ttk.Label(
            self.root,
            text="Loopback + mic · один файл или сегменты · stereo (L/R) или микс",
            foreground="#444",
        ).pack(pady=(0, 8))

        dev = ttk.LabelFrame(self.root, text="Устройства")
        dev.pack(fill="x", padx=12, pady=4)
        ttk.Label(dev, text="Система (loopback):").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.sys_combo = ttk.Combobox(dev, textvariable=self.sys_var, state="readonly", width=70)
        self.sys_combo.grid(row=0, column=1, padx=6, pady=4, sticky="we")
        ttk.Label(dev, text="Микрофон:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.mic_combo = ttk.Combobox(dev, textvariable=self.mic_var, state="readonly", width=70)
        self.mic_combo.grid(row=1, column=1, padx=6, pady=4, sticky="we")
        ttk.Button(dev, text="Обновить", command=self.refresh_devices).grid(
            row=0, column=2, rowspan=2, padx=6, pady=4
        )
        dev.columnconfigure(1, weight=1)

        out = ttk.LabelFrame(self.root, text="Куда писать")
        out.pack(fill="x", padx=12, pady=4)
        ttk.Radiobutton(
            out, text="Один большой файл", variable=self.mode_var, value="continuous"
        ).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Radiobutton(
            out, text="Сегменты в папку", variable=self.mode_var, value="segments"
        ).grid(row=0, column=1, sticky="w", padx=6, pady=2)

        ttk.Label(out, text="Папка:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(out, textvariable=self.folder_var).grid(row=1, column=1, sticky="we", padx=6, pady=4)
        ttk.Button(out, text="Обзор…", command=self.choose_folder).grid(row=1, column=2, padx=6)

        ttk.Label(out, text="Файл:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(out, textvariable=self.file_var).grid(
            row=2, column=1, columnspan=2, sticky="we", padx=6, pady=4
        )

        ttk.Label(out, text="Полный путь:").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(out, textvariable=self.full_path_var, state="readonly").grid(
            row=3, column=1, columnspan=2, sticky="we", padx=6, pady=4
        )
        out.columnconfigure(1, weight=1)

        self.folder_var.trace_add("write", lambda *_: self._update_full_path())
        self.file_var.trace_add("write", lambda *_: self._on_filename_edited())
        self.format_var.trace_add("write", lambda *_: self._on_format_changed())

        opts = ttk.LabelFrame(self.root, text="Параметры")
        opts.pack(fill="x", padx=12, pady=4)
        ttk.Label(opts, text="Раскладка:").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        ttk.Combobox(
            opts,
            textvariable=self.mix_var,
            values=["stereo", "mix"],
            state="readonly",
            width=10,
        ).grid(row=0, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(opts, text="Формат:").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        ttk.Combobox(
            opts,
            textvariable=self.format_var,
            values=list(SUPPORTED_FORMATS),
            state="readonly",
            width=8,
        ).grid(row=0, column=3, padx=6, pady=4, sticky="w")
        ttk.Label(opts, text="Сегмент, сек:").grid(row=0, column=4, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.buffer_var, width=8).grid(
            row=0, column=5, padx=6, pady=4, sticky="w"
        )

        ttk.Checkbutton(
            opts, text="Gate в сегментах", variable=self.gate_enable_var
        ).grid(row=1, column=0, columnspan=2, padx=6, pady=4, sticky="w")
        ttk.Label(opts, text="Gate dB:").grid(row=1, column=2, padx=6, pady=4, sticky="w")
        ttk.Scale(
            opts, from_=-60, to_=-15, variable=self.gate_var, orient=tk.HORIZONTAL, length=140
        ).grid(row=1, column=3, columnspan=2, padx=6, pady=4, sticky="we")
        self.gate_label = ttk.Label(opts, text="-45")
        self.gate_label.grid(row=1, column=5, padx=6)
        self.gate_var.trace_add(
            "write", lambda *_: self.gate_label.config(text=f"{self.gate_var.get():.0f}")
        )

        ttk.Label(opts, text="Pre-roll мс:").grid(row=2, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.pre_roll_var, width=8).grid(
            row=2, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Label(opts, text="Post-roll мс:").grid(row=2, column=2, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.post_roll_var, width=8).grid(
            row=2, column=3, padx=6, pady=4, sticky="w"
        )
        ttk.Checkbutton(opts, text="Voice boost mic", variable=self.boost_var).grid(
            row=2, column=4, columnspan=2, padx=6, pady=4, sticky="w"
        )

        meters = ttk.LabelFrame(self.root, text="Уровни")
        meters.pack(fill="x", padx=12, pady=4)
        self.sys_bar = ttk.Progressbar(meters, maximum=100)
        self.sys_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(meters, textvariable=self.sys_level_var).pack(anchor="w", padx=8)
        self.mic_bar = ttk.Progressbar(meters, maximum=100)
        self.mic_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(meters, textvariable=self.mic_level_var).pack(anchor="w", padx=8)
        self.buf_bar = ttk.Progressbar(meters, maximum=100)
        self.buf_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(meters, textvariable=self.buffer_pct_var).pack(anchor="w", padx=8, pady=(0, 8))

        controls = ttk.Frame(self.root)
        controls.pack(pady=8)
        self.start_btn = ttk.Button(controls, text="▶ Старт", command=self.start_recording)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        self.stop_btn = ttk.Button(
            controls, text="⏹ Стоп", command=self.stop_recording, state="disabled"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Открыть папку", command=self.open_folder).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack()

        log_frame = ttk.LabelFrame(self.root, text="Лог")
        log_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.log = tk.Text(log_frame, height=8, wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh_devices(self) -> None:
        try:
            self.loopbacks = self.recorder.list_loopbacks()
            self.mics = self.recorder.list_mics()
            default_sys = self.recorder.get_default_loopback()
            default_mic = self.recorder.get_default_mic()
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        sys_labels = [str(d) for d in self.loopbacks]
        mic_labels = [str(d) for d in self.mics]
        self.sys_combo["values"] = sys_labels
        self.mic_combo["values"] = mic_labels
        self.sys_var.set(next((str(d) for d in self.loopbacks if d.index == default_sys.index), sys_labels[0] if sys_labels else ""))
        self.mic_var.set(next((str(d) for d in self.mics if d.index == default_mic.index), mic_labels[0] if mic_labels else ""))

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if path:
            self.folder_var.set(path)

    def open_folder(self) -> None:
        folder = Path(self.folder_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder.resolve()))

    def _on_format_changed(self) -> None:
        if self._syncing_paths:
            return
        fmt = self.format_var.get().strip().lower() or "wav"
        name = self.file_var.get().strip() or "conference.wav"
        self._syncing_paths = True
        try:
            self.file_var.set(with_audio_extension(name, fmt))
        finally:
            self._syncing_paths = False
        self._update_full_path()

    def _on_filename_edited(self) -> None:
        if self._syncing_paths:
            return
        # если пользователь вставил полный путь — разложим на папку + имя
        raw = self.file_var.get().strip()
        if raw and (("/" in raw) or ("\\" in raw)):
            path = Path(raw)
            self._syncing_paths = True
            try:
                if path.parent.as_posix() not in (".", ""):
                    self.folder_var.set(str(path.parent))
                fmt = self.format_var.get().strip().lower() or "wav"
                self.file_var.set(with_audio_extension(path.name, fmt))
            finally:
                self._syncing_paths = False
        self._update_full_path()

    def _base_filename(self) -> str:
        fmt = self.format_var.get().strip().lower() or "wav"
        name = self.file_var.get().strip() or "conference.wav"
        return with_audio_extension(Path(name).name, fmt)

    def _update_full_path(self) -> None:
        """Шаблонный путь (без метки времени). Метка появится в имени при Старт."""
        folder = self.folder_var.get().strip()
        if not folder:
            self.full_path_var.set("")
            return
        self.full_path_var.set(str((Path(folder) / self._base_filename()).resolve()))

    def _stamped_continuous_path(self) -> Path:
        """Папка + имя с YYYYMMDD-HH-MM-SS перед расширением (на момент старта)."""
        folder = Path(self.folder_var.get().strip() or ".")
        fmt = self.format_var.get().strip().lower() or "wav"
        stamped = refresh_timestamp_in_filename(self._base_filename(), fmt)
        return folder / stamped

    @staticmethod
    def _index_from_label(label: str) -> int | None:
        if not label:
            return None
        return int(label.split(":", 1)[0])

    def _apply_settings(self) -> None:
        try:
            buffer_seconds = float(self.buffer_var.get().strip())
            pre_roll = int(self.pre_roll_var.get().strip())
            post_roll = int(self.post_roll_var.get().strip())
        except ValueError as exc:
            raise RecorderError("Некорректные числовые параметры") from exc

        fmt = self.format_var.get().strip().lower()
        self.settings.write_mode = self.mode_var.get()  # type: ignore[assignment]
        self.settings.mix_mode = self.mix_var.get()  # type: ignore[assignment]
        self.settings.audio_format = fmt
        self.settings.output_dir = Path(self.folder_var.get())
        if self.settings.write_mode == "continuous":
            # базовое имя в поле не трогаем; метку времени вшиваем только в путь записи
            stamped_path = self._stamped_continuous_path()
            self.settings.continuous_path = stamped_path
            self.full_path_var.set(str(stamped_path.resolve()))
        else:
            self._update_full_path()
        self.settings.buffer_seconds = buffer_seconds
        self.settings.use_gate = bool(self.gate_enable_var.get())
        self.settings.noise_gate_db = float(self.gate_var.get())
        self.settings.pre_roll_ms = max(0, pre_roll)
        self.settings.post_roll_ms = max(0, post_roll)
        self.settings.voice_boost_mic = bool(self.boost_var.get())

    def start_recording(self) -> None:
        try:
            self._apply_settings()
            sys_dev, mic_dev = self.recorder.start(
                loopback_index=self._index_from_label(self.sys_var.get()),
                mic_index=self._index_from_label(self.mic_var.get()),
            )
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        mode = self.settings.write_mode
        self.status_var.set(f"Запись ({mode}): {sys_dev.name} + {mic_dev.name}")
        target = (
            self.settings.continuous_path
            if mode == "continuous"
            else self.settings.output_dir
        )
        self._log(
            f"Старт [{mode}/{self.settings.mix_mode}/{self.settings.audio_format}] "
            f"→ {target} · sys={sys_dev.index} mic={mic_dev.index}"
        )

    def stop_recording(self) -> None:
        saved = self.recorder.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if self.recorder.last_error:
            messagebox.showerror("Ошибка", str(self.recorder.last_error))
            self.status_var.set("Ошибка")
            return
        self.status_var.set("Стоп")
        for path in saved:
            self._log(f"Итог: {path}")
        self.sys_bar["value"] = 0
        self.mic_bar["value"] = 0

    def _on_level(self, info: ConferenceLevel) -> None:
        self._last_level = info

    def _on_saved(self, path: Path) -> None:
        self._pending_saved = path

    def _db_to_bar(self, db: float) -> float:
        # -60..0 → 0..100
        return max(0.0, min(100.0, (db + 60.0) * (100.0 / 60.0)))

    def _poll(self) -> None:
        info = self._last_level
        if info is not None:
            self.sys_bar["value"] = self._db_to_bar(info.system_db)
            self.mic_bar["value"] = self._db_to_bar(info.mic_db)
            self.sys_level_var.set(f"Система: {info.system_db:.1f} dBFS")
            self.mic_level_var.set(f"Микрофон: {info.mic_db:.1f} dBFS")
            if self.settings.write_mode == "segments":
                self.buf_bar["value"] = info.buffer_fill * 100.0
                gate = " · gate" if info.gated else ""
                self.buffer_pct_var.set(f"Буфер: {info.buffer_fill * 100:.0f}%{gate}")
            else:
                self.buf_bar["value"] = 0
                self.buffer_pct_var.set("Буфер: continuous")

        if self._pending_saved is not None:
            path = self._pending_saved
            self._pending_saved = None
            self._log(f"Сохранено: {path}")

        self.root.after(50, self._poll)

    def _log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def on_close(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
        self.recorder.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ConferenceGrabExtApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
