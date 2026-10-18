import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { CalendarEvent, EventKind } from "../api/types";
import { formatWhen, type CalendarItem } from "../calendar";
import { AddToCalendar } from "../components/AddToCalendar";
import { useData } from "../data";
import { headline, money } from "../format";

const KIND_LABELS: Record<EventKind | "viewing", string> = {
  open_day: "🏠 Dzień otwarty",
  fair: "🎪 Targi",
  other: "📌 Wydarzenie",
  viewing: "📅 Oglądanie",
};

interface Entry {
  key: string;
  kind: EventKind | "viewing";
  item: CalendarItem;
  listingId: string | null;
  event?: CalendarEvent;
}

function SubscribeBox() {
  const [url, setUrl] = useState<string | null | undefined>(undefined);
  const [copied, setCopied] = useState(false);
  useEffect(() => { void api.calendarUrl().then(setUrl).catch(() => setUrl(null)); }, []);
  if (url === undefined) return null;
  return (
    <section className="card stack-s">
      <h2>Subskrypcja kalendarza</h2>
      {url ? (
        <>
          <p className="small muted">
            Kalendarz aktualizuje się sam: dni otwarte, targi i Twoje oglądania. Link jest
            prywatny – nie udostępniaj go publicznie.
          </p>
          <div className="row gap">
            <input readOnly value={url} onFocus={(e) => e.target.select()} />
            <button type="button" className="ghost small" onClick={() => {
              void navigator.clipboard?.writeText(url).then(() => setCopied(true));
            }}>{copied ? "Skopiowano" : "Kopiuj"}</button>
          </div>
          <details className="small">
            <summary>Jak dodać?</summary>
            <p><b>iPhone:</b> Ustawienia → Kalendarz → Konta → Dodaj konto → Inne → Dodaj
              subskrybowany kalendarz → wklej link.</p>
            <p><b>Google Calendar</b> (w przeglądarce na komputerze): Inne kalendarze → + →
              Z adresu URL → wklej link. Google odświeża subskrypcje co kilka godzin.</p>
          </details>
        </>
      ) : (
        <p className="small muted">
          Link pojawi się po skonfigurowaniu publikacji kalendarza (sekret
          SUPABASE_SERVICE_KEY – instrukcja w README). Do tego czasu użyj przycisków
          „Dodaj do kalendarza” przy wydarzeniach.
        </p>
      )}
    </section>
  );
}

function AddEventForm({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ kind: "open_day" as EventKind, title: "", date: "",
    from: "10:00", to: "", location: "", url: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form, v: string) => setForm({ ...form, [k]: v });

  if (!open) {
    return <button className="ghost" onClick={() => setOpen(true)}>+ Dodaj wydarzenie</button>;
  }
  async function save() {
    setError(null);
    try {
      const start = new Date(`${form.date}T${form.from || "10:00"}`);
      const end = form.to ? new Date(`${form.date}T${form.to}`) : null;
      await api.addEvent({
        kind: form.kind, title: form.title, starts_at: start.toISOString(),
        ends_at: end?.toISOString() ?? null, location: form.location || null,
        url: form.url || null, notes: form.notes || null, listing_id: null,
      });
      setOpen(false);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <form className="card stack-s" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <h2>Nowe wydarzenie</h2>
      <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
        <option value="open_day">Dzień otwarty</option>
        <option value="fair">Targi</option>
        <option value="other">Inne</option>
      </select>
      <input required placeholder="Nazwa (np. Dzień otwarty – Osiedle X)" value={form.title}
             onChange={(e) => set("title", e.target.value)} />
      <div className="grid3">
        <input type="date" required value={form.date} onChange={(e) => set("date", e.target.value)} />
        <input type="time" value={form.from} onChange={(e) => set("from", e.target.value)} />
        <input type="time" value={form.to} onChange={(e) => set("to", e.target.value)} />
      </div>
      <input placeholder="Miejsce" value={form.location} onChange={(e) => set("location", e.target.value)} />
      <input type="url" placeholder="Link (opcjonalnie)" value={form.url}
             onChange={(e) => set("url", e.target.value)} />
      <input placeholder="Notatka" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
      <div className="row gap">
        <button type="submit">Zapisz</button>
        <button type="button" className="ghost" onClick={() => setOpen(false)}>Anuluj</button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

export function EventsPage() {
  const { statuses, byId, me, isOwner } = useData();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const load = useCallback(() => { void api.events().then(setEvents); }, []);
  useEffect(load, [load]);

  const entries = useMemo<Entry[]>(() => {
    const out: Entry[] = events.map((e) => ({
      key: `e${e.id}`, kind: e.kind, listingId: e.listing_id, event: e,
      item: { uid: `event-${e.id}`, title: `${KIND_LABELS[e.kind]}: ${e.title}`,
              start: e.starts_at, end: e.ends_at, location: e.location,
              description: e.notes, url: e.url },
    }));
    for (const s of statuses.values()) {
      if (s.status !== "viewing" || !s.viewing_at) continue;
      const l = byId.get(s.listing_id);
      out.push({
        key: `v${s.listing_id}`, kind: "viewing", listingId: s.listing_id,
        item: { uid: `viewing-${s.listing_id}`, start: s.viewing_at,
                title: `${KIND_LABELS.viewing}: ${l?.location_text ?? "mieszkanie"}`,
                location: l?.location_text, url: l?.url,
                description: [l && `${headline(l)} · ${money(l.price)}`, s.note]
                  .filter(Boolean).join("\n") },
      });
    }
    const since = Date.now() - 6 * 3600_000;
    return out.filter((e) => new Date(e.item.start).getTime() >= since)
      .sort((a, b) => a.item.start.localeCompare(b.item.start));
  }, [events, statuses, byId]);

  async function remove(id: number) {
    if (!confirm("Usunąć wydarzenie?")) return;
    await api.deleteEvent(id);
    load();
  }

  return (
    <div className="stack">
      <h1>Wydarzenia</h1>
      {entries.length === 0 && (
        <p className="muted">Brak nadchodzących wydarzeń. Dni otwarte z ogłoszeń pojawią się
          tu same; oglądania dodasz, ustawiając status „Oglądanie” z terminem.</p>
      )}
      {entries.map((e) => {
        const listing = e.listingId ? byId.get(e.listingId) : undefined;
        const canDelete = e.event?.source === "manual"
          && (e.event.created_by === me.email || isOwner);
        return (
          <article key={e.key} className="card stack-s event">
            <div className="row between">
              <span className={`chip kind-${e.kind}`}>{KIND_LABELS[e.kind]}</span>
              <b className="small">{formatWhen(e.item.start, e.item.end)}</b>
            </div>
            <strong>{e.event?.title ?? e.item.location}</strong>
            {e.item.location && <span className="muted small">📍 {e.item.location}</span>}
            {e.event?.notes && <span className="small">{e.event.notes}</span>}
            {listing && (
              <Link className="small" to={`/oferta/${encodeURIComponent(listing.id)}`}>
                {headline(listing)} · {money(listing.price)} →
              </Link>
            )}
            <div className="row between gap">
              <AddToCalendar item={e.item} />
              <span className="row gap-s">
                {e.item.url && <a className="small" href={e.item.url} target="_blank"
                                  rel="noreferrer">Szczegóły ↗</a>}
                {canDelete && e.event && (
                  <button className="link" onClick={() => void remove(e.event!.id)}>usuń</button>
                )}
              </span>
            </div>
          </article>
        );
      })}
      <AddEventForm onAdded={load} />
      {isOwner && <SubscribeBox />}
    </div>
  );
}
