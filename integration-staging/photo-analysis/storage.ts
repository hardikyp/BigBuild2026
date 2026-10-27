import type { FieldVisit } from "./field-log";

const DATABASE_NAME = "morgan-field-notes";
const DATABASE_VERSION = 1;
const VISITS_STORE = "visits";
let databasePromise: Promise<IDBDatabase> | null = null;

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("This browser does not support local visit storage."));
  }
  if (databasePromise) return databasePromise;

  const opening = new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(VISITS_STORE)) {
        database.createObjectStore(VISITS_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => {
        database.close();
        databasePromise = null;
      };
      resolve(database);
    };
    request.onerror = () => reject(request.error ?? new Error("Could not open local visit storage."));
    request.onblocked = () => reject(new Error("Local visit storage is blocked by another open tab."));
  });
  const cachedOpening = opening.catch((error: unknown) => {
    databasePromise = null;
    throw error;
  });
  databasePromise = cachedOpening;
  return cachedOpening;
}

function withVisitStore<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDatabase().then(
    (database) =>
      new Promise<T>((resolve, reject) => {
        const transaction = database.transaction(VISITS_STORE, mode);
        const request = operation(transaction.objectStore(VISITS_STORE));
        let result: T | undefined;

        request.onsuccess = () => {
          result = request.result;
        };
        request.onerror = () => {
          reject(request.error ?? new Error("Could not access locally stored visits."));
        };
        transaction.oncomplete = () => {
          if (result === undefined) {
            reject(new Error("Local visit storage returned no result."));
            return;
          }
          resolve(result);
        };
        transaction.onerror = () => {
          reject(transaction.error ?? new Error("Could not save local visit data."));
        };
        transaction.onabort = () => {
          reject(transaction.error ?? new Error("Local visit storage transaction was aborted."));
        };
      }),
    (error: unknown) => Promise.reject(error),
  );
}

export function listVisits(): Promise<FieldVisit[]> {
  return withVisitStore("readonly", (store) => store.getAll());
}

export function saveVisit(visit: FieldVisit): Promise<IDBValidKey> {
  return withVisitStore("readwrite", (store) => store.put(visit));
}

export async function saveVisits(visits: FieldVisit[]): Promise<void> {
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(VISITS_STORE, "readwrite");
    const store = transaction.objectStore(VISITS_STORE);
    for (const visit of visits) store.put(visit);

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not import local visit data."));
    transaction.onabort = () => reject(transaction.error ?? new Error("Visit import was aborted."));
  });
}
