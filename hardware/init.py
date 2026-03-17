# function/init.py

from dynamixel_sdk import PortHandler, PacketHandler
from hardware import config as C
from hardware import dxl_io as io
import time

# config.py에 정의된 변수명을 사용하여 가독성을 높인 초기 목표 위치 (바퀴 제외)
MOTOR_HOME_POSITIONS = {
    C.HEAD_NOD_ID: 4038,    # 1
    C.PAN_ID: 2074,         # 2
    C.SHOULDER_ID: 2080,    # 5
    C.AUX_ID: 2120,         # 6
    C.RIGHT_ARM_ID: 3723,   # 7
    C.RIGHT_HAND_ID: 2019,  # 8
    C.TILT_ID: 2072,        # 9
    10: 1010,               # 10
    C.LEFT_ARM_ID: 1347,    # 11
    C.LEFT_HAND_ID: 2044,   # 12
}

def initialize_robot(port: PortHandler, pkt: PacketHandler, lock):
    """모든 모터를 초기화하고 지정된 위치 및 모드로 설정하는 통합 함수"""
    print("▶️  모든 모터 초기화 및 지정 위치로 이동 시작...")
    
    with lock:
        # 1. 관절 및 얼굴 모터 (위치 제어 모드)
        for motor_id, home_pos in MOTOR_HOME_POSITIONS.items():
            # 토크를 끄고 운영 모드를 위치 제어(3)로 변경 후 다시 켬
            io.write1(pkt, port, motor_id, C.ADDR_TORQUE_ENABLE, 0) 
            io.write1(pkt, port, motor_id, C.ADDR_OPERATING_MODE, 3) 
            io.write4(pkt, port, motor_id, C.ADDR_PROFILE_VELOCITY, 100) 
            io.write1(pkt, port, motor_id, C.ADDR_TORQUE_ENABLE, 1) 
            
            # 지정된 HOME 위치로 이동 명령
            io.write4(pkt, port, motor_id, C.ADDR_GOAL_POSITION, home_pos)
            print(f"  [INIT] 모터 ID #{motor_id:02d} -> 목표 위치 {home_pos}로 이동 명령")

        # 2. 바퀴 모터 (속도 제어 모드)
        print("▶️  바퀴 모터를 속도 제어(Velocity) 모드로 변경합니다...")
        for dxl_id in (C.LEFT_ID, C.RIGHT_ID):
            io.write1(pkt, port, dxl_id, C.ADDR_TORQUE_ENABLE, 0)
            io.write1(pkt, port, dxl_id, C.ADDR_OPERATING_MODE, 1)  # Velocity 모드(1)
            io.write1(pkt, port, dxl_id, C.ADDR_TORQUE_ENABLE, 1)
    
    # 모든 모터가 움직일 시간을 잠시 기다립니다.
    print("▶️  모터가 초기 위치로 이동 중... (3초 대기)")
    time.sleep(3)
    print("✅ 모든 모터 초기화 완료!")


def stop_all_wheels(pkt: PacketHandler, port: PortHandler, lock):
    """시스템 종료 시 바퀴 모터 정지용 함수"""
    from . import wheel
    wheel.set_wheel_speed(pkt, port, lock, C.LEFT_ID,  0)
    wheel.set_wheel_speed(pkt, port, lock, C.RIGHT_ID, 0)