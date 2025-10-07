import pyaudio
import wave
import threading
import time


class SystemAudioRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio = pyaudio.PyAudio()

    def find_stereo_mix_device(self):
        """Найти устройство Stereo Mix"""
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            device_name = device_info['name'].lower()
            # Ищем устройства с названиями, указывающими на системный звук
            if ('stereo mix' in device_name or
                    'what you hear' in device_name or
                    'wave out mix' in device_name or
                    'system audio' in device_name):
                print(f"Найдено устройство для записи системного звука: {device_info['name']}")
                return i
        return None

    def start_recording(self, filename="system_audio.wav", duration=30):
        """Начать запись системного звука"""
        self.recording = True
        self.frames = []

        # Параметры записи
        format = pyaudio.paInt16
        channels = 2
        rate = 44100
        chunk = 1024

        # Поиск устройства Stereo Mix
        device_index = self.find_stereo_mix_device()

        if device_index is None:
            print("Устройство Stereo Mix не найдено!")
            print("Доступные устройства:")
            for i in range(self.audio.get_device_count()):
                device_info = self.audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    print(f"{i}: {device_info['name']} (входные каналы: {device_info['maxInputChannels']})")
            return

        try:
            stream = self.audio.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk,
                input_device_index=device_index
            )

            print(f"Запись системного звука начата... Длительность: {duration} секунд")

            def record():
                start_time = time.time()
                while self.recording and (time.time() - start_time) < duration:
                    try:
                        data = stream.read(chunk, exception_on_overflow=False)
                        self.frames.append(data)
                    except Exception as e:
                        print(f"Ошибка чтения: {e}")
                        break

                stream.stop_stream()
                stream.close()
                self.save_recording(filename, format, channels, rate)

            record_thread = threading.Thread(target=record)
            record_thread.start()

        except Exception as e:
            print(f"Ошибка при записи: {e}")

    def stop_recording(self):
        """Остановить запись"""
        self.recording = False

    def save_recording(self, filename, format, channels, rate):
        """Сохранить запись в файл"""
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(self.audio.get_sample_size(format))
            wf.setframerate(rate)
            wf.writeframes(b''.join(self.frames))

        print(f"Системный звук сохранен в файл: {filename}")
        print(f"Размер файла: {len(b''.join(self.frames)) / 1024 / 1024:.2f} MB")

    def __del__(self):
        self.audio.terminate()


# Пример использования
if __name__ == "__main__":
    recorder = SystemAudioRecorder()

    print("Запуск записи системного звука на 30 секунд...")
    recorder.start_recording("system_recording.wav", duration=30)

    input("Нажмите Enter для досрочной остановки записи...\n")
    recorder.stop_recording()