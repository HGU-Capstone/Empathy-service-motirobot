# display/main.py

import pygame
import sys
import random
import math
import queue
import traceback
import threading

# 각 감정 모듈에서 Emotion 클래스를 불러옵니다. (사용 안 하는 감정 삭제)
from .emotions.neutral import Emotion as NeutralEmotion
from .emotions.happy import Emotion as HappyEmotion
from .emotions.excited import Emotion as ExcitedEmotion
from .emotions.tender import Emotion as TenderEmotion
from .emotions.scared import Emotion as ScaredEmotion
from .emotions.angry import Emotion as AngryEmotion
from .emotions.sad import Emotion as SadEmotion
from .emotions.surprised import Emotion as SurprisedEmotion
from .emotions.listening import Emotion as ListeningEmotion
from .emotions.thinking import Emotion as ThinkingEmotion
from .emotions.close import Emotion as CloseEmotion
from .emotions.scanning import Emotion as ScanningEmotion
from .emotions import eyebrow
from .emotions import cheeks

faceColor = (0, 0, 0)

class RobotFaceApp:
    def __init__(self, emotion_queue=None, stop_event=None, ptt_thread=None):
        pygame.init()

        monitor_sizes = pygame.display.get_desktop_sizes()
        monitor_index = 0
        if len(monitor_sizes) > 1:
            monitor_index = 1

        self.desktop_width, self.desktop_height = monitor_sizes[monitor_index]
        self.original_width, self.original_height = 800, 480
        self.scale_factor = min(self.desktop_width / self.original_width, self.desktop_height / self.original_height)
        self.scaled_width = int(self.original_width * self.scale_factor)
        self.scaled_height = int(self.original_height * self.scale_factor)
        
        self.screen = pygame.display.set_mode((self.scaled_width, self.scaled_height), pygame.NOFRAME, display=monitor_index)
        self.base_surface = pygame.Surface((self.original_width, self.original_height))

        pygame.display.set_caption("Moti Face (경량화 버전)")
        self.clock = pygame.time.Clock()
        
        self.emotion_timer_start_time = pygame.time.get_ticks()
        self.is_mouse_down = False
        self.mouse_down_time = 0
        self.click_count = 0
        self.click_timer = 0
        self.click_timeout = 3000

        self.common_data = {
            'left_eye': (self.original_width // 2 - 200, self.original_height // 2),
            'right_eye': (self.original_width // 2 + 200, self.original_height // 2),
            'offset': [0.0, 0.0], 'time': 0, 'scale_factor': self.scale_factor
        }
        
        self.emotion_queue = emotion_queue
        self.stop_event = stop_event or threading.Event()
        self.ptt_thread = ptt_thread 
        self.target_offset = [0.0, 0.0]
        self.move_speed = 1.5
        self.max_pupil_move_distance = 20
        self.is_blinking = False
        self.blink_progress = 0
        self.normal_blink_speed = 15

        pygame.time.set_timer(pygame.USEREVENT + 1, random.randint(2000, 5000))
        pygame.time.set_timer(pygame.USEREVENT + 2, random.randint(2000, 5000))
        
        # 불필요한 감정(SLEEPY, WAKE, RPS 등) 제거
        self.emotions = {
            "NEUTRAL": NeutralEmotion(), "HAPPY": HappyEmotion(), "EXCITED": ExcitedEmotion(),
            "TENDER": TenderEmotion(), "SCARED": ScaredEmotion(), "ANGRY": AngryEmotion(), 
            "SAD": SadEmotion(), "SURPRISED": SurprisedEmotion(), "LISTENING": ListeningEmotion(),
            "THINKING": ThinkingEmotion(), "CLOSE": CloseEmotion(), "SCANNING": ScanningEmotion()
        }
        self.current_emotion_key = "NEUTRAL"

        self.eyebrow_drawers = {
            "ANGRY": eyebrow.draw_angry_eyebrows, "SAD": eyebrow.draw_sad_eyebrows, "THINKING": eyebrow.draw_thinking_eyebrows, "LISTENING": eyebrow.draw_thinking_eyebrows,
        }
        self.cheek_drawers = {
            "HAPPY": cheeks.draw_happy_cheeks, "TENDER": cheeks.draw_tender_cheeks,
        }

    def change_emotion(self, new_emotion_key):
        if new_emotion_key not in self.emotions:
            print(f"경고: 알 수 없는 감정 키 '{new_emotion_key}'는 무시됩니다.")
            return

        if self.current_emotion_key != new_emotion_key:
            print(f"감정 변경: {self.current_emotion_key} -> {new_emotion_key}")
            self.current_emotion_key = new_emotion_key
            self.emotion_timer_start_time = pygame.time.get_ticks()
            if hasattr(self.emotions[self.current_emotion_key], 'reset'):
                self.emotions[self.current_emotion_key].reset()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                print("ESC 감지(Face App) -> 종료 신호 보냄")
                self.stop_event.set()
                return False
            
            # 숫자 키보드 이벤트(key_map) 전체 삭제 완료
            
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.is_mouse_down = True
                self.mouse_down_time = pygame.time.get_ticks()
                if self.current_emotion_key == "NEUTRAL":
                    current_time = pygame.time.get_ticks()
                    if current_time - self.click_timer > self.click_timeout: self.click_count = 1
                    else: self.click_count += 1
                    self.click_timer = current_time
                else: self.click_count = 0
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1: self.is_mouse_down = False
            if event.type == pygame.USEREVENT + 1: 
                if self.current_emotion_key not in ["LISTENING", "SCANNING"]:
                    self.target_offset = self.get_random_target_offset()
            if event.type == pygame.USEREVENT + 2 and not self.is_blinking:
                self.is_blinking = True
                self.blink_progress = 0
        return True

    def update(self):
        if self.stop_event.is_set():
            return False

        if self.emotion_queue:
            try:
                command = self.emotion_queue.get_nowait()
                self.change_emotion(command)
            except queue.Empty:
                pass

        if self.current_emotion_key == "NEUTRAL":
            if self.click_count >= 3:
                self.change_emotion("ANGRY")
                self.click_count = 0
        else:
            if pygame.time.get_ticks() - self.emotion_timer_start_time >= 30000:
                self.change_emotion("NEUTRAL")

        if self.current_emotion_key in ["LISTENING"]:
            self.target_offset = [0.0, 0.0]
            self.common_data['offset'] = [0.0, 0.0]
        
        elif self.current_emotion_key == "SCANNING":
            current_time = pygame.time.get_ticks() / 1000.0
            rotation_radius = 40 
            rotation_speed = 2.0 
            offset_x = math.cos(current_time * rotation_speed) * rotation_radius
            offset_y = math.sin(current_time * rotation_speed) * rotation_radius
            self.common_data['offset'][0] = offset_x
            self.common_data['offset'][1] = offset_y
            
        else:
            dx, dy = self.target_offset[0] - self.common_data['offset'][0], self.target_offset[1] - self.common_data['offset'][1]
            dist = math.hypot(dx, dy)
            if dist > self.move_speed:
                self.common_data['offset'][0] += (dx / dist) * self.move_speed
                self.common_data['offset'][1] += (dy / dist) * self.move_speed
        
        if self.is_blinking:
            self.blink_progress += self.normal_blink_speed
            if self.blink_progress >= 200: self.is_blinking = False

        self.common_data['time'] = pygame.time.get_ticks()
        return True

    def draw(self):
        self.screen.fill((0, 0, 0))
        self.base_surface.fill(faceColor)
        current_emotion = self.emotions[self.current_emotion_key]
        current_emotion.draw(self.base_surface, self.common_data)

        if self.is_blinking and self.current_emotion_key not in ["SCANNING"]:
            progress = self.blink_progress if self.blink_progress <= 100 else 200 - self.blink_progress
            for eye_center in [self.common_data['left_eye'], self.common_data['right_eye']]:
                top_rect = (eye_center[0]-100, eye_center[1]-150, 200, progress+50)
                bottom_rect = (eye_center[0]-100, eye_center[1]+100-progress, 200, progress+50)
                pygame.draw.rect(self.base_surface, faceColor, top_rect)
                pygame.draw.rect(self.base_surface, faceColor, bottom_rect)

        if self.current_emotion_key in self.eyebrow_drawers:
            self.eyebrow_drawers[self.current_emotion_key](self.base_surface, self.common_data)
            
        if self.current_emotion_key in self.cheek_drawers:
            self.cheek_drawers[self.current_emotion_key](self.base_surface, self.common_data)

        scaled_surface = pygame.transform.scale(self.base_surface, (self.scaled_width, self.scaled_height))
        self.screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()
        
    def get_random_target_offset(self):
        angle = random.uniform(0, 2 * math.pi)
        distance = random.uniform(0, self.max_pupil_move_distance)
        return [math.cos(angle) * distance, math.sin(angle) * distance]

    def run(self):
        running = True
        self.change_emotion("NEUTRAL")

        while running and not self.stop_event.is_set():
            try:
                running = self.handle_events()
                if not running: break
                
                running = self.update()
                if not running: break
                
                self.draw()
                self.clock.tick(60)
            except Exception as e:
                print(f"‼️ Face App 스레드 오류: {type(e).__name__} - {e}")
                traceback.print_exc()
                running = False
        
        print("Face App 종료 절차 시작...")
        
        if self.ptt_thread and self.ptt_thread.is_alive():
            print("   - 작별 인사가 끝날 때까지 화면을 유지합니다...")
            self.ptt_thread.join()

        pygame.quit()
        print("Face App 정상 종료")

def run_face_app(emotion_q, stop_event, ptt_thread: threading.Thread):
    try:
        app = RobotFaceApp(
            emotion_queue=emotion_q, 
            stop_event=stop_event, 
            ptt_thread=ptt_thread
        )
        app.run()
    except Exception as e:
        print(f"Face App 스레드를 시작하는 중 오류 발생: {e}")
        traceback.print_exc()