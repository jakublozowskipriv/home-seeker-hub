import type {
  Api, CalendarEvent, Comment, Listing, ListingStatus, Me, Member, NewEvent, PricePoint, Reaction,
  ReactionKey, StatusKey,
} from "./types";

/**
 * In-memory backend with made-up listings. Used when the app is built without Supabase
 * settings (local preview, screenshots, tests). Nothing here is real data.
 */

const DEST_WORK = "Praca (Nowy Rynek D)";
const DEST_CENTRE = "Stary Rynek";

function fake(
  n: number, district: string, street: string, lat: number, lon: number,
  over: Partial<Listing> & { commute?: [number, number] } = {},
): Listing {
  const { commute = [12, 15], ...rest } = over;
  const price = rest.price ?? 520_000 + n * 17_000;
  const area = rest.area ?? 40 + (n % 9);
  const verdict = rest.verdict ?? "match";
  const day = new Date(Date.now() - n * 7 * 3600_000).toISOString();
  return {
    id: `demo:${n}`,
    source: n % 4 === 0 ? "olx" : "otodom",
    url: "https://example.com/oferta-demo",
    title: `Mieszkanie demo ${n}`,
    price,
    area,
    price_per_m2: Math.round(price / area),
    rooms: 2 + (n % 2),
    floor: 2 + (n % 6),
    floors_total: 8,
    build_year: 2012 + (n % 14),
    market: n % 3 === 0 ? "primary" : "secondary",
    has_balcony: true,
    has_elevator: n % 2 === 0,
    heating: "district",
    ownership: "full",
    completion_date: n % 3 === 0 ? "2027-06-30" : null,
    district,
    location_text: `Poznań, ${district}, ${street}`,
    lat, lon,
    coords_approximate: false,
    images: [],
    is_private_owner: n % 5 === 0,
    agency: null,
    published_at: day,
    verdict,
    score: rest.score ?? 90 - n * 3,
    evaluation: {
      verdict, score: rest.score ?? 90 - n * 3,
      rejections: verdict === "rejected" ? ["za nisko (1. p.)"] : [],
      missing: verdict === "review" ? ["balkon"] : [],
      warnings: n % 4 === 1 ? ["nieznane ogrzewanie"] : [],
      location_category: "preferred", location_name: district,
      commute: { [DEST_WORK]: commute[0], [DEST_CENTRE]: commute[1] },
      commute_method: "timetable",
      commute_routes: {
        [DEST_WORK]: [{ mode: "walk", minutes: 4 },
          { mode: "tram", line: String(2 + (n % 6)), from: "Przystanek demo", to: "Wierzbięcice" },
          { mode: "walk", minutes: 2 }],
        [DEST_CENTRE]: [{ mode: "walk", minutes: 4 },
          { mode: "tram", line: "16", from: "Przystanek demo", to: "Marcinkowskiego" },
          { mode: "walk", minutes: 5 }],
      },
      nearby: {
        tram_stop: { name: "Przystanek demo", m: 150 + n * 40 },
        supermarket: { name: n % 2 ? "Biedronka" : "Lidl", m: 120 + n * 60 },
        shops_500m: 9 - (n % 7),
      },
      land_register: n === 1 ? "PO1P/00000000/0" : null,
    },
    group_id: `demo:${n}`,
    first_seen_at: day,
    last_seen_at: new Date().toISOString(),
    active: true,
    description: "Przykładowy opis mieszkania w trybie demo. Balkon od południa, " +
      "ogrzewanie miejskie, blisko tramwaju i sklepów.",
    raw: n % 3 === 1 ? { parcel: { id: `306401_1.0021.AR_12.${n}/3`, region: "Demo",
                                   number: `${n}/3` } } : {},
    ...rest,
  };
}

const LISTINGS: Listing[] = [
  fake(1, "Wilda", "ul. Przemysłowa", 52.3968, 16.9268, { commute: [5, 15] }),
  fake(2, "Jeżyce", "ul. Kraszewskiego", 52.4109, 16.9055, { commute: [16, 17] }),
  fake(3, "Łazarz", "ul. Głogowska", 52.3962, 16.8987, { commute: [9, 18] }),
  fake(4, "Rataje", "os. Piastowskie", 52.3915, 16.9573, { commute: [16, 16] }),
  fake(5, "Wilda", "ul. Rolna", 52.3881, 16.9238, { commute: [11, 19], verdict: "review" }),
  fake(6, "Stare Miasto", "ul. Garbary", 52.4093, 16.9409, { commute: [15, 6] }),
  fake(7, "Jeżyce", "ul. Janickiego", 52.4153, 16.8968, { commute: [20, 20], price: 815_000,
    verdict: "negotiable" }),
  fake(8, "Grunwald", "ul. Ptasia", 52.4022, 16.8746, { commute: [19, 22] }),
  fake(9, "Łazarz", "ul. Matejki", 52.3985, 16.9065, { commute: [7, 14] }),
  fake(10, "Rataje", "os. Lecha", 52.3866, 16.9659, { commute: [19, 20], verdict: "review" }),
];

