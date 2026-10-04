import { PROSE } from "@/ui/typography";
import { HelpTopic } from "@/ui/help-topic";

// -- Constants ----------------------------------------------------------------

const LINK = "text-composer-text underline underline-offset-2 hover:text-composer-text-bright";

// -- About --------------------------------------------------------------------

const AboutSection: React.FC = () => (
  <div className="space-y-5">
    <div className="relative -mx-6 -mt-6">
      <div className="absolute inset-0 bg-gradient-to-b from-composer-accent/20 to-transparent pointer-events-none" />
      <div className="relative px-6 pt-7 pb-8 flex items-center gap-5">
        <img src="/logo.svg" alt="" className="size-14 shrink-0" />
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold leading-tight tracking-tight">autolyrics</h2>
          <p className="text-sm text-composer-text-secondary">Word-synced lyrics from a song link.</p>
          <p className="text-xs text-composer-text-muted font-mono mt-2">v{__APP_VERSION__}</p>
        </div>
      </div>
    </div>

    <HelpTopic title="What it is">
      <p className={PROSE}>
        Runs on your own machine. A local backend finds the song, its lyrics and the vocals, times every word and
        checks the text with DeepSeek; this editor is where you adjust anything it got wrong.
      </p>
    </HelpTopic>

    <HelpTopic title="Built on Composer">
      <p className={PROSE}>
        The editor is{" "}
        <a href="https://github.com/better-lyrics/composer" target="_blank" rel="noopener noreferrer" className={LINK}>
          Composer
        </a>{" "}
        by{" "}
        <a href="https://boidu.dev" target="_blank" rel="noopener noreferrer" className={LINK}>
          Boidu
        </a>{" "}
        and the{" "}
        <a href="https://betterlyrics.org" target="_blank" rel="noopener noreferrer" className={LINK}>
          Better Lyrics
        </a>{" "}
        community. autolyrics is a modified version and is not affiliated with or endorsed by them; please report
        autolyrics problems here, not to Composer.
      </p>
    </HelpTopic>

    <HelpTopic title="License">
      <p className={PROSE}>
        AGPL v3, like Composer. You can get the complete source of this version and change it under the same terms.
      </p>
    </HelpTopic>
  </div>
);

// -- Exports ------------------------------------------------------------------

export { AboutSection };
