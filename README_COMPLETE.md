# VoiceGuard SIH2614 — Complete Prototype Package

## Components
1. `app.py` — FastAPI backend + AASIST ONNX inference + WebSocket live analysis.
2. `templates/`, `static/` — responsive web dashboard.
3. `android/VoiceGuardAndroid/` — Android companion that hooks into Telecom call state and streams microphone PCM to the same WebSocket engine.

## Deployment
### Backend on Render
Build: `pip install -r requirements.txt`
Start: `gunicorn -k uvicorn.workers.UvicornWorker app:app`

Use HTTPS/WSS in production. The model downloads on first model access.

### Android
Open `android/VoiceGuardAndroid` in Android Studio, sync Gradle and build the APK. Enter your Render URL ending in `/ws/live`.

## Security / production checklist
- Use HTTPS/WSS only.
- Add per-device authentication before real users. The demo endpoint is intentionally simple.
- Do not persist raw call audio unless there is an explicit legal/consent basis.
- Encrypt any stored detection events.
- Add rate limits and request-size limits at the edge.
- Calibrate thresholds using held-out real-world data.
- Evaluate on modern TTS/voice-cloning models, codecs, noise, replay, accents and languages.

## Accuracy statement
No detector should be represented as perfect. AASIST is a research anti-spoofing model and its score is a risk signal. For SIH, describe the system as a real-time anti-spoofing pipeline and report measured validation results from your own evaluation set.

## Direct call detection caveat
The Android component detects call state, but Android's public APIs do not universally expose raw two-sided cellular/WhatsApp audio to third-party apps. Guaranteed remote-party audio capture requires an approved audio path such as an in-app VoIP call, OEM/privileged integration, carrier integration, or another supported recording path.
