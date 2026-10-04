import { PROJECT_STORE_NAME, setInStore } from "@/lib/persistence-idb";

// -- Constants -----------------------------------------------------------------

const CURRENT_KEY = "current";

// -- Helpers -------------------------------------------------------------------

function seedProject(project: unknown): Promise<void> {
  return setInStore(PROJECT_STORE_NAME, CURRENT_KEY, project);
}

// -- Exports -------------------------------------------------------------------

export { seedProject };
