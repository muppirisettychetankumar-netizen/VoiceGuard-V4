import io
import json
import math
import os
import threading
import time
import urllib.request
import wave
import gc
import sqlite3
import uuid
from datetime import datetime, timezone

# Set native/ONNX thread limits before NumPy/ONNX initialization to reduce Render Free memory spikes.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", "1")
os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "1")

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

APP_NAME = "VoiceGuard"
VERSION = "5.2-render-calibrated-history"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")
AASIST_PATH = os.path.join(MODEL_DIR, "aasist.onnx")
FOR_RF_PATH = os.path.join(MODEL_DIR, "for_rf_compact.npz")
AASIST_URL = "https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST/resolve/main/aasist.onnx?download=true"
TARGET_SR = 16000
WINDOW_SAMPLES = 64600
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MIN_SECONDS = 1.2
HISTORY_DB = os.path.join(BASE_DIR, "voiceguard_history.db")
HISTORY_LIMIT = 250

app = FastAPI(title="VoiceGuard SIH2614", version=VERSION)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

_session = None
_session_lock = threading.Lock()
inference_lock = threading.Lock()
_rf = None
_rf_lock = threading.Lock()

# Exact FoR feature configuration used by the training pipeline.
FOR_SR = 16000
FOR_CLIP = 32000
FOR_FRAME = 400
FOR_HOP = 160
FOR_BANDS = 64
FOR_FREQ = np.fft.rfftfreq(FOR_FRAME, 1 / FOR_SR).astype(np.float32)


def _mel_filterbank(nfft, sr, n_bands, lo=60.0, hi=7600.0):
    h2m = lambda f: 2595 * np.log10(1 + f / 700)
    m2h = lambda m: 700 * (10 ** (m / 2595) - 1)
    hz = m2h(np.linspace(h2m(lo), h2m(hi), n_bands + 2))
    bins = np.floor((nfft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_bands, nfft // 2 + 1), dtype=np.float32)
    for b in range(1, n_bands + 1):
        a, c, d = bins[b - 1], bins[b], bins[b + 1]
        if c > a:
            fb[b - 1, a:c] = np.linspace(0, 1, c - a, endpoint=False)
        if d > c:
            fb[b - 1, c:d] = np.linspace(1, 0, d - c, endpoint=False)
    return fb

FOR_FB = _mel_filterbank(FOR_FRAME, FOR_SR, FOR_BANDS)


def _for_features(x):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if x.size == 0:
        raise ValueError("No samples available for support-model analysis.")
    if len(x) < FOR_CLIP:
        x = np.tile(x, int(np.ceil(FOR_CLIP / len(x))))[:FOR_CLIP]
    else:
        start = (len(x) - FOR_CLIP) // 2
        x = x[start:start + FOR_CLIP]

    frames, specs = [], []
    window = np.hanning(FOR_FRAME).astype(np.float32)
    for i in range(0, len(x) - FOR_FRAME + 1, FOR_HOP):
        frame = x[i:i + FOR_FRAME]
        z = frame * window
        mag = np.abs(np.fft.rfft(z)) + 1e-8
        power = mag ** 2
        specs.append(power)
        p = power / (power.sum() + 1e-12)
        centroid = float((FOR_FREQ * p).sum())
        bw = float(np.sqrt(((FOR_FREQ - centroid) ** 2 * p).sum()))
        cdf = np.cumsum(p)
        roll = float(FOR_FREQ[min(len(FOR_FREQ) - 1, np.searchsorted(cdf, 0.85))])
        flat = float(np.exp(np.mean(np.log(power))) / (np.mean(power) + 1e-12))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(frame).astype(np.float32)))))
        rms = float(np.sqrt(np.mean(frame ** 2)))
        peak = float(np.max(np.abs(frame)) + 1e-8)
        frames.append([centroid, bw, roll, flat, zcr, rms, peak, rms / peak])

    a = np.asarray(frames, dtype=np.float32)
    S = np.asarray(specs, dtype=np.float32)
    lm = np.log(FOR_FB @ S.T + 1e-10)
    lm -= np.median(lm, axis=1, keepdims=True)
    delta = np.diff(lm, axis=1, prepend=lm[:, :1])
    parts = [
        a.mean(0), a.std(0), np.median(a, 0), np.percentile(a, 10, axis=0), np.percentile(a, 90, axis=0),
        lm.mean(1), lm.std(1), np.median(lm, 1), np.percentile(lm, 10, axis=1), np.percentile(lm, 90, axis=1),
        delta.mean(1), delta.std(1),
    ]
    rms = a[:, 5]
    speech = rms > max(0.002, np.percentile(rms, 25))
    parts.append(np.array([speech.mean(), np.mean(x * x), np.max(np.abs(x)),
                           np.percentile(np.abs(x), 90), np.percentile(np.abs(x), 99)], dtype=np.float32))
    return np.concatenate(parts).astype(np.float32)


