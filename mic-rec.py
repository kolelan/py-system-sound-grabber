import pyaudio
import wave
import keyboard  # pip install keyboard


def record_from_microphone(filename="microphone_recording.wav", duration=10):
    """
    Запись звука с микрофона
    """
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    audio = pyaudio.PyAudio()

    # Получить список доступных устройств
    print("Доступные аудиоустройства:")
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        print(f"{i}: {device_info['name']} (входов: {device_info['maxInputChannels']})")

    # Открыть поток для записи
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("Запись начата... Нажмите пробел для остановки")
    print(f"Или запись автоматически остановится через {duration} секунд")

    frames = []

    try:
        start_time = time.time()
        while True:
            # Проверка времени записи
            if time.time() - start_time > duration:
                break

            # Проверка нажатия пробела
            if keyboard.is_pressed('space'):
                break

            data = stream.read(CHUNK)
            frames.append(data)

    except KeyboardInterrupt:
        print("\nЗапись прервана пользователем")

    # Остановка записи
    stream.stop_stream()
    stream.close()
    audio.terminate()

    # Сохранение в файл
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    print(f"Запись сохранена в файл: {filename}")


if __name__ == "__main__":
    import time

    record_from_microphone("mic_recording.wav", duration=15)