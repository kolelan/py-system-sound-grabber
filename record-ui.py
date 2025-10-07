import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyaudio
import wave
import threading
import time


class AudioRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Запись звука")
        self.root.geometry("400x200")

        self.recording = False
        self.audio = pyaudio.PyAudio()
        self.frames = []

        self.setup_ui()

    def setup_ui(self):
        # Поле для имени файла
        ttk.Label(self.root, text="Имя файла:").pack(pady=5)
        self.filename_var = tk.StringVar(value="recording.wav")
        filename_entry = ttk.Entry(self.root, textvariable=self.filename_var, width=40)
        filename_entry.pack(pady=5)

        # Кнопка выбора файла
        ttk.Button(self.root, text="Выбрать файл", command=self.choose_file).pack(pady=5)

        # Поле для длительности
        ttk.Label(self.root, text="Длительность (секунды):").pack(pady=5)
        self.duration_var = tk.StringVar(value="10")
        duration_entry = ttk.Entry(self.root, textvariable=self.duration_var, width=10)
        duration_entry.pack(pady=5)

        # Кнопки управления
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)

        self.record_button = ttk.Button(button_frame, text="Начать запись", command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT, padx=10)

        ttk.Button(button_frame, text="Выход", command=self.root.quit).pack(side=tk.LEFT, padx=10)

        # Статус
        self.status_var = tk.StringVar(value="Готов к записи")
        status_label = ttk.Label(self.root, textvariable=self.status_var)
        status_label.pack(pady=10)

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

            self.recording = True
            self.frames = []
            self.record_button.config(text="Остановить запись")
            self.status_var.set("Идет запись...")

            # Запуск записи в отдельном потоке
            thread = threading.Thread(target=self.record_audio, args=(filename, duration))
            thread.daemon = True
            thread.start()

        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректную длительность")

    def stop_recording(self):
        self.recording = False
        self.record_button.config(text="Начать запись")
        self.status_var.set("Запись остановлена")

    def record_audio(self, filename, duration):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100

        try:
            stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )

            start_time = time.time()
            while self.recording and (time.time() - start_time) < duration:
                data = stream.read(CHUNK)
                self.frames.append(data)

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

    def __del__(self):
        if hasattr(self, 'audio'):
            self.audio.terminate()


if __name__ == "__main__":
    root = tk.Tk()
    app = AudioRecorderGUI(root)
    root.mainloop()