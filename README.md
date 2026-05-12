# Subtitle Generator dari Audio Asli Pembicara

Tool untuk menghasilkan file subtitle (.srt / .vtt) berdasarkan audio asli pembicara menggunakan **OpenAI Whisper**. Subtitle dihasilkan dari transkripsi ucapan asli, bukan dari closed captions atau subtitle otomatis platform.

## Fitur

- Mendukung input dari **YouTube URL** dan **file lokal** (video/audio)
- Ekstraksi audio otomatis dari file video menggunakan `ffmpeg`
- Transkripsi menggunakan **OpenAI Whisper** dengan dukungan multilingual
- Output format **SRT** atau **WebVTT**
- Timestamp yang sinkron dengan audio asli
- Mendukung berbagai ukuran model Whisper (tiny, base, small, medium, large)
- Deteksi bahasa otomatis atau manual

## Dependencies

- **Python** >= 3.10
- **ffmpeg** (harus terinstall di sistem)
- **openai-whisper** — model speech-to-text dari OpenAI
- **yt-dlp** — untuk download audio dari YouTube

## Instalasi

### 1. Install ffmpeg

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

## Cara Menjalankan

### Dari YouTube URL

```bash
# Bahasa Indonesia
python generate_subtitle.py https://www.youtube.com/watch?v=VIDEO_ID -l id

# Auto-detect bahasa
python generate_subtitle.py https://www.youtube.com/watch?v=VIDEO_ID

# Dengan model lebih besar untuk akurasi lebih tinggi
python generate_subtitle.py https://www.youtube.com/watch?v=VIDEO_ID -l id -m medium
```

### Dari File Video Lokal

```bash
python generate_subtitle.py video.mp4 -o subtitle.srt -l id
```

### Dari File Audio Lokal

```bash
python generate_subtitle.py audio.wav -m medium -f vtt
```

### Opsi Lengkap

```
usage: generate_subtitle.py [-h] [-o OUTPUT] [-f {srt,vtt}]
                             [-m {tiny,base,small,medium,large}]
                             [-l LANGUAGE] source

Generate subtitles from original speaker audio using Whisper.

positional arguments:
  source                YouTube URL or path to a local video/audio file

optional arguments:
  -o, --output          Output subtitle file path (default: auto-generated)
  -f, --format          Subtitle format: srt or vtt (default: srt)
  -m, --model           Whisper model size (default: base)
  -l, --language        Language code, e.g. 'id' for Indonesian (default: auto-detect)
```

## Contoh Output

### Format SRT

```
1
00:00:00,000 --> 00:00:03,520
Halo semuanya, selamat datang di channel saya.

2
00:00:03,520 --> 00:00:07,200
Hari ini kita akan membahas tentang...
```

### Format VTT

```
WEBVTT

1
00:00:00.000 --> 00:00:03.520
Halo semuanya, selamat datang di channel saya.

2
00:00:03.520 --> 00:00:07.200
Hari ini kita akan membahas tentang...
```

## Catatan

- Model `base` sudah cukup untuk transkripsi umum. Gunakan `medium` atau `large` untuk akurasi yang lebih tinggi.
- Model `large` membutuhkan GPU dan RAM yang lebih besar.
- Jika audio mengandung campuran bahasa, Whisper akan mempertahankan bahasa asli yang diucapkan pembicara.
- Hasil transkripsi mencerminkan ucapan sebenarnya, bukan parafrase atau ringkasan.
