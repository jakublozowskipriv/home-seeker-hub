import { DemoApi } from "./demo";
import { SupabaseApi } from "./supabase";
import type { Api } from "./types";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

/** Real backend when built with Supabase settings, otherwise the demo backend. */
export const api: Api = url && key ? new SupabaseApi(url, key) : new DemoApi();
export type * from "./types";
