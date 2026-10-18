import { describe, expect, it } from "vitest";
import { googleCalendarUrl, icsFor } from "./calendar";

const item = {
  uid: "event-1", title: "Dzień otwarty; Wilda", start: "2026-10-25T09:00:00.000Z",
  location: "Poznań, ul. Rolna 1", url: "https://example.com",
};

describe("calendar", () => {
  it("builds a Google Calendar link with a default one-hour slot", () => {
    const url = new URL(googleCalendarUrl(item));
    expect(url.searchParams.get("dates")).toBe("20261025T090000Z/20261025T100000Z");
    expect(url.searchParams.get("text")).toBe("Dzień otwarty; Wilda");
  });

  it("escapes iCalendar text", () => {
    const ics = icsFor(item);
    expect(ics).toContain("SUMMARY:Dzień otwarty\; Wilda");
    expect(ics).toContain("LOCATION:Poznań\\, ul. Rolna 1");
    expect(ics).toContain("DTSTART:20261025T090000Z");
  });
});
