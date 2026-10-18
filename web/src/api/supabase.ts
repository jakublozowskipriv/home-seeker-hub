import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type {
  Api, Comment, Listing, ListingStatus, Me, Member, PricePoint, Reaction, ReactionKey, StatusKey,
} from "./types";

/** Columns for the list view: everything except the heavy description / raw data. */
const LIST_COLUMNS = [
  "id", "source", "url", "title", "price", "area", "price_per_m2", "rooms", "floor",
  "floors_total", "build_year", "market", "has_balcony", "has_elevator", "heating", "ownership",
  "completion_date", "district", "location_text", "lat", "lon", "coords_approximate", "images",
  "is_private_owner", "agency", "published_at", "verdict", "score", "evaluation", "group_id",
  "first_seen_at", "last_seen_at", "active",
].join(",");
const PAGE = 1000; // Supabase returns at most 1000 rows per request

const NETWORK_ERRORS = ["Load failed", "Failed to fetch", "NetworkError", "Network request failed"];

/** Human-readable (Polish) message for a Supabase / network error. */
export function errorMessage(message: string): string {
  if (NETWORK_ERRORS.some((m) => message.includes(m))) {
    return "Brak połączenia z serwerem – sprawdź internet i spróbuj ponownie.";
  }
  if (message.includes("row-level security") || message.includes("permission denied")) {
    return "Brak uprawnień do tej operacji.";
  }
  if (message.includes("duplicate key")) return "Taki wpis już istnieje.";
  return message;
}

function check<T>(result: { data: T; error: { message: string } | null }): T {
  if (result.error) throw new Error(errorMessage(result.error.message));
  return result.data;
}

export class SupabaseApi implements Api {
  readonly demo = false;
  private db: SupabaseClient;

  constructor(url: string, key: string) {
    // PKCE: the e-mail link returns with ?code=… (a query parameter), which does not clash
    // with the app's #/hash routes; supabase-js exchanges it for a session on start.
    this.db = createClient(url, key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true,
              flowType: "pkce" },
    });
  }

  private async email(): Promise<string> {
    const { data } = await this.db.auth.getSession();
    const email = data.session?.user.email;
    if (!email) throw new Error("Nie jesteś zalogowany");
    return email.toLowerCase();
  }

  async currentUser(): Promise<Me | null> {
    const { data } = await this.db.auth.getSession();
    const email = data.session?.user.email?.toLowerCase();
    if (!email) return null;
    const rows = check(await this.db.from("members").select("email,role,display_name")
      .eq("email", email));
    return { email, member: (rows?.[0] as Member) ?? null };
  }

  async sendCode(email: string): Promise<void> {
    const { error } = await this.db.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: { emailRedirectTo: window.location.origin + window.location.pathname },
    });
    if (error) throw new Error(error.message);
  }

  async verifyCode(email: string, code: string): Promise<void> {
    const { error } = await this.db.auth.verifyOtp({
      email: email.trim().toLowerCase(), token: code.trim(), type: "email",
    });
    if (error) throw new Error(error.message);
  }

  async signOut(): Promise<void> {
    await this.db.auth.signOut();
  }

  async listings(includeRejected: boolean): Promise<Listing[]> {
    const out: Listing[] = [];
    for (let from = 0; ; from += PAGE) {
      let query = this.db.from("listings").select(LIST_COLUMNS).eq("active", true)
        .order("score", { ascending: false }).range(from, from + PAGE - 1);
      if (!includeRejected) query = query.neq("verdict", "rejected");
      const rows = check(await query) as unknown as Listing[];
      out.push(...rows);
      if (rows.length < PAGE) return out;
    }
  }

  async listing(id: string): Promise<Listing | null> {
    const rows = check(await this.db.from("listings").select("*").eq("id", id));
    return (rows?.[0] as Listing) ?? null;
  }

  async priceHistory(id: string): Promise<PricePoint[]> {
    return check(await this.db.from("price_history").select("price,seen_at").eq("listing_id", id)
      .order("seen_at")) as PricePoint[];
  }

  async lastRunAt(): Promise<string | null> {
    const rows = check(await this.db.from("runs").select("finished_at")
      .not("finished_at", "is", null).order("finished_at", { ascending: false }).limit(1));
    return (rows?.[0] as { finished_at: string } | undefined)?.finished_at ?? null;
  }

  async statuses(): Promise<ListingStatus[]> {
    return check(await this.db.from("listing_status").select("*")) as ListingStatus[];
  }

  async setStatus(listingId: string, status: StatusKey | null, note: string | null = null,
                  viewingAt: string | null = null): Promise<void> {
    if (status === null) {
      check(await this.db.from("listing_status").delete().eq("listing_id", listingId));
      return;
    }
    check(await this.db.from("listing_status").upsert({
      listing_id: listingId, status, note, viewing_at: viewingAt,
      updated_by: await this.email(), updated_at: new Date().toISOString(),
    }));
  }

  async reactions(): Promise<Reaction[]> {
    return check(await this.db.from("reactions").select("listing_id,email,reaction")) as Reaction[];
  }

  async setReaction(listingId: string, reaction: ReactionKey | null): Promise<void> {
    const email = await this.email();
    if (reaction === null) {
      check(await this.db.from("reactions").delete().eq("listing_id", listingId)
        .eq("email", email));
      return;
    }
    check(await this.db.from("reactions").upsert({
      listing_id: listingId, email, reaction, created_at: new Date().toISOString(),
    }));
  }

  async comments(listingId: string): Promise<Comment[]> {
    return check(await this.db.from("comments").select("*").eq("listing_id", listingId)
      .order("created_at")) as Comment[];
  }

  async commentCounts(): Promise<Record<string, number>> {
    const rows = check(await this.db.from("comments").select("listing_id")) as
      { listing_id: string }[];
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.listing_id] = (counts[r.listing_id] ?? 0) + 1;
    return counts;
  }

  async addComment(listingId: string, body: string): Promise<void> {
    check(await this.db.from("comments").insert({
      listing_id: listingId, author_email: await this.email(), body,
      created_at: new Date().toISOString(),
    }));
  }

  async deleteComment(id: number): Promise<void> {
    check(await this.db.from("comments").delete().eq("id", id));
  }

  async members(): Promise<Member[]> {
    return check(await this.db.from("members").select("email,role,display_name")
      .order("role")) as Member[];
  }

  async addMember(email: string, displayName: string | null): Promise<void> {
    check(await this.db.from("members").insert({
      email: email.trim().toLowerCase(), role: "member", display_name: displayName,
      created_at: new Date().toISOString(),
    }));
  }

  async removeMember(email: string): Promise<void> {
    check(await this.db.from("members").delete().eq("email", email));
  }

  async touchVisit(): Promise<string | null> {
    const email = await this.email();
    const rows = check(await this.db.from("member_visits").select("last_visit_at")
      .eq("email", email));
    const previous = (rows?.[0] as { last_visit_at: string } | undefined)?.last_visit_at ?? null;
    check(await this.db.from("member_visits").upsert({
      email, last_visit_at: new Date().toISOString(),
    }));
    return previous;
  }

  async preferences(): Promise<Record<string, unknown> | null> {
    const rows = check(await this.db.from("settings").select("value").eq("key", "preferences"));
    return (rows?.[0] as { value: Record<string, unknown> } | undefined)?.value ?? null;
  }

  async savePreferences(prefs: Record<string, unknown>): Promise<void> {
    check(await this.db.from("settings").upsert({
      key: "preferences", value: prefs, updated_at: new Date().toISOString(),
    }));
  }
}
