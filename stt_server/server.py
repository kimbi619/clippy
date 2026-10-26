"""Lightweight faster-whisper transcription server.

Accepts raw 16-bit little-endian PCM audio (16 kHz mono) via HTTP POST
and returns a JSON transcript. Runs on port 8001 by default.

Usage:
    pip install faster-whisper fastapi uvicorn
    python stt_server/server.py
"""

import io
import struct
import os
import logging

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stt_server")

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
PORT = int(os.environ.get("STT_PORT", "8001"))

log.info("Loading Whisper model=%s device=%s compute=%s …", MODEL_SIZE, DEVICE, COMPUTE_TYPE)
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
log.info("Model ready.")

app = FastAPI(title="Clippy STT Server")


def pcm16_to_wav_bytes(pcm: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wrap raw int16 PCM bytes in a minimal WAV container."""
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_len = len(pcm)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_len))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_len))
    buf.write(pcm)
    return buf.getvalue()


@app.post("/transcribe")
async def transcribe(request: Request):
    """
    Body: raw int16 little-endian PCM, 16 kHz mono.
    Returns: {"text": "...", "segments": [...]}
    """
    pcm = await request.body()
    if not pcm:
        raise HTTPException(status_code=400, detail="empty body")

    wav = pcm16_to_wav_bytes(pcm)
    audio_file = io.BytesIO(wav)

    segments, info = model.transcribe(
        audio_file,
        language="en",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )

    result_segments = []
    full_text_parts = []
    for seg in segments:
        result_segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        full_text_parts.append(seg.text.strip())

    text = " ".join(full_text_parts)
    log.info("transcribed %.1fs audio → %r", info.duration, text[:80])
    return {"text": text, "segments": result_segments}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_SIZE}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
