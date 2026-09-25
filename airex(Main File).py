import speech_recognition as sr
import sounddevice as sd
import numpy as np
from scipy.io import wavfile
import os
import time
import json
import webbrowser
import urllib.parse
import random
import threading
import math
from datetime import datetime
from pathlib import Path
from openai import OpenAI

try:
    import pygame
except ImportError:
    pygame = None

# API configuration
#
# Put exactly one of these environment variables in rex/.env, or set it before starting REX:
#   OPENAI_API_KEY       for the OpenAI API
#   OPENROUTER_API_KEY   for OpenRouter (keys that begin with "sk-or-v1-")
# Never paste a secret API key into this source file.
def load_local_env():
    """Load simple KEY=value entries from rex/.env without another dependency."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if openrouter_api_key:
    MODEL = os.getenv("REX_MODEL", "openai/gpt-4o-mini")
    client = OpenAI(
        api_key=openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )
elif openai_api_key:
    MODEL = os.getenv("REX_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=openai_api_key)
else:
    MODEL = os.getenv("REX_MODEL", "gpt-4o-mini")
    client = None

conversation = []


class AssistantState:
    def __init__(self):
        self.is_running = True
        self.is_muted = False
        self.awaiting_follow_up = False
        self.status = "IDLE"
        self.audio_energy = 0.0


state = AssistantState()

SYSTEM_PROMPT = """
You are REX, a personal AI desktop assistant.
You are based on Jarvis from Iron Man. Your relationshiop with the user is like Jarvis and Tony Stark.


Your personality:
- Intelligent
- Butler-like
- Helpful
- Confident
- Slightly futuristic
- Friendly
- Concise (the user is impatient and wants answers in 1-2 short sentences)
- You may call the user "sir" occasionally, every other sentence or so

You are controlling a Python voice assistant.

You have access to tools that allow you to:
- Open websites
- Search Google
- Get the current time and date
- Set timers
- Tell jokes
- Save notes
- Read saved notes
- Remember information
- Forget information
- Open applications
- Shut down REX
- Mute and unmute REX
- Assist with basic questions and knowledge

