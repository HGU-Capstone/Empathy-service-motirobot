# Empathy-service-motirobot

> **Multi-modal Interaction을 위한 통합 로보틱스 시스템**

<p align="center">
   <img width="40%" alt="SirLab Logo" src="https://github.com/user-attachments/assets/4cb0b76d-4d31-428f-a5f0-a7362f37c754">
</p>

본 프로젝트는 실시간 비전 프로세싱과 **ART(Adaptive Resonance Theory)** 알고리즘을 융합하여 단 한 번의 학습만으로 사용자를 정밀하게 식별 및 기억(**One-Shot Learning**)하는 지능형 로봇 시스템입니다.

특히, **비동기 멀티스레드 아키텍처(Asynchronous Multi-threaded Architecture)**를 도입하여 시스템의 동시성(Concurrency)과 반응 속도를 극대화했습니다. Vision, Voice, Control 등 각 모듈을 독립적인 스레드로 병렬 실행하고, 데이터 흐름을 **메시지 큐(Message Queue)**로 관리하여 프로세스 간 병목 현상을 제거했습니다.

또한, 대화 데이터를 실시간으로 디스크에 쓰지 않고 **인메모리 버퍼링(In-memory Buffering)** 후 세션 종료 시 일괄 저장(**Batch Processing**)하는 최적화 기법을 적용하여, I/O로 인한 지연(Blocking) 없이 **인지(Perception)-판단(Cognition)-행동(Action)**이 실시간으로 연결되는 고성능 상호작용 루프를 완성했습니다.

---

## Main Function

### Natural Interaction
사용자의 움직임을 실시간으로 인식하여 반응합니다. 로봇의 시선이 사용자의 얼굴을 따라가는 **Face Tracking** 기술과 동작 인식을 통해 역동적인 상호작용을 제공합니다.

### LLM-based Conversation
**Google Gemini API**를 활용하여 정해진 답변이 아닌, 사용자의 맥락과 상황을 이해하는 자유로운 대화가 가능합니다. **하이브리드 라우팅(Hybrid Routing)**을 통해 단순 명령은 즉각 처리하고, 복잡한 대화는 LLM이 처리하여 효율성을 높였습니다.

### User Recognition & Memory
MediaPipe와 **ART(Adaptive Resonance Theory)** 알고리즘을 결합하여, **단 1장의 사진만으로도 사용자를 즉시 등록하고 재인식**합니다. 대화 내용을 요약하여 JSON으로 관리함으로써, 이전 대화 맥락을 기억하고 연속적인 대화를 이어갑니다.

### Real-time Response
**비동기(Asynchronous)** 아키텍처를 적용하여 대화 처리 중에도 끊김 없는 아이컨택(Eye-contact)과 **60FPS**의 부드러운 표정 변화를 유지합니다. 사용자와 대화 중에 고개 끄덕거림을 통해 적극적으로 경청합니다.

---

## File Structure

프로젝트는 기능별로 명확하게 분리된 모듈 구조를 가집니다.

```text
EMPATHY-SERVICE-MOTIROBOT/
├── core/ # 두뇌 및 시스템 유틸리티 
│ ├── init.py
│ ├── profile_manager.py # 사용자 기억/프로필 관리 및 요약
│ ├── suppress.py # 경고 메시지/로그 숨김 유틸리티
│ └── utils.py # 시스템 프롬프트, 환경변수, 시간 계산 등
│
├── hardware/ # 모터 및 물리 제어 
│ ├── init.py
│ ├── config.py # 로봇 설정값 (포트, 상수, PID 등)
│ ├── dxl_io.py # Dynamixel 모터 제어 (읽기/쓰기)
│ ├── init.py # 로봇 초기 자세 및 포트 세팅
│ ├── motion.py # 고개 끄덕임 등 특정 모션 스크립트
│ └── wheel.py # 모바일 베이스(바퀴) 구동 제어
│
├── media/ # 오디오 및 음성 제어 
│ ├── init.py
│ ├── audio_manager.py # 마이크 녹음 및 입력 제어 
│ └── tts_manager.py # Typecast API 음성 출력 제어 
│
├── vision/ # 카메라 및 시각 인지
│ ├── init.py
│ ├── face.py # 사용자 얼굴 추적(Tracking) 스레드
│ └── vision_brain.py # MediaPipe 및 ART 기반 얼굴 식별 로직
│
├── display/ # 화면(표정) 및 자막 
│ ├── emotions/ # 감정별 표정 렌더링 파일들 (happy, sad 등)
│ ├── fonts/ # UI 폰트 리소스
│ ├── common_helpers.py # 디스플레이 공통 함수
│ ├── main.py # 그래픽 렌더링 메인 스레드
│ └── subtitle.py # 하단 자막 윈도우 프로세스
│
├── models/ # AI 모델 파일 
│ └── face_landmarker.task
│
├── art_brain_manage.py # 얼굴 인식 DB 관리 유틸 
├── debug_motor_positions.py # 모터 위치 디버깅 유틸 
├── gemini_api.py # LLM 메인 대화 엔진 
├── launcher.py # 전체 시스템 슈퍼바이저 (메인 실행 파일)
├── README.md # 프로젝트 설명서
└── .gitignore # Git 제외 목록
```
---

## Architecture

<p align="center">
   <img width="80%" height="50%" alt="Architecture" src="https://github.com/user-attachments/assets/7003056e-616f-4176-aee6-2a17c5c25c29">
</p>

이 로봇은 **인지(Perception) - 판단(Cognition) - 표현(Action)** 의 3계층 구조로 작동합니다.

1.  **Perception (인지)**
    * 마이크와 카메라를 통해 사용자의 음성, 얼굴 좌표, 제스처 데이터를 수집합니다.
    * **Multi-modal Trigger** 방식을 사용하여 음성과 시각 정보를 융합해 인식률을 높입니다.

2.  **Cognition (판단)**
    * **LLM Engine:** 입력된 텍스트와 상황을 분석하여 자연스러운 대화와 행동을 생성합니다.
    * **State Manager:** 로봇의 현재 상태(Idle, Active, Sleep 등)를 관리하고 적절한 작업을 스케줄링합니다.

3.  **Action (표현)**
    * **Visual:** 현재 감정 상태에 맞는 표정을 디스플레이에 실시간으로 렌더링합니다.
    * **Physical:** PID 제어를 통해 얼굴을 추적(Tracking)하거나, 제스처를 물리적으로 수행합니다.
