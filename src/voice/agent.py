import asyncio
import audioop
import base64
import builtins
import os
import subprocess
import tempfile
import speech_recognition as sr

WINDOWS_LOW_LEVEL_AUDIO_APIS = ("wdm-ks",)
WINDOWS_INPUT_ALIAS_NAMES = (
    "microsoft sound mapper",
    "primary sound capture driver",
    "primary sound driver",
)
NON_MIC_INPUT_NAMES = ("stereo mix", "speakers", "headphones", "output")


def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        new_args = []
        for arg in args:
            if isinstance(arg, str):
                new_args.append(arg.encode('ascii', errors='backslashreplace').decode('ascii'))
            else:
                new_args.append(arg)
        try:
            builtins.print(*new_args, **kwargs)
        except Exception:
            pass

print = safe_print

# Optional dependencies, catch import errors gracefully
try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import pygame
    pygame.mixer.init()
except Exception:
    pygame = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


class AsyncVoiceAgent:
    def __init__(self, language: str = "vi-VN"):
        self.language = language
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self._microphone = None
        self.microphone_index = None
        self.is_calibrated = False

    @property
    def microphone(self):
        if self._microphone is None:
            self._microphone = sr.Microphone(
                device_index=self._get_effective_microphone_index()
            )
        return self._microphone

    def set_microphone_index(self, index):
        self.microphone_index = index
        self._microphone = None
        self.is_calibrated = False

    def _get_effective_microphone_index(self):
        if self.microphone_index is not None:
            return self.microphone_index
        return self.get_default_microphone_index()

    @staticmethod
    def _clean_microphone_name(name):
        return " ".join(str(name or "").replace("\r", " ").replace("\n", " ").split())

    @staticmethod
    def _get_host_api_name(audio, host_api_index):
        try:
            return audio.get_host_api_info_by_index(host_api_index).get("name", "")
        except Exception:
            return ""

    @classmethod
    def _is_user_selectable_input(cls, device):
        name = cls._clean_microphone_name(device.get("name", ""))
        lowered_name = name.lower()
        if not name or int(device.get("maxInputChannels", 0)) <= 0:
            return False
        if any(alias in lowered_name for alias in WINDOWS_INPUT_ALIAS_NAMES):
            return False
        if any(alias in lowered_name for alias in NON_MIC_INPUT_NAMES):
            return False
        return True

    @classmethod
    def _input_devices_from_audio(cls, audio):
        devices = []
        for index in range(audio.get_device_count()):
            info = dict(audio.get_device_info_by_index(index))
            info["index"] = int(info.get("index", index))
            info["name"] = cls._clean_microphone_name(
                info.get("name", f"Microphone {index}")
            )
            info["hostApiName"] = cls._get_host_api_name(audio, info.get("hostApi"))
            if cls._is_user_selectable_input(info):
                devices.append(info)
        return devices

    @staticmethod
    def _prefer_host_api(devices):
        if not devices:
            return []

        wasapi_devices = [
            device
            for device in devices
            if "wasapi" in device.get("hostApiName", "").lower()
        ]
        if wasapi_devices:
            return wasapi_devices

        high_level_devices = [
            device
            for device in devices
            if not any(
                api in device.get("hostApiName", "").lower()
                for api in WINDOWS_LOW_LEVEL_AUDIO_APIS
            )
        ]
        return high_level_devices or devices

    @classmethod
    def _dedupe_devices(cls, devices):
        seen = set()
        unique = []
        for device in devices:
            key = cls._clean_microphone_name(device.get("name", "")).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(device)
        return unique

    @staticmethod
    def list_microphones():
        try:
            import pyaudio

            audio = pyaudio.PyAudio()
            try:
                devices = AsyncVoiceAgent._input_devices_from_audio(audio)
                devices = AsyncVoiceAgent._prefer_host_api(devices)
                devices = AsyncVoiceAgent._dedupe_devices(devices)
                return [
                    (device["index"], device["name"])
                    for device in devices
                ]
            finally:
                audio.terminate()
        except Exception as e:
            print(f"Failed to list microphones: {e}")
            try:
                return [
                    (index, name)
                    for index, name in enumerate(sr.Microphone.list_microphone_names())
                    if name and not any(
                        alias in name.lower()
                        for alias in (*WINDOWS_INPUT_ALIAS_NAMES, *NON_MIC_INPUT_NAMES)
                    )
                ]
            except Exception:
                return []

    @classmethod
    def get_default_microphone_info(cls):
        try:
            import pyaudio

            audio = pyaudio.PyAudio()
            try:
                info = audio.get_default_input_device_info()
                if int(info.get("maxInputChannels", 0)) > 0 and cls._is_user_selectable_input(info):
                    return (
                        int(info["index"]),
                        cls._clean_microphone_name(info.get("name", "")),
                    )
            finally:
                audio.terminate()
        except Exception as e:
            print(f"Failed to resolve default microphone: {e}")
        devices = cls.list_microphones()
        if devices:
            return devices[0]
        return None

    @classmethod
    def get_default_microphone_index(cls):
        info = cls.get_default_microphone_info()
        if info is not None:
            return info[0]
        return None

    @classmethod
    def get_microphone_label(cls, index=None):
        if index is None:
            default_info = cls.get_default_microphone_info()
            if default_info is not None:
                device_index, name = default_info
                return f"Mic {device_index}: {name}"
            return "micro mặc định hệ thống"

        for device_index, name in cls.list_microphones():
            if device_index == index:
                return f"Mic {device_index}: {name}"
        return f"Mic {index}"

    async def calibrate(self):
        """Calibrates the microphone for ambient noise in a non-blocking executor."""
        if not self.is_calibrated:
            def _calibrate():
                try:
                    with self.microphone as source:
                        print("Calibrating microphone for ambient noise (1s)...")
                        self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                except Exception as e:
                    print(f"Calibration warning/error: {e}")

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _calibrate)
            self.is_calibrated = True

    async def listen(self, log_callback=None) -> str:
        """Listens to microphone and performs Speech-to-Text (STT) for Vietnamese."""
        audio_data = await self.record_audio(log_callback=log_callback)
        if audio_data is None:
            return ""

        loop = asyncio.get_running_loop()
        try:
            if log_callback:
                await log_callback("Đang nhận diện giọng nói...")

            def _recognize(audio):
                return self.recognizer.recognize_google(audio, language=self.language)

            text = await loop.run_in_executor(None, _recognize, audio_data)
            print(f"Recognized STT: {text}")
            return text

        except sr.UnknownValueError:
            print("Could not understand audio.")
            if log_callback:
                await log_callback("Không thể nhận diện được giọng nói.")
            return ""
        except Exception as e:
            print(f"STT Error: {e}")
            if log_callback:
                await log_callback(f"Lỗi STT: {str(e)}")
            return ""

    async def record_audio(self, log_callback=None):
        """Records a microphone utterance without running local STT."""
        if log_callback:
            await log_callback("Đang chuẩn bị micro...")
            await log_callback(f"Micro đang dùng: {self.get_microphone_label(self._get_effective_microphone_index())}")
        
        try:
            await self.calibrate()
        except Exception as e:
            if log_callback:
                await log_callback(f"Lỗi calibrate micro: {e}")

        def _record():
            with self.microphone as source:
                print("Listening...")
                audio = self.recognizer.listen(source, timeout=8, phrase_time_limit=10)
                return audio

        loop = asyncio.get_running_loop()
        try:
            if log_callback:
                await log_callback("Đang lắng nghe giọng nói...")
            return await loop.run_in_executor(None, _record)

        except sr.WaitTimeoutError:
            print("Listening timed out.")
            if log_callback:
                await log_callback("Hết thời gian lắng nghe (không có âm thanh).")
            return None
        except Exception as e:
            print(f"Recording Error: {e}")
            if log_callback:
                await log_callback(f"Lỗi ghi âm: {str(e)}")
            return None

    @staticmethod
    def _convert_microphone_chunk(
        pcm_bytes: bytes,
        sample_width: int,
        input_rate: int,
        input_channels: int,
        output_rate: int,
        rate_state=None,
    ):
        if input_channels == 2:
            pcm_bytes = audioop.tomono(pcm_bytes, sample_width, 0.5, 0.5)
        elif input_channels != 1:
            raise ValueError("Only mono or stereo microphone input is supported")
        if input_rate != output_rate:
            pcm_bytes, rate_state = audioop.ratecv(
                pcm_bytes,
                sample_width,
                1,
                input_rate,
                output_rate,
                rate_state,
            )
        return pcm_bytes, rate_state

    async def stream_microphone_pcm_frames(
        self,
        sample_rate: int,
        frame_duration_ms: int,
        log_callback=None,
        sample_width: int = 2,
        channels: int = 1,
        listen_timeout: float = 8.0,
        phrase_time_limit: float = 10.0,
        silence_duration: float = 1.0,
        stop_event: asyncio.Event | None = None,
    ):
        """Streams microphone PCM frames directly for XiaoZhi, without local STT."""
        if sample_width != 2:
            raise ValueError("Only 16-bit PCM microphone streaming is supported")
        if channels != 1:
            raise ValueError("Only mono microphone streaming is supported")

        try:
            import pyaudio
        except ImportError as exc:
            raise RuntimeError("PyAudio is required for XiaoZhi microphone streaming") from exc

        if log_callback:
            await log_callback("Preparing microphone stream for XiaoZhi...")
            await log_callback(
                f"Microphone in use: {self.get_microphone_label(self._get_effective_microphone_index())}"
            )

        frame_samples = max(1, int(sample_rate * frame_duration_ms / 1000))
        frame_bytes = frame_samples * sample_width
        audio = pyaudio.PyAudio()
        stream = None
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        speech_started_at = None
        silence_started_at = None
        threshold = max(300, int(self.recognizer.energy_threshold))
        noise_samples = []
        pending_pcm = b""
        rate_state = None

        try:
            device_index = self._get_effective_microphone_index()
            if device_index is None:
                device_info = audio.get_default_input_device_info()
            else:
                device_info = audio.get_device_info_by_index(device_index)
            native_rate = max(1, int(float(device_info.get("defaultSampleRate", sample_rate))))
            native_channels = max(1, min(2, int(device_info.get("maxInputChannels", 1))))
            candidates = []
            for candidate in (
                (native_rate, native_channels),
                (native_rate, 1),
                (sample_rate, channels),
            ):
                if candidate not in candidates:
                    candidates.append(candidate)

            open_errors = []
            input_rate = sample_rate
            input_channels = channels
            for input_rate, input_channels in candidates:
                input_frame_samples = max(
                    1, int(input_rate * frame_duration_ms / 1000)
                )
                try:
                    stream = audio.open(
                        format=pyaudio.paInt16,
                        channels=input_channels,
                        rate=input_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=input_frame_samples,
                    )
                    break
                except Exception as exc:
                    open_errors.append(
                        f"{input_rate}Hz/{input_channels}ch: {exc}"
                    )
            if stream is None:
                raise RuntimeError("; ".join(open_errors))

            if log_callback:
                await log_callback(
                    "Streaming microphone audio to XiaoZhi: "
                    f"device={input_rate}Hz/{input_channels}ch -> "
                    f"protocol={sample_rate}Hz/{channels}ch, frame={frame_duration_ms}ms"
                )

            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                now = loop.time()
                if speech_started_at is None and now - started_at >= listen_timeout:
                    return
                if speech_started_at is not None and now - speech_started_at >= phrase_time_limit:
                    return

                raw_chunk = await asyncio.to_thread(
                    stream.read,
                    input_frame_samples,
                    exception_on_overflow=False,
                )
                raw_chunk, rate_state = self._convert_microphone_chunk(
                    raw_chunk,
                    sample_width,
                    input_rate,
                    input_channels,
                    sample_rate,
                    rate_state,
                )
                pending_pcm += raw_chunk

                while len(pending_pcm) >= frame_bytes:
                    chunk = pending_pcm[:frame_bytes]
                    pending_pcm = pending_pcm[frame_bytes:]
                    rms = audioop.rms(chunk, sample_width) if chunk else 0

                    if speech_started_at is None:
                        if now - started_at < 0.4:
                            noise_samples.append(rms)
                            if noise_samples:
                                threshold = max(
                                    threshold, int(max(noise_samples) * 2.5)
                                )
                        if rms >= threshold:
                            speech_started_at = now

                    yield chunk

                    if stop_event is not None and stop_event.is_set():
                        return
                    if speech_started_at is None:
                        continue

                    if stop_event is None:
                        if rms < threshold:
                            if silence_started_at is None:
                                silence_started_at = now
                            elif now - silence_started_at >= silence_duration:
                                return
                        else:
                            silence_started_at = None
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio.terminate()

    async def speak(self, text: str, log_callback=None) -> bool:
        """Synthesizes speech (TTS) and plays it back asynchronously."""
        if not text:
            return False
        
        print(f"Speaking: {text}")
        if log_callback:
            await log_callback(f"TTS: {text}")

        if edge_tts is not None and pygame is not None:
            try:
                success = await self._speak_edge_tts(text)
                if success:
                    return True
            except Exception as e:
                print(f"edge-tts failed: {e}. Falling back to system TTS...")
                if log_callback:
                    await log_callback("edge-tts lỗi, chuyển sang TTS hệ thống...")

        if os.name == "nt":
            try:
                await self._speak_windows_sapi(text)
                return True
            except Exception as e:
                print(f"Windows SAPI failed: {e}")
                if log_callback:
                    await log_callback(f"TTS Windows lỗi: {e}")

        if pyttsx3 is not None:
            try:
                await self._speak_pyttsx3(text)
                return True
            except Exception as e:
                print(f"pyttsx3 failed: {e}")
                if log_callback:
                    await log_callback(f"TTS lỗi hoàn toàn: {e}")
        else:
            print("No TTS engine available.")
            if log_callback:
                await log_callback("Không tìm thấy bộ phát âm thanh phù hợp.")
        
        return False

    async def _speak_edge_tts(self, text: str, voice: str = "vi-VN-HoaiMyNeural") -> bool:
        """Runs edge-tts and plays via pygame.mixer."""
        communicate = edge_tts.Communicate(text, voice)
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, "nexus_tts.mp3")

        await communicate.save(temp_file_path)

        def _play():
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(temp_file_path)
                pygame.mixer.music.play()
                return True
            except Exception as e:
                print(f"pygame music load/play error: {e}")
                return False

        loop = asyncio.get_running_loop()
        play_started = await loop.run_in_executor(None, _play)
        
        if not play_started:
            return False

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        try:
            pygame.mixer.music.unload()
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except Exception as e:
            print(f"Failed to clean up temp TTS file: {e}")

        return True

    async def _speak_windows_sapi(self, text: str):
        """Uses Windows System.Speech directly as an offline TTS fallback."""
        text_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        script = f"""
$bytes = [Convert]::FromBase64String('{text_b64}')
$text = [Text.Encoding]::UTF8.GetString($bytes)
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = 0
$speaker.Volume = 100
$speaker.Speak($text)
"""
        encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        timeout = max(15, min(90, len(text) // 8 + 15))

        def _speak():
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_script,
                ],
                check=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _speak)

    async def _speak_pyttsx3(self, text: str):
        """Runs pyttsx3 in an executor since it is synchronous."""
        def _speak():
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)
            
            voices = engine.getProperty('voices')
            vi_voice = None
            for voice in voices:
                if "vietnam" in voice.name.lower() or "vi" in voice.id.lower():
                    vi_voice = voice.id
                    break
            
            if vi_voice:
                engine.setProperty('voice', vi_voice)
            
            engine.say(text)
            engine.runAndWait()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _speak)
