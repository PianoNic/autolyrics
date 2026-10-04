import type { Agent } from "@/domain/agent/model";
import type { LinkGroup } from "@/domain/group/template";
import { migrateLegacyTransliterationLine } from "@/domain/language/migrate";
import type { LyricLine } from "@/domain/line/model";
import type { MetadataKey } from "@/domain/project/imported-metadata";
import type { ProjectMetadata } from "@/domain/project/metadata";
import type { SnapPoint } from "@/domain/snap-point/model";
import { PROJECT_STORE_NAME, deleteFromStore, getFromStore, setInStore } from "@/lib/persistence-idb";
import type { GranularityMode } from "@/stores/project";
import type { SyllableSplitDefaults, TtmlEditState } from "@/stores/project/types";

// -- Types --------------------------------------------------------------------

type SavedAudioSource = { kind: "file"; name: string };

interface SavedProject {
  version: 1 | 2 | 3;
  savedAt: number;
  metadata: ProjectMetadata;
  agents: Agent[];
  lines: LyricLine[];
  groups?: LinkGroup[];
  granularity: GranularityMode;
  syllableSplitDefaults?: SyllableSplitDefaults;
  audioFileName?: string;
  audioSource?: SavedAudioSource;
  dismissedSuggestions?: string[];
  dismissedExplicitSuggestions?: string[];
  primingStripped?: boolean;
  customSnapPoints?: (SnapPoint | number)[];
  hasUnexportedImport?: boolean;
  importedMetadataKeys?: MetadataKey[];
  ttmlEditState?: TtmlEditState;
}

interface ProjectSaveInput {
  metadata: ProjectMetadata;
  agents: Agent[];
  lines: LyricLine[];
  groups: LinkGroup[];
  granularity: GranularityMode;
  syllableSplitDefaults: SyllableSplitDefaults;
  audioSource: SavedAudioSource | undefined;
  dismissedSuggestions: string[];
  dismissedExplicitSuggestions: string[];
  primingStripped: boolean;
  customSnapPoints: SnapPoint[];
  hasUnexportedImport: boolean;
  importedMetadataKeys: MetadataKey[];
  ttmlEditState: TtmlEditState;
}

// -- Constants ----------------------------------------------------------------

const CURRENT_PROJECT_KEY = "current";
const AUDIO_FILE_KEY = "current-audio";

// -- Public API ---------------------------------------------------------------

async function saveCurrentProject(input: ProjectSaveInput): Promise<void> {
  const audioFileName = input.audioSource?.kind === "file" ? input.audioSource.name : undefined;
  const project: SavedProject = { version: 3, savedAt: Date.now(), ...input, audioFileName };
  await setInStore(PROJECT_STORE_NAME, CURRENT_PROJECT_KEY, project);
}

async function loadCurrentProject(): Promise<SavedProject | undefined> {
  const project = await getFromStore<SavedProject>(PROJECT_STORE_NAME, CURRENT_PROJECT_KEY);
  if (project && project.version < 3) {
    if (Array.isArray(project.lines)) project.lines = project.lines.map(migrateLegacyTransliterationLine);
    project.version = 3;
    await setInStore(PROJECT_STORE_NAME, CURRENT_PROJECT_KEY, project);
  }
  return project;
}

async function replaceCurrentProject(project: SavedProject): Promise<void> {
  await setInStore(PROJECT_STORE_NAME, CURRENT_PROJECT_KEY, project);
}

async function clearCurrentProject(): Promise<void> {
  await deleteFromStore(PROJECT_STORE_NAME, CURRENT_PROJECT_KEY);
  await clearAudioFile();
}

// -- Audio File Persistence ---------------------------------------------------

interface SavedAudioFile {
  name: string;
  type: string;
  data: ArrayBuffer;
}

async function saveAudioFile(file: File): Promise<void> {
  const data = await file.arrayBuffer();
  await setInStore<SavedAudioFile>(PROJECT_STORE_NAME, AUDIO_FILE_KEY, {
    name: file.name,
    type: file.type,
    data,
  });
}

async function loadAudioFile(): Promise<File | undefined> {
  const saved = await getFromStore<SavedAudioFile>(PROJECT_STORE_NAME, AUDIO_FILE_KEY);
  if (!saved) return undefined;
  return new File([saved.data], saved.name, { type: saved.type });
}

async function clearAudioFile(): Promise<void> {
  await deleteFromStore(PROJECT_STORE_NAME, AUDIO_FILE_KEY);
}

// -- Exports ------------------------------------------------------------------

export {
  saveCurrentProject,
  loadCurrentProject,
  replaceCurrentProject,
  clearCurrentProject,
  saveAudioFile,
  loadAudioFile,
  clearAudioFile,
};
export type { ProjectSaveInput, SavedAudioSource, SavedProject };
