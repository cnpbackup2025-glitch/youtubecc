#!/usr/bin/env python3
"""
Subtitle Generator from Original Speaker Audio

Generates subtitle files (.srt or .vtt) by transcribing the original
speaker's audio from video/audio files using OpenAI Whisper.
Supports YouTube URLs and local files.
"""

import argparse
import os
import subprocess
import sys
import tempfile

import whisper


def format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """Convert seconds to VTT timestamp format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def write_srt(segments: list, output_path: str) -> None:
    """Write segments to an SRT subtitle file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = format_timestamp_srt(seg["start"])
            end = format_timestamp_srt(seg["end"])
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def write_vtt(segments: list, output_path: str) -> None:
    """Write segments to a WebVTT subtitle file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, seg in enumerate(segments, start=1):
            start = format_timestamp_vtt(seg["start"])
            end = format_timestamp_vtt(seg["end"])
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def download_youtube_audio(url: str, output_dir: str) -> str:
    """Download audio from a YouTube URL using yt-dlp."""
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "--no-playlist",
        "--output",
        output_template,
        url,
    ]
    print(f"Downloading audio from: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"yt-dlp stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Failed to download audio: {result.stderr}")

    # Find the downloaded file
    for fname in os.listdir(output_dir):
        if fname.endswith(".wav"):
            return os.path.join(output_dir, fname)

    raise FileNotFoundError("Downloaded audio file not found")


def extract_audio_from_video(video_path: str, output_dir: str) -> str:
    """Extract audio track from a local video file using ffmpeg."""
    base = os.path.splitext(os.path.basename(video_path))[0]
    audio_path = os.path.join(output_dir, f"{base}.wav")
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-y",
        audio_path,
    ]
    print(f"Extracting audio from: {video_path}")
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to extract audio: {stderr_text}")
    return audio_path


def is_audio_file(path: str) -> bool:
    """Check if the file is an audio file based on extension."""
    audio_exts = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
    return os.path.splitext(path)[1].lower() in audio_exts


def is_video_file(path: str) -> bool:
    """Check if the file is a video file based on extension."""
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".ts"}
    return os.path.splitext(path)[1].lower() in video_exts


def is_youtube_url(source: str) -> bool:
    """Check if the source is a YouTube URL."""
    return any(
        domain in source
        for domain in ["youtube.com", "youtu.be", "youtube-nocookie.com"]
    )


def transcribe_audio(audio_path: str, model_name: str, language: str | None) -> dict:
    """Transcribe audio using OpenAI Whisper."""
    print(f"Loading Whisper model: {model_name}")
    model = whisper.load_model(model_name)

    print(f"Transcribing: {audio_path}")
    options = {"verbose": True}
    if language:
        options["language"] = language

    result = model.transcribe(audio_path, **options)
    print(f"Detected language: {result.get('language', 'unknown')}")
    return result


def generate_subtitle(
    source: str,
    output: str | None = None,
    fmt: str = "srt",
    model_name: str = "base",
    language: str | None = None,
) -> str:
    """
    Generate subtitle from an audio/video source.

    Args:
        source: YouTube URL, or path to a local video/audio file.
        output: Output subtitle file path. Auto-generated if None.
        fmt: Subtitle format, 'srt' or 'vtt'.
        model_name: Whisper model name (tiny, base, small, medium, large).
        language: Language code for transcription (e.g., 'id' for Indonesian).

    Returns:
        Path to the generated subtitle file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        if is_youtube_url(source):
            audio_path = download_youtube_audio(source, tmp_dir)
        elif os.path.isfile(source):
            if is_audio_file(source):
                audio_path = source
            elif is_video_file(source):
                audio_path = extract_audio_from_video(source, tmp_dir)
            else:
                raise ValueError(
                    f"Unsupported file type: {source}. Use a video or audio file."
                )
        else:
            raise FileNotFoundError(f"Source not found: {source}")

        result = transcribe_audio(audio_path, model_name, language)

    segments = result.get("segments", [])
    if not segments:
        raise RuntimeError("No speech segments detected in the audio.")

    if output is None:
        if is_youtube_url(source):
            base_name = "subtitle"
        else:
            base_name = os.path.splitext(os.path.basename(source))[0]
        output = f"{base_name}.{fmt}"

    if fmt == "vtt":
        write_vtt(segments, output)
    else:
        write_srt(segments, output)

    print(f"Subtitle saved to: {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate subtitles from original speaker audio using Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From a YouTube video (Indonesian language, base model)
  python generate_subtitle.py https://www.youtube.com/watch?v=VIDEO_ID -l id

  # From a local video file
  python generate_subtitle.py video.mp4 -o subtitle.srt -l id

  # From a local audio file with larger model
  python generate_subtitle.py audio.wav -m medium -f vtt

  # Auto-detect language
  python generate_subtitle.py video.mp4
        """,
    )
    parser.add_argument(
        "source",
        help="YouTube URL or path to a local video/audio file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output subtitle file path (default: auto-generated)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["srt", "vtt"],
        default="srt",
        help="Subtitle format (default: srt)",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "-l",
        "--language",
        default=None,
        help="Language code, e.g. 'id' for Indonesian (default: auto-detect)",
    )

    args = parser.parse_args()

    generate_subtitle(
        source=args.source,
        output=args.output,
        fmt=args.format,
        model_name=args.model,
        language=args.language,
    )


if __name__ == "__main__":
    main()
