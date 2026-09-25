import threading
import time
import math
import os
import random
import urllib.parse
from datetime import datetime

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
import speech_recognition as sr
import pyttsx3

import pygame
import psutil
import pyautogui

# Web Automation
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# ==========================================
# GLOBAL STATE
# ==========================================
class AssistantState:
    def __init__(self):
        self.is_muted = False
        self.is_running = True
        self.status = "IDLE"  # IDLE, LISTENING, SPEAKING
        self.audio_energy = 0.0
        self.driver = None

state = AssistantState()

# ==========================================
# TTS ENGINE (Thread-Safe)
# ==========================================
def inject_sir(text):
    text_clean = text.strip()
    position = random.choice([0, 1, 2])
    
    if position == 0:
        return f"Sir, {text_clean[0].lower() + text_clean[1:]}" if len(text_clean) > 1 else f"Sir, {text_clean}"
    elif position == 1:
        if text_clean.endswith(('.', '!', '?')):
            punct = text_clean[-1]
            return f"{text_clean[:-1]}, sir{punct}"
        return f"{text_clean}, sir."
    else:
        words = text_clean.split(" ")
        if len(words) > 3:
            words.insert(2, "sir,")
            return " ".join(words)
        else:
            return f"{text_clean}, sir."

def speak(text):
    def run_speech():
        state.status = "SPEAKING"
        text_with_sir = inject_sir(text)
        print(f"🤖 REX: {text_with_sir}")
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 180)
            engine.say(text_with_sir)
            engine.runAndWait()
        except Exception as e:
            print(f"[Voice Error]: {e}")
        finally:
            state.status = "IDLE"

    threading.Thread(target=run_speech, daemon=True).start()

