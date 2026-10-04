import { describe, expect, it } from "vitest";
import {
  DB_NAME,
  DB_VERSION,
  PROJECT_STORE_NAME,
  deleteFromStore,
  getFromStore,
  openDB,
  setInStore,
} from "@/lib/persistence-idb";

// The shared browser setup (src/test/setup-browser.ts) deletes the entire
// `ttml-composer` database before every test, so each test starts from a
// fresh cold-open of the schema.

// -- Schema -------------------------------------------------------------------

describe("persistence-idb · schema", () => {
  it("openDB returns a db at the expected version with only the project store", async () => {
    const db = await openDB();
    expect(db.version).toBe(DB_VERSION);
    expect([...db.objectStoreNames]).toEqual([PROJECT_STORE_NAME]);
    db.close();
  });

  it("opening twice returns a db with identical schema (no spurious upgrade)", async () => {
    const first = await openDB();
    expect(first.version).toBe(DB_VERSION);
    first.close();
    const second = await openDB();
    expect(second.version).toBe(DB_VERSION);
    expect([...second.objectStoreNames]).toEqual([PROJECT_STORE_NAME]);
    second.close();
  });

  it("upgrading a version 2 database drops the stem cache and keeps the project", async () => {
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 2);
      request.onupgradeneeded = () => {
        request.result.createObjectStore(PROJECT_STORE_NAME).put("saved work", "current");
        request.result.createObjectStore("separated-stems").put("stem bytes", "song");
      };
      request.onsuccess = () => {
        request.result.close();
        resolve();
      };
      request.onerror = () => reject(request.error);
    });

    const db = await openDB();
    expect([...db.objectStoreNames]).toEqual([PROJECT_STORE_NAME]);
    db.close();
    expect(await getFromStore(PROJECT_STORE_NAME, "current")).toBe("saved work");
  });
});

// -- CRUD ---------------------------------------------------------------------

describe("persistence-idb · CRUD", () => {
  it("getFromStore returns undefined when key absent", async () => {
    const value = await getFromStore<string>(PROJECT_STORE_NAME, "missing-key");
    expect(value).toBeUndefined();
  });

  it("set + get round-trips primitive values", async () => {
    await setInStore<string>(PROJECT_STORE_NAME, "k", "hello");
    expect(await getFromStore<string>(PROJECT_STORE_NAME, "k")).toBe("hello");
  });

  it("set + get round-trips structured values", async () => {
    const value = { title: "Song", tags: ["a", "b"], nested: { count: 3 } };
    await setInStore(PROJECT_STORE_NAME, "k", value);
    expect(await getFromStore(PROJECT_STORE_NAME, "k")).toEqual(value);
  });

  it("set overwrites the previous value at the same key", async () => {
    await setInStore(PROJECT_STORE_NAME, "k", "first");
    await setInStore(PROJECT_STORE_NAME, "k", "second");
    expect(await getFromStore(PROJECT_STORE_NAME, "k")).toBe("second");
  });

  it("deleteFromStore removes a present key", async () => {
    await setInStore(PROJECT_STORE_NAME, "k", "v");
    await deleteFromStore(PROJECT_STORE_NAME, "k");
    expect(await getFromStore(PROJECT_STORE_NAME, "k")).toBeUndefined();
  });

  it("deleteFromStore on an absent key resolves without throwing", async () => {
    await expect(deleteFromStore(PROJECT_STORE_NAME, "never-set")).resolves.toBeUndefined();
  });
});
