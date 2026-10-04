// Adapted from Spicy Lyrics by Spikerko (https://github.com/Spikerko/spicy-lyrics), AGPL-3.0.
// Upstream: src/utils/Lyrics/isRtl.ts (fcc5f83).

// -- Constants ----------------------------------------------------------------

// Hebrew, Arabic, Syriac, Thaana, Arabic supplements and presentation forms.
const RTL_SCRIPT = /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB1D-\uFB4F\uFB50-\uFDFF\uFE70-\uFEFF]/;

// Digits, whitespace and common punctuation carry no direction of their own.
const NEUTRAL_CHARACTER = /[\d\s,.;:?!()[\]{}"'\\/<>@#$%^&*_=+-]/;

// -- Helpers ------------------------------------------------------------------

/** True when the first strongly directional character of the text is right-to-left. */
function isRtl(text: string): boolean {
  for (const char of text) {
    if (NEUTRAL_CHARACTER.test(char)) continue;
    return RTL_SCRIPT.test(char);
  }
  return false;
}

// -- Exports ------------------------------------------------------------------

export { isRtl };
