import pyaudio
import torch
import numpy as np
import time
import wave
import os
import requests
import state
import local_voice

print("[System: Booting audio cortex (Silero VAD + Groq Whisper API)...]")

# Auto-load .env so the key persists across terminal sessions.
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

_vad_model = None
_utils = None

def _get_vad_model():
    global _vad_model, _utils
    if _vad_model is None:
        try:
            val_model, utils_set = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)
            _vad_model = val_model
            _utils = utils_set
        except Exception as e:
            print(f"[System Error: PyTorch VAD Load Failed: {e}]")
            raise e
    return _vad_model, _utils

def get_target_input_index(p: pyaudio.PyAudio) -> int|None:
    target_index = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            name = info.get('name', '')
            if "Stereo Mix" in name or "Virtual" in name or "ManyCam" in name:
                continue
            if "Array" in name or "Realtek" in name or "Built-in" in name:
                target_index = i
                break
    return target_index

def listen_and_transcribe() -> str:
    p = pyaudio.PyAudio()
    target_index = get_target_input_index(p)
    
    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, 
                    input=True, input_device_index=target_index, 
                    frames_per_buffer=CHUNK)
                    
    frames = []
    has_started = False
    speech_duration = 0.0
    silence_duration = 0.0
    vocalizing_accum = 0.0
    
    print("Friday is listening...")
    
    try:
        while True:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
            except Exception:
                break
                
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            # Silero expects float32
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            tensor = torch.from_numpy(audio_float32)
            
            v_model, _ = _get_vad_model()
            confidence = v_model(tensor, RATE).item()
            
            if confidence > 0.6:
                vocalizing_accum += (CHUNK / RATE)
                if vocalizing_accum >= 0.2:  # Cooling down pop filter!
                    if not has_started:
                        has_started = True
                        print("[System: Audio detected! Transcribing...]")
                        if getattr(state.is_talking, 'value', False):
                            local_voice.interrupt()
                    speech_duration += (CHUNK / RATE)
                    silence_duration = 0.0
                    frames.append(data)
            else:
                if has_started:
                    frames.append(data)
                    silence_duration += (CHUNK / RATE)
                    if silence_duration > 1.2:
                        break
                else:
                    vocalizing_accum = 0.0 # reset pop filter
                    
    except KeyboardInterrupt: pass

    stream.stop_stream()
    stream.close()
    p.terminate()

    if not frames:
        return ""
        
    wf = wave.open("temp_audio.wav", 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    try:
        if not GROQ_API_KEY:
            print("[System WARNING: GROQ_API_KEY missing! You must set it in environment arrays. Aborting Groq STT.]")
            return ""
            
        with open("temp_audio.wav", "rb") as f:
            files = { "file": ("temp_audio.wav", f, "audio/wav") }
            data = { "model": "whisper-large-v3" }
            headers = { "Authorization": f"Bearer {GROQ_API_KEY}" }
            resp = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
            
        if resp.status_code == 200:
            text = resp.json().get("text", "").strip()
        else:
            print(f"[Groq API Error]: {resp.text}")
            text = ""
            
        if os.path.exists("temp_audio.wav"):
            os.remove("temp_audio.wav")
        return text
    except Exception as e:
        print(f"[Hardware/Cloud Error]: {e}")
        return ""
