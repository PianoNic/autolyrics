from pathlib import Path

from autolyrics.formats.lrc import write_lrc
from autolyrics.formats.qrc import write_qrc
from autolyrics.formats.srt import write_srt
from autolyrics.formats.ttml import write_ttml
from autolyrics.model import Lyrics


def export_all(lyrics: Lyrics, out_dir: Path) -> dict[str, Path]:
    """Write every output format; word-level formats only when the lyrics are word-timed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "ttml": ("lyrics.ttml", write_ttml(lyrics)),
        "lrc": ("lyrics.lrc", write_lrc(lyrics)),
        "srt": ("lyrics.srt", write_srt(lyrics)),
    }
    if lyrics.sync_type.is_word_level:
        files["lrc_word"] = ("lyrics.word.lrc", write_lrc(lyrics, word_level=True))
        files["qrc"] = ("lyrics.qrc", write_qrc(lyrics))
    written = {}
    for key, (name, content) in files.items():
        path = out_dir / name
        # LF everywhere, so files match what Composer writes regardless of the OS.
        path.write_text(content, encoding="utf-8", newline="\n")
        written[key] = path
    return written
