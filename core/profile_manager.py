# core/profile_manager.py

from __future__ import annotations
import os
import json
import threading
import google.generativeai as genai
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gemini_api import PressToTalk

from core.utils import _get_relative_time_str, _extract_text, build_main_system_instruction

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DB_FILE = os.path.join(BASE_DIR, "user_profiles.json")

class ProfileManager:
    """사용자 프로필(DB) 및 Gemini 세션 초기화를 전담하는 클래스"""
    def __init__(self, ptt_instance: 'PressToTalk'):
        self.ptt = ptt_instance
        self.MODEL_NAME = ptt_instance.MODEL_NAME
        self.db_file = PROFILE_DB_FILE
        self.lock = threading.Lock() 

    def init_db(self):
        if not os.path.exists(self.db_file):
            print(f"ℹ️ 프로필 DB 파일({self.db_file})이 없어 새로 생성합니다.")
            try:
                with open(self.db_file, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"❌ 프로필 DB 파일 생성 실패: {e}")

    def _load_all_profiles(self) -> dict:
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, "r", encoding="utf-8") as f:
                    try: return json.load(f)
                    except json.JSONDecodeError: return {}
            return {}
        except Exception as e:
            print(f"❌ 프로필 로드 실패: {e}")
            return {}

    def _save_to_file(self, data: dict):
        try:
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ 프로필 저장 실패: {e}")

    # 👇 [추가됨] 8단계 인터뷰 정보(user_info)를 안전하게 DB에 저장
    def save_user_info(self, name: str, user_info: dict):
        if not name or name == "Unknown": return
        with self.lock:
            data = self._load_all_profiles()
            if name not in data:
                data[name] = {"chat_summary": "신규 사용자입니다.", "last_seen": datetime.now().isoformat()}
            data[name]["user_info"] = user_info
            self._save_to_file(data)
            print(f"✅ {name}님의 8단계 인터뷰 프로필 DB 저장 완료!")

    def load_profile_for_chat(self, name: str):
        """이름을 기반으로 프로필을 로드하고 Gemini 뇌(System Instruction)를 장착합니다."""
        if not name: return
        print(f"⏳ {name}님의 프로필 로드를 시도합니다...")
        
        chat_summary = "아직 기록된 내용이 없습니다."
        last_seen_str = "기록 없음" 
        relative_time_str = "기록 없음" 
        user_info = {} # 8단계 프로필

        with self.lock:
            data = self._load_all_profiles()
            if name in data:
                chat_summary = data[name].get("chat_summary", "아직 기록된 내용이 없습니다.")
                user_info = data[name].get("user_info", {})
                last_seen_iso = data[name].get("last_seen")
                
                if last_seen_iso:
                    try:
                        last_seen_dt_obj = datetime.fromisoformat(last_seen_iso)
                        dt_now = datetime.now()
                        relative_time_str = _get_relative_time_str(last_seen_dt_obj, dt_now) 
                        last_seen_str = last_seen_dt_obj.strftime('%Y년 %m월 %d일 %H시 %M분')
                    except ValueError: pass 
            else:
                data[name] = {
                    "chat_summary": "신규 사용자입니다.",
                    "last_seen": datetime.now().isoformat(),
                    "user_info": {}
                }
                self._save_to_file(data)
        
        # PTT 인스턴스에 값 전달
        self.ptt.current_user_name = name
        self.ptt.initial_chat_summary = chat_summary
        self.ptt.initial_last_seen_str = last_seen_str 
        self.ptt.temp_user_info = user_info # 👈 gemini_api가 쓸 수 있게 넘겨줌

        current_time_str = datetime.now().strftime('%Y년 %m월 %d일 %A')

        # 👇 [핵심 연동] utils.py의 '한동대 뇌 조립 공장'을 호출합니다.
        base_instruction = build_main_system_instruction(user_info)
        
        enhanced_system_instruction = (
            base_instruction +
            f"\n\n--- 현재 시간 ---\n"
            f"오늘은 {current_time_str}입니다. 이 시간 정보를 바탕으로 '어제', '오늘' 등을 정확히 인지하세요."
            "\n\n--- 중요 기억 (필독!) ---\n"
            f"당신은 지금 **'{name}'님**과 대화하고 있습니다. **사용자의 이름을 잊지 말고 항상 기억하세요.**\n"
            f"다음은 '{name}'님에 대해 당신이 기억하고 있는 중요한 사실들입니다 ( {relative_time_str} 기준):\n"
            f"{chat_summary}\n"
            "--- 중요 기억 활용 규칙 ---\n"
            "1. 사용자의 질문에 답하기 전, 항상 [중요 기억] 섹션에 관련 정보가 있는지 먼저 확인하세요.\n"
            f"2. (예시) 사용자가 '오늘 뭐할까?'라고 물었고, [중요 기억]에 '- 5시까지 공부할 예정'이라고 적혀있다면, '기억하기로는 오늘 5시까지 공부하실 계획이 있으셨어요.'라고 먼저 알려주세요.\n"
            "3. [중요 기억]은 대화 주제와 '직접적으로 관련이 있을 때만' 자연스럽게 언급하세요. 뜬금없이 반복해서 말하지 마세요.\n" 
            "4. [!! 중요 대화 규칙 !!] 기억 속의 사실을 언급할 때, 절대 날짜를 직접 말하지 말고 '어제', '며칠 전에' 같은 상대 시간으로 자연스럽게 표현하세요.\n"
            "--- 중요 기억 끝 ---"
        )
        
        # 여기서 Gemini Chat 세션을 한방에 덮어씌웁니다!
        self.ptt.chat = genai.GenerativeModel(
            self.MODEL_NAME, 
            system_instruction=enhanced_system_instruction
        ).start_chat(history=[])

        print(f"🧠 Gemini Chat 세션을 {name}님 맞춤형으로 성공적으로 재설정했습니다.")

    def batch_update_summary(self, conversation_log: str):
        if not conversation_log or not self.ptt.current_user_name:
            return

        name = self.ptt.current_user_name
        print(f"🧠 [Memory] {name}님과의 대화 내용을 정리하여 저장합니다...")

        old_summary = self.ptt.initial_chat_summary
        last_seen_str = self.ptt.initial_last_seen_str
        
        current_time_dt = datetime.now()
        one_week_ago_dt = current_time_dt - timedelta(days=7)
        
        current_time_str = current_time_dt.strftime('%Y년 %m월 %d일 %H시 %M분')
        one_week_ago_str = one_week_ago_dt.strftime('%Y년 %m월 %d일')

        try:
            summarizer_prompt = (
                f"당신은 대화 내용을 바탕으로 사용자의 프로필을 관리하는 AI입니다.\n"
                f"현재 시간은 [ {current_time_str} ]입니다.\n"
                f"!! 삭제 기준일은 [ {one_week_ago_str} ]입니다. (오늘로부터 1주일 전)\n"
                f"아래의 [기존 사실] ( {last_seen_str} 기준)을 [이번 세션 전체 대화] ( {current_time_str} 에 종료됨)의 내용으로 업데이트하여, [새로운 사실 목록]을 만드세요.\n\n"
                "규칙:\n"
                "1. 대화에서 '사용자'에 대한 '중요한 개인 정보'만 추출합니다.\n"
                "2. 단순한 인사나 잡담은 무시합니다.\n"
                "3. '새로운 사실 목록'은 항상 간결한 불렛 포인트(-)로 작성합니다.\n"
                "4. [이번 세션 전체 대화]에서 추출할 새 사실이 없다면, [기존 사실]을 (삭제 규칙 적용 후) 그대로 출력합니다.\n"
                "5. [!!기억 삭제 규칙!!] 1주일이 지난 일상적인 잡담이나 일회성 상태는 삭제하되, 핵심 개인정보(이름, 생일, 직업, 성격, 취향, 게임, 운동, 좋아하는 것, 취미, 장기 목표 등)는 1주일이 지나도 절대 삭제하지 말고 영구적으로 유지하세요. (단, 8번 규칙에 의해 정보가 갱신되어 덮어쓰는 경우는 예외입니다.)\n"
                "6. [!!날짜/사실 분리 규칙!!] 영구적 사실은 날짜를 적지 않고(예: - 전공: 미술), 특정 시점 사건이나 상태는 기준일을 포함하세요(예: - 수업 듣는 중 (상태, 2026년 03월 06일)).\n"
                "7. [!!메아리 방지 규칙!!] 대화 로그에서 AI(모티)가 사용자의 과거 취향이나 기억을 단순히 '대답(회상)'해준 내용은 절대 새로운 정보로 추출하지 마세요. 오직 사용자가 '새롭게 직접 말한' 정보만 추출해야 합니다. 이미 [기존 사실]에 있는 내용을 재확인한 대화라면 기존 사실의 날짜를 오늘로 갱신하지 말고 예전 그대로 유지하세요.\n"
                "8. [!!정보 갱신(덮어쓰기) 규칙!!] 사용자의 직업, 취향, 관심사, 목표 등 기존 [기존 사실]의 내용이 새롭게 변경되었거나 과거 사실과 충돌하는 경우(예: 학생 -> 취업), 옛날 정보와 새 정보를 중복해서 나열하지 말고 반드시 **가장 최신 정보 하나로 덮어쓰기(Overwrite)** 하세요.\n"
                "9. [!!출력 규칙!!] 대답을 시작할 때 '네, 업데이트하겠습니다' 등의 인사말이나 부연 설명을 절대 하지 말고, 오직 업데이트된 불렛 포인트(-) 목록만 반환하세요.\n\n"
                f"[기존 사실 ( {last_seen_str} 기준)]\n{old_summary}\n\n"
                f"[이번 세션 전체 대화 ( {current_time_str} 에 종료됨)]\n"
                f"{conversation_log}\n\n"
                "[새로운 사실 목록] (1주일 이내의 정보 + 핵심 정보만 포함)\n"
            )

            summarizer_model = genai.GenerativeModel(self.MODEL_NAME)
            response = summarizer_model.generate_content(summarizer_prompt)
            new_summary = _extract_text(response)

            with self.lock:
                data = self._load_all_profiles()
                if name not in data:
                    data[name] = {}
                data[name]["chat_summary"] = new_summary
                data[name]["last_seen"] = datetime.now().isoformat()
                self._save_to_file(data)

            self.ptt.initial_chat_summary = new_summary
            self.ptt.initial_last_seen_str = current_time_str
            print(f"✅ {name}님의 기억(프로필) 업데이트 완료!")

        except Exception as e:
            print(f"❌ [Memory] 기억 업데이트 실패: {e}")

    def save_profile_at_exit(self):
        current_user = self.ptt.shared_state.get('current_user_name')
        if not current_user or current_user == "Unknown": return

        print(f"💾 {current_user}님의 기본 프로필(접속기록) 저장을 시도합니다...")
        with self.lock:
            data = self._load_all_profiles()
            if current_user not in data:
                data[current_user] = {"chat_summary": "신규 등록된 사용자입니다.", "created_at": datetime.now().isoformat()}
            data[current_user]['last_seen'] = datetime.now().isoformat()
            self._save_to_file(data)
            print(f"✅ {current_user}님의 프로필이 {self.db_file}에 저장되었습니다.")