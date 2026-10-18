import { describe, expect, it } from "vitest";
import { projectUrl } from "./api";
import { errorMessage } from "./api/supabase";
import type { Listing, ListingStatus } from "./api/types";
import {
  applyFilters, DEFAULT_FILTERS, distance, floorText, geoportalUrl, groupDuplicates, legText,
  money, relativeTime, routeLines, shortDestination,
} from "./format";

function listing(id: string, over: Partial<Listing> = {}): Listing {
  return {
    id, source: "otodom", url: "", title: "", price: 500_000, area: 45, price_per_m2: 11_000,
    rooms: 2, floor: 3, floors_total: 5, build_year: 2018, market: "secondary",
    has_balcony: true, has_elevator: true, heating: "district", ownership: "full",
    completion_date: null, district: "Wilda", location_text: "Poznań, Wilda", lat: 52.4,
    lon: 16.9, coords_approximate: false, images: [], is_private_owner: false, agency: null,
    published_at: null, verdict: "match", score: 70, evaluation: null, group_id: null,
    first_seen_at: "2026-10-18T10:00:00Z", last_seen_at: "2026-10-18T10:00:00Z", active: true,
    ...over,
  };
}

describe("format", () => {
  it("formats money and floors in Polish", () => {
    expect(money(599000).replace(/\s/g, " ")).toBe("599 000 zł");
    expect(money(null)).toBe("cena ?");
    expect(floorText(0, null)).toBe("parter");
    expect(floorText(4, 6)).toBe("4. piętro z 6");
    expect(shortDestination("Praca (Nowy Rynek D)")).toBe("Praca");
  });

  it("describes relative time", () => {
    const now = Date.parse("2026-10-18T12:00:00Z");
    expect(relativeTime("2026-10-18T11:30:00Z", now)).toBe("30 min temu");
    expect(relativeTime("2026-10-17T11:00:00Z", now)).toBe("wczoraj");
    expect(relativeTime(null, now)).toBe("nigdy");
  });

  it("collapses duplicates into the best-scored listing", () => {
    const groups = groupDuplicates([
      listing("a", { group_id: "g", score: 60 }),
      listing("b", { group_id: "g", score: 80, source: "olx" }),
      listing("c"),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0].listing.id).toBe("b");
    expect(groups[0].duplicates.map((d) => d.id)).toEqual(["a"]);
  });

  it("filters by verdict, status and novelty and sorts", () => {
    const items = groupDuplicates([
      listing("a", { score: 60, price: 700_000 }),
      listing("b", { score: 90, price: 600_000, first_seen_at: "2026-10-19T00:00:00Z" }),
      listing("c", { verdict: "review" }),
      listing("d", { score: 95 }),
    ]);
    const statuses = new Map<string, ListingStatus>([
      ["d", { listing_id: "d", status: "rejected", note: null, viewing_at: null,
        updated_by: null, updated_at: "" }],
    ]);
    const ids = (f = DEFAULT_FILTERS) =>
      applyFilters(items, f, statuses, "2026-10-18T12:00:00Z").map((g) => g.listing.id);
    expect(ids()).toEqual(["b", "a"]); // rejected by me is hidden, review filtered out
    expect(ids({ ...DEFAULT_FILTERS, sort: "price" })).toEqual(["b", "a"]);
    expect(ids({ ...DEFAULT_FILTERS, onlyNew: true })).toEqual(["b"]);
    expect(ids({ ...DEFAULT_FILTERS, status: "rejected" })).toEqual(["d"]);
    expect(ids({ ...DEFAULT_FILTERS, verdict: "all", query: "wilda" })).toHaveLength(3);
  });
});

describe("projectUrl", () => {
  it("strips paths and slashes from the Supabase URL", () => {
    expect(projectUrl("https://abcd.supabase.co/rest/v1/")).toBe("https://abcd.supabase.co");
    expect(projectUrl("https://abcd.supabase.co")).toBe("https://abcd.supabase.co");
    expect(projectUrl("abcd.supabase.co")).toBeUndefined();
  });
});

describe("errorMessage", () => {
  it("explains network and permission errors in Polish", () => {
    expect(errorMessage("TypeError: Load failed")).toContain("Brak połączenia");
    expect(errorMessage('new row violates row-level security policy for table "members"'))
      .toBe("Brak uprawnień do tej operacji.");
    expect(errorMessage("duplicate key value violates unique constraint")).toContain("już istnieje");
  });
});

describe("commute and surroundings", () => {
  it("lists the lines of a route", () => {
    expect(routeLines([{ mode: "walk", minutes: 3 },
      { mode: "tram", line: "5", from: "A", to: "B" },
      { mode: "tram", line: "2", from: "B", to: "C" }])).toBe("linie 5 → 2");
    expect(routeLines([{ mode: "walk", minutes: 9 }])).toBe("pieszo");
    expect(legText({ mode: "bus", line: "170", from: "A", to: "B" })).toBe("🚌 170: A → B");
  });
  it("formats distances and links the parcel", () => {
    expect(distance(347)).toBe("350 m");
    expect(distance(1260)).toBe("1,3 km");
    expect(geoportalUrl({ id: "306401_1.0021.AR_12.45/3", region: "Jeżyce", number: "45/3" }))
      .toBe("https://mapy.geoportal.gov.pl/imapnext/imap/?identifyParcel=306401_1.0021.AR_12.45%2F3");
  });
});
