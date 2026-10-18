/** "Add to calendar" helpers: Google Calendar link and a downloadable .ics (Apple). */

export interface CalendarItem {
  uid: string;
  title: string;
  start: string; // ISO
  end?: string | null;
  location?: string | null;
  description?: string | null;
  url?: string | null;
}

const HOUR = 3600_000;

function stamp(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function endOf(item: CalendarItem): string {
  return item.end ?? new Date(new Date(item.start).getTime() + HOUR).toISOString();
}

export function googleCalendarUrl(item: CalendarItem): string {
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: item.title,
    dates: `${stamp(item.start)}/${stamp(endOf(item))}`,
    details: [item.description, item.url].filter(Boolean).join("\n"),
    location: item.location ?? "",
  });
  return `https://calendar.google.com/calendar/render?${params}`;
}

function escape(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n");
}

export function icsFor(item: CalendarItem): string {
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//home-seeker-hub//PL", "BEGIN:VEVENT",
    `UID:${item.uid}@home-seeker-hub`, `DTSTAMP:${stamp(new Date().toISOString())}`,
    `DTSTART:${stamp(item.start)}`, `DTEND:${stamp(endOf(item))}`,
    `SUMMARY:${escape(item.title)}`,
    ...(item.location ? [`LOCATION:${escape(item.location)}`] : []),
    ...(item.description ? [`DESCRIPTION:${escape(item.description)}`] : []),
    ...(item.url ? [`URL:${item.url}`] : []),
    "END:VEVENT", "END:VCALENDAR",
  ];
  return lines.join("\r\n") + "\r\n";
}

/** Opens the .ics: iOS shows "Add to Calendar", desktop browsers download the file. */
export function downloadIcs(item: CalendarItem): void {
  const blob = new Blob([icsFor(item)], { type: "text/calendar;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${item.uid}.ics`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
}

export function formatWhen(start: string, end?: string | null): string {
  const s = new Date(start);
  const day = s.toLocaleDateString("pl-PL", { weekday: "short", day: "numeric", month: "long" });
  const time = (d: Date) => d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
  return end ? `${day}, ${time(s)}–${time(new Date(end))}` : `${day}, ${time(s)}`;
}
