# function/config.py
import os
try:
    import serial.tools.list_ports
except ImportError:
    print("⚠️ 'pyserial' 라이브러리가 필요합니다. 'pip install pyserial' 명령어로 설치해주세요.")
    serial = None

# ---- DXL Control Table ----
ADDR_OPERATING_MODE   = 11
ADDR_TORQUE_ENABLE    = 64
ADDR_PROFILE_VELOCITY = 112
ADDR_GOAL_POSITION    = 116
ADDR_PRESENT_POSITION = 132
ADDR_GOAL_VELOCITY    = 104
ADDR_PROFILE_ACCELERATION = 108
HEAD_NOD_HOME_POS = 4000
HEAD_NOD_DOWN_POS = 3900
HEAD_NOD_MAX_POS = 4030

def find_dxl_port() -> str | None:
    """
    PC에 연결된 시리얼 포트 목록을 스캔하여 'U2D2', 'USB Serial', 'FTDI' 등
    다이나믹셀 제어기와 관련된 키워드를 포함한 포트를 찾아 반환합니다.
    """
    if serial is None:
        return None

    print("▶️  사용 가능한 시리얼 포트 검색 중...")
    ports = serial.tools.list_ports.comports()
    dxl_port = None
    
    for port in ports:
        print(f"  - 포트: {port.device}, 설명: {port.description}")
        if 'U2D2' in port.description or \
           'USB Serial Port' in port.description or \
           'FTDI' in port.description:
            dxl_port = port.device
            print(f"✅ 다이나믹셀 포트를 찾았습니다: {dxl_port}")
            break

    if dxl_port is None:
        print("⚠️  자동으로 다이나믹셀 포트를 찾지 못했습니다.")

    return dxl_port

# ---- 기본 HW (Windows 전용) ----
_DEFAULT_PORT = "COM3"

MANUAL_PORT = os.getenv("DXL_PORT")
if MANUAL_PORT:
    print(f"ℹ️  .env.local에 지정된 포트({MANUAL_PORT})를 사용합니다.")
    DEVICENAME = MANUAL_PORT
else:
    DEVICENAME = find_dxl_port() or _DEFAULT_PORT

BAUDRATE         = int(os.getenv("DXL_BAUD", "57600"))
PROTOCOL_VERSION = float(os.getenv("DXL_PROTO", "2.0"))

# ---- 팬/틸트(Position) (얼굴 추적용 핵심 모터) ----
PAN_ID, TILT_ID = 2, 9
SERVO_MIN, SERVO_MAX = 0, 4095
TILT_POS_MAX = 2040 
PAN_SIGN = 1      
TILT_SIGN = -1    
KP_PAN, KP_TILT = 0.1, 0.1       
KI_PAN, KI_TILT = 0.0, 0.0     
KD_PAN, KD_TILT = 0.0, 0.0       
DEAD_ZONE = 100
MAX_PIXEL_OFF = 200
PROFILE_VELOCITY = 100
MIN_MOVE_DELTA = 5

# ---- 휠(Velocity) (바퀴 제어용 핵심 모터) ----
LEFT_ID, RIGHT_ID = 4, 3
LEFT_DIR, RIGHT_DIR = -1, +1
RPM_PER_UNIT = 0.229
BASE_RPM = float(os.getenv("BASE_RPM", "25.0"))
TURN_RPM = float(os.getenv("TURN_RPM", "25.0"))
VEL_MIN, VEL_MAX = -1023, +1023

def rpm_to_unit(rpm: float) -> int:
    return int(round(rpm / RPM_PER_UNIT))

BASE_SPEED_UNITS = rpm_to_unit(BASE_RPM)
TURN_SPEED_UNITS = rpm_to_unit(TURN_RPM)

# ---- 사용하지 않는 관절 모터 ID (안전 종료 시 토크 해제용) ----
# 기능은 삭제되었지만, 물리적으로 연결된 모터들이 뻗대지 않도록 ID만 남겨둡니다.
HEAD_NOD_ID = 1
SHOULDER_ID = 5
AUX_ID = 6
RIGHT_ARM_ID = 7
RIGHT_HAND_ID = 8
LEFT_ARM_ID = 11
LEFT_HAND_ID = 12

# 런처에서 안전하게 토크를 끄기 위해 하나로 묶어줍니다.
EXTRA_POS_IDS = (HEAD_NOD_ID, SHOULDER_ID, AUX_ID, RIGHT_ARM_ID, RIGHT_HAND_ID, LEFT_ARM_ID, LEFT_HAND_ID)