# ==========================================
# PYGAME HUD VISUALIZER
# ==========================================
def run_hud():
    pygame.init()
    WIDTH, HEIGHT = 600, 600
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("REX AI - Neural Interface")
    clock = pygame.time.Clock()

    CENTER = (WIDTH // 2, HEIGHT // 2)
    angle = 0

    while state.is_running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                state.is_running = False

        screen.fill((10, 12, 18))  # Dark cyan/black background
        angle += 0.03

        # Color palette depending on state
        if state.is_muted:
            primary_color = (200, 50, 50)    # Red
        elif state.status == "LISTENING":
            primary_color = (0, 255, 200)   # Bright Cyan
        elif state.status == "SPEAKING":
            primary_color = (0, 150, 255)   # Vivid Blue
        else:
            primary_color = (0, 200, 150)   # Teal IDLE

        # Dynamic expansion factor based on audio energy
        pulse = math.sin(angle) * 5 + (state.audio_energy / 200)

        # Outer Rotating Arc Ring
        for i in range(3):
            r = 120 + i * 25 + pulse
            rect = pygame.Rect(CENTER[0] - r, CENTER[1] - r, r * 2, r * 2)
            start_angle = angle * (1 if i % 2 == 0 else -1) + (i * math.pi / 3)
            pygame.draw.arc(screen, primary_color, rect, start_angle, start_angle + math.pi / 2, 2)

        # Inner Core
        core_radius = max(20, int(40 + pulse * 2))
        pygame.draw.circle(screen, primary_color, CENTER, core_radius, 2)
        pygame.draw.circle(screen, (255, 255, 255), CENTER, max(5, core_radius - 15))

        # Status Overlay
        font = pygame.font.SysFont("Consolas", 18)
        status_text = f"STATUS: {state.status}" if not state.is_muted else "STATUS: MUTED"
        text_surface = font.render(status_text, True, primary_color)
        screen.blit(text_surface, (20, HEIGHT - 40))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

# ==========================================
# BROWSER AUTOMATION (SELENIUM)
# ==========================================
def init_browser():
    try:
        options = webdriver.ChromeOptions()
        options.add_experimental_option("detach", True)
        state.driver = webdriver.Chrome(options=options)
        speak("Browser automation initialized.")
    except Exception as e:
        print(f"[Browser Init Error]: {e}")
        speak("Could not initialize browser controller. Falling back to standard web navigation.")

def handle_browser_command(command):
    if not state.driver:
        init_browser()
    
    driver = state.driver
    if not driver:
        return

    if "open tab" in command or "new tab" in command:
        driver.execute_script("window.open('https://google.com', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        speak("Opened a new tab.")

    elif "close tab" in command or "close this tab" in command:
        if len(driver.window_handles) > 0:
            driver.close()
            if len(driver.window_handles) > 0:
                driver.switch_to.window(driver.window_handles[-1])
            speak("Tab closed.")
        else:
            speak("No open tabs to close.")

    elif "next tab" in command or "switch tab" in command:
        if len(driver.window_handles) > 1:
            curr_idx = driver.window_handles.index(driver.current_window_handle)
            next_idx = (curr_idx + 1) % len(driver.window_handles)
            driver.switch_to.window(driver.window_handles[next_idx])
            speak(f"Switched to tab {next_idx + 1}.")
        else:
            speak("Only one tab is currently open.")

    elif "youtube search" in command or "play on youtube" in command:
        query = command.replace("youtube search", "").replace("play on youtube", "").strip()
        encoded = urllib.parse.quote(query)
        driver.get(f"https://www.youtube.com/results?search_query={encoded}")
        speak(f"Searching YouTube for {query}.")

# ==========================================
# COMMAND PROCESSOR
# ==========================================
def execute_command(command):
    # Mute Control
    if "mute" in command or "shut up" in command or "stop listening" in command:
        state.is_muted = True
        speak("Muting audio capture systems now.")
        return True

    # Tab & Web Control
    elif any(k in command for k in ["open tab", "close tab", "next tab", "switch tab", "youtube search"]):
        handle_browser_command(command)

    # Web Applications
    elif "canvas" in command or "school" in command:
        speak("Opening Canvas...")
        if state.driver:
            state.driver.get("https://bcp.instructure.com")

    elif "portal" in command or "bellarmine" in command:
        speak("Opening Student Portal...")
        if state.driver:
            state.driver.get("https://b.bcp.org/b/dashboard/index")

    # System Status Diagnostics
    elif "system status" in command or "cpu" in command or "battery" in command:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        bat_str = f"{battery.percent}%" if battery else "Desktop System (N/A)"
        speak(f"CPU load is at {cpu} percent. Memory utilization is at {ram} percent. Battery level is {bat_str}.")

    # System Media / Volume Control
    elif "volume up" in command:
        pyautogui.press("volumeup", presses=5)
        speak("Increasing volume.")

    elif "volume down" in command:
        pyautogui.press("volumedown", presses=5)
        speak("Decreasing volume.")

    elif "pause" in command or "play music" in command:
        pyautogui.press("playpause")
        speak("Toggled media state.")

    # Application Launchers
    elif "open code" in command or "open vs code" in command:
        speak("Launching Visual Studio Code...")
        os.system("code .")

    # Utilities
    elif "time" in command:
        current_time = datetime.now().strftime("%I:%M %p")
        speak(f"The time is {current_time}.")

    elif "shutdown" in command or "turn off" in command:
        speak("Deactivating system cores. Goodbye!")
        if state.driver:
            state.driver.quit()
        return False

    else:
        speak("Command recognized, but no matching routine was found.")

    return True

# ==========================================
# AUDIO PROCESSING
# ==========================================
def record_adaptive_audio(sample_rate=16000, chunk_size=1024):
    SILENCE_THRESHOLD = 800
    SILENCE_DURATION = 0.8
    audio_buffer = []
    speaking = False
    silence_chunks = 0
    max_silence_chunks = int((SILENCE_DURATION * sample_rate) / chunk_size)

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
        while state.is_running:
            data, overflow = stream.read(chunk_size)
            audio_buffer.append(data)
            energy = np.linalg.norm(data)
            state.audio_energy = energy

            if not speaking and energy > SILENCE_THRESHOLD:
                speaking = True
                state.status = "LISTENING"

            if speaking:
                if energy < SILENCE_THRESHOLD:
                    silence_chunks += 1
                else:
                    silence_chunks = 0

                if silence_chunks > max_silence_chunks:
                    break

            if not speaking and len(audio_buffer) > int((4 * sample_rate) / chunk_size):
                audio_buffer = audio_buffer[-int((1.5 * sample_rate) / chunk_size):]

    if not state.is_running:
        return None

    audio_data = np.concatenate(audio_buffer, axis=0)
    filename = "background_temp.wav"
    wavfile.write(filename, sample_rate, audio_data)
    return filename

def transcribe_file(filename):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(filename) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio).lower()
        return text
    except:
        return ""
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# ==========================================
# MAIN LOOP
# ==========================================
def main():
    # Launch HUD visualizer in a background thread
    hud_thread = threading.Thread(target=run_hud, daemon=True)
    hud_thread.start()

    print("=========================================")
    print("🤖 REX SYSTEM ONLINE - VISUAL INTERFACE ACTIVE")
    print("=========================================")

    while state.is_running:
        audio_file = record_adaptive_audio()
        if not audio_file:
            break

        spoken_text = transcribe_file(audio_file)
        state.status = "IDLE"

        if spoken_text:
            if state.is_muted:
                if "rex" in spoken_text and ("unmute" in spoken_text or "wake up" in spoken_text or "listen" in spoken_text):
                    state.is_muted = False
                    speak("System unmuted. Ready for commands.")
                continue

            print(f"[Mic Heard]: {spoken_text}")
            if "rex" in spoken_text:
                clean_command = spoken_text.replace("rex", "").strip()
                if not clean_command:
                    speak("Online. How may I assist you?")
                else:
                    state.is_running = execute_command(clean_command)

        time.sleep(0.1)

if __name__ == "__main__":
    main()