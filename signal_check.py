import sounddevice as sd
import numpy as np

def callback(indata, frames, time, status):
    volume_norm = np.linalg.norm(indata) * 10
    print("|" * int(volume_norm)) # This creates a live volume bar

with sd.InputStream(callback=callback):
    print("Speak now! You should see a moving bar below:")
    sd.sleep(10000)
