from autolyrics.formats.timefmt import format_srt_time
from autolyrics.model import Lyrics


def write_srt(lyrics: Lyrics) -> str:
    blocks = []
    for line in lyrics.lines:
        bounds = line.bounds()
        if bounds is None:
            continue
        text = line.text
        if line.background:
            text = f"{text} ({line.background_text})" if text else f"({line.background_text})"
        blocks.append(
            f"{len(blocks) + 1}\n{format_srt_time(bounds[0])} --> {format_srt_time(bounds[1])}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)
