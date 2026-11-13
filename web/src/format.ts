import type {
  Leg, Listing, ListingStatus, Member, Parcel, PricePoint, Reaction, RedFlag, StatusKey, Verdict,
} from "./api/types";

export const STATUS_LABELS: Record<StatusKey, string> = {
  interesting: "⭐ Interesujące",
  viewing: "📅 Oglądanie",
  seen: "👀 Obejrzane",
  offer: "🤝 Negocjacje",
  rejected: "✖️ Odrzucone",
};

export const VERDICT_LABELS: Record<Verdict, string> = {
  match: "Pasuje",
  review: "Do sprawdzenia",
  negotiable: "Do negocjacji",
  rejected: "Odrzucone",
};

export const HEATING_LABELS: Record<string, string> = {
  district: "miejskie", gas: "gazowe", electric: "elektryczne", heat_pump: "pompa ciepła",
  other: "inne",
};

export function money(value: number | null | undefined): string {
  if (value == null) return "cena ?";
  return `${Math.round(value).toLocaleString("pl-PL")} zł`;
}

export function floorText(floor: number | null, total: number | null): string {
  if (floor == null) return "piętro ?";
  const label = floor === 0 ? "parter" : `${floor}. piętro`;
  return total ? `${label} z ${total}` : label;
}

export function headline(l: Listing): string {
  const rooms = l.rooms ? `${l.rooms} pok.` : "? pok.";
  const area = l.area ? `${l.area.toLocaleString("pl-PL")} m²` : "? m²";
  return `${rooms} · ${area} · ${floorText(l.floor, l.floors_total)}`;
}

/** "Praca (Nowy Rynek D)" -> "Praca" */
export function shortDestination(name: string): string {
  return name.split(" (")[0];
}

/** Commute entries in a stable order (JSONB does not keep key order). */
export function commuteEntries(l: Listing): [string, number][] {
  return Object.entries(l.evaluation?.commute ?? {}).sort(([a], [b]) => a.localeCompare(b));
}

export function isEstimate(l: Listing): boolean {
  return l.evaluation?.commute_method !== "timetable";
}

/** "linia 2", "linie 5 → 2" (with a change) or "pieszo". */
export function routeLines(legs: Leg[] | undefined): string {
  const rides = (legs ?? []).flatMap((leg) => (leg.mode === "walk" ? [] : [leg.line]));
  if (!rides.length) return "pieszo";
  return `${rides.length === 1 ? "linia" : "linie"} ${rides.join(" → ")}`;
}

export function legText(leg: Leg): string {
  if (leg.mode === "walk") return `🚶 ${leg.minutes} min`;
  return `${leg.mode === "tram" ? "🚋" : "🚌"} ${leg.line}: ${leg.from} → ${leg.to}`;
}

export function distance(m: number): string {
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`;
}

/** Map of the parcel in the national Geoportal (cadastre, zoning). */
export function geoportalUrl(parcel: Parcel): string {
  return `https://mapy.geoportal.gov.pl/imapnext/imap/?identifyParcel=${encodeURIComponent(parcel.id)}`;
}

export const EKW_URL = "https://przegladarka-ekw.ms.gov.pl/eukw_prz/KsiegiWieczyste/wyszukiwanieKW";

/** Median price per m² by district (from all stored listings, at least 8 per district). */
export function districtMedians(listings: Listing[]): Map<string, number> {
  const by = new Map<string, number[]>();
  for (const l of listings) {
    if (!l.district || !l.price_per_m2) continue;
    const key = l.district.toLowerCase();
    by.set(key, [...(by.get(key) ?? []), l.price_per_m2]);
  }
  const out = new Map<string, number>();
  for (const [key, values] of by) {
    if (values.length < 8) continue;
    values.sort((a, b) => a - b);
    const mid = values.length >> 1;
    out.set(key, values.length % 2 ? values[mid]! : (values[mid - 1]! + values[mid]!) / 2);
  }
  return out;
}

