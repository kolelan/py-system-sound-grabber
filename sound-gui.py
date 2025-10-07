import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import pyaudio
import wave


class SystemAudioRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Запись системного звука")
        self.root.geometry("500x350")

        self.recording = False
        self.audio = pyaudio.PyAudio()
        self.frames = []

        self.setup_ui()
        self.refresh_devices()

    def setup_ui(self):
        # Заголовок
        title_label = ttk.Label(self.root, text="Запись системного звука",
                                font=("Arial", 14, "bold"))
        title_label.pack(pady=10)

        # Выбор устройства
        device_frame = ttk.LabelFrame(self.root, text="Выбор устройства записи")
        device_frame.pack(fill="x", padx=10, pady=5)

        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=60)
        self.device_combo.pack(padx=5, pady=5)

        ttk.Button(device_frame, text="Обновить список",
                   command=self.refresh_devices).pack(pady=5)

        # Настройки записи
        settings_frame = ttk.LabelFrame(self.root, text="Настройки записи")
        settings_frame.pack(fill="x", padx=10, pady=5)

        # Имя файла
        ttk.Label(settings_frame, text="Имя файла:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.filename_var = tk.StringVar(value="system_recording.wav")
        filename_entry = ttk.Entry(settings_frame, textvariable=self.filename_var, width=30)
        filename_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="Обзор", command=self.choose_file).grid(row=0, column=2, padx=5)

        # Длительность
        ttk.Label(settings_frame, text="Длительность (секунды):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.duration_var = tk.StringVar(value="30")
        duration_entry = ttk.Entry(settings_frame, textvariable=self.duration_var, width=10)
        duration_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Кнопки управления
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)

        self.record_button = ttk.Button(button_frame, text="Начать запись",
                                        command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT, padx=10)

        ttk.Button(button_frame, text="Выход", command=self.root.quit).pack(side=tk.LEFT, padx=10)

        # Статус и информация
        self.status_var = tk.StringVar(value="Готов к записи")
        status_label = ttk.Label(self.root, textvariable=self.status_var, foreground="blue")
        status_label.pack(pady=10)

        self.info_text = tk.Text(self.root, height=6, width=60)
        self.info_text.pack(padx=10, pady=5, fill="both", expand=True)

    def refresh_devices(self):
        """Обновить список устройств"""
        self.info_text.delete(1.0, tk.END)
        devices = []

        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                device_name = device_info['name']
                devices.append(f"{i}: {device_name}")

                # Автоматически выбираем Stereo Mix если найден
                if 'stereo mix' in device_name.lower():
                    self.device_var.set(f"{i}: {device_name}")

        self.device_combo['values'] = devices
        self.info_text.insert(tk.END, "\n".join(devices))

    def choose_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")]
        )
        if filename:
            self.filename_var.set(filename)

    def toggle_recording(self):
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        try:
            duration = int(self.duration_var.get())
            filename = self.filename_var.get()
            device_str = self.device_var.get()

            if not device_str:
                messagebox.showerror("Ошибка", "Выберите устройство записи!")
                return

            device_index = int(device_str.split(":")[0])

            self.recording = True
            self.frames = []
            self.record_button.config(text="Остановить запись")
            self.status_var.set("Идет запись системного звука...")

            thread = threading.Thread(target=self.record_audio,
                                      args=(filename, duration, device_index))
            thread.daemon = True
            thread.start()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Некорректные параметры: {e}")

    def record_audio(self, filename, duration, device_index):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 2
        RATE = 44100

        try:
            stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=device_index
            )

            start_time = time.time()
            while self.recording and (time.time() - start_time) < duration:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    self.frames.append(data)
                except Exception as e:
                    self.root.after(0, lambda: self.status_var.set(f"Ошибка: {e}"))
                    break

            stream.stop_stream()
            stream.close()

            # Сохранение файла
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(self.frames))

            self.root.after(0, lambda: self.status_var.set(f"Запись сохранена: {filename}"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка записи: {e}"))

        self.root.after(0, lambda: self.record_button.config(text="Начать запись"))
        self.recording = False

    def stop_recording(self):
        self.recording = False
        self.status_var.set("Запись остановлена")

    def __del__(self):
        if hasattr(self, 'audio'):
            self.audio.terminate()


if __name__ == "__main__":
    root = tk.Tk()
    app = SystemAudioRecorderGUI(root)
    root.mainloop()