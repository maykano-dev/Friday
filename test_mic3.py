import speech_recognition as sr
m=sr.Microphone(device_index=3)
r=sr.Recognizer()
try:
    with m as source:
        r.adjust_for_ambient_noise(source, 1)
        print("ENERGY_3:", r.energy_threshold)
except Exception as e:
    print("FAILED_3:", e)

m=sr.Microphone(device_index=14)
try:
    with m as source:
        r.adjust_for_ambient_noise(source, 1)
        print("ENERGY_14:", r.energy_threshold)
except Exception as e:
    print("FAILED_14:", e)
