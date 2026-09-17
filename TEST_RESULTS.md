# VoiceGuard Calibration Results

Calibration set: 13,954 labeled recordings (6,977 human + 6,977 AI).

## Production signal: FoR

- Threshold: **0.555**
- AUC: **0.99960**
- Human false-positive rate: **0.086%** (6 / 6,977)
- AI detection rate: **90.98%** (6,348 / 6,977)
- AI missed: **9.02%** (629 / 6,977)

A lower FoR threshold (for example 0.5) increases AI recall but also increases human false positives. The selected 0.555 boundary preserves the project's conservative human-side behavior.

## AASIST

AASIST was evaluated as a secondary score. On this dataset its AUC, when treated as a spoof probability, was about **0.773**, substantially below FoR's 0.9996, and its human/AI score distributions overlap heavily.

Therefore AASIST is **not allowed to override a low FoR score**. It remains loaded and exposed for supporting model breakdown/telemetry.

## Final production rule

- FoR < 0.555 -> **Likely human**
- FoR >= 0.555 -> **Likely AI-generated**

This is a dataset-specific validation result, not a universal accuracy guarantee.
