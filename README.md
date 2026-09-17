---
title: VoiceGuard
description: AI-powered real-time voice cloning and spoofing detection for SIH2614
emoji: 🛡️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# VoiceGuard — SIH2614

VoiceGuard is an AI-powered voice anti-spoofing prototype combining AASIST with a trained Fake-or-Real support classifier and a conservative fusion layer.

## Run

The Docker Space listens on port **7860**.

- Upload a PCM WAV file for analysis.
- Use microphone capture for supported browsers.
- Use tab/system audio capture where the browser exposes an audio track.
- Live WebSocket analysis is available at `/ws/live`.

> Prototype note: a browser cannot universally access protected cellular-call or WhatsApp remote-party audio. Do not claim that it can.


## Calibration update
The production fusion is FoR-primary using threshold 0.555, calibrated on 13,954 labeled recordings. AASIST remains supporting evidence and is not permitted to override a low FoR score.
