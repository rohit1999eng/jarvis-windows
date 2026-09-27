"""
JARVIS main loop:
  1. Listen for the wake word ("Hey Jarvis")
  2. Acknowledge and record your spoken command
  3. Transcribe it locally with faster-whisper
  4. Send it to dolphin-llama3:8b via Ollama (with tool-calling support)
  5. Speak the answer with Piper
  6. Go back to step 1
"""
import random
import traceback

from config import WAKE_ACK_PHRASES
from wake_word import wait_for_wake_word
from stt import record_command, transcribe
from tts import speak
from llm import Conversation, ask


def main():
    conversation = Conversation()
    print("=== JARVIS is online ===")
    speak("Systems online.")

    while True:
        try:
            wait_for_wake_word()
            speak(random.choice(WAKE_ACK_PHRASES))

            audio = record_command()
            user_text = transcribe(audio)

            if not user_text.strip():
                speak("I didn't catch that.")
                continue

            print(f"[you] {user_text}")

            if user_text.strip().lower() in ("stop", "shut down", "goodbye", "go to sleep"):
                speak("Going to sleep. Say the wake word to bring me back.")
                continue

            reply = ask(conversation, user_text)
            speak(reply)

        except KeyboardInterrupt:
            speak("Shutting down.")
            break
        except Exception as e:
            print("[error]", traceback.format_exc())
            speak("Sorry, I ran into an error.")


if __name__ == "__main__":
    main()
