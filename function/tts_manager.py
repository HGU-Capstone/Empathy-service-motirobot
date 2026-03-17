# function/tts_manager.py
import io
import wave
import queue
import threading
import requests
import numpy as np
import sounddevice as sd

from function.utils import _get_env

class TTSManager:
    def __init__(self):
        self._q: queue.Queue[str | dict | None] = queue.Queue()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=False)
        self.subtitle_queue = None

    def start(self):
        self.thread.start()
        self.ready.wait(timeout=5)

    def speak(self, data):
        if not data: return
        text = data if isinstance(data, str) else data.get("text", "")
        print(f"🔊 TTS enqueue ({len(text)} chars)")
        self._q.put(data)

    def wait(self):
        self._q.join()

    def close_and_join(self, drain: bool = True, timeout: float = 30.0):
        try:
            if drain: self._q.join()
            self._q.put(None)
            self.thread.join(timeout=timeout)
        except Exception: pass

    def _run(self):
        try:
            api_key = _get_env("TYPECAST_API_KEY")
            voice_id = _get_env("TYPECAST_VOICE_ID")
            if not api_key or not voice_id:
                print("❗ TYPECAST_API_KEY 또는 TYPECAST_VOICE_ID가 비어있습니다.")
                self.ready.set()
                return
            
            model = _get_env("TYPECAST_MODEL", "ssfm-v21")
            language = _get_env("TYPECAST_LANGUAGE", "kor")
            audio_format = _get_env("TYPECAST_AUDIO_FORMAT", "wav")
            emotion = _get_env("TYPECAST_EMOTION", "")
            intensity = float(_get_env("TYPECAST_EMOTION_INTENSITY", "1.0") or "1.0")
            seed_env = _get_env("TYPECAST_SEED", "")
            seed = int(seed_env) if (seed_env and seed_env.isdigit()) else None
            
            self.ready.set()
            print("▶ Typecast TTS 준비 완료")
            url = "https://api.typecast.ai/v1/text-to-speech"
            headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
            
            while True:
                item = self._q.get()
                if item is None: 
                    self._q.task_done()
                    break
                try:
                    if isinstance(item, dict):
                        text = item.get("text")
                        rate_sapi = item.get("rate", 0) 
                        rate_multiplier = 1.0 + (rate_sapi / 10.0) * 0.5 
                        volume = item.get("volume", 100)
                        pitch = item.get("pitch", 0)
                    else:
                        text = item
                        rate_multiplier = 1.0
                        volume = 100
                        pitch = 0

                    if not text: continue
                    
                    payload = {
                        "voice_id": voice_id, "text": text, "model": model, "language": language, 
                        "output": {
                            "volume": volume, 
                            "audio_pitch": pitch, 
                            "audio_tempo": rate_multiplier, 
                            "audio_format": audio_format
                        }
                    }
                    if emotion: payload["prompt"] = {"emotion_preset": emotion, "emotion_intensity": intensity}
                    if seed is not None: payload["seed"] = seed
                    
                    r = requests.post(url, headers=headers, json=payload, timeout=60)
                    if r.status_code == 200:
                        data = r.content
                        with io.BytesIO(data) as buf:
                            with wave.open(buf, "rb") as wf:
                                sr = wf.getframerate()
                                frames = wf.readframes(wf.getnframes())
                        
                        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                        
                        if self.subtitle_queue:
                            self.subtitle_queue.put(text)

                        sd.play(audio, sr)
                        sd.wait()
                        print("✅ TTS done")
                    else: 
                        print(f"❌ Typecast 오류 {r.status_code}: {r.text[:200]}")
                finally: 
                    self._q.task_done()
        except Exception as e: 
            print(f"ℹ️ Typecast TTS 스레드 오류: {e}")
            self.ready.set()