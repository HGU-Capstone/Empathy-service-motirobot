# core/report_manager.py

import os
from datetime import datetime
import google.generativeai as genai
from core.utils import _extract_text

class ReportManager:
    """
    모티(Moti) 상담 결과지 및 전체 대화록을 txt 파일로 자동 생성하고 저장하는 클래스
    """
    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate_and_save_reports(self, user_name: str, conversation_log: str, user_info: dict, vitals_data: dict = None):
        if not user_name or user_name == "Unknown":
            return

        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result_dir = os.path.join(base_dir, "user_result")
            os.makedirs(result_dir, exist_ok=True)

            # 1. 대화록 저장
            chat_filename = os.path.join(result_dir, f"{today_str}_{user_name}_대화.txt")
            formatted_log = ""
            for line in conversation_log.split('\n'):
                parts = line.split(" | Moti: ")
                if len(parts) == 2:
                    formatted_log += f"👤 사용자: {parts[0].replace('User: ', '').strip()}\n"
                    formatted_log += f"🤖 모티: {parts[1].strip()}\n\n"
                else:
                    formatted_log += line + "\n"

            with open(chat_filename, "w", encoding="utf-8") as f:
                f.write(f"--- {user_name}님과의 전체 대화 기록 ---\n")
                f.write(f"일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(formatted_log)
            print(f"📄 전체 대화문 저장 완료: {chat_filename}")

            # 🚨 [신규 추가] 수동으로 입력받은 신체 활력 데이터 포맷팅
            if vitals_data:
                vitals_text = f"""
- 평균 심박수: {vitals_data.get('avg_hr', '알 수 없음')}
- 최고 심박수: {vitals_data.get('max_hr', '알 수 없음')}
- 스트레스 지수: {vitals_data.get('stress', '알 수 없음')}
- 기분 요약: {vitals_data.get('mood', '알 수 없음')}
"""
            else:
                vitals_text = "- 신체 활력 데이터: 없음 (측정 불가)"

            # 2. 결과지 생성
            print(f"⏳ {user_name}님의 상담 결과지 자동 생성을 시작합니다...")
            report_prompt = f"""
당신은 한동대학교 학우들의 지친 마음을 달래주는 따뜻한 공감 로봇 '모티(Moti)'의 전문 심리 분석 AI입니다.
아래의 [내담자 정보], [신체 활력 데이터], [전체 대화 내용]을 바탕으로, 사용자가 읽고 큰 위로와 재미를 느낄 수 있는 '모티의 마음 처방전'을 작성해 주세요.

[내담자 정보]
- 이름: {user_info.get('이름', user_name)}
- 학년/전공: {user_info.get('학년', '알 수 없음')} / {user_info.get('전공', '알 수 없음')}
- 소속(RC): {user_info.get('RC', '알 수 없음')}
- 성향(MBTI): {user_info.get('MBTI', '알 수 없음')}

[신체 활력 데이터]
{vitals_text}

[전체 대화 내용]
{formatted_log}

[작성 가이드라인 - 아래 양식과 이모지를 반드시 지켜서 작성하세요]

## 💌 모티가 발급한 [ {user_info.get('이름', user_name)} ]님만의 마음 처방전 💌

**"오늘 하루도 정말 고생 많으셨어요. 모티가 당신의 내일을 응원합니다!"**

---

### 📋 1. 오늘의 내담자 프로필
* **이름:** {user_info.get('이름', user_name)} 학우님
* **소속/학년:** {user_info.get('전공', '알 수 없음')} ({user_info.get('학년', '알 수 없음')})
* **오늘의 MBTI 무기:** [여기에 내담자의 MBTI를 적고, 그 MBTI의 긍정적인 강점을 한 줄로 적어주세요. 예: ESTP - 특유의 긍정 에너지와 빠른 실행력!]

### 🩺 2. 모티의 마음 진단서
* **오늘의 마음 온도:** [대화 내용을 바탕으로 오늘의 기분을 비유적으로 표현하세요. 예: 먹구름 낀 뒤 점차 맑아짐 ⛅]
* **증상 요약:** [사용자가 겪은 힘든 일이나 고민을 2~3줄로 따뜻하게 요약하세요.]
* **모티의 공감 시선:** [왜 사용자가 그런 감정을 느끼는 것이 당연하고 자연스러운지, 그들의 노력을 칭찬하고 깊이 공감해주는 내용을 적어주세요.]

### 💊 3. 맞춤형 힐링 처방
* **행동 처방전:** [대화에서 제시했던 솔루션이나, 사용자가 당장 오늘 밤이나 내일 해보면 좋을 작고 확실한 행복(소확행) 행동을 추천해주세요. 한동대 캠퍼스(히즈빈스, 평봉필드 등)나 야식 메뉴 등을 언급하면 좋습니다.]
* **추천 힐링 BGM:** [사용자의 현재 기분과 상황에 딱 맞는 위로가 되거나 신나는 노래 1곡을 추천하고, 추천 이유를 덧붙여주세요.]

### 🫀 4. 신체 활력 & 스트레스 분석
* **측정 결과:** 평균 심박수 {vitals_data.get('avg_hr', '측정불가')}bpm / 최고 심박수 {vitals_data.get('max_hr', '측정불가')}bpm / 스트레스 {vitals_data.get('stress', '측정불가')}
* **건강 코멘트:** [제공된 데이터를 바탕으로 가볍게 건강 상태를 짚어주고, 휴식을 권장하는 따뜻한 멘트를 남겨주세요.]

---

### 💬 모티의 비밀 편지
"[이곳에는 모티의 1인칭 시점으로, 내담자에게 직접 말하듯 반말과 존댓말을 적절히 섞은 친근하고 다정한 응원의 편지를 3~4문장으로 작성해주세요. '언제든 또 찾아와'라는 뉘앙스를 꼭 넣어주세요.]"
"""
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(report_prompt)
            report_text = _extract_text(response)

            report_filename = os.path.join(result_dir, f"{today_str}_{user_name}_결과지.txt")
            with open(report_filename, "w", encoding="utf-8") as f:
                f.write(report_text)
            print(f"📄 상담 결과지 저장 완료: {report_filename}")

        except Exception as e:
            print(f"❌ 보고서 자동 저장 중 오류 발생: {e}")