function inDays(days: number, hour: number): string {
  const d = new Date(Date.now() + days * 86400_000);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

const ME: Member = { email: "ty@example.com", role: "owner", display_name: "Ty" };

export class DemoApi implements Api {
  readonly demo = true;
  private signedIn = true;
  private statusRows: ListingStatus[] = [
    { listing_id: "demo:1", status: "viewing", note: "Dzień otwarty w sobotę",
      viewing_at: new Date(Date.now() + 2 * 86400_000).toISOString(), updated_by: ME.email,
      updated_at: new Date().toISOString() },
    { listing_id: "demo:3", status: "interesting", note: null, viewing_at: null,
      updated_by: ME.email, updated_at: new Date().toISOString() },
  ];
  private reactionRows: Reaction[] = [
    { listing_id: "demo:1", email: "mama@example.com", reaction: "up" },
    { listing_id: "demo:2", email: "mama@example.com", reaction: "down" },
  ];
  private commentRows: Comment[] = [
    { id: 1, listing_id: "demo:1", author_email: "mama@example.com",
      body: "Ładna kuchnia, ale zapytaj o czynsz.", created_at: new Date().toISOString() },
  ];
  private memberRows: Member[] = [
    ME, { email: "mama@example.com", role: "member", display_name: "Mama" },
  ];
  private prefs: Record<string, unknown> | null = null;
  private eventRows: CalendarEvent[] = [
    { id: 1, kind: "open_day", title: "Dzień otwarty – osiedle demo przy ul. Przemysłowej",
      starts_at: inDays(5, 10), ends_at: inDays(5, 14), location: "Poznań, ul. Przemysłowa",
      url: "https://example.com/dni-otwarte", listing_id: "demo:1", source: "otodom",
      notes: null, created_by: null },
    { id: 2, kind: "fair", title: "Targi Mieszkań i Domów (demo)", starts_at: inDays(12, 10),
      ends_at: inDays(12, 17), location: "Poznań, MTP, ul. Głogowska 14",
      url: "https://example.com/targi", listing_id: null, source: "fairs", notes: null,
      created_by: null },
  ];

  async currentUser(): Promise<Me | null> {
    return this.signedIn ? { email: ME.email, member: ME } : null;
  }
  async sendCode(): Promise<void> {}
  async verifyCode(): Promise<void> { this.signedIn = true; }
  async signOut(): Promise<void> { this.signedIn = false; }

  async listings(includeRejected: boolean): Promise<Listing[]> {
    return LISTINGS.filter((l) => includeRejected || l.verdict !== "rejected");
  }
  async listing(id: string): Promise<Listing | null> {
    return LISTINGS.find((l) => l.id === id) ?? null;
  }
  async priceHistory(id: string): Promise<PricePoint[]> {
    const l = LISTINGS.find((x) => x.id === id);
    if (!l?.price) return [];
    return [
      { price: l.price + 25_000, seen_at: new Date(Date.now() - 20 * 86400_000).toISOString() },
      { price: l.price, seen_at: new Date(Date.now() - 3 * 86400_000).toISOString() },
    ];
  }
  async lastRunAt(): Promise<string | null> {
    return new Date(Date.now() - 40 * 60_000).toISOString();
  }

  async statuses(): Promise<ListingStatus[]> { return [...this.statusRows]; }
  async setStatus(listingId: string, status: StatusKey | null, note: string | null = null,
                  viewingAt: string | null = null): Promise<void> {
    this.statusRows = this.statusRows.filter((s) => s.listing_id !== listingId);
    if (status) {
      this.statusRows.push({ listing_id: listingId, status, note, viewing_at: viewingAt,
        updated_by: ME.email, updated_at: new Date().toISOString() });
    }
  }
  async reactions(): Promise<Reaction[]> { return [...this.reactionRows]; }
  async setReaction(listingId: string, reaction: ReactionKey | null): Promise<void> {
    this.reactionRows = this.reactionRows.filter(
      (r) => !(r.listing_id === listingId && r.email === ME.email));
    if (reaction) this.reactionRows.push({ listing_id: listingId, email: ME.email, reaction });
  }
  async comments(listingId: string): Promise<Comment[]> {
    return this.commentRows.filter((c) => c.listing_id === listingId);
  }
  async commentCounts(): Promise<Record<string, number>> {
    const out: Record<string, number> = {};
    for (const c of this.commentRows) out[c.listing_id] = (out[c.listing_id] ?? 0) + 1;
    return out;
  }
  async addComment(listingId: string, body: string): Promise<void> {
    this.commentRows.push({ id: Date.now(), listing_id: listingId, author_email: ME.email, body,
      created_at: new Date().toISOString() });
  }
  async deleteComment(id: number): Promise<void> {
    this.commentRows = this.commentRows.filter((c) => c.id !== id);
  }
  async members(): Promise<Member[]> { return [...this.memberRows]; }
  async addMember(email: string, displayName: string | null): Promise<void> {
    this.memberRows.push({ email: email.toLowerCase(), role: "member", display_name: displayName });
  }
  async removeMember(email: string): Promise<void> {
    this.memberRows = this.memberRows.filter((m) => m.email !== email);
  }
  async touchVisit(): Promise<string | null> {
    return new Date(Date.now() - 30 * 3600_000).toISOString();
  }
  async events(): Promise<CalendarEvent[]> { return [...this.eventRows]; }
  async addEvent(event: NewEvent): Promise<void> {
    this.eventRows.push({ ...event, id: Date.now(), source: "manual", created_by: ME.email });
  }
  async deleteEvent(id: number): Promise<void> {
    this.eventRows = this.eventRows.filter((e) => e.id !== id);
  }
  async calendarUrl(): Promise<string | null> {
    return "https://example.supabase.co/storage/v1/object/public/calendar/demo.ics";
  }
  async preferences(): Promise<Record<string, unknown> | null> { return this.prefs; }
  async savePreferences(prefs: Record<string, unknown>): Promise<void> { this.prefs = prefs; }
}
