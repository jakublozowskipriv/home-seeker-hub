import { useEffect, useState } from "react";

/** Listings picked for side-by-side comparison (per device, at most MAX_COMPARE). */
export const MAX_COMPARE = 4;
const KEY = "hs-compare";
const EVENT = "hs-compare-changed";

export function compareIds(): string[] {
  try {
    const ids = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(ids) ? ids.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function setCompareIds(ids: string[]): void {
  try { localStorage.setItem(KEY, JSON.stringify(ids.slice(0, MAX_COMPARE))); } catch { /* */ }
  window.dispatchEvent(new Event(EVENT));
}

/** Adds or removes a listing; the oldest pick makes room when the list is full. */
export function toggleCompare(id: string): void {
  const ids = compareIds();
  setCompareIds(ids.includes(id) ? ids.filter((x) => x !== id)
    : [...ids, id].slice(-MAX_COMPARE));
}

export function useCompare(): string[] {
  const [ids, setIds] = useState(compareIds);
  useEffect(() => {
    const update = () => setIds(compareIds());
    window.addEventListener(EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return ids;
}
