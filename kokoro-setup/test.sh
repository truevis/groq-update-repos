#!/usr/bin/env bash
# Verifies the local Kokoro endpoint and writes test.mp3
curl -fsS http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"kokoro","input":"Kokoro is running on alpha.","voice":"af_heart","response_format":"mp3"}' \
  --output test.mp3 && echo "OK: wrote test.mp3 (docs: http://localhost:8880/docs)"