/** Red flags from the description, plus a suspiciously low price for the district. */
export function redFlags(l: Listing, medians: Map<string, number>): RedFlag[] {
  const flags = [...(l.evaluation?.red_flags ?? [])];
  const median = l.district ? medians.get(l.district.toLowerCase()) : undefined;
  if (median && l.price_per_m2 && l.price_per_m2 < median * 0.75) {
    const below = Math.round((1 - l.price_per_m2 / median) * 100);
    flags.push({ level: "high", text: `cena za m² o ${below}% niższa niż mediana w dzielnicy ` +
      `(${money(median)}/m²) – zapytaj, dlaczego tak tanio` });
  }
  return flags;
}

export function sourceName(source: string): string {
  return { otodom: "Otodom", olx: "OLX" }[source] ?? source;
}

export function googleMapsUrl(l: Listing): string | null {
  return l.lat != null && l.lon != null
    ? `https://www.google.com/maps/search/?api=1&query=${l.lat},${l.lon}` : null;
}

export function appleMapsUrl(l: Listing): string | null {
  return l.lat != null && l.lon != null ? `https://maps.apple.com/?ll=${l.lat},${l.lon}&q=Mieszkanie`
    : null;
}

export function relativeTime(iso: string | null, now = Date.now()): string {
  if (!iso) return "nigdy";
  const minutes = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "przed chwilą";
  if (minutes < 60) return `${minutes} min temu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} godz. temu`;
  const days = Math.round(hours / 24);
  return days === 1 ? "wczoraj" : `${days} dni temu`;
}

export function personName(email: string, members: Member[]): string {
  const m = members.find((x) => x.email === email);
  return m?.display_name || email.split("@")[0];
}

export function initials(name: string): string {
  return name.split(/[\s.@_-]+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase())
    .join("");
}

/**
 * One entry per apartment: listings of the same duplicate group (same flat on several
 * portals) collapse into the best-scored one, remembering the other sources.
 */
export interface Grouped {
  listing: Listing;
  duplicates: Listing[];
}

export function groupDuplicates(listings: Listing[]): Grouped[] {
  const groups = new Map<string, Grouped>();
  for (const l of listings) {
    const key = l.group_id ?? l.id;
    const g = groups.get(key);
    if (!g) groups.set(key, { listing: l, duplicates: [] });
    else if (l.score > g.listing.score) {
      g.duplicates.push(g.listing);
      g.listing = l;
    } else g.duplicates.push(l);
  }
  return [...groups.values()];
}

export type SortKey = "score" | "price" | "newest" | "price_m2" | "drop";
export type VerdictFilter = "match" | "review" | "negotiable" | "all";
export type MarketFilter = "all" | "secondary" | "primary";
export type ReactionFilter = "any" | "liked" | "liked_by_me" | "disliked" | "none";

export interface Filters {
  verdict: VerdictFilter;
  status: StatusKey | "none" | "any";
  sort: SortKey;
  query: string;
  onlyNew: boolean;
  market: MarketFilter;
  reaction: ReactionFilter;
  sunny: boolean;
}

export const DEFAULT_FILTERS: Filters = {
  verdict: "match", status: "any", sort: "score", query: "", onlyNew: false, market: "all",
  reaction: "any", sunny: false,
};

/** Days on the market (since the portal's publication date, else since we first saw it)
 * and the drop from the highest price seen. */
export interface PriceStats {
  days: number;
  since: string;
  dropPct: number | null;
  fromPrice: number | null;
}

export function priceStats(l: Listing, history: PricePoint[] | undefined,
                           now = Date.now()): PriceStats {
  const since = l.published_at ?? l.first_seen_at;
  const days = Math.max(0, Math.floor((now - new Date(since).getTime()) / 86400_000));
  const top = Math.max(l.price ?? 0, ...(history ?? []).map((p) => p.price));
  const dropped = l.price != null && top > l.price * 1.005;
  return {
    days, since,
    dropPct: dropped ? Math.round((1 - l.price! / top) * 1000) / 10 : null,
    fromPrice: dropped ? top : null,
  };
}

