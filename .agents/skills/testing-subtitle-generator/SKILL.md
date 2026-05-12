---
name: testing-subtitle-generator
description: Test the generate_subtitle.py CLI tool end-to-end. Use when verifying subtitle generation from audio/video files.
---

# Testing the Subtitle Generator

## Prerequisites

- Python >= 3.10
- ffmpeg installed (`which ffmpeg`)
- Dependencies installed: `pip install -r requirements.txt`
- For linting: `pip install ruff`

## Generate Sample Test Audio

Since YouTube downloads may be blocked by bot detection, create a sample audio using gTTS:

```bash
pip install gTTS
python3 -c "
from gtts import gTTS
text = 'Halo semuanya, selamat datang di video kali ini. Hari ini kita akan membahas tentang pentingnya belajar bahasa pemrograman.'
tts = gTTS(text=text, lang='id', slow=False)
tts.save('output/sample_audio.mp3')
"
```

## Core Test Cases

### 1. CLI Help
```bash
python generate_subtitle.py --help
# Expect: exit 0, shows source, -o, -f, -m, -l options
```

### 2. SRT Generation from Audio
```bash
python generate_subtitle.py output/sample_audio.mp3 -l id -m tiny -o /tmp/test.srt
# Expect: exit 0, valid SRT with comma timestamps, Indonesian content, >= 5 segments
```

### 3. VTT Generation from Audio
```bash
python generate_subtitle.py output/sample_audio.mp3 -l id -m tiny -o /tmp/test.vtt -f vtt
# Expect: exit 0, starts with WEBVTT, dot timestamps
```

### 4. Auto-generated Filename
```bash
python generate_subtitle.py output/sample_audio.mp3 -l id -m tiny
# Expect: creates sample_audio.srt in CWD
```

### 5. Video Audio Extraction
```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -f lavfi -i "color=c=black:s=320x240:d=3" -c:v libx264 -c:a aac -y /tmp/test_video.mp4
python generate_subtitle.py /tmp/test_video.mp4 -m tiny -o /tmp/video_sub.srt
# Expect: prints "Extracting audio from:", then RuntimeError (no speech in sine wave) — this is correct behavior
```

### 6. Error: Non-existent File
```bash
python generate_subtitle.py /tmp/nonexistent.mp4
# Expect: exit 1, FileNotFoundError
```

### 7. Error: Unsupported File Type
```bash
echo "hello" > /tmp/test.txt && python generate_subtitle.py /tmp/test.txt
# Expect: exit 1, ValueError: Unsupported file type
```

### 8. Unit Checks (import and run in Python)
```python
from generate_subtitle import is_youtube_url, format_timestamp_srt, format_timestamp_vtt
assert is_youtube_url('https://www.youtube.com/watch?v=abc') == True
assert is_youtube_url('https://vimeo.com/123') == False
assert format_timestamp_srt(3661.5) == '01:01:01,500'
assert format_timestamp_vtt(3661.5) == '01:01:01.500'
```

### 9. Timestamp Accuracy
Parse the generated SRT and verify:
- First segment starts near 0.0s
- Last segment ends near total audio duration
- Timestamps are monotonically increasing
- No negative or extreme values

## Linting
```bash
ruff check generate_subtitle.py
ruff format --check generate_subtitle.py
```

## Known Limitations

- **YouTube downloads** may fail with "Sign in to confirm you're not a bot" from cloud/CI environments. The `download_youtube_audio()` path requires browser cookies. Test locally with `--cookies-from-browser chrome` added to yt-dlp args if needed.
- **Whisper model accuracy**: `tiny`/`base` models produce imprecise transcriptions for some words. Use `medium` or `large` for production-quality output.
- **CPU-only**: Without GPU, transcription runs on FP32 and is slower. The FP16 warning is expected and harmless.
