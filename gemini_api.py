# gemini_api.py
from __future__ import annotations

import os
import sys
import json
import base64
import queue
import threading
import random
import time
import re 
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
import multiprocessing

from core.profile_manager import ProfileManager
from core.utils import _get_relative_time_str, _extract_text, _get_env, SYSTEM_INSTRUCTION
from media.audio_manager import AudioManager
from media.tts_manager import TTSManager 

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from vision.vision_brain import RobotBrain

try:
    from dotenv import load_dotenv
    if os.path.exists(".env.local"):
        load_dotenv(dotenv_path=".env.local")
    else:
        load_dotenv()
except Exception:
    pass

from pynput import keyboard
import google.generativeai as genai

PROFILE_DB_FILE = "user_profiles.json"
MODEL_NAME = _get_env("MODEL_NAME", "gemini-3.1-flash-lite-preview")
GREETING_TEXT = _get_env("GREETING_TEXT", "안녕하세요! 모티입니다.")
FAREWELL_TEXT = _get_env("FAREWELL_TEXT", "도움이 되었길 바라요. 언제든 다시 불러주세요.")
ENABLE_GREETING = _get_env("ENABLE_GREETING", "1") not in ("0", "false", "False")


# --- 메인 PressToTalk 클래스 (컨트롤러) ---
class PressToTalk:
    def __init__(self,
                emotion_queue: Optional[queue.Queue] = None,
                subtitle_queue: Optional[multiprocessing.Queue] = None, 
                stop_event: Optional[threading.Event] = None,
                shared_state: Optional[dict] = None,
                mouth_event_queue: Optional[queue.Queue] = None,
                brain_instance = None,
                perform_head_nod_cb: Optional[Callable[[int], None]] = None,
                ): 
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key or not api_key.strip():
            print("❗ GOOGLE_API_KEY가 없습니다."); sys.exit(1)

        genai.configure(api_key=api_key)
        self.MODEL_NAME = MODEL_NAME
        self.model = genai.GenerativeModel(MODEL_NAME)
        self.chat = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_INSTRUCTION).start_chat(history=[])
        
        self.current_user_name = None
        self.profile_db_file = PROFILE_DB_FILE
        self.initial_chat_summary = "아직 기록된 내용이 없습니다."
        self.initial_last_seen_str = "기록 없음"
        self.session_history = []

        self.emotion_queue = emotion_queue
        self.subtitle_queue = subtitle_queue
        self.stop_event = stop_event or threading.Event()
        
        self.brain = brain_instance
        self.last_logged_in_user = None

        self.mouth_event_queue = mouth_event_queue
        self.listening_enabled = threading.Event() 
        self.mouth_listener_thread = None 
        
        self.last_activity_time = 0
        self.current_listener = None

        self.busy_lock = threading.Lock()
        self.busy_signals = 0

        self.perform_head_nod_cb = perform_head_nod_cb
        self.nodding_thread = None
        self.stop_nodding_event = threading.Event()

        # 📢 TTS 엔진 초기화 및 연결
        self.tts = TTSManager()
        self.tts.subtitle_queue = subtitle_queue
        self.tts.start()

        self.audio = AudioManager() 
        self._print_intro()

        self.profile_manager = ProfileManager(self)
        self.profile_manager.init_db()
        
        if ENABLE_GREETING:
            self._speak_and_subtitle(GREETING_TEXT)
            if self.emotion_queue: self.emotion_queue.put("NEUTRAL")

        self.shared_state = shared_state

    def raise_busy_signal(self):
        with self.busy_lock:
            self.busy_signals += 1
            print(f"⚡ 바쁨 신호 증가 (현재: {self.busy_signals})")

    def lower_busy_signal(self):
        with self.busy_lock:
            self.busy_signals = max(0, self.busy_signals - 1)
            print(f"⚡ 바쁨 신호 감소 (현재: {self.busy_signals})")
            if self.busy_signals == 0:
                self.last_activity_time = time.time()

    def _listening_nod_worker(self):
        print("👂 경청 모드: 랜덤 끄덕임 스레드 시작...")
        
        start_wait = random.uniform(0.5, 1.5)
        interrupted = self.stop_nodding_event.wait(timeout=start_wait)
        if interrupted:
            return

        while not self.stop_nodding_event.is_set():
            reps = 2 if random.random() < 0.3 else 1
            if callable(self.perform_head_nod_cb):
                try:
                    threading.Thread(target=self.perform_head_nod_cb, args=(reps,), daemon=True).start()
                except Exception: pass
            
            wait_time = random.uniform(1.5, 4.0)
            if self.stop_nodding_event.wait(timeout=wait_time):
                break
        
        print("👂 경청 모드: 랜덤 끄덕임 스레드 종료.")

    def _mouth_listener_worker(self):
        print("▶ 🔊 Mouth-to-Talk listener thread started.")
        while not self.stop_event.is_set():
            try:
                msg = self.mouth_event_queue.get(timeout=0.2) 
                
                if msg == "START_RECORDING":
                    if self.listening_enabled.is_set():
                        if self.busy_signals > 0:
                            print(f"👄 말하는 중 인식 멈춤 (busy_signals: {self.busy_signals})")
                            continue
                        self._start_recording()
                elif msg == "STOP_RECORDING":
                    self._stop_recording_and_transcribe()

            except queue.Empty:
                continue 
            except Exception as e:
                print(f"❌ Mouth listener error: {e}")
        print("■ 🔊 Mouth-to-Talk listener thread stopped.")

    def _speak_and_subtitle(self, text_data: str | dict):
        if not text_data:
            return

        try:
            if isinstance(text_data, dict):
                text_to_display = text_data.get("text", "")
            else:
                text_to_display = str(text_data).strip()

            if not text_to_display:
                return

            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] 🗣️ 모티: {text_to_display}")
            
            self.tts.speak(text_data)
            self.tts.wait() 
        finally:
            pass

    def _print_intro(self):
        print("\n=== Gemini PTT (경량화 공감 버전) ===")
        print("▶ 입 열기로 대화 시작 → ESC로 종료")
        print("▶ Typecast 클라우드 음성 엔진 전용 구동")
        print(f"▶ MODEL={MODEL_NAME}")
        print("----------------------------------------------------------------\n")

    def _start_recording(self):
        if self.audio.recording: return
        if self.emotion_queue:
            self.emotion_queue.put("LISTENING") 

        self.last_activity_time = time.time()
        print("✅ User started speaking.")
        print("🎙️  녹음 시작...")
        
        self.audio.start_recording()

        if callable(self.perform_head_nod_cb) and (self.nodding_thread is None or not self.nodding_thread.is_alive()):
            self.stop_nodding_event.clear()
            self.nodding_thread = threading.Thread(target=self._listening_nod_worker, daemon=True)
            self.nodding_thread.start()

    def _stop_recording_and_transcribe(self):
        if not self.audio.recording: return
        if self.emotion_queue:
            self.emotion_queue.put("THINKING") 
        self.last_activity_time = time.time()
        print("⏹️  녹음 종료, 전사 중...")
        
        self.stop_nodding_event.set()

        wav_bytes = self.audio.stop_recording()
        
        if not wav_bytes:
            print("(녹음 데이터가 없습니다.)\n")
            if self.emotion_queue: self.emotion_queue.put("NEUTRAL") 
            return
            
        threading.Thread(target=self._transcribe_then_chat, args=(wav_bytes,), daemon=True).start()

    def _transcribe_then_chat(self, wav_bytes: bytes):
        self.raise_busy_signal()
        ts = datetime.now().strftime("%H:%M:%S")

        intent = "chat"
        user_text = ""
        speak_text_full = ""

        try:
            b64 = base64.b64encode(wav_bytes).decode("ascii")
            current_face_name = self.shared_state.get('current_user_name')

            is_waiting_for_name = (self.last_logged_in_user == "Wait_For_Name")
            known_name = self.last_logged_in_user if self.last_logged_in_user not in [None, "Unknown", "Wait_For_Name"] else current_face_name

            if is_waiting_for_name:
                situation_hint = (
                    "\n[시스템 힌트]: 모티가 방금 '성함이 어떻게 되시나요?'라고 질문하고 대답을 기다리는 중입니다. "
                    "사용자가 이름을 말하면 'introduction'으로 분류하고 [NAME]에 이름을 추출하세요. "
                    "그리고 의도가 'chat'인 경우, 대답을 마친 뒤 다시 '그나저나 성함이 어떻게 되시나요?'라고 물어보세요."
                )
            elif known_name and known_name not in ["Unknown", "Thinking..."]:
                situation_hint = (
                    f"\n[시스템 힌트]: 모티는 이미 사용자가 '{known_name}'님이라는 것을 인지하고 있습니다. "
                    f"사용자가 '{known_name}'이라고 다시 말하면 'chat'으로 분류하고 '알고 있어요 {known_name}님!'처럼 대답하세요."
                )
            else:
                situation_hint = "\n[시스템 힌트]: 일반적인 대화 중입니다."

            current_time_str = datetime.now().strftime("%Y년 %m월 %d일 %p %I시 %M분").replace("AM", "오전").replace("PM", "오후")

            prompt = (
                f"현재 시간: {current_time_str}\n"
                f"현재 사용자: {current_face_name}{situation_hint}\n"
                "첨부된 오디오를 듣고 다음 규칙을 지켜 출력해.\n"
                "1. [INTENT]의도[/INTENT] ('introduction', 'chat' 중 택 1)\n"
                "2. [NAME]이름[/NAME] ('introduction'일 때만)\n"
                "3. [USER]사용자가 한 말[/USER]\n"
                "4. [EMOTION]감정[/EMOTION] (사용자의 말에 공감하는 모티의 표정. 반드시 다음 중 하나만 선택: HAPPY, SAD, ANGRY, SURPRISED, TENDER, NEUTRAL)\n"
                "5. 그 다음 줄부터: 모티의 대답\n"
            )

            contents = list(self.chat.history)
            contents.append({
                "role": "user",
                "parts": [prompt, {"inline_data": {"mime_type": "audio/wav", "data": b64}}]
            })

            print(f"[{ts}] [Gemini] 🔥 초고속 스트리밍 호출 시작...")
            response_stream = self.chat.model.generate_content(contents, stream=True)

            buffer = ""
            terminators = ['.', '!', '?', '\n']
            header_parsed = False

            for chunk in response_stream:
                if not chunk.text: continue
                buffer += chunk.text

                if not header_parsed:
                    if "[/EMOTION]" in buffer or ("[USER]" in buffer and len(buffer.split("[/USER]")[-1]) > 100):
                        intent_match = re.search(r'\[INTENT\](.*?)\[/INTENT\]', buffer, re.DOTALL)
                        user_match = re.search(r'\[USER\](.*?)\[/USER\]', buffer, re.DOTALL)
                        name_match = re.search(r'\[NAME\](.*?)\[/NAME\]', buffer, re.DOTALL)
                        emotion_match = re.search(r'\[EMOTION\](.*?)\[/EMOTION\]', buffer, re.DOTALL)
                        
                        if intent_match: intent = intent_match.group(1).strip()
                        if user_match: user_text = user_match.group(1).strip()
                        extracted_name = name_match.group(1).strip() if name_match else None
                        
                        extracted_emotion = emotion_match.group(1).strip().upper() if emotion_match else "NEUTRAL"
                        
                        print(f"[{ts}] [User] {user_text}")
                        print(f"[{ts}] [Intent] {intent}")
                        if extracted_name: print(f"[{ts}] [Name] {extracted_name}")
                        print(f"[{ts}] [Emotion] {extracted_emotion}")
                        
                        if self.emotion_queue:
                            valid_emotions = ["HAPPY", "SAD", "ANGRY", "SURPRISED", "TENDER", "NEUTRAL"]
                            if extracted_emotion in valid_emotions:
                                self.emotion_queue.put(extracted_emotion)
                            else:
                                self.emotion_queue.put("NEUTRAL")

                        if intent == "introduction":
                            name = extracted_name if extracted_name else user_text.split(" ")[0]
                            if current_face_name and current_face_name not in ["Unknown", "Thinking..."]:
                                name = current_face_name
                                
                            print(f"💡 이름 확보 완료: '{name}'. 얼굴 학습 시작.")
                            self.profile_manager.load_profile_for_chat(name)
                            self.shared_state['current_user_name'] = name
                            self.last_logged_in_user = name
                            
                            self._speak_and_subtitle(f"반가워요 {name}님! 더 잘 기억하기 위해 얼굴을 인식할게요. 10초 동안 카메라를 봐주세요.")
                            if self.emotion_queue: self.emotion_queue.put("SCANNING")
                            
                            print("⏳ 10초 얼굴 학습 시작...")
                            self.shared_state['force_learning'] = True
                            self.shared_state['learning_target_name'] = name
                            time.sleep(10)
                            self.shared_state['force_learning'] = False
                            
                            if self.emotion_queue: self.emotion_queue.put("HAPPY")
                            speak_text_full = "등록이 완료되었습니다! 이제 대화를 시작해요."
                            self._speak_and_subtitle(speak_text_full)
                            try: self.profile_manager.save_profile_at_exit()
                            except Exception as e: print(f"❌ 프로필 저장 실패: {e}")
                            break

                        split_token = "[/EMOTION]" if "[/EMOTION]" in buffer else "[/USER]"
                        buffer = buffer.split(split_token)[-1].lstrip()
                        header_parsed = True
                    else:
                        continue 

                if header_parsed:
                    while any(t in buffer for t in terminators):
                        first_term_idx = min([buffer.find(t) for t in terminators if t in buffer])
                        sentence = buffer[:first_term_idx+1].strip()
                        buffer = buffer[first_term_idx+1:]
                        sentence = sentence.replace('*', '').strip()
                        
                        if sentence:
                            print(f"[{ts}] 🗣️ 말하기: {sentence}")
                            self.tts.speak(sentence)
                            speak_text_full += sentence + " "
            
            if header_parsed and buffer.strip():
                sentence = buffer.replace('*', '').strip()
                if sentence:
                    print(f"[{ts}] 🗣️ 마지막 말하기: {sentence}")
                    if self.subtitle_queue: self.subtitle_queue.put(sentence)
                    self.tts.speak(sentence)
                    speak_text_full += sentence + " "

            speak_text_full = speak_text_full.strip()

            if user_text and speak_text_full:
                new_history = list(self.chat.history)
                new_history.append({'role': 'user', 'parts': [user_text]})
                new_history.append({'role': 'model', 'parts': [speak_text_full]})
                self.chat = self.chat.model.start_chat(history=new_history)

        except Exception as e:
            print(f"❌ 처리 실패: {e}\n")
            if self.emotion_queue: self.emotion_queue.put("NEUTRAL")
            
        finally:
            print("... TTS 대기 ...")
            self.tts.wait()

            if self.emotion_queue:
                self.emotion_queue.put("NEUTRAL")

            if user_text and speak_text_full:
                log_entry = f"User: {user_text} | Moti: {speak_text_full}"
                self.session_history.append(log_entry)
                print(f"📝 대화 메모리 기록 (현재 {len(self.session_history)}턴 쌓임)")

            self.lower_busy_signal()

    def _flush_session_history(self):
        if not self.session_history:
            self.chat = genai.GenerativeModel(self.MODEL_NAME, system_instruction=SYSTEM_INSTRUCTION).start_chat(history=[])
            return

        print("💾 대화 세션 전환. 기억을 정리하여 저장합니다...")
        
        full_conversation_log = "\n".join(self.session_history)
        
        if hasattr(self.profile_manager, "batch_update_summary"):
            threading.Thread(
                target=self.profile_manager.batch_update_summary, 
                args=(full_conversation_log,),
                daemon=True
            ).start()
        else:
            print("⚠️ ProfileManager에 batch_update_summary 메서드가 없습니다. (임시 Skip)")

        self.session_history = []
        self.chat = genai.GenerativeModel(self.MODEL_NAME, system_instruction=SYSTEM_INSTRUCTION).start_chat(history=[])
        print("🧹 Gemini 단기 기억 초기화 완료 (다음 응답 속도 최적화)")
    
    def _quick_listen_for_yes_no(self, timeout=3.0) -> bool:
        print(f"👂 [Yes/No] {timeout}초간 답변 듣기 시작...")
        if self.emotion_queue: self.emotion_queue.put("LISTENING")
        
        wav_bytes = self.audio.record_fixed_duration(timeout)
        
        if not wav_bytes:
            return False
            
        print("✅ [Yes/No] 녹음 완료, 분석 중...")
        if self.emotion_queue: self.emotion_queue.put("THINKING")

        try:
            b64 = base64.b64encode(wav_bytes).decode("ascii")
            
            prompt = (
                "사용자의 오디오를 듣고 '긍정(Yes)'인지 '부정(No)'인지 판단하세요. "
                "사용자가 '네', '응', '좋아', '그래', '어'라고 하면 긍정입니다. "
                "사용자가 '아니', '아니요', '됐어', '싫어'라고 하거나 아무 말도 없으면 부정입니다. "
                "반드시 JSON으로만 출력하세요: {\"answer\": \"yes\"} 또는 {\"answer\": \"no\"}"
            )
            
            resp = self.model.generate_content([
                prompt,
                {"inline_data": {"mime_type": "audio/wav", "data": b64}}
            ])
            
            txt = _extract_text(resp).lower()
            if '"yes"' in txt or "'yes'" in txt:
                print("💡 판단 결과: YES (학습 진행)")
                return True
            else:
                print("💡 판단 결과: NO (학습 스킵)")
                return False
        except Exception as e:
            print(f"❌ 판단 오류: {e}")
            return False 

    def _on_press(self, key):
        pass

    def _on_release(self, key):
        if self.stop_event.is_set(): return False
        try:
            if key == keyboard.Key.esc:
                print("ESC 감지 -> 종료 신호 보냄")
                self.stop_event.set()
                self.stop_nodding_event.set() 
                if self.current_listener and self.current_listener.is_alive():
                    self.current_listener.stop()
                return False 
        except Exception as e: print(f"[키 처리 오류 on_release] {e}", file=sys.stderr)

    def run(self):
        self.current_listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.current_listener.start()
        
        if self.mouth_event_queue:
            self.mouth_listener_thread = threading.Thread(target=self._mouth_listener_worker, daemon=True)
            self.mouth_listener_thread.start()
        else:
            print("⚠️ Mouth event queue not provided. Mouth-to-talk disabled.")

        self.last_activity_time = time.time()
        self.listening_enabled.set()
        print("▶ 대화 세션을 시작합니다. (상시 대기 상태)")

        while not self.stop_event.is_set():
            if self.shared_state:
                raw_name = self.shared_state.get('detected_user')
                
                # 얼굴 감지 시
                if raw_name and raw_name not in ["Thinking...", None]:
                    
                    # 디바운스(안정화 대기) 로직
                    stabilize_timeout = 2.5 
                    elapsed = 0.0
                    check_interval = 0.1
                    final_name = raw_name
                    
                    while elapsed < stabilize_timeout:
                        if self.stop_event.is_set(): break
                        current_name = self.shared_state.get('detected_user')
                        
                        if current_name and current_name not in ["Unknown", "Thinking...", None]:
                            final_name = current_name
                            break
                            
                        if current_name is None:
                            final_name = None
                            break
                            
                        time.sleep(check_interval)
                        elapsed += check_interval
                    
                    if not final_name or final_name in ["Thinking...", None]:
                        continue 
                    
                    detected_name = final_name

                    if detected_name != self.last_logged_in_user:
                        if detected_name == "Unknown":
                            if self.last_logged_in_user != "Wait_For_Name":
                                print("🤖 새로운 Unknown 감지 -> 이름 질문 프로세스")
                                self.raise_busy_signal()
                                self._speak_and_subtitle("안녕하세요! 처음 뵙네요. 성함이 어떻게 되시나요?")
                                self.tts.wait()
                                self.last_logged_in_user = "Wait_For_Name"
                                self.lower_busy_signal()
                        else:
                            if self.last_logged_in_user == "Wait_For_Name":
                                self.last_logged_in_user = detected_name
                            else:
                                print(f"🤖 아는 사람({detected_name}) -> 학습 질문")
                                self.raise_busy_signal()
                                
                                self.profile_manager.load_profile_for_chat(detected_name)
                                self.last_logged_in_user = detected_name
                                self.shared_state['current_user_name'] = detected_name
                                
                                if self.emotion_queue: self.emotion_queue.put("HAPPY")
                                
                                greeting_msg = f"{detected_name}님 안녕하세요! {detected_name}님을 더 잘 기억할 수 있게 얼굴 인식을 수행할까요?"
                                self._speak_and_subtitle(greeting_msg)
                                self.tts.wait()

                                do_learning = self._quick_listen_for_yes_no(timeout=4.0)

                                if do_learning:
                                    self._speak_and_subtitle("네! 10초 동안 카메라를 봐주세요.")
                                    if self.emotion_queue: self.emotion_queue.put("SCANNING")
                                    self.shared_state['force_learning'] = True
                                    self.shared_state['learning_target_name'] = detected_name
                                    time.sleep(10) 
                                    self.shared_state['force_learning'] = False
                                    
                                    if self.emotion_queue: self.emotion_queue.put("HAPPY")
                                    self._speak_and_subtitle("얼굴 데이터 업데이트 완료! 이제 대화를 시작해요!")
                                else:
                                    if self.emotion_queue: self.emotion_queue.put("HAPPY")
                                    self._speak_and_subtitle("네, 바로 대화를 시작할게요.")
                                    self.tts.wait()
                                
                                self.lower_busy_signal()

            time.sleep(0.1)

        print("PTT App 종료 절차 시작...")
        
        self._flush_session_history()
        self.listening_enabled.clear()
        
        if self.current_listener and self.current_listener.is_alive():
            self.current_listener.stop()
        
        if self.mouth_listener_thread and self.mouth_listener_thread.is_alive():
            self.mouth_listener_thread.join(timeout=1.0)
        
        try:
            self.profile_manager.save_profile_at_exit()
        except Exception as e:
            print(f"❌ 종료 요약 저장 중 치명적 오류: {e}")

        try:
            if FAREWELL_TEXT: self.tts.speak(FAREWELL_TEXT)
        finally:
            self.tts.close_and_join(drain=True)
        print("PTT App 정상 종료")