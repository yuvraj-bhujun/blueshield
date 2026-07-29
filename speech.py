import os
import scipy.io.wavfile
import torch
from google import genai
from transformers import AutoTokenizer, VitsModel

# =========================================================================
# 🔑 REPLACE THIS WITH YOUR ACTUAL API KEY (or set GEMINI_API_KEY env var)
# =========================================================================
API_KEY = os.environ.get("GEMINI_API_KEY") or "..."


def english_to_mauritian_creole_speech(
    english_text: str, api_key: str, output_file: str = "mauritian_creole.wav"
):
    # Validate API key before calling Google Client
    if not api_key or api_key == "YOUR_ACTUAL_GEMINI_API_KEY_HERE":
        raise ValueError(
            "\n❌ ERROR: API key missing!\n"
            "Please paste your real API key into the API_KEY variable in speech.py, "
            "or set the GEMINI_API_KEY environment variable in PowerShell:\n"
            '  $env:GEMINI_API_KEY="AIzaSy..."'
        )

    print(f"Original Text (English): {english_text}")

    # Step 1: Translate text using Gemma / Gemini model via Google AI API
    print("\n1. Translating text using Gemma model...")
    client = genai.Client(api_key=api_key)

    prompt = (
        "You are an expert English to Mauritian Creole (Kreol Morisien) translator. "
        "Translate the following English text into natural Mauritian Creole. "
        "Return ONLY the translated Creole text without quotes or explanation.\n\n"
        f"English Text: {english_text}"
    )

    # Note: Use 'gemma-2-9b-it' or 'gemma-2-27b-it' for Gemma models on Google AI Studio,
    # or 'gemini-2.5-flash' / 'gemini-2.0-flash'.
    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it",
        contents=prompt,
    )

    creole_text = response.text.strip()
    print(f"Creole Translation: {creole_text}")

    # Step 2: Synthesize Mauritian Creole speech using Meta MMS TTS
    print("\n2. Synthesizing Mauritian Creole speech audio...")
    tts_model_name = "facebook/mms-tts-mfe"
    tokenizer = AutoTokenizer.from_pretrained(tts_model_name)
    model = VitsModel.from_pretrained(tts_model_name)

    inputs = tokenizer(creole_text, return_tensors="pt")

    with torch.no_grad():
        output = model(**inputs).waveform

    # Step 3: Save audio as a WAV file
    sampling_rate = model.config.sampling_rate
    audio_data = output.squeeze().cpu().numpy()
    scipy.io.wavfile.write(output_file, rate=sampling_rate, data=audio_data)

    print(f"\nSuccess! Audio saved to: {output_file}")


if __name__ == "__main__":
    sample_text = "The grounding of the MV Wakashio in 2020 caused one of the worst environmental disasters in Mauritian history, devastating coral reefs, mangroves, marine life, and coastal communities. Although modern maritime tracking systems exist, they often depend heavily on human operators continuously monitoring thousands of vessels. This makes it difficult to identify dangerous situations early enough to prevent accidents."
    english_to_mauritian_creole_speech(
        sample_text, api_key=API_KEY, output_file="mauritian_creole.wav"
    )