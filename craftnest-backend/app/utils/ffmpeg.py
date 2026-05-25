import subprocess
import shlex
from pathlib import Path
from typing import Tuple

# Define allowed ffmpeg binary path (assumes ffmpeg is in PATH)
FFMPEG_CMD = "ffmpeg"

def _run_cmd(cmd: list[str]) -> Tuple[int, str, str]:
    """Run a subprocess command safely.
    Returns (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def get_video_duration(file_path: Path) -> float:
    """Return video duration in seconds using ffprobe.
    Raises RuntimeError if ffprobe is not available or fails."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    rc, out, err = _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffprobe failed: {err.strip()}")
    try:
        return float(out.strip())
    except ValueError as e:
        raise RuntimeError(f"Unable to parse duration output: {out}") from e

def reencode_video(input_path: Path, output_path: Path) -> None:
    """Re‑encode video to MP4 H.264 720p at ~1500 kbps.
    Overwrites output_path if it exists.
    """
    cmd = [
        FFMPEG_CMD,
        "-y",  # overwrite output
        "-i",
        str(input_path),
        "-vf",
        "scale=-2:720",  # maintain aspect ratio, height 720
        "-c:v",
        "libx264",
        "-b:v",
        "1500k",
        "-preset",
        "fast",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    rc, out, err = _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg re‑encode failed: {err.strip()}")

def generate_thumbnail(input_path: Path, output_path: Path, time_offset: float = 1.0) -> None:
    """Generate a JPEG thumbnail at the given time offset (seconds)."""
    cmd = [
        FFMPEG_CMD,
        "-y",
        "-i",
        str(input_path),
        "-ss",
        str(time_offset),
        "-vframes",
        "1",
        "-vf",
        "scale=-2:720",
        "-q:v",
        "2",  # quality (2 is high, 31 is low)
        str(output_path),
    ]
    rc, out, err = _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg thumbnail generation failed: {err.strip()}")
