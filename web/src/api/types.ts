export type Verdict = "match" | "review" | "negotiable" | "rejected";
export type Market = "primary" | "secondary";
export type StatusKey = "interesting" | "viewing" | "seen" | "rejected" | "offer";
export type ReactionKey = "up" | "down";
export type Role = "owner" | "member";

export interface Evaluation {
  verdict: Verdict;
  score: number;
  rejections: string[];
  missing: string[];
  warnings: string[];
  location_category: string | null;
  location_name: string | null;
  commute: Record<string, number>;
}

/** A listing as stored by the scraper (`listings` table). */
export interface Listing {
  id: string;
  source: string;
  url: string;
  title: string | null;
  price: number | null;
  area: number | null;
  price_per_m2: number | null;
  rooms: number | null;
  floor: number | null;
  floors_total: number | null;
  build_year: number | null;
  market: Market | null;
  has_balcony: boolean | null;
  has_elevator: boolean | null;
  heating: string | null;
  ownership: string | null;
  completion_date: string | null;
  district: string | null;
  location_text: string | null;
  lat: number | null;
  lon: number | null;
  coords_approximate: boolean;
  images: string[] | null;
  is_private_owner: boolean | null;
  agency: string | null;
  published_at: string | null;
  verdict: Verdict;
  score: number;
  evaluation: Evaluation | null;
  group_id: string | null;
  first_seen_at: string;
  last_seen_at: string;
  active: boolean;
  description?: string | null;
  raw?: Record<string, unknown> | null;
}

export interface ListingStatus {
  listing_id: string;
  status: StatusKey;
  note: string | null;
  viewing_at: string | null;
  updated_by: string | null;
  updated_at: string;
}

export interface Reaction {
  listing_id: string;
  email: string;
  reaction: ReactionKey;
}

export interface Comment {
  id: number;
  listing_id: string;
  author_email: string;
  body: string;
  created_at: string;
}

export interface Member {
  email: string;
  role: Role;
  display_name: string | null;
}

export interface PricePoint {
  price: number;
  seen_at: string;
}

export interface Me {
  email: string;
  member: Member | null; // null: signed in, but not on the members list
}

/** Everything the web app needs from the backend; Supabase and demo implement it. */
export interface Api {
  readonly demo: boolean;
  // auth
  currentUser(): Promise<Me | null>;
  sendCode(email: string): Promise<void>;
  verifyCode(email: string, code: string): Promise<void>;
  signOut(): Promise<void>;
  // listings
  listings(includeRejected: boolean): Promise<Listing[]>;
  listing(id: string): Promise<Listing | null>;
  priceHistory(id: string): Promise<PricePoint[]>;
  lastRunAt(): Promise<string | null>;
  // shared state
  statuses(): Promise<ListingStatus[]>;
  setStatus(listingId: string, status: StatusKey | null, note?: string | null,
            viewingAt?: string | null): Promise<void>;
  reactions(): Promise<Reaction[]>;
  setReaction(listingId: string, reaction: ReactionKey | null): Promise<void>;
  comments(listingId: string): Promise<Comment[]>;
  commentCounts(): Promise<Record<string, number>>;
  addComment(listingId: string, body: string): Promise<void>;
  deleteComment(id: number): Promise<void>;
  // members, visits, preferences
  members(): Promise<Member[]>;
  addMember(email: string, displayName: string | null): Promise<void>;
  removeMember(email: string): Promise<void>;
  /** Returns the previous visit time and records the current one. */
  touchVisit(): Promise<string | null>;
  preferences(): Promise<Record<string, unknown> | null>;
  savePreferences(prefs: Record<string, unknown>): Promise<void>;
}
