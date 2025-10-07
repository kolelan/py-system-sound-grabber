import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import time


class SystemAudioRecorderSD:
    def __init__(self):
        self.recording = False
        self.audio_data = []
        self.sample_rate = 44100

    def list_devices(self):
        """Показать все аудиоустройства"""
        print("Доступные устройства:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                print(f"{i}: {device['name']} (входные каналы: {device['max_input_channels']})")

    def find_system_output_device(self):
        """Найти устройство для записи системного вывода"""
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            device_name = device['name'].lower()
            # Ищем устройства для записи системного звука
            if (('stereo mix' in device_name or
                 'what you hear' in device_name or
                 'loopback' in device_name or
                 'virtual cable' in device_name) and
                    device['max_input_channels'] > 0):
                return i
        return None

    def start_recording(self, filename="system_audio.wav", duration=30):
        """Начать запись системного звука"""
        device_index = self.find_system_output_device()

        if device_index is None:
            print("Устройство для записи системного звука не найдено!")
            self.list_devices()
            print("\nПопробуйте использовать одно из перечисленных устройств")
            return

        self.recording = True
        self.audio_data = []

        def callback(indata, frames, time, status):
            if status:
                print(f"Статус: {status}")
            if self.recording:
                self.audio_data.append(indata.copy())

        print(f"Запись системного звука начата... Длительность: {duration} секунд")
        print(f"Используется устройство: {sd.query_devices(device_index)['name']}")

        try:
            with sd.InputStream(device=device_index,
                                channels=2,
                                samplerate=self.sample_rate,
                                callback=callback,
                                blocksize=1024):

                start_time = time.time()
                while self.recording and (time.time() - start_time) < duration:
                    time.sleep(0.1)

                # Сохранение записи
                if self.audio_data:
                    audio_array = np.concatenate(self.audio_data, axis=0)
                    sf.write(filename, audio_array, self.sample_rate)
                    print(f"Системный звук сохранен в файл: {filename}")
                    print(f"Размер данных: {audio_array.nbytes / 1024 / 1024:.2f} MB")

        except Exception as e:
            print(f"Ошибка записи: {e}")

    def stop_recording(self):
        """Остановить запись"""
        self.recording = False


# Пример использования
if __name__ == "__main__":
    recorder = SystemAudioRecorderSD()
    recorder.start_recording("system_recording_sd.wav", duration=30)