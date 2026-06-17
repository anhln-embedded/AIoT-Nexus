import asyncio
from typing import Optional


class XiaozhiAudioPlayer:
    """Decodes XiaoZhi Opus frames and plays them through a continuous output stream."""

    def __init__(self, sample_rate: int = 24000, channels: int = 1, log_callback=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.output_sample_rate = 48000
        self.output_channels = 1
        self.log_callback = log_callback
        self.is_available = False
        self._logged_unavailable = False
        self._logged_first_frame = False
        self._play_lock = asyncio.Lock()
        self._audio = None
        self._stream = None
        self._backend = None

        try:
            import av
            import pyaudio

            self.av = av
            self.pyaudio = pyaudio
            self.codec = av.CodecContext.create("opus", "r")
            self.resampler = av.audio.resampler.AudioResampler(
                format="s16",
                layout="mono",
                rate=self.output_sample_rate,
            )
            self._audio = pyaudio.PyAudio()
            self._backend = "pyaudio"
            self.is_available = True
        except Exception as exc:
            self.av = None
            self.pyaudio = None
            self.codec = None
            self.resampler = None
            self._init_error = exc

    def update_audio_params(self, sample_rate: Optional[int] = None, channels: Optional[int] = None):
        if sample_rate:
            self.sample_rate = int(sample_rate)
        if channels:
            self.channels = int(channels)
        if self.is_available:
            self.resampler = self.av.audio.resampler.AudioResampler(
                format="s16",
                layout="mono",
                rate=self.output_sample_rate,
            )

    async def play_opus_frame(self, frame_bytes: bytes):
        if not self.is_available:
            if not self._logged_unavailable:
                await self._log(f"XiaoZhi audio playback unavailable: {self._init_error}")
                self._logged_unavailable = True
            return

        packet = self.av.Packet(frame_bytes)
        try:
            frames = self.codec.decode(packet)
        except Exception as exc:
            await self._log(f"XiaoZhi Opus decode error: {exc}")
            return

        for frame in frames:
            converted = self.resampler.resample(frame)
            if converted is None:
                continue
            if not isinstance(converted, list):
                converted = [converted]
            for pcm_frame in converted:
                pcm_bytes = pcm_frame.to_ndarray().tobytes()
                if pcm_bytes:
                    if not self._logged_first_frame:
                        await self._log(
                            "XiaoZhi audio frame: "
                            f"opus_bytes={len(frame_bytes)}, "
                            f"decoded_rate={frame.sample_rate}, "
                            f"decoded_layout={frame.layout.name}, "
                            f"pcm_rate={self.output_sample_rate}, "
                            f"pcm_channels={self.output_channels}, "
                            f"pcm_bytes={len(pcm_bytes)}, "
                            f"backend={self._backend}"
                        )
                        self._logged_first_frame = True
                    await self._play_pcm(pcm_bytes)

    async def _play_pcm(self, pcm_bytes: bytes):
        async with self._play_lock:
            self._ensure_stream()
            await asyncio.to_thread(self._stream.write, pcm_bytes)

    def _ensure_stream(self):
        if self._stream and self._stream.is_active():
            return
        if self._stream:
            self._stream.close()
        self._stream = self._audio.open(
            format=self.pyaudio.paInt16,
            channels=self.output_channels,
            rate=self.output_sample_rate,
            output=True,
            frames_per_buffer=960,
        )

    def close(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._audio:
            self._audio.terminate()
            self._audio = None

    async def _log(self, message: str):
        if self.log_callback:
            await self.log_callback(message)