def _history_conn():
    conn = sqlite3.connect(HISTORY_DB, timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS scans (
        id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, source TEXT NOT NULL,
        name TEXT, verdict TEXT NOT NULL, level TEXT NOT NULL,
        ai_probability REAL, human_probability REAL, aasist_probability REAL,
        for_probability REAL, confidence REAL, duration REAL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp DESC)")
    return conn

def record_history(result, source="upload", name=""):
    try:
        ts = datetime.now(timezone.utc).isoformat()
        conn = _history_conn()
        conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            uuid.uuid4().hex, ts, source, (name or "")[:200],
            result.get("verdict", "Unknown"), result.get("level", "warning"),
            float(result.get("synthetic_probability", 0)), float(result.get("human_probability", 0)),
            float(result.get("aasist_probability", 0)), float(result.get("for_probability", 0)),
            float(result.get("confidence", 0)), float(result.get("duration", 0))
        ))
        conn.execute("DELETE FROM scans WHERE id NOT IN (SELECT id FROM scans ORDER BY timestamp DESC LIMIT ?)", (HISTORY_LIMIT,))
        conn.commit(); conn.close()
    except Exception as exc:
        print("History log skipped:", repr(exc))

@app.get("/api/history")
async def history(limit: int = 50):
    limit = max(1, min(250, int(limit)))
    try:
        conn = _history_conn()
        rows = conn.execute("SELECT id,timestamp,source,name,verdict,level,ai_probability,human_probability,aasist_probability,for_probability,confidence,duration FROM scans ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        keys = ["id","timestamp","source","name","verdict","level","ai_probability","human_probability","aasist_probability","for_probability","confidence","duration"]
        return {"items": [dict(zip(keys, r)) for r in rows], "persistent": True, "limit": limit}
    except Exception as exc:
        return {"items": [], "persistent": False, "error": str(exc)}

@app.delete("/api/history")
async def clear_history():
    try:
        conn = _history_conn(); conn.execute("DELETE FROM scans"); conn.commit(); conn.close()
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

def get_rf():
    global _rf
    if _rf is None:
        with _rf_lock:
            if _rf is None:
                if not os.path.exists(FOR_RF_PATH):
                    raise RuntimeError("FoR support model is not available on the server.")
                z = np.load(FOR_RF_PATH, allow_pickle=False)
                _rf = {k: z[k] for k in z.files}
                z.close()
    return _rf


def compact_rf_predict_proba(features):
    """Run the exported 600-tree RandomForest without importing scikit-learn."""
    rf = get_rf()
    left, right = rf["left"], rf["right"]
    feature, threshold, p1, offsets = rf["feature"], rf["threshold"], rf["p1"], rf["offsets"]
    x = np.asarray(features, dtype=np.float32)
    total = 0.0
    trees = len(offsets) - 1
    for t in range(trees):
        base, end = int(offsets[t]), int(offsets[t + 1])
        node = 0
        while True:
            idx = base + node
            child = int(left[idx])
            if child == -1:
                total += float(p1[idx])
                break
            f = int(feature[idx])
            if x[f] <= threshold[idx]:
                node = int(left[idx])
            else:
                node = int(right[idx])
            if base + node >= end:
                raise RuntimeError("Corrupt compact support model.")
    return total / max(trees, 1)


def for_spoof(x16):
    probability = compact_rf_predict_proba(_for_features(x16))
    threshold = float(get_rf()["threshold_model"])
    return probability, threshold


def fuse_scores(aasist_spoof, for_score):
    """FoR-primary calibrated decision. AASIST is corroborating telemetry.

    Calibration on 13,954 labeled recordings found FoR substantially stronger
    on this evaluation distribution. AASIST is therefore prevented from
    overriding a low FoR score, reducing avoidable human false positives.
    """
    if for_score >= 0.555:
        return for_score, "Likely AI-generated", "danger"
    return for_score, "Likely human", "safe"

def ensure_aasist():
    os.makedirs(MODEL_DIR, exist_ok=True)
    if os.path.exists(AASIST_PATH) and os.path.getsize(AASIST_PATH) > 500_000:
        return AASIST_PATH
    tmp = AASIST_PATH + ".part"
    print("Downloading AASIST ONNX model...")
    urllib.request.urlretrieve(AASIST_URL, tmp)
    os.replace(tmp, AASIST_PATH)
    return AASIST_PATH


def get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                opts.enable_mem_pattern = False
                opts.enable_cpu_mem_arena = True
                path = ensure_aasist()
                _session = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
                print("AASIST ready:", [x.name for x in _session.get_inputs()], [x.name for x in _session.get_outputs()])
    return _session


def decode_wav(data: bytes):
    if not data:
        raise ValueError("The uploaded file is empty.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            sr, channels, width, frames = wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
            raw = wf.readframes(frames)
    except wave.Error as exc:
        raise ValueError("Invalid WAV file. Please upload an uncompressed PCM WAV sample.") from exc
    if sr <= 0 or channels <= 0 or frames <= 0:
        raise ValueError("The WAV file does not contain usable audio.")
    if width == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise ValueError("Unsupported WAV sample width. Use 8-, 16-, or 32-bit PCM WAV.")
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return np.nan_to_num(x), sr


def resample_linear(x, sr, target=TARGET_SR):
    if sr == target:
        return x.astype(np.float32, copy=False)
    if sr <= 0:
        raise ValueError("Invalid sample rate.")
    n = max(1, int(round(len(x) * target / sr)))
    positions = np.linspace(0, len(x) - 1, n, dtype=np.float32)
    base = np.arange(len(x), dtype=np.float32)
    return np.interp(positions, base, x).astype(np.float32)


def prepare(x, sr):
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    x = np.nan_to_num(x)
    if x.size == 0:
        raise ValueError("No audio samples received.")
    x = resample_linear(x, int(sr), TARGET_SR)
    x -= np.mean(x)
    if len(x) >= WINDOW_SAMPLES:
        return x[:WINDOW_SAMPLES].astype(np.float32)
    return np.tile(x, WINDOW_SAMPLES // len(x) + 1)[:WINDOW_SAMPLES].astype(np.float32)


def softmax(values):
    values = np.asarray(values, dtype=np.float32).reshape(-1)
    values -= np.max(values)
    exp = np.exp(values)
    return exp / (np.sum(exp) + 1e-9)


def infer(x16):
    session = get_session()
    input_info = session.get_inputs()[0]
    arr = x16.reshape(1, -1).astype(np.float32)
    if len(input_info.shape) == 1:
        arr = arr.reshape(-1)
    with inference_lock:
        output = session.run(None, {input_info.name: arr})
    flat = np.asarray(output[0]).reshape(-1)
    del output
    if flat.size >= 2:
        probs = softmax(flat[:2])
        spoof, human = float(probs[0]), float(probs[1])
        raw = float(flat[1] - flat[0])
    else:
        raw = float(flat[0])
        human = 1 / (1 + math.exp(-max(-30, min(30, raw))))
        spoof = 1 - human
    return human, spoof, raw


def analyze(x, sr):
    duration = len(x) / max(sr, 1)
    if duration < MIN_SECONDS:
        raise ValueError(f"Please provide at least {MIN_SECONDS:.1f} seconds of speech.")
    rms = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float32) ** 2)) + 1e-12)
    if rms < 0.003:
        return {"verdict": "Not enough speech", "level": "warning", "human_probability": 50.0,
                "synthetic_probability": 50.0, "fusion_probability": 50.0, "aasist_probability": 50.0,
                "for_probability": 50.0, "confidence": 0.0, "duration": round(duration, 2),
                "sample_rate": sr, "model": "AASIST + FoR support classifier",
                "note": "The sample is too quiet for a reliable decision. Try a clear speech recording."}

    x16 = resample_linear(x, int(sr), TARGET_SR)
    aasist_x16 = prepare(x, sr)
    try:
        human, aasist_spoof, raw = infer(aasist_x16)
        try:
            for_score, for_threshold = for_spoof(x16)
            fusion, verdict, level = fuse_scores(aasist_spoof, for_score)
            model_label = "FoR (primary) + AASIST (corroborating)"
        except Exception as exc:
            # Fail safely if the calibrated FoR support model is unavailable.
            # AASIST alone must not accuse a speaker.
            for_score, for_threshold = 0.5, 0.555
            fusion = 0.5
            verdict, level = "Needs review", "warning"
            model_label = "FoR unavailable - manual review required"
            print("FoR support model unavailable:", repr(exc))
        confidence = min(99.0, abs(fusion - 0.5) * 200.0)
        return {
            "verdict": verdict, "level": level,
            "human_probability": round((1 - fusion) * 100, 1),
            "synthetic_probability": round(fusion * 100, 1),
            "fusion_probability": round(fusion * 100, 1),
            "aasist_probability": round(aasist_spoof * 100, 1),
            "for_probability": round(for_score * 100, 1),
            "confidence": round(confidence, 1), "duration": round(duration, 2), "sample_rate": sr,
            "model": model_label, "raw_score": round(raw, 4), "for_threshold": round(for_threshold * 100, 1),
            "window_seconds": round(WINDOW_SAMPLES / TARGET_SR, 2),
            "note": "FoR is the calibrated primary decision signal; AASIST is retained as corroborating evidence and telemetry.",
        }
    finally:
        del x16, aasist_x16
        gc.collect()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "service": APP_NAME, "version": VERSION,
            "aasist_file": os.path.exists(AASIST_PATH), "support_model_file": os.path.exists(FOR_RF_PATH)}