const COMPASS: Record<string, string> = { N: "północ", E: "wschód", S: "południe", W: "zachód" };

export function exposureText(exposure: string[] | undefined): string | null {
  return exposure?.length ? exposure.map((d) => COMPASS[d] ?? d).join(", ") : null;
}

/** Windows to the south or west: the sunny side. */
export function isSunny(l: Listing): boolean {
  return (l.evaluation?.exposure ?? []).some((d) => d === "S" || d === "W");
}

/** What filtering needs besides the listings and the filters. */
export interface FilterContext {
  statuses: Map<string, ListingStatus>;
  lastVisit: string | null;
  reactions?: Reaction[];
  me?: string | null;
  history?: Map<string, PricePoint[]>;
  now?: number;
}

export function isNew(l: Listing, lastVisit: string | null): boolean {
  return lastVisit != null && l.first_seen_at > lastVisit;
}

/** Does a (grouped) listing pass the reaction filter? Reactions on any portal's copy count. */
function matchesReaction(g: Grouped, f: ReactionFilter, reactions: Reaction[], me: string | null) {
  if (f === "any") return true;
  const ids = new Set([g.listing.id, ...g.duplicates.map((d) => d.id)]);
  const mine = reactions.filter((r) => ids.has(r.listing_id));
  if (f === "liked") return mine.some((r) => r.reaction === "up");
  if (f === "liked_by_me") return mine.some((r) => r.reaction === "up" && r.email === me);
  if (f === "disliked") return mine.some((r) => r.reaction === "down");
  return mine.length === 0;
}

export function applyFilters(items: Grouped[], f: Filters, ctx: FilterContext): Grouped[] {
  const { statuses, lastVisit, reactions = [], me = null, history = new Map() } = ctx;
  const q = f.query.trim().toLowerCase();
  const drop = (l: Listing) => priceStats(l, history.get(l.id), ctx.now).dropPct ?? 0;
  const out = items.filter((g) => {
    const l = g.listing;
    if (!matchesReaction(g, f.reaction, reactions, me)) return false;
    if (f.sunny && !isSunny(l)) return false;
    if (f.verdict !== "all" && l.verdict !== f.verdict) return false;
    const status = statuses.get(l.id)?.status;
    if (f.status === "none" && status) return false;
    if (f.status !== "any" && f.status !== "none" && status !== f.status) return false;
    // Listings I rejected myself disappear unless I look for them explicitly.
    if (f.status === "any" && status === "rejected") return false;
    if (f.onlyNew && !isNew(l, lastVisit)) return false;
    if (f.market !== "all" && l.market !== f.market) return false;
    if (q && !`${l.location_text ?? ""} ${l.district ?? ""} ${l.title ?? ""}`.toLowerCase()
      .includes(q)) return false;
    return true;
  });
  const by: Record<SortKey, (a: Listing, b: Listing) => number> = {
    score: (a, b) => b.score - a.score,
    price: (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
    price_m2: (a, b) => (a.price_per_m2 ?? Infinity) - (b.price_per_m2 ?? Infinity),
    newest: (a, b) => b.first_seen_at.localeCompare(a.first_seen_at),
    drop: (a, b) => drop(b) - drop(a) || b.score - a.score,
  };
  return out.sort((a, b) => by[f.sort](a.listing, b.listing));
}

export function reactionSummary(listingId: string, reactions: Reaction[]) {
  const mine = reactions.filter((r) => r.listing_id === listingId);
  return {
    up: mine.filter((r) => r.reaction === "up"),
    down: mine.filter((r) => r.reaction === "down"),
  };
}

export function scoreClass(score: number): string {
  return score >= 75 ? "score-high" : score >= 55 ? "score-mid" : "score-low";
}
