import os
import sys
from dynamixel_sdk import PortHandler, PacketHandler
from hardware import config as C
from hardware import dxl_io as io

def main():
    """모터 ID 1번부터 12번까지의 현재 위치를 스캔하고 출력합니다."""

    # --- 포트 연결 (launcher.py와 동일한 로직) ---
    try:
        portHandler = PortHandler(C.DEVICENAME)
        packetHandler = PacketHandler(C.PROTOCOL_VERSION)

        if not portHandler.openPort():
            print(f"❌ 포트를 열 수 없습니다: {C.DEVICENAME}")
            sys.exit(1)
        
        if not portHandler.setBaudRate(C.BAUDRATE):
            print(f"❌ Baudrate 설정 실패: {C.BAUDRATE}")
            sys.exit(1)
            
        print(f"✅ 포트 연결 성공: {C.DEVICENAME} @ {C.BAUDRATE} bps")
        print("--------------------------------------------------")
        print("🦿🦾 모터 위치 스캔 시작 (ID 1~12)...")
        print("--------------------------------------------------")

        # --- 모든 모터 위치 읽기 ---
        for motor_id in range(1, 13):
            # 각 모터의 현재 위치(PRESENT_POSITION) 값을 읽어옵니다.
            pos, dxl_comm_result, dxl_error = io.read4(packetHandler, portHandler, motor_id, C.ADDR_PRESENT_POSITION)
            
            if io.dxl_ok(dxl_comm_result, dxl_error):
                # 통신에 성공하면 위치 값을 출력합니다.
                print(f"  ✅ 모터 ID #{motor_id:02d} | 현재 위치: {pos}")
            else:
                # 통신에 실패하면 응답이 없는 것으로 간주합니다.
                print(f"  ⚠️ 모터 ID #{motor_id:02d} | 응답 없음")

    except Exception as e:
        print(f"스크립트 실행 중 오류 발생: {e}")
    finally:
        # --- 포트 닫기 ---
        if 'portHandler' in locals() and portHandler.is_open:
            portHandler.closePort()
            print("--------------------------------------------------")
            print("⏹️  포트를 닫았습니다.")

if __name__ == "__main__":
    main()