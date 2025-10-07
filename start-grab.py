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
        self.root.geometry("600x450")

        self.recording = False
        self.paused = False  # Добавлено инициализация paused
        self.audio = pyaudio.PyAudio()
        self.frames = []
        self.current_stream = None
        self.record_thread = None

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

        # Панель управления записью
        control_frame = ttk.LabelFrame(self.root, text="Управление записью")
        control_frame.pack(fill="x", padx=10, pady=10)

        # Кнопки управления в отдельном фрейме
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(pady=10)

        # Основные кнопки управления записью
        self.start_button = ttk.Button(button_frame, text="▶ Старт записи",
                                       command=self.start_recording,
                                       state="normal")
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(button_frame, text="⏹ Стоп",
                                      command=self.stop_recording,
                                      state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.pause_button = ttk.Button(button_frame, text="⏸ Пауза",
                                       command=self.pause_recording,
                                       state="disabled")
        self.pause_button.pack(side=tk.LEFT, padx=5)

        # Дополнительные кнопки
        util_frame = ttk.Frame(control_frame)
        util_frame.pack(pady=5)

        ttk.Button(util_frame, text="Тест устройства",
                   command=self.test_device).pack(side=tk.LEFT, padx=5)

        ttk.Button(util_frame, text="Просмотр папки",
                   command=self.open_folder).pack(side=tk.LEFT, padx=5)

        ttk.Button(util_frame, text="Выход", command=self.cleanup_exit).pack(side=tk.LEFT, padx=5)

        # Статус и информация
        self.status_var = tk.StringVar(value="Готов к записи")
        status_label = ttk.Label(self.root, textvariable=self.status_var,
                                 font=("Arial", 10, "bold"), foreground="blue")
        status_label.pack(pady=5)

        # Таймер записи
        self.timer_var = tk.StringVar(value="Время: 00:00 / 00:00")
        timer_label = ttk.Label(self.root, textvariable=self.timer_var,
                                font=("Arial", 9), foreground="green")
        timer_label.pack()

        # Прогресс бар
        self.progress = ttk.Progressbar(self.root, orient='horizontal', length=500, mode='determinate')
        self.progress.pack(pady=5, fill="x", padx=10)

        # Информационное текстовое поле
        self.info_text = tk.Text(self.root, height=8, width=70)
        self.info_text.pack(padx=10, pady=5, fill="both", expand=True)

        # Добавляем скроллбар для текстового поля
        scrollbar = ttk.Scrollbar(self.info_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.info_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.info_text.yview)

    def update_timer(self, elapsed, total):
        """Обновление таймера записи"""
        elapsed_min = int(elapsed // 60)
        elapsed_sec = int(elapsed % 60)
        total_min = int(total // 60)
        total_sec = int(total % 60)

        self.timer_var.set(f"Время: {elapsed_min:02d}:{elapsed_sec:02d} / {total_min:02d}:{total_sec:02d}")

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
            if system_devices:  # Добавлена проверка на пустой список
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
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")]
        )
        if filename:
            self.filename_var.set(filename)

    def open_folder(self):
        """Открыть папку с записанными файлами"""
        import os
        import subprocess
        current_dir = os.getcwd()
        try:
            if os.name == 'nt':  # Windows
                os.startfile(current_dir)
            else:  # MacOS, Linux
                subprocess.run(['open', current_dir] if sys.platform == 'darwin' else ['xdg-open', current_dir])
        except Exception as e:
            messagebox.showwarning("Предупреждение", f"Не удалось открыть папку: {e}")

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

    def start_recording(self):
        """Начать запись"""
        try:
            duration = int(self.duration_var.get())
            filename = self.filename_var.get()
            device_str = self.device_var.get()

            if not device_str:
                messagebox.showerror("Ошибка", "Выберите устройство записи!")
                return

            device_index = int(device_str.split(":")[0])

            self.recording = True
            self.paused = False  # Сбрасываем паузу при старте
            self.frames = []

            # Обновляем состояние кнопок
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.pause_button.config(state="normal")

            self.status_var.set("🔴 Идет запись системного звука...")
            self.progress['maximum'] = duration
            self.progress['value'] = 0
            self.timer_var.set(f"Время: 00:00 / {int(duration // 60):02d}:{int(duration % 60):02d}")

            # Запускаем запись в отдельном потоке
            self.record_thread = threading.Thread(target=self.record_audio,
                                                  args=(filename, duration, device_index))
            self.record_thread.daemon = True
            self.record_thread.start()

        except ValueError as e:
            messagebox.showerror("Ошибка", f"Некорректные параметры: {e}")

    def pause_recording(self):
        """Пауза/продолжение записи"""
        if self.paused:
            # Продолжить запись
            self.paused = False
            self.pause_button.config(text="⏸ Пауза")
            self.status_var.set("🔴 Идет запись системного звука...")
        else:
            # Поставить на паузу
            self.paused = True
            self.pause_button.config(text="▶ Продолжить")
            self.status_var.set("⏸ Запись на паузе")

    def stop_recording(self):
        """Остановить запись"""
        self.recording = False
        self.paused = False

        # Обновляем состояние кнопок
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.pause_button.config(state="disabled")
        self.pause_button.config(text="⏸ Пауза")

        self.status_var.set("Запись остановлена")
        self.progress['value'] = 0
        self.timer_var.set("Время: 00:00 / 00:00")

    def record_audio(self, filename, duration, device_index):
        """Поток записи аудио"""
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
                    # Проверка паузы
                    if self.paused:
                        time.sleep(0.1)
                        continue

                    data = self.current_stream.read(CHUNK, exception_on_overflow=False)
                    self.frames.append(data)

                    # Обновляем прогресс и таймер
                    elapsed = time.time() - start_time
                    # Исправлено: передаем переменные как параметры лямбда-функций
                    self.root.after(0, lambda e=elapsed: self.progress.config(value=e))
                    self.root.after(0, lambda e=elapsed, d=duration: self.update_timer(e, d))

                except Exception as e:
                    # Исправлено: передаем ошибку как параметр
                    error_msg = str(e)
                    self.root.after(0, lambda msg=error_msg: self.status_var.set(f"Ошибка: {msg}"))
                    break

            # Завершение записи
            if self.current_stream:
                self.current_stream.stop_stream()
                self.current_stream.close()
                self.current_stream = None

            # Сохранение файла только если есть данные
            if self.frames and self.recording:
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(self.audio.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b''.join(self.frames))

                file_size = len(b''.join(self.frames)) / 1024 / 1024
                # Исправлено: передаем переменные как параметры
                self.root.after(0, lambda f=filename, fs=file_size: self.status_var.set(
                    f"✅ Запись сохранена: {f} ({fs:.1f} MB)"))

        except Exception as e:
            # Исправлено: передаем ошибку как параметр
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("Ошибка записи", f"Ошибка: {msg}"))

        # Восстановление интерфейса
        self.root.after(0, self.stop_recording)

    def cleanup_exit(self):
        """Корректное завершение работы"""
        self.stop_recording()
        # Ждем завершения потока записи
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=1.0)
        if hasattr(self, 'audio'):
            self.audio.terminate()
        self.root.quit()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SystemAudioRecorderGUI(root)

    def on_closing():
        app.cleanup_exit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()