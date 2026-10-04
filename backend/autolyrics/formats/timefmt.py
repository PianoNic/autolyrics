import math
import re


def format_time(seconds: float) -> str:
    """Composer/Apple timestamp: m:ss.mmm with minutes unbounded."""
    if not math.isfinite(seconds) or seconds < 0:
        return "0:00.000"
    total_ms = round(seconds * 1000)
    mins, rem = divmod(total_ms, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{mins}:{secs:02d}.{ms:03d}"


def format_lrc_time(seconds: float) -> str:
    """LRC timestamp: mm:ss.xx (centiseconds)."""
    total_cs = round(max(0.0, seconds) * 100)
    mins, rem = divmod(total_cs, 6000)
    secs, cs = divmod(rem, 100)
    return f"{mins:02d}:{secs:02d}.{cs:02d}"


def format_srt_time(seconds: float) -> str:
    total_ms = round(max(0.0, seconds) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    mins, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{ms:03d}"


_CLOCK = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+)(?:\.(\d+))?$")
_OFFSET = re.compile(r"^(\d+(?:\.\d+)?)(h|m|s|ms)$")


def parse_ttml_time(value: str) -> float | None:
    """Parse HH:MM:SS.mmm, MM:SS.mmm, SS.mmm or offset forms like 12.5s."""
    value = (value or "").strip()
    if not value:
        return None
    m = _OFFSET.match(value)
    if m:
        n = float(m.group(1))
        return n * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[m.group(2)]
    m = _CLOCK.match(value)
    if not m:
        return None
    a, b, secs, frac = m.groups()
    if a is not None and b is not None:
        hours, mins = int(a), int(b)
    else:
        hours, mins = 0, int(a) if a is not None else 0
    fraction = int(frac.ljust(3, "0")[:3]) / 1000 if frac else 0.0
    return hours * 3600 + mins * 60 + int(secs) + fraction
