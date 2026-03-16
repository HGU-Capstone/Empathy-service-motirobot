# launcher.py
# ONE-PORT orchestrator: FaceTrack + Wheels + Gemini PTT + Visual Face
# - moti-face 앱을 별도 스레드로 실행하고, Queue를 통해 통신합니다.
from __future__ import annotations

import os
import sys
import signal
import threading
import platform
import queue
import multiprocessing

from dynamixel_sdk import PortHandler, PacketHandler

from function import config as C
from function import init as I
from function import face as F
from function import wheel as W
from function import dxl_io as IO
from function import motion as M

from gemini_api import PressToTalk
from display.main import run_face_app
from display.subtitle import subtitle_window_process

from function.vision_brain import RobotBrain

def _get_env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return default if v is None or not str(v).strip() else str(v).strip()

def _default_cam_index() -> int:
    return 0 if platform.system() == "Darwin" else 1

def _open_port() -> tuple[PortHandler, PacketHandler]:
    port = PortHandler(C.DEVICENAME)
    pkt = PacketHandler(C.PROTOCOL_VERSION)

    if not port.openPort():
        print(f"❌ 포트를 열 수 없습니다: {C.DEVICENAME}")
        sys.exit(1)
    if not port.setBaudRate(C.BAUDRATE):
        print(f"❌ Baudrate 설정 실패: {C.BAUDRATE}")
        try: port.closePort()
        finally: sys.exit(1)
    print(f"▶ 포트 열림: {C.DEVICENAME}, Baud={C.BAUDRATE}, Proto={C.PROTOCOL_VERSION}")
    return port, pkt

def _graceful_shutdown(port: PortHandler, pkt: PacketHandler, dxl_lock: threading.Lock):
    print("▶ 시스템 종료 절차 시작...")
    
    try: I.stop_all_wheels(pkt, port, dxl_lock)
    except Exception as e: print(f"  - 휠 정지 중 오류: {e}")
    
    try:
        with dxl_lock:
            ids = (C.PAN_ID, C.TILT_ID, *C.EXTRA_POS_IDS)
            for i in ids: IO.write1(pkt, port, i, C.ADDR_TORQUE_ENABLE, 0)
        print("  - 모든 모터 토크 OFF 완료")
    except Exception as e: print(f"  - 모터 토크 해제 중 오류: {e}")
    finally:
        try:
            port.closePort()
            print("■ 종료: 포트 닫힘")
        except Exception as e: print(f"  - 포트 닫기 중 오류: {e}")

def run_ptt(
    emotion_queue, subtitle_queue, stop_event,
    shared_state, mouth_event_queue, brain_instance=None, perform_head_nod_cb=None
):
    """PTT 스레드를 실행하는 타겟 함수"""
    try:
        app = PressToTalk(
            emotion_queue=emotion_queue,
            subtitle_queue=subtitle_queue,
            stop_event=stop_event,
            shared_state=shared_state,
            mouth_event_queue=mouth_event_queue,
            brain_instance=brain_instance,
            perform_head_nod_cb=perform_head_nod_cb
        )
        app.run()
    except Exception as e:
        print(f"❌ PTT 스레드에서 치명적 오류 발생: {e}")
    finally:
        print("■ PTT 스레드 종료")

def main():
    print("▶ launcher: (통합 버전) FaceTrack + Wheels + PTT + Visual Face")
    print(f" - Port={C.DEVICENAME}, Baud={C.BAUDRATE}, Proto={C.PROTOCOL_VERSION}")

    port, pkt = _open_port()
    dxl_lock = threading.Lock()
    stop_event = threading.Event()
    
    # 필수 큐만 남김
    emotion_queue = queue.Queue()
    mouth_event_queue = queue.Queue()
    video_frame_q = queue.Queue(maxsize=1)
    shared_state = {'mode': 'tracking', 'detected_user': None, 'current_face_embedding': None}

    try:
        brain = RobotBrain()
    except Exception as e:
        print(f"❌ RobotBrain 초기화 실패: {e}")
        brain = None

    subtitle_q = multiprocessing.Queue()
    subtitle_proc = multiprocessing.Process(
        target=subtitle_window_process,
        args=(subtitle_q,),
        name="subtitle_window",
        daemon=True
    )
    subtitle_proc.start()
    print("▶ Subtitle Window 프로세스 시작")
    
    def _handle_sigint(sig, frame):
        print("\n🛑 SIGINT(Ctrl+C) 감지 → 종료 신호 보냄")
        stop_event.set()
    signal.signal(signal.SIGINT, _handle_sigint)

    try:
        I.initialize_robot(port, pkt, dxl_lock)
        print("▶ 초기화 완료: 모든 모터가 지정된 위치로 이동했습니다.")
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        _graceful_shutdown(port, pkt, dxl_lock)
        sys.exit(1)

    cam_default = str(_default_cam_index())
    cam_index = int(_get_env("CAM_INDEX", cam_default))

    t_face = threading.Thread(
        target=F.face_tracker_worker,
        args=(port, pkt, dxl_lock, stop_event, video_frame_q, shared_state),
        kwargs=dict(camera_index=cam_index, draw_mesh=True, print_debug=True, mouth_event_queue=mouth_event_queue, brain=brain),
        name="face", daemon=True)
    
    perform_head_nod = lambda reps=2: M.perform_head_nod(port, pkt, dxl_lock, repetitions=reps)

    t_ptt = threading.Thread(
        target=run_ptt,
        args=(emotion_queue, subtitle_q, stop_event, shared_state, mouth_event_queue),
        kwargs={'brain_instance': brain, 'perform_head_nod_cb': perform_head_nod},
        name="ptt", daemon=True)

    t_visual_face = threading.Thread(
        target=run_face_app,
        args=(emotion_queue, stop_event, t_ptt), 
        name="visual_face", daemon=True)
    
    t_wheels = threading.Thread(
        target=W.wheel_loop,
        args=(port, pkt, dxl_lock, stop_event),
        name="wheels", daemon=True)

    t_face.start()
    print(f"▶ FaceTracker 시작 (camera_index={cam_index})")
    t_visual_face.start()
    print("▶ Visual Face App 스레드 시작")
    t_ptt.start()
    print("▶ PTT App 스레드 시작")
    t_wheels.start()
    print("▶ Wheel 제어 스레드 시작")

    try:
        F.display_loop_main_thread(stop_event, window_name="Camera Feed (on Laptop)")
    except KeyboardInterrupt:
        print("\n🛑 KeyboardInterrupt 감지 → 종료 신호 보냄")
        stop_event.set()
    finally:
        if not stop_event.is_set(): stop_event.set()
        print("▶ 모든 스레드 종료 대기 중...")

        if brain:
            print("💾 종료 시 뇌 저장 중...")
            brain.save_brain()
            
        if subtitle_q:
            subtitle_q.put("__QUIT__")
        if subtitle_proc:
            subtitle_proc.join(timeout=3)
        t_ptt.join(timeout=10.0)
        t_visual_face.join(timeout=15.0)
        t_face.join(timeout=3.0)
        t_wheels.join(timeout=3.0)
        _graceful_shutdown(port, pkt, dxl_lock)
        print("■ launcher 정상 종료")
        
if __name__ == "__main__":  
    multiprocessing.freeze_support()                                       
    main()