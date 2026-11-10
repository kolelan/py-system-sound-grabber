#!/usr/bin/env python3
"""GUI: запись системного звука через WASAPI loopback."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from recorder import LoopbackDevice, RecorderError, SystemAudioRecorder


def format_time(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


class GrabApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Запись системного звука (WASAPI)")
        self.root.geometry("560x360")

        self.recorder = SystemAudioRecorder()
        self.devices: list[LoopbackDevice] = []
        self._tick_job: str | None = None

        self.device_var = tk.StringVar()
        self.filename_var = tk.StringVar(value="system_recording.wav")
        self.duration_var = tk.StringVar(value="")  # пусто = до стопа
        self.status_var = tk.StringVar(value="Готов к записи")
        self.timer_var = tk.StringVar(value="Время: 00:00")

        self._build_ui()
        self.refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        title = ttk.Label(self.root, text="WASAPI loopback", font=("Segoe UI", 14, "bold"))
        title.pack(pady=(12, 4))

        hint = ttk.Label(
            self.root,
            text="Пишет то, что играет сейчас. Stereo Mix не нужен.",
            foreground="#444",
        )
        hint.pack(pady=(0, 8))

        device_frame = ttk.LabelFrame(self.root, text="Устройство вывода (loopback)")
        device_frame.pack(fill="x", padx=12, pady=6)
        self.device_combo = ttk.Combobox(
            device_frame, textvariable=self.device_var, state="readonly", width=70
        )
        self.device_combo.pack(side=tk.LEFT, padx=6, pady=6, fill="x", expand=True)
        ttk.Button(device_frame, text="Обновить", command=self.refresh_devices).pack(
            side=tk.RIGHT, padx=6, pady=6
        )

        settings = ttk.LabelFrame(self.root, text="Файл")
        settings.pack(fill="x", padx=12, pady=6)
        ttk.Label(settings, text="WAV:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Entry(settings, textvariable=self.filename_var, width=42).grid(
            row=0, column=1, padx=6, pady=6, sticky="we"
        )
        ttk.Button(settings, text="Обзор…", command=self.choose_file).grid(
            row=0, column=2, padx=6, pady=6
        )
        ttk.Label(settings, text="Лимит, сек (пусто = вручную):").grid(
            row=1, column=0, padx=6, pady=6, sticky="w"
        )
        ttk.Entry(settings, textvariable=self.duration_var, width=10).grid(
            row=1, column=1, padx=6, pady=6, sticky="w"
        )
        settings.columnconfigure(1, weight=1)

        controls = ttk.Frame(self.root)
        controls.pack(pady=12)
        self.start_btn = ttk.Button(controls, text="▶ Старт", command=self.start_recording)
        self.start_btn.pack(side=tk.LEFT, padx=4)
        self.pause_btn = ttk.Button(
            controls, text="⏸ Пауза", command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side=tk.LEFT, padx=4)
        self.stop_btn = ttk.Button(
            controls, text="⏹ Стоп", command=self.stop_recording, state="disabled"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=4)

        ttk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack()
        ttk.Label(self.root, textvariable=self.timer_var).pack(pady=4)

    def refresh_devices(self) -> None:
        try:
            self.devices = self.recorder.list_devices()
            default = self.recorder.get_default_device()
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            self.devices = []
            self.device_combo["values"] = []
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

    def choose_file(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV", "*.wav"), ("Все файлы", "*.*")],
        )
        if path:
            self.filename_var.set(path)

    def _selected_device_index(self) -> int | None:
        selected = self.device_var.get()
        if not selected:
            return None
        return int(selected.split(":", 1)[0])

    def start_recording(self) -> None:
        duration_raw = self.duration_var.get().strip()
        duration = float(duration_raw) if duration_raw else None
        if duration is not None and duration <= 0:
            messagebox.showerror("Ошибка", "Длительность должна быть > 0")
            return

        try:
            device = self.recorder.start(
                output_path=self.filename_var.get(),
                device_index=self._selected_device_index(),
                duration=duration,
            )
        except RecorderError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректная длительность")
            return

        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="⏸ Пауза")
        self.stop_btn.config(state="normal")
        self.status_var.set(f"Запись: {device.name}")
        self._schedule_tick()

    def toggle_pause(self) -> None:
        if not self.recorder.is_recording:
            return
        if self.recorder.is_paused:
            self.recorder.resume()
            self.pause_btn.config(text="⏸ Пауза")
            self.status_var.set("Запись продолжена")
        else:
            self.recorder.pause()
            self.pause_btn.config(text="▶ Продолжить")
            self.status_var.set("Пауза")

    def stop_recording(self) -> None:
        path = self.recorder.stop()
        self._cancel_tick()
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="⏸ Пауза")
        self.stop_btn.config(state="disabled")
        self.timer_var.set("Время: 00:00")

        if self.recorder.last_error:
            messagebox.showerror("Ошибка записи", str(self.recorder.last_error))
            self.status_var.set("Ошибка записи")
            return

        if path and path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            self.status_var.set(f"Сохранено: {Path(path).name} ({size_mb:.1f} MB)")
        else:
            self.status_var.set("Запись остановлена")

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        self._tick()

    def _tick(self) -> None:
        if not self.recorder.is_recording:
            # поток сам завершился по duration
            if self.recorder.output_path:
                self.stop_recording()
            return

        limit = self.duration_var.get().strip()
        elapsed = self.recorder.elapsed
        if limit:
            self.timer_var.set(f"Время: {format_time(elapsed)} / {format_time(float(limit))}")
        else:
            self.timer_var.set(f"Время: {format_time(elapsed)}")
        self._tick_job = self.root.after(200, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None

    def on_close(self) -> None:
        self._cancel_tick()
        self.recorder.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GrabApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
