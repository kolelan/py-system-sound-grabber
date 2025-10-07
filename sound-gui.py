import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import pyaudio
import wave
import sys


class SystemAudioRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Запись системного звука")
        self.root.geometry("600x400")

        self.recording = False
        self.audio = pyaudio.PyAudio()
        self.frames = []
        self.current_stream = None

        self.setup_ui()
        self.refresh_devices()

    def setup_ui(self):
        # Заголовок
        title_label = ttk.Label(self.root, text="Запись системного звука",
                                font=("Arial", 14, "bold"))
        title_label.pack(pady=10)

        # Информационная панель
        info_frame = ttk.Frame(self.root)
        info_frame.pack(fill="x", padx=10, pady=5)

        info_text = """Если устройство 'Stereo Mix' не найдено:
1. Правый клик на значке звука → 'Звуки'
2. Вкладка 'Запись' → Показать отключенные устройства
3. Включите 'Stereo Mix'
ИЛИ
Установите VB-Audio Virtual Cable"""

        info_label = ttk.Label(info_frame, text=info_text, foreground="darkred",
                               wraplength=580, justify="left")
        info_label.pack()

        # Выбор устройства
        device_frame = ttk.LabelFrame(self.root, text="Выбор устройства записи")
        device_frame.pack(fill="x", padx=10, pady=5)

        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=70)
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

        # Качество записи
        ttk.Label(settings_frame, text="Качество:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.quality_var = tk.StringVar(value="Высокое")
        quality_combo = ttk.Combobox(settings_frame, textvariable=self.quality_var,
                                     values=["Низкое", "Среднее", "Высокое"], width=10)
        quality_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # Кнопки управления
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)

        self.record_button = ttk.Button(button_frame, text="Начать запись",
                                        command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT, padx=10)

        ttk.Button(button_frame, text="Тест устройства",
                   command=self.test_device).pack(side=tk.LEFT, padx=10)

        ttk.Button(button_frame, text="Выход", command=self.cleanup_exit).pack(side=tk.LEFT, padx=10)

        # Статус и информация
        self.status_var = tk.StringVar(value="Готов к записи")
        status_label = ttk.Label(self.root, textvariable=self.status_var, foreground="blue")
        status_label.pack(pady=10)

        # Прогресс бар
        self.progress = ttk.Progressbar(self.root, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=5)

        self.info_text = tk.Text(self.root, height=8, width=70)
        self.info_text.pack(padx=10, pady=5, fill="both", expand=True)

    def find_system_audio_devices(self):
        """Найти устройства для записи системного звука"""
        system_devices = []

        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            device_name = device_info['name'].lower()

            # Критерии для системного звука
            is_system_device = (
                    'stereo mix' in device_name or
                    'what you hear' in device_name or
                    'wave out mix' in device_name or
                    'system mixer' in device_name or
                    'virtual cable' in device_name or
                    'loopback' in device_name or
                    'output' in device_name and 'input' not in device_name
            )

            if device_info['maxInputChannels'] > 0:
                if is_system_device:
                    system_devices.insert(0, (i, device_info))  # Добавляем в начало
                else:
                    system_devices.append((i, device_info))

        return system_devices

    def refresh_devices(self):
        """Обновить список устройств"""
        self.info_text.delete(1.0, tk.END)
        devices_list = []

        system_devices = self.find_system_audio_devices()

        if system_devices:
            self.info_text.insert(tk.END, "=== РЕКОМЕНДУЕМЫЕ УСТРОЙСТВА ===\n")
            for i, device_info in system_devices[:3]:  # Первые 3 системных устройства
                devices_list.append(f"{i}: {device_info['name']} [СИСТЕМНЫЙ ЗВУК]")
                self.info_text.insert(tk.END,
                                      f"{i}: {device_info['name']} (каналы: {device_info['maxInputChannels']})\n")

            self.info_text.insert(tk.END, "\n=== ДРУГИЕ УСТРОЙСТВА ===\n")

            # Автоматически выбираем первое системное устройство
            first_device = system_devices[0]
            self.device_var.set(f"{first_device[0]}: {first_device[1]['name']} [СИСТЕМНЫЙ ЗВУК]")

        # Добавляем остальные устройства
        for i, device_info in system_devices:
            if f"{i}: {device_info['name']} [СИСТЕМНЫЙ ЗВУК]" not in devices_list:
                devices_list.append(f"{i}: {device_info['name']}")
                self.info_text.insert(tk.END,
                                      f"{i}: {device_info['name']} (каналы: {device_info['maxInputChannels']})\n")

        self.device_combo['values'] = devices_list

        if not devices_list:
            self.info_text.insert(tk.END, "Устройства записи не найдены!\n")
            self.info_text.insert(tk.END, "Проверьте настройки звука Windows.")

    def choose_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV files", "*.wav"), ("MP3 files", "*.mp3"), ("All files", "*.*")]
        )
        if filename:
            self.filename_var.set(filename)

    def test_device(self):
        """Тестирование выбранного устройства"""
        device_str = self.device_var.get()
        if not device_str:
            messagebox.showwarning("Предупреждение", "Сначала выберите устройство!")
            return

        try:
            device_index = int(device_str.split(":")[0])
            device_info = self.audio.get_device_info_by_index(device_index)

            # Пробуем открыть поток
            test_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=2,
                rate=44100,
                input=True,
                frames_per_buffer=1024,
                input_device_index=device_index
            )

            test_stream.stop_stream()
            test_stream.close()

            messagebox.showinfo("Тест устройства",
                                f"Устройство '{device_info['name']}' работает корректно!\n"
                                f"Каналы: {device_info['maxInputChannels']}\n"
                                f"Частота: {device_info['defaultSampleRate']} Hz")

        except Exception as e:
            messagebox.showerror("Ошибка теста",
                                 f"Устройство не работает:\n{str(e)}")

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
            self.progress['maximum'] = duration
            self.progress['value'] = 0

            thread = threading.Thread(target=self.record_audio,
                                      args=(filename, duration, device_index))
            thread.daemon = True
            thread.start()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Некорректные параметры: {e}")

    def record_audio(self, filename, duration, device_index):
        # Настройки качества
        quality_settings = {
            "Низкое": {"chunk": 512, "rate": 22050},
            "Среднее": {"chunk": 1024, "rate": 44100},
            "Высокое": {"chunk": 2048, "rate": 48000}
        }

        quality = self.quality_var.get()
        settings = quality_settings.get(quality, quality_settings["Высокое"])

        CHUNK = settings["chunk"]
        FORMAT = pyaudio.paInt16
        CHANNELS = 2
        RATE = settings["rate"]

        try:
            self.current_stream = self.audio.open(
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
                    data = self.current_stream.read(CHUNK, exception_on_overflow=False)
                    self.frames.append(data)

                    # Обновляем прогресс
                    elapsed = time.time() - start_time
                    self.root.after(0, lambda: self.progress.config(value=elapsed))

                except Exception as e:
                    self.root.after(0, lambda: self.status_var.set(f"Ошибка: {e}"))
                    break

            self.current_stream.stop_stream()
            self.current_stream.close()
            self.current_stream = None

            # Сохранение файла
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(self.frames))

            file_size = len(b''.join(self.frames)) / 1024 / 1024
            self.root.after(0, lambda: self.status_var.set(
                f"Запись сохранена: {filename} ({file_size:.1f} MB)"))
            self.root.after(0, lambda: self.progress.config(value=0))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка записи",
                                                            f"Ошибка: {str(e)}"))

        self.root.after(0, lambda: self.record_button.config(text="Начать запись"))
        self.recording = False

    def stop_recording(self):
        self.recording = False
        if self.current_stream:
            self.current_stream.stop_stream()
            self.current_stream.close()
            self.current_stream = None
        self.status_var.set("Запись остановлена")

    def cleanup_exit(self):
        """Корректное завершение работы"""
        self.stop_recording()
        if hasattr(self, 'audio'):
            self.audio.terminate()
        self.root.quit()
        self.root.destroy()

    def __del__(self):
        self.cleanup_exit()


if __name__ == "__main__":
    root = tk.Tk()
    app = SystemAudioRecorderGUI(root)


    def on_closing():
        app.cleanup_exit()


    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()