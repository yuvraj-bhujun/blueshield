import hashlib
import os
import numpy as np
import scipy.io.wavfile
import torch
from google import genai
from transformers import AutoTokenizer, VitsModel

API_KEY = "..."

# Directory to save generated audio files
CACHE_DIR = "audio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# =========================================================================
# ⚡ OPTIMIZATION 1: PRE-LOAD TTS MODEL ON STARTUP (Saves 5-10s per request)
# =========================================================================
print("Loading Mauritian Creole TTS model into memory...")
TTS_MODEL_NAME = "facebook/mms-tts-mfe"
TTS_TOKENIZER = AutoTokenizer.from_pretrained(TTS_MODEL_NAME)
TTS_MODEL = VitsModel.from_pretrained(TTS_MODEL_NAME)
TTS_MODEL.eval()
print("✅ TTS Model ready!")


def english_to_mauritian_creole_speech(
    english_text: str, api_key: str, cache_key: str = None
) -> str:
    # Create a unique filename based on vessel ID or text hash
    if not cache_key:
        cache_key = hashlib.md5(english_text.encode("utf-8")).hexdigest()

    cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}.wav")

    # ⚡ OPTIMIZATION 2: DISK CACHE (Return existing audio instantly if already generated)
    if os.path.exists(cached_file_path):
        print(f"⚡ Returning cached audio instantly: {cached_file_path}")
        return cached_file_path

    print(f"Generating new Creole speech for: {cache_key}...")

    # 1. Translate using Gemma 4
    client = genai.Client(api_key=api_key)
    prompt = (
        "You are an expert English to Mauritian Creole (Kreol Morisien) translator. "
        "Translate the following English text into natural Mauritian Creole. "
        "Return ONLY the translated Creole text without quotes or explanation.\n\n"
        f"English Text: {english_text}"
    )

    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it", contents=prompt
    )
    creole_text = response.text.strip()
    print(f"Creole Translation: {creole_text}")

    # 2. Synthesize using pre-loaded model
    inputs = TTS_TOKENIZER(creole_text, return_tensors="pt")
    with torch.no_grad():
        output = TTS_MODEL(**inputs).waveform

    sampling_rate = TTS_MODEL.config.sampling_rate
    audio_data = output.squeeze().cpu().numpy()
    audio_data_int16 = (audio_data * 32767).astype(np.int16)

    # Save to cache folder
    scipy.io.wavfile.write(
        cached_file_path, rate=sampling_rate, data=audio_data_int16
    )

    return cached_file_path