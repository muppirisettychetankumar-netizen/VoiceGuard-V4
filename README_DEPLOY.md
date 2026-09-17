# VoiceGuard — Render deployment

## Render settings
- Runtime: Python 3
- Branch: main
- Root Directory: blank
- Build Command: `pip install --no-cache-dir -r requirements.txt && python download_model.py`
- Start Command: `gunicorn -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 180 --keep-alive 30 app:app`
- Plan: Free
- Environment variable: `PYTHON_VERSION=3.12.8`

This build is specifically optimized for Render Free's 512 MB limit without removing the AASIST detector. The scikit-learn runtime is removed from production: the trained 600-tree FoR model is exported to a compact NumPy representation and evaluated directly. AASIST uses one ONNX thread and inference is serialized to prevent concurrent memory spikes.


## Scan history
The app records scan metadata (timestamp, source, filename/session label, verdict, AASIST score, FoR score, confidence, and duration) in a small SQLite database and mirrors recent upload history in browser localStorage. Audio bytes are not saved by the history feature. On Render Free, the server filesystem is ephemeral, so server-side history can be lost after a restart/redeploy; browser history on the same device remains available.

## History on Render Free
The app stores up to 250 metadata-only scan records in SQLite and also keeps recent metadata in the browser. Render Free storage is not guaranteed to survive service replacement/redeploys, so this is not an archival call recording system. Audio itself is not stored by the history feature.
