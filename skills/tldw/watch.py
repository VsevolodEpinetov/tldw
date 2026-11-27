# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#     "yt-dlp",
#     "faster-whisper>=1.1",
#     "numpy",
#     "Pillow",
#     "imagehash",
# ]
# ///
"""Turn a video (URL or local file) into frames + a transcript an agent can read.

Usage:
    uv run watch.py <url-or-path> [--frames N] [--lang ru] [--no-audio]
    uv run watch.py --selftest

Everything runs locally: yt-dlp downloads, ffmpeg cuts frames, faster-whisper
transcribes on CPU. Prints one JSON object with the result paths to stdout.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

RUNS_ROOT = Path.home() / ".tldw" / "runs"
FRAME_WIDTH = 640
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024
# Hamming distance between perceptual hashes below which two frames count as the same shot.
DUPLICATE_HASH_DISTANCE = 5
WHISPER_MODEL = "small"


def fail(message: str) -> None:
    print(f"tldw: {message}", file=sys.stderr)
    sys.exit(1)


def run_tool(command: list[str]) -> str:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        fail(f"{command[0]} not found — install ffmpeg (brew install ffmpeg)")
    except subprocess.CalledProcessError as error:
        fail(f"{command[0]} failed: {error.stderr.strip()[-500:]}")


def frame_budget(duration_seconds: float) -> int:
    if duration_seconds <= 30:
        return 16
    if duration_seconds <= 90:
        return 24
    if duration_seconds <= 600:
        return 40
    return 60


def download(url: str, run_dir: Path) -> tuple[Path, dict]:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    options = {
        # A fixed name keeps a hostile video title out of the file system.
        "outtmpl": str(run_dir / "source.%(ext)s"),
        "format": "bv*+ba/b",
        "format_sort": ["res:720", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "max_filesize": MAX_DOWNLOAD_BYTES,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
    except DownloadError as error:
        fail(f"download failed: {error}")
    video_files = sorted(run_dir.glob("source.*"))
    if not video_files:
        fail("download finished but no file was written (size limit or login wall)")
    post = {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "description": info.get("description"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url"),
    }
    return video_files[0], post


def probe(video: Path) -> dict:
    raw = run_tool([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", "--", str(video),
    ])
    data = json.loads(raw)
    stream_types = [stream.get("codec_type") for stream in data.get("streams", [])]
    if "video" not in stream_types:
        fail(f"{video.name} has no video stream")
    return {
        "duration_seconds": float(data["format"]["duration"]),
        "has_audio": "audio" in stream_types,
    }


def extract_frames(video: Path, frames_dir: Path, frames_per_second: float) -> list[dict]:
    frames_dir.mkdir()
    run_tool([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"fps={frames_per_second},scale={FRAME_WIDTH}:-2",
        "-q:v", "3", str(frames_dir / "raw_%03d.jpg"),
    ])
    raw_frames = sorted(frames_dir.glob("raw_*.jpg"))
    return [
        {"path": frame_path, "seconds": round(frame_index / frames_per_second, 1)}
        for frame_index, frame_path in enumerate(raw_frames)
    ]


def drop_duplicates(frames: list[dict]) -> list[dict]:
    import imagehash
    from PIL import Image

    kept: list[dict] = []
    last_hash = None
    for frame in frames:
        with Image.open(frame["path"]) as image:
            frame_hash = imagehash.phash(image)
        if last_hash is not None and frame_hash - last_hash < DUPLICATE_HASH_DISTANCE:
            frame["path"].unlink()
            continue
        last_hash = frame_hash
        kept.append(frame)
    return kept


def name_by_timestamp(frames: list[dict]) -> list[dict]:
    named = []
    for frame in frames:
        minutes, seconds = divmod(int(frame["seconds"]), 60)
        target = frame["path"].with_name(f"{minutes:02d}-{seconds:02d}.jpg")
        if target.exists():
            target = frame["path"].with_name(f"{minutes:02d}-{seconds:02d}b.jpg")
        frame["path"].rename(target)
        named.append({"file": str(target), "seconds": frame["seconds"]})
    return named


def transcribe(video: Path, run_dir: Path, language: str | None) -> dict:
    from faster_whisper import WhisperModel

    import numpy

    # faster-whisper's own decoder breaks on newer PyAV, so ffmpeg hands it raw samples.
    pcm = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    samples = numpy.frombuffer(pcm, dtype=numpy.int16).astype(numpy.float32) / 32768.0
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        samples, language=language, beam_size=5, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    lines = []
    for segment in segments:
        minutes, seconds = divmod(int(segment.start), 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {segment.text.strip()}")
    transcript = run_dir / "transcript.md"
    transcript.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    return {
        "file": str(transcript),
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "lines": len(lines),
    }


def watch(source: str, options: argparse.Namespace) -> dict:
    run_dir = RUNS_ROOT / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    post = None
    if urlparse(source).scheme in ("http", "https"):
        video, post = download(source, run_dir)
    else:
        video = Path(source).expanduser().resolve()
        if not video.is_file():
            fail(f"not a file and not an http(s) URL: {source}")

    video_info = probe(video)
    duration = video_info["duration_seconds"]
    frame_count = options.frames or frame_budget(duration)
    frames = extract_frames(video, run_dir / "frames", frame_count / max(duration, 1.0))
    frames = name_by_timestamp(drop_duplicates(frames))

    transcript = None
    if video_info["has_audio"] and not options.no_audio:
        transcript = transcribe(video, run_dir, options.lang)

    result = {
        "run_dir": str(run_dir),
        "video": str(video),
        "duration_seconds": round(duration, 1),
        "post": post,
        "frames": frames,
        "transcript": transcript,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def selftest() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        sample = Path(temp_dir) / "sample.mp4"
        run_tool([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=10",
            "-pix_fmt", "yuv420p", str(sample),
        ])
        options = argparse.Namespace(frames=6, lang=None, no_audio=True)
        result = watch(str(sample), options)
        try:
            assert result["duration_seconds"] == 6.0, result
            assert 1 <= len(result["frames"]) <= 6, result
            assert all(Path(frame["file"]).is_file() for frame in result["frames"]), result
            assert result["transcript"] is None, result
            assert frame_budget(20) < frame_budget(60) < frame_budget(300) < frame_budget(3600)
        finally:
            shutil.rmtree(result["run_dir"])
    print("selftest ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn a video into frames and a transcript.")
    parser.add_argument("source", nargs="?", help="http(s) URL or path to a video file")
    parser.add_argument("--frames", type=int, help="frames to cut before dedup (default: by duration)")
    parser.add_argument("--lang", help="spoken language as ISO code, e.g. ru (default: auto-detect)")
    parser.add_argument("--no-audio", action="store_true", help="skip transcription")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        selftest()
        return
    if not options.source:
        parser.error("source is required")
    if options.frames is not None and not 1 <= options.frames <= 200:
        parser.error("--frames must be between 1 and 200")
    print(json.dumps(watch(options.source, options), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
