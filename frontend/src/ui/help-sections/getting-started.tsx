import { LYRICS_FORMATS_PROSE } from "@/domain/lyrics-file/supported-formats";
import { getEffectiveKeysArray } from "@/stores/shortcut-bindings";
import { PROSE } from "@/ui/typography";
import { InlineKeyBadge } from "@/ui/inline-key-badge";
import { MOD_KEY } from "@/utils/platform";
import { HelpTopic } from "@/ui/help-topic";

// -- Getting Started ----------------------------------------------------------

const GettingStartedSection: React.FC = () => (
  <div className="space-y-5">
    <p className={PROSE}>
      This is the autolyrics editor, built on Composer. autolyrics opens finished songs on the Timeline with every
      word already timed; the tabs left-to-right are the manual way through: import, edit, sync and export.
    </p>

    <div className="space-y-4">
      <HelpTopic title="1. Import your audio">
        <p className={PROSE}>
          Drop an audio file (MP3, WAV, M4A, OGG, FLAC) into the Import tab, or paste a YouTube URL to pull the audio
          from a video. Local files can also be dropped straight onto the Timeline. The waveform appears once the audio
          loads.
        </p>
      </HelpTopic>
      <HelpTopic title="2. Add your lyrics">
        <p className={PROSE}>
          Go to the Edit tab and type or paste your lyrics, one line per row. If you have a lyrics file (
          {LYRICS_FORMATS_PROSE}), drop it there instead. You can also use{" "}
          <InlineKeyBadge keys={getEffectiveKeysArray("timeline.importLyrics")} /> in Timeline to import lyrics without
          leaving that view.
        </p>
      </HelpTopic>
      <HelpTopic title="3. Sync the timing">
        <p className={PROSE}>
          The Sync tab lets you sync words to the music using two keys: tap Space to mark gapless word boundaries, or
          hold F to capture a word's full duration. You can also tap Space while holding F to create gapless syllable
          boundaries. If you miss one, use the arrow keys to nudge the timing. For finer control, switch to Timeline and
          drag word blocks directly on the waveform.
        </p>
      </HelpTopic>
      <HelpTopic title="4. Preview and export">
        <p className={PROSE}>
          The Preview tab shows a live karaoke-style playback of your work. When you're happy with it, go to Export and
          download your TTML file. You can also copy the raw XML or export a project file to share with someone else.
        </p>
      </HelpTopic>
    </div>

    <p className={PROSE}>
      The tabs are meant to be followed left-to-right, but you can jump between them anytime using {MOD_KEY} + 1 through
      6.
    </p>

    <div className="aspect-video w-full rounded-lg overflow-hidden border border-composer-border">
      <iframe
        src="https://www.youtube.com/embed/to138zXZ0nc?rel=0"
        loading="lazy"
        title="Composer tutorial"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
        allowFullScreen
        className="w-full h-full"
      />
    </div>
  </div>
);

// -- Exports ------------------------------------------------------------------

export { GettingStartedSection };
