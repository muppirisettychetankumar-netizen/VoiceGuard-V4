# VoiceGuard realtime detector update

This version uses the official AASIST deterministic 64,600-sample evaluation window and a conservative temporal-consensus gate for live monitoring. A single model spike cannot trigger a high-risk AI verdict; three strong windows are required.

This is deliberate: the official AASIST model is a research anti-spoofing model and its published out-of-domain error rates are substantially higher than its in-domain benchmark. The detector must be treated as a risk signal, not a forensic guarantee.

Render:
- Build: pip install -r requirements.txt && python download_model.py
- Start: gunicorn -k uvicorn.workers.UvicornWorker app:app
- Root Directory: blank
- Environment variables: none
