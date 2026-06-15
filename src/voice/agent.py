import asyncio
import os
import tempfile
import speech_recognition as sr

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
        self.is_calibrated = False

    @property
    def microphone(self):
        if self._microphone is None:
            self._microphone = sr.Microphone()
        return self._microphone

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
        if log_callback:
            await log_callback("Đang chuẩn bị micro...")
        
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
            
            audio_data = await loop.run_in_executor(None, _record)
            
            if log_callback:
                await log_callback("Đang nhận diện giọng nói...")

            def _recognize(audio):
                return self.recognizer.recognize_google(audio, language=self.language)

            text = await loop.run_in_executor(None, _recognize, audio_data)
            print(f"Recognized STT: {text}")
            return text

        except sr.WaitTimeoutError:
            print("Listening timed out.")
            if log_callback:
                await log_callback("Hết thời gian lắng nghe (không có âm thanh).")
            return ""
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
                print(f"edge-tts failed: {e}. Falling back to pyttsx3...")
                if log_callback:
                    await log_callback("edge-tts lỗi, chuyển sang TTS hệ thống...")

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
