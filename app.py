#!/usr/bin/env python3
"""
YouTube Transcript Web App

A small Flask web app that accepts a YouTube URL and returns the
spoken-text transcript of the video. Tries to fetch the video's
existing captions via yt-dlp first (fast path); falls back to
transcribing the audio with OpenAI Whisper if no captions exist.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

from flask import Flask, jsonify, render_template, request


def is_youtube_url(source: str) -> bool:
    """Check if the source is a YouTube URL. Mirrors generate_subtitle.is_youtube_url."""
    return any(
        domain in source
        for domain in ["youtube.com", "youtu.be", "youtube-nocookie.com"]
    )


app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class TranscriptError(RuntimeError):
    """Raised when transcript fetching fails with a user-presentable reason."""


def _ytdlp_auth_hint(stderr: str) -> Optional[str]:
    """Detect YouTube anti-bot / auth errors and return a friendly hint."""
    blockers = [
        "Sign in to confirm",
        "confirm you're not a bot",
        "confirm you\u2019re not a bot",
        "cookies-from-browser",
        "This video is unavailable",
        "Private video",
        "members-only",
        "age-restricted",
    ]
    if any(b.lower() in stderr.lower() for b in blockers):
        return (
            "YouTube memerlukan autentikasi untuk video ini. Sediakan file "
            "cookies.txt (format Netscape) dan set environment variable "
            "YTDLP_COOKIES ke path file tersebut, atau letakkan di "
            "./cookies.txt di root project."
        )
    return None


def _cookies_args() -> list[str]:
    """Build yt-dlp cookies CLI arguments if a cookies file is available."""
    cookies_path = os.environ.get("YTDLP_COOKIES")
    if not cookies_path:
        default = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.isfile(default):
            cookies_path = default
    if cookies_path and os.path.isfile(cookies_path):
        return ["--cookies", cookies_path]
    return []


def _strip_vtt_tags(text: str) -> str:
    """Remove VTT inline timing tags like <00:00:01.000> and styling tags."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return text


def parse_vtt_to_text(vtt_content: str) -> str:
    """Parse WebVTT content and return spoken text only.

    Removes timestamps, headers, cue identifiers, and consecutive
    duplicate lines that are common in auto-generated captions.
    """
    lines = vtt_content.splitlines()
    output: list[str] = []
    last_line = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("NOTE") or line.startswith("STYLE"):
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^[A-Za-z\-]+:\s*", line) and "-->" not in line:
            # Skip lines like "Kind: captions" or "Language: en"
            if ":" in line and len(line.split(":", 1)[0]) <= 20:
                key = line.split(":", 1)[0].lower()
                if key in {"kind", "language", "x-timestamp-map"}:
                    continue
        cleaned = _strip_vtt_tags(line).strip()
        if not cleaned:
            continue
        if cleaned == last_line:
            continue
        output.append(cleaned)
        last_line = cleaned
    return "\n".join(output)


def fetch_youtube_metadata(url: str) -> dict:
    """Fetch video metadata (title, uploader, duration) using yt-dlp.

    Raises TranscriptError when yt-dlp signals an auth/bot blocker so the
    UI can show an actionable message instead of an empty result.
    """
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--skip-download",
        "--dump-single-json",
        *_cookies_args(),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {}
    if result.returncode != 0:
        stderr = result.stderr or ""
        logger.warning("yt-dlp metadata failed: %s", stderr[:500])
        hint = _ytdlp_auth_hint(stderr)
        if hint:
            raise TranscriptError(hint)
        return {}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return {
        "title": data.get("title"),
        "uploader": data.get("uploader") or data.get("channel"),
        "duration": data.get("duration"),
        "video_id": data.get("id"),
        "thumbnail": data.get("thumbnail"),
        "webpage_url": data.get("webpage_url") or url,
    }


