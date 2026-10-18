import { JSON_SCHEMA, load } from "js-yaml";
import defaultsYaml from "../../config/preferences.default.yaml?raw";
import { api } from "./api";
import type { Destination } from "./components/MapView";

export type Prefs = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

/** Defaults bundled from config/preferences.default.yaml (same file the scraper uses). */
// JSON schema keeps dates as "YYYY-MM-DD" strings, which is what the scraper expects.
export const DEFAULT_PREFS: Prefs = load(defaultsYaml, { schema: JSON_SCHEMA }) as Prefs;

export async function loadPrefs(): Promise<{ prefs: Prefs; stored: boolean }> {
  const stored = await api.preferences();
  return stored ? { prefs: stored, stored: true }
    : { prefs: structuredClone(DEFAULT_PREFS), stored: false };
}

export function destinations(prefs: Prefs): Destination[] {
  return (prefs.destinations ?? []) as Destination[];
}