Use tools whenever the user asks you to perform an action.
For normal questions, answer normally.
Never claim that you performed an action unless the tool actually succeeded.
Do not execute arbitrary operating-system commands.
For potentially dangerous or destructive actions, do not perform them unless there is an explicitly defined safe tool for that action.
"""

memory_file = "rex_memory.json"
notes_file = "rex_notes.txt"


def speak(text):
    print(f"\n🤖 REX: {text}")
    state.status = "SPEAKING"
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 180)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[Voice Error]: {e}")
    finally:
        if state.is_running:
            state.status = "IDLE"


def record_adaptive_audio(sample_rate=16000, chunk_size=1024):
    channels = 1
    silence_threshold = 500
    silence_duration = 1.2
    audio_buffer = []
    speaking = False
    silence_chunks = 0
    max_silence_chunks = int((silence_duration * sample_rate) / chunk_size)

    state.status = "LISTENING"
    with sd.InputStream(samplerate=sample_rate, channels=channels, dtype="int16") as stream:
        while True:
            data, overflow = stream.read(chunk_size)
            audio_buffer.append(data)
            energy = np.linalg.norm(data)
            state.audio_energy = min(float(energy), 4000.0)

            if not speaking and energy > silence_threshold:
                speaking = True

            if speaking:
                if energy < silence_threshold:
                    silence_chunks += 1
                else:
                    silence_chunks = 0

                if silence_chunks > max_silence_chunks:
                    break

            if not speaking and len(audio_buffer) > int((5 * sample_rate) / chunk_size):
                audio_buffer = audio_buffer[-int((2 * sample_rate) / chunk_size):]

    audio_data = np.concatenate(audio_buffer, axis=0)
    state.audio_energy = 0.0
    state.status = "IDLE"
    filename = "rex_temp.wav"
    wavfile.write(filename, sample_rate, audio_data)
    return filename


def run_hud():
    """Run the animated REX interface in a separate window."""
    if pygame is None:
        print("[HUD Error]: Pygame is not installed. Run: pip install pygame")
        return

    pygame.init()
    width, height = 600, 600
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("REX AI - Neural Interface")
    clock = pygame.time.Clock()
    center = (width // 2, height // 2)
    angle = 0.0
    font = pygame.font.SysFont("Consolas", 18)

    while state.is_running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                state.is_running = False

        screen.fill((10, 12, 18))
        angle += 0.03

        if state.is_muted:
            primary_color = (200, 50, 50)
            status_label = "MUTED"
        elif state.status == "LISTENING":
            primary_color = (0, 255, 200)
            status_label = "LISTENING"
        elif state.status == "SPEAKING":
            primary_color = (0, 150, 255)
            status_label = "SPEAKING"
        elif state.status == "THINKING":
            primary_color = (180, 90, 255)
            status_label = "THINKING"
        else:
            primary_color = (0, 200, 150)
            status_label = "IDLE"

        pulse = math.sin(angle) * 5 + (state.audio_energy / 200)
        for index in range(3):
            radius = 120 + index * 25 + pulse
            rect = pygame.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
            start_angle = angle * (1 if index % 2 == 0 else -1) + (index * math.pi / 3)
            pygame.draw.arc(screen, primary_color, rect, start_angle, start_angle + math.pi / 2, 2)

        core_radius = max(20, int(40 + pulse * 2))
        pygame.draw.circle(screen, primary_color, center, core_radius, 2)
        pygame.draw.circle(screen, (255, 255, 255), center, max(5, core_radius - 15))

        title = font.render("REX // NEURAL INTERFACE", True, primary_color)
        status = font.render(f"STATUS: {status_label}", True, primary_color)
        screen.blit(title, (20, 20))
        screen.blit(status, (20, height - 40))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def transcribe_file(filename):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(filename) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio).lower()
        return text
    except Exception:
        return ""
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def get_time():
    return datetime.now().strftime("%I:%M %p")


def get_date():
    return datetime.now().strftime("%A, %B %d, %Y")


def open_website(site):
    websites = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "spotify": "https://open.spotify.com",
        "canvas": "https://bcp.instructure.com",
        "school": "https://bcp.instructure.com",
        "portal": "https://b.bcp.org",
        "bellarmine": "https://bcp.org",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "reddit": "https://reddit.com"
    }

    site = site.lower().strip()
    if site in websites:
        webbrowser.open(websites[site])
        return f"Opened {site}."

    if not site.startswith("http"):
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(site))
        return f"I searched Google for {site}."

    webbrowser.open(site)
    return f"Opened {site}."


def google_search(query):
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    webbrowser.open(url)
    return f"Searching Google for {query}."


def tell_joke():
    jokes = [
        "Why do programmers wear glasses? Because they can't C sharp.",
        "There are 10 types of people in the world: those who understand binary and those who don't.",
        "Why did the computer go to the doctor? It had a virus.",
        "How many programmers does it take to change a light bulb? None. That's a hardware problem.",
        "I told my computer I needed a break. Now it keeps sending me vacation ads.",
        "Why was the Python programmer so calm? Because they knew how to handle exceptions."
    ]
    return random.choice(jokes)


def save_note(note):
    try:
        with open(notes_file, "a", encoding="utf-8") as file:
            timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
            file.write(f"[{timestamp}] {note}\n")
        return "I saved that note."
    except Exception as e:
        return f"I couldn't save the note: {e}"


def read_notes():
    if not os.path.exists(notes_file):
        return "You don't have any saved notes."
    try:
        with open(notes_file, "r", encoding="utf-8") as file:
            notes = file.read().strip()
        if not notes:
            return "You don't have any saved notes."
        return notes
    except Exception as e:
        return f"I couldn't read your notes: {e}"


def remember(key, value):
    memory = {}
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as file:
                memory = json.load(file)
        except Exception:
            memory = {}
    memory[key] = value
    try:
        with open(memory_file, "w", encoding="utf-8") as file:
            json.dump(memory, file, indent=4)
        return f"I'll remember that {key} is {value}."
    except Exception as e:
        return f"I couldn't save that memory: {e}"


def recall_memory():
    if not os.path.exists(memory_file):
        return "I don't have any saved memories."
    try:
        with open(memory_file, "r", encoding="utf-8") as file:
            memory = json.load(file)
        if not memory:
            return "I don't have any saved memories."
        result = [f"{key}: {value}" for key, value in memory.items()]
        return "\n".join(result)
    except Exception as e:
        return f"I couldn't access my memory: {e}"


def forget_memory(key):
    if not os.path.exists(memory_file):
        return "I don't have any memories to forget."
    try:
        with open(memory_file, "r", encoding="utf-8") as file:
            memory = json.load(file)
        if key not in memory:
            return f"I don't have a memory about {key}."
        del memory[key]
        with open(memory_file, "w", encoding="utf-8") as file:
            json.dump(memory, file, indent=4)
        return f"I forgot the memory about {key}."
    except Exception as e:
        return f"I couldn't forget that memory: {e}"


def set_timer(seconds, description):
    def timer_finished():
        time.sleep(seconds)
        speak(f"Sir your timer for {description} is finished.")

    thread = threading.Thread(target=timer_finished, daemon=True)
    thread.start()

    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if minutes > 0:
        duration = f"{minutes} minute" + ("s" if minutes != 1 else "")
        if remaining_seconds > 0:
            duration += f" and {remaining_seconds} seconds"
    else:
        duration = f"{seconds} seconds"

    return f"Timer set for {duration}."


def open_application(application):
    allowed_apps = {
        "calculator": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe"
    }
    app = application.lower().strip()
    if app not in allowed_apps:
        return f"I don't have permission to open the application '{application}'."
    try:
        os.startfile(allowed_apps[app])
        return f"Opening {application}."
    except Exception as e:
        return f"I couldn't open {application}: {e}"


def shutdown_rex():
    return "SHUTDOWN"


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current local time.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "Get the current local date.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a website or service.",
            "parameters": {
                "type": "object",
                "properties": {"site": {"type": "string", "description": "Website or service to open."}},
                "required": ["site"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Search Google for something.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for."}},
                "required": ["query"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tell_joke",
            "description": "Tell the user a joke.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save a note for the user.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string", "description": "The note to save."}},
                "required": ["note"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_notes",
            "description": "Read the user's saved notes.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Remember a piece of information for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Name of the memory."},
                    "value": {"type": "string", "description": "Information to remember."}
                },
                "required": ["key", "value"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Recall information saved in REX's memory.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forget_memory",
            "description": "Forget a saved memory.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "Memory to delete."}},
                "required": ["key"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a timer in seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer", "description": "Number of seconds."},
                    "description": {"type": "string", "description": "What the timer is for."}
                },
                "required": ["seconds", "description"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open one of the approved desktop applications.",
            "parameters": {
                "type": "object",
                "properties": {"application": {"type": "string", "description": "Application to open."}},
                "required": ["application"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_rex",
            "description": "Stop the REX assistant.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True
        }
    }
]


def run_tool(name, arguments):
    if name == "get_time":
        return get_time()
    if name == "get_date":
        return get_date()
    if name == "open_website":
        return open_website(arguments["site"])
    if name == "google_search":
        return google_search(arguments["query"])
    if name == "tell_joke":
        return tell_joke()
    if name == "save_note":
        return save_note(arguments["note"])
    if name == "read_notes":
        return read_notes()
    if name == "remember":
        return remember(arguments["key"], arguments["value"])
    if name == "recall_memory":
        return recall_memory()
    if name == "forget_memory":
        return forget_memory(arguments["key"])
    if name == "set_timer":
        return set_timer(arguments["seconds"], arguments["description"])
    if name == "open_application":
        return open_application(arguments["application"])
    if name == "shutdown_rex":
        return shutdown_rex()
    return "Unknown tool."


def ask_ai(user_text):
    global conversation

    if client is None:
        print("[AI Error]: No API key configured.")
        return "My AI key is not configured yet."

    if not conversation:
        conversation.append({"role": "system", "content": SYSTEM_PROMPT})

    conversation.append({"role": "user", "content": user_text})

    state.status = "THINKING"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=conversation,
            tools=tools
        )

        response_message = response.choices[0].message

        while response_message.tool_calls:
            conversation.append(response_message)

            for tool_call in response_message.tool_calls:
                name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                print(f"⚙️ Tool: {name}")
                result = run_tool(name, arguments)
                print(f"   → {result}")

                if result == "SHUTDOWN":
                    return "SHUTDOWN"

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })

            response = client.chat.completions.create(
                model=MODEL,
                messages=conversation,
                tools=tools
            )
            response_message = response.choices[0].message

        final_response = response_message.content.strip()
        conversation.append({"role": "assistant", "content": final_response})
        return final_response

    except Exception as e:
        print(f"[AI Error]: {e}")
        return "I'm having trouble connecting to my AI system."
    finally:
        if state.is_running and state.status == "THINKING":
            state.status = "IDLE"


def asks_for_follow_up(text):
    normalized = " ".join(text.lower().split())
    phrases = (
        "can i help you with anything",
        "can i help u with anything",
        "how else can i help",
        "may i assist further",
        "can i assist further",
    )
    return any(phrase in normalized for phrase in phrases)


def declines_follow_up(text):
    normalized = " ".join(text.lower().replace(",", " ").split()).rstrip(".!?")
    return normalized in {
        "no",
        "no thanks",
        "no thank you",
        "that's all",
        "that is all",
        "nothing else",
    }


def main():
    print()
    print("=========================================")
    print("             🤖 REX 2.0")
    print("=========================================")
    print("AI-Powered Personal Assistant")
    print("-----------------------------------------")
    print("Wake word: REX")
    print("AI: ONLINE")
    print("Voice recognition: ONLINE")
    print("Memory: ENABLED")
    print("Tools: ENABLED")
    print("=========================================")
    print()

    hud_thread = threading.Thread(target=run_hud, daemon=True)
    hud_thread.start()

    while state.is_running:
        try:
            audio_file = record_adaptive_audio()
            spoken_text = transcribe_file(audio_file)

            if spoken_text:
                print(f"🎤 Heard: {spoken_text}")

                if state.awaiting_follow_up:
                    state.awaiting_follow_up = False

                    if declines_follow_up(spoken_text):
                        speak("Understood, sir.")
                        continue

                    print("⚡ Follow-up command received")
                    response = ask_ai(spoken_text)

                    if response == "SHUTDOWN":
                        speak("Goodbye sir.")
                        state.is_running = False
                    else:
                        speak(response)
                        state.awaiting_follow_up = asks_for_follow_up(response)
                elif "rex" in spoken_text:
                    clean_command = spoken_text.replace("rex", "", 1).strip()
                    print("⚡ REX activated")

                    if not clean_command:
                        speak("Yes sir?")
                    else:
                        print("🧠 Thinking...")
                        response = ask_ai(clean_command)

                        if response == "SHUTDOWN":
                            speak("Goodbye sir.")
                            state.is_running = False
                        else:
                            speak(response)
                            state.awaiting_follow_up = asks_for_follow_up(response)

            time.sleep(0.3)

        except KeyboardInterrupt:
            print()
            speak("Shutting down.")
            state.is_running = False
            break
        except Exception as e:
            print(f"[REX Error]: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
