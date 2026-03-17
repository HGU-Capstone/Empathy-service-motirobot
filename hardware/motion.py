# function/motion.py

import time
import threading
from dynamixel_sdk import PortHandler, PacketHandler
from hardware import config as C
from hardware import dxl_io as io

def perform_head_nod(port: PortHandler, pkt: PacketHandler, lock: threading.Lock, shared_state: dict, repetitions=2):
    """
    고개를 부드럽게 끄덕이는 독립 실행 함수.
    가속도 프로파일을 사용하며, C.HEAD_NOD_HOME_POS(4000)을 준수합니다.
    """
    print(f"🤖 고개 끄덕이기 {repetitions}회 시작... (Face Tracking 일시 정지)")
    
    # 1. 상태 변경: Face Tracking 중지
    if shared_state:
        shared_state['mode'] = 'nodding'
        time.sleep(0.1) # 진행 중이던 추적 루프가 안전하게 멈출 수 있도록 아주 잠깐 대기
    
    # 2. 동작 값 정의
    home_pos = C.HEAD_NOD_HOME_POS  # 4000 (들린 상태)
    down_pos = C.HEAD_NOD_DOWN_POS  # 3800 (숙인 상태)
    accel_value = 30                # 부드러운 가속 (0이 아닌 값)
    velocity_value = 300            # 끄덕이는 속도 (조절 가능)
    default_velocity = 100          # init.py의 기본 속도값
    nod_wait_time = 0.3             # 숙이고 머무는 시간
    nod_wait_time_up = 0.4          # 들고 머무는 시간
    
    # 3. 모터 설정 및 동작 (가속도/속도) - try/finally로 안전하게
    try:
        with lock:
            # [방어 코드 추가] 본격적인 끄덕임 전, 1번 모터가 확실히 초기 위치(4000)에 있는지 보장
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_ACCELERATION, 20) # 부드럽게 홈으로 복귀
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_VELOCITY, default_velocity)
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_GOAL_POSITION, home_pos)
        
        time.sleep(0.2) # 홈 포지션으로 맞춰질 때까지 잠시 대기

        with lock:
            print("  - 끄덕임용 가속도/속도 설정...")
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_ACCELERATION, accel_value)
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_VELOCITY, velocity_value)

        # 끄덕임 동작 수행
        for i in range(repetitions):
            print(f"  - 끄덕 {i+1}회")
            with lock:
                # 고개 숙이기 (Down)
                io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_GOAL_POSITION, down_pos)
            time.sleep(nod_wait_time)
            
            with lock:
                # 고개 들기 (Home)
                io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_GOAL_POSITION, home_pos)
            time.sleep(nod_wait_time_up)

    finally:
        # 4. 모터 설정 초기화 및 Face Tracking 재개
        with lock:
            print("  - 끄덕임 설정 초기화 (가속도 0, 속도 100)...")
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_ACCELERATION, 0)
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_PROFILE_VELOCITY, default_velocity) 
            
            # 마지막으로 홈 포지션으로 한 번 더 복귀
            io.write4(pkt, port, C.HEAD_NOD_ID, C.ADDR_GOAL_POSITION, home_pos)
        
        # 동작이 완전히 끝난 후 Tracking 모드로 복구
        if shared_state:
            shared_state['mode'] = 'tracking'
            
        print("✅ 고개 끄덕이기 완료! (Face Tracking 재개)")