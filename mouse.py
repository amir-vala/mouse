import cv2
import mediapipe as mp
import pyautogui
import math
import time
import threading

# مقداردهی اولیه MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# گرفتن ابعاد صفحه نمایش
screen_width, screen_height = pyautogui.size()
pyautogui.FAILSAFE = False

# --- پارامترهای قابل تنظیم ---
MOUSE_CONTROL_LANDMARK = mp_hands.HandLandmark.MIDDLE_FINGER_MCP
Y_OFFSET_SCREEN = 20

CAM_ACTIVE_SENSOR_WIDTH_MIN = 0.35
CAM_ACTIVE_SENSOR_WIDTH_MAX = 0.65
CAM_ACTIVE_SENSOR_HEIGHT_MIN = 0.35
CAM_ACTIVE_SENSOR_HEIGHT_MAX = 0.65

# آستانه برای نیشگون شست و اشاره (کلیک چپ / درگ)
THUMB_INDEX_PINCH_DISTANCE_THRESHOLD = 35
# آستانه جدید برای نیشگون شست و انگشت کوچک (کلیک راست)
THUMB_PINKY_PINCH_DISTANCE_THRESHOLD = 30 # ممکن است نیاز به تنظیم داشته باشد

SMOOTHING_FACTOR = 0.65
last_actual_mouse_x, last_actual_mouse_y = pyautogui.position()
MIN_MOVEMENT_THRESHOLD_SCREEN = 7

DRAG_INITIATION_MOVEMENT_THRESHOLD = 14 # برای درگ با شست و اشاره

# --- متغیرهای وضعیت ---
# برای نیشگون شست و اشاره (Left Click / Drag)
is_thumb_index_pinch_active = False
thumb_index_pinch_start_time = 0.0 # دیگر برای کلیک راست استفاده نمی‌شود، اما برای اطلاعات می‌تواند بماند
thumb_index_pinch_start_screen_pos = None
thumb_index_action_initiated = False # مشخص می‌کند آیا درگ با شست-اشاره شروع شده
is_dragging = False

# برای نیشگون شست و انگشت کوچک (Right Click)
was_thumb_pinky_pinching_prev_frame = False


def threaded_mouse_down(x, y):
    pyautogui.moveTo(x, y)
    time.sleep(0.02)
    pyautogui.mouseDown()
    print(f"Thread: mouseDown event triggered at ({x},{y})")

def threaded_mouse_up():
    pyautogui.mouseUp()
    print(f"Thread: mouseUp event triggered")

cap = cv2.VideoCapture(0)
TARGET_CAM_WIDTH = 640
TARGET_CAM_HEIGHT = 480
cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_CAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_CAM_HEIGHT)

if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

actual_cam_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_cam_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Virtual Mouse (New Right Click Gesture: Thumb-Pinky)")
print(f"Screen: {screen_width}x{screen_height}. Actual Cam: {actual_cam_width}x{actual_cam_height}")
print(f"TI-Pinch Drag Move Thresh: {DRAG_INITIATION_MOVEMENT_THRESHOLD}px")
print(f"TP-Pinch RClick Thresh: {THUMB_PINKY_PINCH_DISTANCE_THRESHOLD} (cam_px)")