@app.get("/api/model-status")
async def model_status():
    try:
        session = get_session()
        return {"ready": True, "service": APP_NAME, "version": VERSION,
                "inputs": [x.name for x in session.get_inputs()], "outputs": [x.name for x in session.get_outputs()],
                "support_model_available": os.path.exists(FOR_RF_PATH)}
    except Exception as exc:
        return JSONResponse({"ready": False, "error": str(exc)}, status_code=503)


@app.post("/api/analyze")
async def analyze_upload(audio: UploadFile = File(...)):
    try:
        if audio.content_type and audio.content_type not in {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"}:
            if not (audio.filename or "").lower().endswith(".wav"):
                raise ValueError("Please upload a WAV audio file.")
        data = await audio.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("File is too large. Please use a WAV sample under 15 MB.")
        x, sr = decode_wav(data)
        result = analyze(x, sr)
        result.update({"filename": audio.filename or "audio.wav", "timestamp": time.time()})
        record_history(result, "upload", audio.filename or "audio.wav")
        del x, data
        gc.collect()
        return result
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        print("Analysis error:", repr(exc))
        return JSONResponse({"error": "The server could not analyze this sample."}, status_code=500)


@app.websocket("/ws/live")
async def live_socket(ws: WebSocket):
    await ws.accept()
    buffer = np.zeros(0, dtype=np.float32)
    recent = []
    last_emit = 0.0
    input_sr = TARGET_SR
    session_started = time.time()
    session_mode = "live"
    session_results = []
    try:
        await ws.send_json({"type": "status", "message": "connected", "version": VERSION})
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text"):
                try:
                    payload = json.loads(message["text"])
                    if payload.get("type") == "config":
                        input_sr = max(8000, min(96000, int(payload.get("sampleRate", TARGET_SR))))
                        session_mode = str(payload.get("mode", "live"))[:30]
                except Exception:
                    pass
                continue
            raw = message.get("bytes")
            if not raw or len(raw) % 2:
                continue
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if input_sr != TARGET_SR:
                pcm = resample_linear(pcm, input_sr, TARGET_SR)
            buffer = np.concatenate((buffer, pcm))
            if len(buffer) > WINDOW_SAMPLES * 2:
                buffer = buffer[-WINDOW_SAMPLES * 2:]
            now = time.time()
            if len(buffer) < WINDOW_SAMPLES or now - last_emit < 1.5:
                continue
            try:
                result = analyze(buffer[-WINDOW_SAMPLES:], TARGET_SR)
                score = result.get("synthetic_probability", 50.0) / 100.0
                recent = (recent + [score])[-5:]
                strong = sum(v >= 0.92 for v in recent)
                if result.get("verdict") == "Needs review" and strong >= 3 and result.get("aasist_probability", 0) >= 92 and result.get("for_probability", 0) >= 55.5:
                    result["verdict"], result["level"] = "Likely AI-generated", "danger"
                elif result.get("verdict") == "Likely human":
                    result["verdict"], result["level"] = "Likely human", "safe"
                else:
                    result["verdict"], result["level"] = "Needs review", "warning"
                result.update({"type": "result", "consensus_windows": len(recent), "strong_ai_windows": strong, "timestamp": now})
                session_results.append(result)
                await ws.send_json(result)
                last_emit = now
            except Exception as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
                last_emit = now
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print("WebSocket error:", repr(exc))
        try:
            await ws.send_json({"type": "error", "message": "Live analysis stopped unexpectedly."})
        except Exception:
            pass
    finally:
        if session_results:
            last = session_results[-1].copy()
            last["duration"] = round(max(0.0, time.time() - session_started), 2)
            record_history(last, "live", f"{session_mode} session")
        del buffer, recent, session_results
        gc.collect()
