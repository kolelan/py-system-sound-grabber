#!/usr/bin/env python3
"""
Расширенный GUI для микрофона (экспериментальный).

- папка для сегментов
- уровень входящего сигнала
- voice boost (подъём речевых частот)
- буфер N секунд → файл
- noise gate (тишина не попадает в буфер)
- pre/post-roll вокруг речи (мс до и после)
- форматы: wav / flac / ogg / mp3

Базовый mic_grab / mic_grab_gui не меняется.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from mic_recorder import MicDevice
from mic_recorder_ext import (
    SUPPORTED_FORMATS,
    ExtSettings,
    LevelInfo,
    SegmentedMicRecorder,
)
from recorder import RecorderError


class MicGrabExtApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Микрофон — расширенная запись")
        self.root.geometry("640x620")

        self.settings = ExtSettings()
        self.recorder = SegmentedMicRecorder(
            settings=self.settings,
            on_level=self._on_level,
            on_saved=self._on_saved,
        )
        self.devices: list[MicDevice] = []

        self.device_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(Path("mic_segments").resolve()))
        self.buffer_var = tk.StringVar(value="10")
        self.gate_var = tk.DoubleVar(value=-40.0)
        self.pre_roll_var = tk.StringVar(value="200")
        self.post_roll_var = tk.StringVar(value="300")
        self.boost_var = tk.BooleanVar(value=True)
        self.boost_db_var = tk.StringVar(value="6")
        self.format_var = tk.StringVar(value="wav")
        self.status_var = tk.StringVar(value="Готов")
        self.level_db_var = tk.StringVar(value="Уровень: —")
        self.buffer_pct_var = tk.StringVar(value="Буфер: 0%")
        self.gate_state_var = tk.StringVar(value="Gate: —")

        self._level_value = 0.0
        self._build_ui()
        self.refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll_meters()

    def _build_ui(self) -> None:
        ttk.Label(self.root, text="mic_grab_ext", font=("Segoe UI", 14, "bold")).pack(
            pady=(12, 2)
        )
        ttk.Label(
            self.root,
            text="Сегменты по буферу · noise gate · voice boost · выбор формата",
            foreground="#444",
        ).pack(pady=(0, 8))

        device_frame = ttk.LabelFrame(self.root, text="Микрофон")
        device_frame.pack(fill="x", padx=12, pady=4)
        self.device_combo = ttk.Combobox(
            device_frame, textvariable=self.device_var, state="readonly", width=72
        )
        self.device_combo.pack(side=tk.LEFT, padx=6, pady=6, fill="x", expand=True)
        ttk.Button(device_frame, text="Обновить", command=self.refresh_devices).pack(
            side=tk.RIGHT, padx=6, pady=6
        )

        folder_frame = ttk.LabelFrame(self.root, text="Папка для сегментов")
        folder_frame.pack(fill="x", padx=12, pady=4)
        ttk.Entry(folder_frame, textvariable=self.folder_var).pack(
            side=tk.LEFT, padx=6, pady=6, fill="x", expand=True
        )
        ttk.Button(folder_frame, text="Обзор…", command=self.choose_folder).pack(
            side=tk.RIGHT, padx=6, pady=6
        )

        opts = ttk.LabelFrame(self.root, text="Параметры")
        opts.pack(fill="x", padx=12, pady=4)

        ttk.Label(opts, text="Буфер, сек:").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.buffer_var, width=8).grid(
            row=0, column=1, padx=6, pady=4, sticky="w"
        )

        ttk.Label(opts, text="Формат:").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        ttk.Combobox(
            opts,
            textvariable=self.format_var,
            values=list(SUPPORTED_FORMATS),
            state="readonly",
            width=8,
        ).grid(row=0, column=3, padx=6, pady=4, sticky="w")

        ttk.Label(opts, text="Noise gate, dB:").grid(row=1, column=0, padx=6, pady=4, sticky="w")
        gate_scale = ttk.Scale(
            opts, from_=-60.0, to_=-10.0, variable=self.gate_var, orient=tk.HORIZONTAL, length=180
        )
        gate_scale.grid(row=1, column=1, columnspan=2, padx=6, pady=4, sticky="we")
        self.gate_label = ttk.Label(opts, text="-40 dB")
        self.gate_label.grid(row=1, column=3, padx=6, pady=4, sticky="w")
        self.gate_var.trace_add("write", self._update_gate_label)

        ttk.Label(opts, text="Pre-roll, мс:").grid(row=2, column=0, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.pre_roll_var, width=8).grid(
            row=2, column=1, padx=6, pady=4, sticky="w"
        )
        ttk.Label(opts, text="Post-roll, мс:").grid(row=2, column=2, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.post_roll_var, width=8).grid(
            row=2, column=3, padx=6, pady=4, sticky="w"
        )

        ttk.Checkbutton(
            opts, text="Voice boost (речивая полоса)", variable=self.boost_var
        ).grid(row=3, column=0, columnspan=2, padx=6, pady=4, sticky="w")
        ttk.Label(opts, text="Boost, dB:").grid(row=3, column=2, padx=6, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.boost_db_var, width=6).grid(
            row=3, column=3, padx=6, pady=4, sticky="w"
        )
        opts.columnconfigure(1, weight=1)

        meters = ttk.LabelFrame(self.root, text="Уровень и буфер")
        meters.pack(fill="x", padx=12, pady=4)
        self.level_bar = ttk.Progressbar(meters, maximum=100, mode="determinate")
        self.level_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(meters, textvariable=self.level_db_var).pack(anchor="w", padx=8)
        ttk.Label(meters, textvariable=self.gate_state_var).pack(anchor="w", padx=8)
        self.buffer_bar = ttk.Progressbar(meters, maximum=100, mode="determinate")
        self.buffer_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(meters, textvariable=self.buffer_pct_var).pack(anchor="w", padx=8, pady=(0, 8))

        controls = ttk.Frame(self.root)
        controls.pack(pady=10)
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

        log_frame = ttk.LabelFrame(self.root, text="Сохранённые сегменты")
        log_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.log = tk.Text(log_frame, height=8, wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def _update_gate_label(self, *_args) -> None:
        self.gate_label.config(text=f"{self.gate_var.get():.0f} dB")

    def refresh_devices(self) -> None:
        try:
            self.devices = self.recorder.list_devices()
            default = self.recorder.get_default_device()
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        labels = [str(d) for d in self.devices]
        self.device_combo["values"] = labels
        for d in self.devices:
            if d.index == default.index:
                self.device_var.set(str(d))
                break
        else:
            if labels:
                self.device_var.set(labels[0])

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if path:
            self.folder_var.set(path)

    def open_folder(self) -> None:
        folder = Path(self.folder_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        try:
            folder_str = str(folder.resolve())
            import os

            os.startfile(folder_str)  # noqa: S606 — Windows explorer
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("Папка", str(exc))

    def _selected_device_index(self) -> int | None:
        selected = self.device_var.get()
        if not selected:
            return None
        return int(selected.split(":", 1)[0])

    def _apply_settings_from_ui(self) -> None:
        try:
            buffer_seconds = float(self.buffer_var.get().strip())
            boost_db = float(self.boost_db_var.get().strip())
            pre_roll_ms = int(self.pre_roll_var.get().strip())
            post_roll_ms = int(self.post_roll_var.get().strip())
        except ValueError as exc:
            raise RecorderError("Некорректные числовые параметры") from exc

        self.settings.output_dir = Path(self.folder_var.get())
        self.settings.buffer_seconds = buffer_seconds
        self.settings.noise_gate_db = float(self.gate_var.get())
        self.settings.pre_roll_ms = max(0, pre_roll_ms)
        self.settings.post_roll_ms = max(0, post_roll_ms)
        self.settings.voice_boost = bool(self.boost_var.get())
        self.settings.voice_boost_db = boost_db
        self.settings.audio_format = self.format_var.get().strip().lower()

    def start_recording(self) -> None:
        try:
            self._apply_settings_from_ui()
            device = self.recorder.start(device_index=self._selected_device_index())
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set(f"Слушаю: {device.name}")
        self._log(f"Старт → {self.settings.output_dir} · буфер {self.settings.buffer_seconds}с · {self.settings.audio_format}")

    def stop_recording(self) -> None:
        saved = self.recorder.stop(flush=True)
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if self.recorder.last_error:
            messagebox.showerror("Ошибка", str(self.recorder.last_error))
            self.status_var.set("Ошибка")
            return
        self.status_var.set(f"Стоп. Сегментов за сессию: доп. flush={len(saved)}")
        self.level_bar["value"] = 0
        self.buffer_bar["value"] = 0

    def _on_level(self, info: LevelInfo) -> None:
        # вызывается из audio-потока — только кладём значение, UI обновит poll
        self._level_value = max(0.0, min(1.0, info.rms * 8.0))  # грубая шкала для бара
        self._last_level = info

    def _on_saved(self, path: Path) -> None:
        self._pending_saved = path

    def _poll_meters(self) -> None:
        info = getattr(self, "_last_level", None)
        if info is not None:
            self.level_bar["value"] = self._level_value * 100.0
            self.level_db_var.set(f"Уровень: {info.db:.1f} dBFS  (peak {info.peak:.2f})")
            self.gate_state_var.set("Gate: тишина (не пишем)" if info.gated else "Gate: сигнал → буфер")
            self.buffer_bar["value"] = info.buffer_fill * 100.0
            self.buffer_pct_var.set(f"Буфер: {info.buffer_fill * 100:.0f}%")

        pending = getattr(self, "_pending_saved", None)
        if pending is not None:
            self._pending_saved = None
            self._log(f"Сохранено: {pending}")
            self.status_var.set(f"Сохранён сегмент: {pending.name}")

        self.root.after(50, self._poll_meters)

    def _log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def on_close(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop(flush=True)
        self.recorder.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MicGrabExtApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
