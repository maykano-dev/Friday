import speech_recognition as sr

print("--- AVAILABLE AUDIO DEVICES ---")
for index, name in enumerate(sr.Microphone.list_microphone_names()):
    print(f"[{index}] {name}")

print("\n--- TESTING DEFAULT AUDIO CHANNEL ---")
r = sr.Recognizer()
r.dynamic_energy_threshold = True # Let it auto-adjust just for the test

try:
    with sr.Microphone() as source:
        print("Calibrating to room noise for 2 seconds (Be quiet)...")
        r.adjust_for_ambient_noise(source, duration=2)
        print(f">>> Base energy threshold set by Windows: {r.energy_threshold}")
        
        print("\nSpeak loudly into your laptop right now!")
        audio = r.listen(source, timeout=5, phrase_time_limit=5)
        print(">>> SUCCESS: Audio buffer captured!")
except sr.WaitTimeoutError:
    print(">>> FAILED: Timed out. Microphone heard absolutely nothing.")
except Exception as e:
    print(f">>> FAILED: Hardware blocked. Details: {e}")
