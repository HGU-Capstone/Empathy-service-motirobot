# function/audio_manager.py
import os
import io
import sys
import wave
import queue
import numpy as np
import sounddevice as sd
from typing import Optional

from function.utils import _get_env

class AudioManager:
    def __init__(self):
        self.sample_rate = int(_get_env("SAMPLE_RATE", "16000"))
        self.channels = int(_get_env("CHANNELS", "1"))
        self.dtype = _get_env("DTYPE", "int16")
        
        self.recording = False
        self.frames_q = queue.Queue()
        self.stream: Optional[sd.InputStream] = None
        self.device_idx = self._get_device_index()

    def _get_device_index(self) -> Optional[int]:
        env_dev = os.environ.get("INPUT_DEVICE_INDEX")
        if env_dev and env_dev.strip():
            try: return int(env_dev.strip())
            except Exception: pass
            
        name_substr = os.environ.get("INPUT_DEVICE_NAME", "")
        if name_substr:
            key = name_substr.lower()
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d.get('max_input_channels', 0) > 0 and key in d.get('name', '').lower():
                        return i
            except Exception: pass
        return None

    def _audio_callback(self, indata, frames, time_info, status):
        if status: print(f"[오디오 경고] {status}", file=sys.stderr)
        try:
            self.frames_q.put_nowait(indata.copy())
        except queue.Full:
            pass 

    def start_recording(self):
        if self.recording: return
        
        # 이전 찌꺼기 큐 비우기
        while not self.frames_q.empty():
            try: self.frames_q.get_nowait()
            except queue.Empty: break
            
        try:
            if self.device_idx is not None: dinfo = sd.query_devices(self.device_idx, 'input')
            else: default_in = sd.default.device[0]; dinfo = sd.query_devices(default_in, 'input')
            print(f"🎚️  입력 장치: {dinfo['name']}")
        except Exception: pass
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate, 
            channels=self.channels, 
            dtype=self.dtype, 
            callback=self._audio_callback, 
            blocksize=0, 
            device=self.device_idx
        )
        self.stream.start()
        self.recording = True

    def stop_recording(self) -> Optional[bytes]:
        """녹음을 중지하고 WAV 바이트 데이터를 반환합니다."""
        if not self.recording: return None
        self.recording = False
        
        try:
            if self.stream: 
                self.stream.stop()
                self.stream.close()
        finally: 
            self.stream = None

        chunks = []
        while not self.frames_q.empty(): 
            try: chunks.append(self.frames_q.get_nowait())
            except queue.Empty: break
                
        if not chunks: 
            return None
            
        audio_np = np.concatenate(chunks, axis=0)
        return self._to_wav_bytes(audio_np)

    def record_fixed_duration(self, timeout: float) -> Optional[bytes]:
        """Yes/No 확인용: 지정된 시간 동안 블로킹하여 녹음 후 WAV 바이트 반환"""
        try:
            recording = sd.rec(
                int(timeout * self.sample_rate), 
                samplerate=self.sample_rate, 
                channels=self.channels, 
                dtype=self.dtype, 
                blocking=True
            )
            return self._to_wav_bytes(recording)
        except Exception as e:
            print(f"❌ 녹음 실패: {e}")
            return None

    def _to_wav_bytes(self, audio_np: np.ndarray) -> bytes:
        with io.BytesIO() as buf:
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(np.dtype(self.dtype).itemsize)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_np.tobytes())
            return buf.getvalue()