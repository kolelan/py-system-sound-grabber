import pyaudio
import wave
import threading
import time


class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio = pyaudio.PyAudio()

    def start_recording(self, filename="output.wav", duration=10):
        """Начать запись звука"""
        self.recording = True
        self.frames = []

        # Параметры записи
        format = pyaudio.paInt16
        channels = 2
        rate = 44100
        chunk = 1024

        try:
            # Попытка открыть поток для записи системного звука
            # Для Windows может потребоваться установка дополнительных драйверов
            stream = self.audio.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk,
                input_device_index=None  # Использовать устройство по умолчанию
            )

            print(f"Начата запись... Длительность: {duration} секунд")

            # Запись в отдельном потоке
            def record():
                start_time = time.time()
                while self.recording and (time.time() - start_time) < duration:
                    data = stream.read(chunk)
                    self.frames.append(data)

                stream.stop_stream()
                stream.close()

                # Сохранение в файл
                self.save_recording(filename, format, channels, rate)

            record_thread = threading.Thread(target=record)
            record_thread.start()

        except Exception as e:
            print(f"Ошибка при записи: {e}")
            print("Возможно, требуется установить дополнительные драйверы для записи системного звука")

    def stop_recording(self):
        """Остановить запись"""
        self.recording = False

    def save_recording(self, filename, format, channels, rate):
        """Сохранить запись в WAV файл"""
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(self.audio.get_sample_size(format))
            wf.setframerate(rate)
            wf.writeframes(b''.join(self.frames))

        print(f"Запись сохранена в файл: {filename}")

    def __del__(self):
        self.audio.terminate()


# Пример использования
if __name__ == "__main__":
    recorder = AudioRecorder()

    # Запись в течение 10 секунд
    recorder.start_recording("my_recording.wav", duration=10)

    # Ждем завершения записи
    input("Нажмите Enter для остановки записи...")
    recorder.stop_recording()