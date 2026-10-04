import type { ModalNavSection } from "@/ui/modal-nav-layout";
import {
  IconAward,
  IconEye,
  IconInfoHexagon,
  IconKeyboard,
  IconLayoutRows,
  IconLifebuoy,
  IconLink,
  IconPencil,
  IconRocket,
  IconTagStarred,
} from "@tabler/icons-react";

// -- Sections ------------------------------------------------------------------

const HELP_SECTIONS: readonly ModalNavSection[] = [
  { id: "getting-started", label: "Getting Started", icon: IconRocket },
  { id: "best-practices", label: "Best practices", icon: IconTagStarred },
  { id: "keyboard-shortcuts", label: "Keyboard Shortcuts", icon: IconKeyboard },
  { id: "editing", label: "Editing Lyrics", icon: IconPencil },
  { id: "timeline", label: "Timeline", icon: IconLayoutRows },
  { id: "groups", label: "Linked groups", icon: IconLink },
  { id: "preview", label: "Preview", icon: IconEye },
  { id: "recovery", label: "Recovery", icon: IconLifebuoy },
  { id: "ttml-standards", label: "TTML & standards", icon: IconAward },
  { id: "about", label: "About", icon: IconInfoHexagon },
];

// -- Exports -------------------------------------------------------------------

export { HELP_SECTIONS };
