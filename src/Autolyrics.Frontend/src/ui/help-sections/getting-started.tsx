import { getEffectiveKeysArray } from "@/stores/shortcut-bindings";
import { PROSE } from "@/ui/typography";
import { InlineKeyBadge } from "@/ui/inline-key-badge";
import { HelpTopic } from "@/ui/help-topic";

// -- Getting Started ----------------------------------------------------------

const GettingStartedSection: React.FC = () => (
  <div className="space-y-5">
    <p className={PROSE}>
      This is the autolyrics editor, built on Composer. autolyrics finds the lyrics, times every word and opens the
      finished song here, so all that is left is checking it and fixing what the machine got wrong.
    </p>

    <div className="space-y-4">
      <HelpTopic title="1. Check the flagged lines">
        <p className={PROSE}>
          The song opens on the Timeline. The <strong>to check</strong> button in the header lists the lines autolyrics
          was unsure about; pick one to jump the playhead there, and tick it off once it sounds right.
        </p>
      </HelpTopic>
      <HelpTopic title="2. Fix the timing">
        <p className={PROSE}>
          Drag word blocks on the waveform to move them, drag their edges to resize them, and split or merge words and
          syllables. Everything you change saves itself back to the song.
        </p>
      </HelpTopic>
      <HelpTopic title="3. Fix the text">
        <p className={PROSE}>
          The Edit tab shows the lyrics as plain text, one line per row. Correct a word there and its timing stays put;
          assign singers and background vocals in the same place.
        </p>
      </HelpTopic>
      <HelpTopic title="4. Preview and download">
        <p className={PROSE}>
          The Preview tab plays the song karaoke-style with the timing you set. The <strong>Files</strong> button in the
          header downloads the lyrics as TTML, LRC, SRT or QRC.
        </p>
      </HelpTopic>
    </div>

    <p className={PROSE}>
      Switch between the tabs with <InlineKeyBadge keys={getEffectiveKeysArray("global.goToEdit")} />,{" "}
      <InlineKeyBadge keys={getEffectiveKeysArray("global.goToTimeline")} /> and{" "}
      <InlineKeyBadge keys={getEffectiveKeysArray("global.goToPreview")} />.
    </p>
  </div>
);

// -- Exports ------------------------------------------------------------------

export { GettingStartedSection };
