import { DemoApi } from "./demo";
import { SupabaseApi } from "./supabase";
import type { Api } from "./types";

const rawUrl = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.trim();
const key = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined)?.trim();

/** Supabase wants the bare project URL; dashboards often show it with /rest/v1 appended. */
export function projectUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    return new URL(value).origin;
  } catch {
    return undefined;
  }
}

const url = projectUrl(rawUrl);

/** Real backend when built with Supabase settings, otherwise the demo backend. */
export const api: Api = url && key ? new SupabaseApi(url, key) : new DemoApi();
export type * from "./types";
