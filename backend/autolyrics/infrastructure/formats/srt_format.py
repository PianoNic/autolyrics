from autolyrics.domain.lyrics import Lyrics
from autolyrics.infrastructure.formats.time_format import TimeFormat


class SrtFormat:
    @staticmethod
    def write(lyrics: Lyrics) -> str:
        blocks = []
        for line in lyrics.lines:
            bounds = line.bounds()
            if bounds is None:
                continue
            text = line.text
            if line.background:
                text = f"{text} ({line.background_text})" if text else f"({line.background_text})"
            blocks.append(f"{len(blocks) + 1}\n{TimeFormat.srt(bounds[0])} --> "
                          f"{TimeFormat.srt(bounds[1])}\n{text}\n")
        return "\n".join(blocks)
