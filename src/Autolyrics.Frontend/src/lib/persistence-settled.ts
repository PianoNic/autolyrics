// -- Boot-time settled signals ------------------------------------------------
//
// A module-scoped promise that resolves once the boot-time restore from IndexedDB
// finishes. Opening a job awaits it before replacing the project, so the restore
// never clobbers the job's lyrics and audio.
//
// Tests reset the singleton via `__resetPersistenceSettledForTests` so each test
// starts with a fresh pending promise.

let _markPersistenceSettled: () => void = () => {};
let persistenceSettled: Promise<void> = new Promise<void>((resolve) => {
  _markPersistenceSettled = resolve;
});

function getPersistenceSettled(): Promise<void> {
  return persistenceSettled;
}

function markPersistenceSettled(): void {
  _markPersistenceSettled();
}

function __resetPersistenceSettledForTests(): void {
  persistenceSettled = new Promise<void>((resolve) => {
    _markPersistenceSettled = resolve;
  });
}

// -- Exports ------------------------------------------------------------------

export { getPersistenceSettled, markPersistenceSettled, __resetPersistenceSettledForTests };