while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("Error: Could not read frame from camera.")
        break

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_height_cam_actual, frame_width_cam_actual, _ = frame.shape
    results = hands.process(frame_rgb)

    # وضعیت‌های HUD
    hud_main_action = "No Action" # وضعیت کلی یا مربوط به شست-اشاره
    hud_right_click_event = ""    # برای نمایش لحظه‌ای کلیک راست

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.get_default_hand_landmarks_style(),
                mp_drawing_styles.get_default_hand_connections_style())

            control_landmark_obj = hand_landmarks.landmark[MOUSE_CONTROL_LANDMARK]
            control_x_cam_disp = int(control_landmark_obj.x * frame_width_cam_actual)
            control_y_cam_disp = int(control_landmark_obj.y * frame_height_cam_actual)
            cv2.circle(frame, (control_x_cam_disp, control_y_cam_disp), 7, (0, 255, 255), -1)

            # --- 1. حرکت موس (بدون تغییر) ---
            input_val_for_screen_x = control_landmark_obj.x
            input_val_for_screen_y = control_landmark_obj.y
            # ... (بقیه محاسبات حرکت موس مانند قبل) ...
            screen_norm_x_raw = (input_val_for_screen_x - CAM_ACTIVE_SENSOR_WIDTH_MIN) / \
                                (CAM_ACTIVE_SENSOR_WIDTH_MAX - CAM_ACTIVE_SENSOR_WIDTH_MIN)
            screen_norm_y_raw = (input_val_for_screen_y - CAM_ACTIVE_SENSOR_HEIGHT_MIN) / \
                                (CAM_ACTIVE_SENSOR_HEIGHT_MAX - CAM_ACTIVE_SENSOR_HEIGHT_MIN)

            screen_norm_x_clamped = max(0.0, min(1.0, screen_norm_x_raw))
            screen_norm_y_clamped = max(0.0, min(1.0, screen_norm_y_raw))

            effective_target_x = (1.0 - screen_norm_x_clamped) * screen_width
            target_y_screen_normalized = screen_norm_y_clamped
            target_y_screen_pixels = target_y_screen_normalized * screen_height
            target_y_screen_with_offset = target_y_screen_pixels - Y_OFFSET_SCREEN
            effective_target_y = max(0, min(screen_height - 1, target_y_screen_with_offset))

            potential_mouse_x = last_actual_mouse_x * SMOOTHING_FACTOR + effective_target_x * (1 - SMOOTHING_FACTOR)
            potential_mouse_y = last_actual_mouse_y * SMOOTHING_FACTOR + effective_target_y * (1 - SMOOTHING_FACTOR)

            delta_mouse_x = potential_mouse_x - last_actual_mouse_x
            delta_mouse_y = potential_mouse_y - last_actual_mouse_y
            movement_distance_from_last_pos = math.sqrt(delta_mouse_x**2 + delta_mouse_y**2)

            if movement_distance_from_last_pos >= MIN_MOVEMENT_THRESHOLD_SCREEN or is_dragging:
                pyautogui.moveTo(int(potential_mouse_x), int(potential_mouse_y))
                last_actual_mouse_x = potential_mouse_x
                last_actual_mouse_y = potential_mouse_y

            # --- استخراج لندمارک‌های مورد نیاز برای نیشگون‌ها ---
            thumb_tip_lm = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_finger_tip_lm = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            pinky_tip_lm = hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP]

            # تبدیل به مختصات پیکسلی دوربین
            thumb_tip_px = (thumb_tip_lm.x * frame_width_cam_actual, thumb_tip_lm.y * frame_height_cam_actual)
            index_finger_tip_px = (index_finger_tip_lm.x * frame_width_cam_actual, index_finger_tip_lm.y * frame_height_cam_actual)
            pinky_tip_px = (pinky_tip_lm.x * frame_width_cam_actual, pinky_tip_lm.y * frame_height_cam_actual)

            # --- 2a. منطق کلیک راست با نیشگون شست و انگشت کوچک ---
            dist_thumb_pinky = math.sqrt((thumb_tip_px[0] - pinky_tip_px[0])**2 + (thumb_tip_px[1] - pinky_tip_px[1])**2)
            cv2.putText(frame, f"TP-Dist: {dist_thumb_pinky:.1f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 100), 2)
            
            is_thumb_pinky_currently_pinching = dist_thumb_pinky < THUMB_PINKY_PINCH_DISTANCE_THRESHOLD

            if is_thumb_pinky_currently_pinching and not was_thumb_pinky_pinching_prev_frame and not is_dragging:
                # کلیک راست در موقعیت فعلی موس
                pyautogui.rightClick(x=int(last_actual_mouse_x), y=int(last_actual_mouse_y))
                print(f"Right Click (Thumb-Pinky) at ({int(last_actual_mouse_x)},{int(last_actual_mouse_y)})")
                hud_right_click_event = "RClick (TP)!" # این پیام برای یک فریم نمایش داده می‌شود
            was_thumb_pinky_pinching_prev_frame = is_thumb_pinky_currently_pinching


            # --- 2b. منطق کلیک چپ و درگ با نیشگون شست و اشاره ---
            dist_thumb_index = math.sqrt((thumb_tip_px[0] - index_finger_tip_px[0])**2 + (thumb_tip_px[1] - index_finger_tip_px[1])**2)
            cv2.putText(frame, f"TI-Dist: {dist_thumb_index:.1f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            current_time = time.time() # زمان فعلی برای منطق شست-اشاره
            if dist_thumb_index < THUMB_INDEX_PINCH_DISTANCE_THRESHOLD: # نیشگون شست-اشاره فعال است
                if not is_thumb_index_pinch_active: # نیشگون شست-اشاره به تازگی شروع شده
                    is_thumb_index_pinch_active = True
                    is_dragging = False # مهم: ریست کردن وضعیت درگ برای این نیشگون جدید
                    thumb_index_action_initiated = False
                    thumb_index_pinch_start_time = current_time # گرچه برای کلیک راست استفاده نمی‌شود
                    thumb_index_pinch_start_screen_pos = (last_actual_mouse_x, last_actual_mouse_y)
                    hud_main_action = f"TI-Pinch (Mov>{DRAG_INITIATION_MOVEMENT_THRESHOLD}px:Drg)"
                else: # نیشگون شست-اشاره ادامه دارد
                    if is_dragging:
                        hud_main_action = "Dragging"
                    elif not thumb_index_action_initiated:
                        movement_from_pinch_start = math.sqrt(
                            (last_actual_mouse_x - thumb_index_pinch_start_screen_pos[0])**2 +
                            (last_actual_mouse_y - thumb_index_pinch_start_screen_pos[1])**2
                        )
                        if movement_from_pinch_start > DRAG_INITIATION_MOVEMENT_THRESHOLD:
                            is_dragging = True
                            thumb_index_action_initiated = True
                            thread_down = threading.Thread(target=threaded_mouse_down, args=(int(thumb_index_pinch_start_screen_pos[0]), int(thumb_index_pinch_start_screen_pos[1])))
                            thread_down.start()
                            print(f"Main: Drag Start initiated (TI-Pinch, movement: {movement_from_pinch_start:.1f}px)")
                            hud_main_action = "Dragging"
                        else: # حرکت برای درگ کافی نبوده، و دیگر شرط زمانی برای کلیک راست نداریم
                            hud_main_action = f"TI-Pinch (Mov>{DRAG_INITIATION_MOVEMENT_THRESHOLD}px:Drg)"
            
            else: # نیشگون شست-اشاره فعال نیست (انگشتان باز شده‌اند)
                if is_thumb_index_pinch_active: # نیشگون شست-اشاره به تازگی رها شده
                    if is_dragging:
                        thread_up = threading.Thread(target=threaded_mouse_up)
                        thread_up.start()
                        print(f"Main: Drag End initiated (Dropped)")
                        hud_main_action = "Dropped!"
                    elif not thumb_index_action_initiated: # اگر درگ شروع نشده بود، پس کلیک چپ است
                        pyautogui.click(button='left', x=int(thumb_index_pinch_start_screen_pos[0]), y=int(thumb_index_pinch_start_screen_pos[1]))
                        print(f"Left Click performed (TI-Pinch)")
                        hud_main_action = "Left Click!"
                    
                    is_thumb_index_pinch_active = False
                    thumb_index_action_initiated = False
                    if is_dragging: is_dragging = False
    
    else: # هیچ دستی پیدا نشد
        # ریست کردن وضعیت‌های نیشگون‌ها اگر دستی خارج شد
        if is_thumb_index_pinch_active:
            if is_dragging:
                thread_up = threading.Thread(target=threaded_mouse_up)
                thread_up.start()
                print("Drag cancelled (hand lost), mouseUp thread initiated.")
            is_thumb_index_pinch_active = False
            is_dragging = False
            thumb_index_action_initiated = False
        was_thumb_pinky_pinching_prev_frame = False
        hud_main_action = "No Hand Detected"

    # تعیین وضعیت نهایی HUD با اولویت کلیک راست لحظه‌ای
    final_hud_status = hud_right_click_event if hud_right_click_event else hud_main_action
    if not results.multi_hand_landmarks and final_hud_status == "No Action": # اگر دستی نبود و اکشن دیگری هم نبود
        final_hud_status = "No Hand Detected"
    elif results.multi_hand_landmarks and final_hud_status == "No Action" and not is_thumb_index_pinch_active and not was_thumb_pinky_pinching_prev_frame : # اگر دست هست ولی هیچ نیشگونی فعال نیست
        final_hud_status = "Hand Detected"


    text_color = (200, 200, 200)
    if "Click!" in final_hud_status or "Dropped!" in final_hud_status or "RClick (TP)!" in final_hud_status: text_color = (0, 255, 0)
    elif "Dragging" in final_hud_status: text_color = (255, 165, 0)
    elif "Pinch" in final_hud_status or "Detected" in final_hud_status: text_color = (0, 165, 255)
    elif "No Hand" in final_hud_status: text_color = (0, 0, 255)

    cv2.putText(frame, final_hud_status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
    cv2.imshow('Virtual Mouse', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("Program terminated.")
print("Program terminated.")