def fetch_youtube_captions(
    url: str, preferred_lang: Optional[str] = None
) -> Optional[dict]:
    """Try to download existing YouTube captions and parse them to text.

    Returns a dict with keys {text, language, source} on success, or None
    if no captions are available.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "captions.%(ext)s")
        languages = []
        if preferred_lang:
            languages.append(preferred_lang)
        # Always also try common defaults; yt-dlp accepts a comma list
        for lang in ["id", "en", "en-US", "en-GB"]:
            if lang not in languages:
                languages.append(lang)
        sub_langs = ",".join(languages)

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--no-playlist",
            "--write-subs",
            "--write-auto-subs",
            "--sub-format",
            "vtt",
            "--sub-langs",
            sub_langs,
            "--output",
            out_template,
            *_cookies_args(),
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp subtitle fetch timed out")
            return None
        if result.returncode != 0:
            stderr = result.stderr or ""
            logger.info("yt-dlp subtitle fetch failed: %s", stderr[:500])
            hint = _ytdlp_auth_hint(stderr)
            if hint:
                raise TranscriptError(hint)

        # Look for .vtt files in tmp_dir
        candidates = [f for f in os.listdir(tmp_dir) if f.endswith(".vtt")]
        if not candidates:
            return None

        # Prefer manually-uploaded captions over auto-generated ones if both
        # exist for the same language. yt-dlp suffixes auto-generated files
        # with the language code only; both look the same on disk, so we
        # simply pick the first candidate matching our preferred language,
        # otherwise fall back to the first one.
        chosen = None
        if preferred_lang:
            for f in candidates:
                if f".{preferred_lang}." in f:
                    chosen = f
                    break
        if chosen is None:
            # Prefer non-auto by file size heuristic: auto-subs include many
            # duplicate-rolling captions and tend to be larger, but this is
            # unreliable. Just pick the first candidate deterministically.
            candidates.sort()
            chosen = candidates[0]

        # Extract language from filename like "captions.en.vtt"
        m = re.match(r".*\.([A-Za-z\-]+)\.vtt$", chosen)
        lang = m.group(1) if m else "unknown"

        path = os.path.join(tmp_dir, chosen)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            vtt_content = f.read()
        text = parse_vtt_to_text(vtt_content)
        if not text.strip():
            return None
        return {
            "text": text,
            "language": lang,
            "source": "youtube_captions",
        }


def transcribe_with_whisper(
    url: str, model_name: str = "base", language: Optional[str] = None
) -> dict:
    """Download audio and transcribe with Whisper. Returns dict with text and language."""
    # Lazy import to avoid loading the heavy `whisper` package when the user
    # only needs the YouTube-captions fast path.
    try:
        from generate_subtitle import download_youtube_audio, transcribe_audio
    except ImportError as exc:
        raise TranscriptError(
            "Whisper belum terinstall. Jalankan `pip install -r requirements.txt` "
            "untuk mengaktifkan transkripsi fallback."
        ) from exc

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            audio_path = download_youtube_audio(url, tmp_dir)
        except RuntimeError as exc:
            hint = _ytdlp_auth_hint(str(exc))
            if hint:
                raise TranscriptError(hint) from exc
            raise
        result = transcribe_audio(audio_path, model_name, language)
    segments = result.get("segments", [])
    text_parts = [seg.get("text", "").strip() for seg in segments]
    text = "\n".join(p for p in text_parts if p)
    return {
        "text": text or result.get("text", "").strip(),
        "language": result.get("language", "unknown"),
        "source": f"whisper:{model_name}",
    }


def get_transcript(
    url: str,
    language: Optional[str] = None,
    force_whisper: bool = False,
    model_name: str = "base",
) -> dict:
    """Resolve a YouTube URL to a transcript dict.

    Strategy:
      1. If not force_whisper, try YouTube captions (fast).
      2. Otherwise, or on failure to find captions, transcribe with Whisper.

    Raises ValueError for invalid input and TranscriptError for
    user-presentable failures (e.g. YouTube auth required).
    """
    if not is_youtube_url(url):
        raise ValueError("URL bukan link YouTube yang valid.")

    try:
        metadata = fetch_youtube_metadata(url)
    except TranscriptError:
        # Metadata is optional; only re-raise if it's an auth blocker that
        # will affect the rest of the flow too. Surface it now so the user
        # sees a clear message instead of opaque downstream errors.
        raise

    if not force_whisper:
        caps = fetch_youtube_captions(url, preferred_lang=language)
        if caps is not None:
            caps["metadata"] = metadata
            return caps

    transcript = transcribe_with_whisper(url, model_name=model_name, language=language)
    transcript["metadata"] = metadata
    return transcript


@app.route("/", methods=["GET"])
def index() -> str:
    return render_template("index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe_route():
    url = (request.form.get("url") or "").strip()
    language = (request.form.get("language") or "").strip() or None
    force_whisper = request.form.get("force_whisper") == "on"
    model_name = (request.form.get("model") or "base").strip() or "base"
    wants_json = request.headers.get("Accept", "").startswith("application/json") or (
        request.form.get("format") == "json"
    )

    if not url:
        msg = "URL YouTube wajib diisi."
        if wants_json:
            return jsonify({"error": msg}), 400
        return render_template("index.html", error=msg), 400

    try:
        transcript = get_transcript(
            url,
            language=language,
            force_whisper=force_whisper,
            model_name=model_name,
        )
    except ValueError as exc:
        if wants_json:
            return jsonify({"error": str(exc)}), 400
        return render_template("index.html", error=str(exc), url=url), 400
    except TranscriptError as exc:
        if wants_json:
            return jsonify({"error": str(exc)}), 502
        return render_template("index.html", error=str(exc), url=url), 502
    except Exception as exc:  # noqa: BLE001 - surface failure to the user
        logger.exception("Gagal mengambil transcript")
        msg = f"Gagal mengambil transcript: {exc}"
        if wants_json:
            return jsonify({"error": msg}), 500
        return render_template("index.html", error=msg, url=url), 500

    if wants_json:
        return jsonify(transcript)

    return render_template("result.html", url=url, **transcript)


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL YouTube wajib diisi."}), 400
    language = data.get("language") or None
    force_whisper = bool(data.get("force_whisper"))
    model_name = data.get("model") or "base"
    try:
        transcript = get_transcript(
            url,
            language=language,
            force_whisper=force_whisper,
            model_name=model_name,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except TranscriptError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        logger.exception("API transcript failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify(transcript)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


def main() -> None:
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
