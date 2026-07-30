import hashlib
import os
import json
import requests
import numpy as np
import scipy.io.wavfile
import torch

from transformers import AutoTokenizer, VitsModel


# =========================================================================
# LOCAL GEMMA THROUGH OLLAMA
# =========================================================================

OLLAMA_URL = "http://localhost:11434/api/generate"

GEMMA_MODEL = "gemma4:e2b"


# Directory to save generated audio files
CACHE_DIR = "audio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)



# =========================================================================
# ⚡ OPTIMIZATION 1: PRE-LOAD TTS MODEL ON STARTUP
# =========================================================================

print("Loading Mauritian Creole TTS model into memory...")


TTS_MODEL_NAME = "facebook/mms-tts-mfe"

TTS_TOKENIZER = AutoTokenizer.from_pretrained(
    TTS_MODEL_NAME
)

TTS_MODEL = VitsModel.from_pretrained(
    TTS_MODEL_NAME
)

TTS_MODEL.eval()


print("✅ TTS Model ready!")



# =========================================================================
# GEMMA LOCAL TRANSLATION FUNCTION
# =========================================================================

def translate_to_mauritian_creole(
        english_text
):

    prompt = f"""
You are an expert English to Mauritian Creole (Kreol Morisien) translator.

Translate the following English text into natural Mauritian Creole.

STRICT RULES:
- Return ONLY the translated Creole text.
- Do not add explanations.
- Do not add quotes.
- Do not mention that you are translating.

English text:

{english_text}
"""


    payload = {

        "model": GEMMA_MODEL,

        "prompt": prompt,

        "stream": False,

        "options": {

            "temperature": 0.2

        }

    }


    try:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120
        )


        result = response.json()


        creole_text = result.get(
            "response",
            ""
        ).strip()


        return creole_text


    except Exception as e:

        print(
            "Gemma Ollama Error:",
            e
        )

        return english_text



# =========================================================================
# MAIN TTS FUNCTION
# =========================================================================

def english_to_mauritian_creole_speech(
        english_text: str,
        cache_key: str = None
):


    # Create unique filename

    if not cache_key:

        cache_key = hashlib.md5(
            english_text.encode("utf-8")
        ).hexdigest()



    cached_file_path = os.path.join(
        CACHE_DIR,
        f"{cache_key}.wav"
    )



    # =========================================================================
    # ⚡ OPTIMIZATION 2: AUDIO CACHE
    # =========================================================================

    if os.path.exists(cached_file_path):

        print(
            f"⚡ Returning cached audio instantly: {cached_file_path}"
        )

        return cached_file_path



    print(
        f"Generating new Creole speech for: {cache_key}..."
    )



    # =========================================================================
    # 1. GEMMA LOCAL TRANSLATION
    # =========================================================================

    creole_text = translate_to_mauritian_creole(
        english_text
    )


    print(
        "Creole Translation:",
        creole_text
    )



    # =========================================================================
    # 2. SYNTHESIZE WITH MMS-TTS
    # =========================================================================


    inputs = TTS_TOKENIZER(
        creole_text,
        return_tensors="pt"
    )


    with torch.no_grad():

        output = TTS_MODEL(
            **inputs
        ).waveform



    sampling_rate = (
        TTS_MODEL.config.sampling_rate
    )


    audio_data = (
        output.squeeze()
        .cpu()
        .numpy()
    )


    audio_data_int16 = (
        audio_data * 32767
    ).astype(
        np.int16
    )



    scipy.io.wavfile.write(
        cached_file_path,
        rate=sampling_rate,
        data=audio_data_int16
    )


    return cached_file_path