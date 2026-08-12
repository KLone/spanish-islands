"""
transcribe_audio.py

Transcribes an audio file using Claude's multimodal API.
Usage: python transcribe_audio.py <audio_file_path>
"""

import base64
import subprocess
import sys
import os

import anthropic


def load_api_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "anthropic_api_key", "-w"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERROR: Could not load API key from Keychain.")
        sys.exit(1)
    return result.stdout.strip()


def transcribe(audio_path: str) -> str:
    api_key = load_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    with open(audio_path, "rb") as f:
        audio_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = os.path.splitext(audio_path)[1].lower()
    media_type_map = {
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
    }
    media_type = media_type_map.get(ext, "audio/mp4")

    print(f"Transcribing {audio_path} ({media_type})...")

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please transcribe this audio recording exactly as spoken. Include all content, capturing the speaker's exact words."
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": audio_data,
                        },
                    },
                ],
            }
        ],
    )

    return response.content[0].text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe_audio.py <audio_file_path>")
        sys.exit(1)

    audio_file = sys.argv[1]
    if not os.path.exists(audio_file):
        print(f"ERROR: File not found: {audio_file}")
        sys.exit(1)

    transcript = transcribe(audio_file)
    print("\n=== TRANSCRIPT ===")
    print(transcript)
