import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Comment, Listing, PricePoint, StatusKey } from "../api/types";
import { Avatars, Photo, ScoreBadge } from "../components/ListingCard";
import { MapView } from "../components/MapView";
import { useData } from "../data";
import {
  appleMapsUrl, commuteEntries, floorText, googleMapsUrl, HEATING_LABELS, money, personName,
  reactionSummary, relativeTime, shortDestination, sourceName, STATUS_LABELS, VERDICT_LABELS,
} from "../format";
import { destinations, loadPrefs, type Prefs } from "../preferences";

function yesNo(value: boolean | null): string {
  return value == null ? "?" : value ? "tak" : "nie";
}

function Facts({ l }: { l: Listing }) {
  const rows: [string, string][] = [
    ["Cena", money(l.price)],
    ["Cena za m²", l.price_per_m2 ? money(l.price_per_m2) : "?"],
    ["Metraż", l.area ? `${l.area.toLocaleString("pl-PL")} m²` : "?"],
    ["Pokoje", l.rooms?.toString() ?? "?"],
    ["Piętro", floorText(l.floor, l.floors_total)],
    ["Rok budowy", l.build_year?.toString() ?? "?"],
    ["Rynek", l.market === "primary" ? "pierwotny" : l.market === "secondary" ? "wtórny" : "?"],
    ...(l.completion_date ? [["Termin oddania", l.completion_date] as [string, string]] : []),
    ["Balkon / loggia", yesNo(l.has_balcony)],
    ["Winda", yesNo(l.has_elevator)],
    ["Ogrzewanie", l.heating ? HEATING_LABELS[l.heating] ?? l.heating : "?"],
    ["Własność", l.ownership === "full" ? "pełna" : l.ownership === "cooperative"
      ? "spółdzielcze" : "?"],
    ["Ogłoszenie", l.is_private_owner ? "prywatne" : l.agency ?? "biuro / deweloper"],
  ];
  return (
    <dl className="facts">
      {rows.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
    </dl>
  );
}

function StatusEditor({ listingId }: { listingId: string }) {
  const { statuses, isOwner, refreshShared } = useData();
  const current = statuses.get(listingId);
  const [note, setNote] = useState(current?.note ?? "");
  const [viewing, setViewing] = useState(current?.viewing_at?.slice(0, 16) ?? "");
  const [busy, setBusy] = useState(false);

  async function save(status: StatusKey | null) {
    setBusy(true);
    try {
      await api.setStatus(listingId, status, note || null,
                          viewing ? new Date(viewing).toISOString() : null);
      await refreshShared();
    } finally {
      setBusy(false);
    }
  }

  if (!isOwner) {
    return current ? (
      <p><span className="status">{STATUS_LABELS[current.status]}</span>
        {current.note && <span className="muted"> – {current.note}</span>}</p>
    ) : <p className="muted">Bez statusu.</p>;
  }
  return (
    <div className="stack-s">
      <div className="status-buttons">
        {(Object.keys(STATUS_LABELS) as StatusKey[]).map((s) => (
          <button key={s} disabled={busy}
                  className={current?.status === s ? "active" : "ghost"}
                  onClick={() => void save(current?.status === s ? null : s)}>
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>
      <input placeholder="Notatka (np. czynsz, kontakt, wrażenia)" value={note}
             onChange={(e) => setNote(e.target.value)}
             onBlur={() => current && void save(current.status)} />
      {(current?.status === "viewing") && (
        <label className="stack-s small">Termin oglądania
          <input type="datetime-local" value={viewing} onChange={(e) => setViewing(e.target.value)}
                 onBlur={() => void save("viewing")} />
        </label>
      )}
    </div>
  );
}

function Reactions({ listingId }: { listingId: string }) {
  const { reactions, members, me, refreshShared } = useData();
  const { up, down } = reactionSummary(listingId, reactions);
  const mine = reactions.find((r) => r.listing_id === listingId && r.email === me.email);

  async function toggle(kind: "up" | "down") {
    await api.setReaction(listingId, mine?.reaction === kind ? null : kind);
    await refreshShared();
  }
  return (
    <div className="row gap">
      <button className={mine?.reaction === "up" ? "active" : "ghost"}
              onClick={() => void toggle("up")}>👍 {up.length}</button>
      <button className={mine?.reaction === "down" ? "active" : "ghost"}
              onClick={() => void toggle("down")}>👎 {down.length}</button>
      <Avatars emails={[...up, ...down].map((r) => r.email)} members={members} />
    </div>
  );
}

function Comments({ listingId }: { listingId: string }) {
  const { members, me, isOwner, refreshShared } = useData();
  const [items, setItems] = useState<Comment[]>([]);
  const [body, setBody] = useState("");
  const load = useCallback(() => { void api.comments(listingId).then(setItems); }, [listingId]);
  useEffect(load, [load]);

  async function add() {
    if (!body.trim()) return;
    await api.addComment(listingId, body.trim());
    setBody("");
    load();
    await refreshShared();
  }
  async function remove(id: number) {
    await api.deleteComment(id);
    load();
    await refreshShared();
  }
  return (
    <div className="stack-s">
      {items.length === 0 && <p className="muted small">Brak komentarzy.</p>}
      {items.map((c) => (
        <div key={c.id} className="comment">
          <div className="row between small muted">
            <b>{personName(c.author_email, members)}</b>
            <span>{relativeTime(c.created_at)}
              {(c.author_email === me.email || isOwner) && (
                <button className="link" onClick={() => void remove(c.id)}>usuń</button>
              )}
            </span>
          </div>
          <p>{c.body}</p>
        </div>
      ))}
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <input placeholder="Dodaj komentarz…" value={body} onChange={(e) => setBody(e.target.value)} />
        <button type="submit">Wyślij</button>
      </form>
    </div>
  );
}

export function DetailPage() {
  const { id = "" } = useParams();
  const { byId, grouped } = useData();
  const [listing, setListing] = useState<Listing | null | undefined>(byId.get(id));
  const [history, setHistory] = useState<PricePoint[]>([]);
  const [prefs, setPrefs] = useState<Prefs | null>(null);

  useEffect(() => {
    void api.listing(id).then(setListing);
    void api.priceHistory(id).then(setHistory);
    void loadPrefs().then((p) => setPrefs(p.prefs));
  }, [id]);

  if (listing === undefined) return <p className="muted">Ładuję…</p>;
  if (listing === null) return <p>Nie znaleziono oferty. <Link to="/">Wróć</Link></p>;
  const l = listing;
  const ev = l.evaluation;
  const others = grouped.find((g) => g.listing.id === l.id)?.duplicates ?? [];
  const investment = (l.raw?.investment ?? null) as { title?: string; url?: string } | null;
  const google = googleMapsUrl(l);
  const apple = appleMapsUrl(l);

  return (
    <article className="stack detail">
      <Link to="/" className="back">← Oferty</Link>
      <div className="gallery">
        {(l.images?.length ? l.images : [null]).map((src, i) =>
          src ? <img key={src} src={src} alt={`Zdjęcie ${i + 1}`} loading="lazy"
                     referrerPolicy="no-referrer" />
              : <Photo key="none" listing={l} />,
        )}
      </div>

      <section className="card stack-s">
        <div className="row between">
          <h1 className="price">{money(l.price)}</h1>
          <ScoreBadge score={l.score} />
        </div>
        <p className="headline">{l.title}</p>
        <p className="muted">{l.location_text ?? l.district}</p>
        <div className="chips">
          <span className={`chip verdict-${l.verdict}`}>{VERDICT_LABELS[l.verdict]}</span>
          {commuteEntries(l).map(([name, min]) => (
            <span key={name} className="chip">🚋 ~{Math.round(min)} min {shortDestination(name)}</span>
          ))}
        </div>
        {ev && (ev.missing.length > 0 || ev.warnings.length > 0 || ev.rejections.length > 0) && (
          <ul className="notes">
            {ev.rejections.map((r) => <li key={r}>✖️ {r}</li>)}
            {ev.missing.map((m) => <li key={m}>❓ do sprawdzenia: {m}</li>)}
            {ev.warnings.map((w) => <li key={w}>⚠️ {w}</li>)}
          </ul>
        )}
        <div className="links">
          <a className="button" href={l.url} target="_blank" rel="noreferrer">
            Otwórz w {sourceName(l.source)} ↗
          </a>
          {others.map((o) => (
            <a key={o.id} className="button ghost" href={o.url} target="_blank" rel="noreferrer">
              {sourceName(o.source)} ↗
            </a>
          ))}
          {google && <a className="button ghost" href={google} target="_blank" rel="noreferrer">Google Maps</a>}
          {apple && <a className="button ghost" href={apple} target="_blank" rel="noreferrer">Apple Maps</a>}
          {investment?.url && (
            <a className="button ghost" href={investment.url} target="_blank" rel="noreferrer">
              Inwestycja: {investment.title} ↗
            </a>
          )}
        </div>
      </section>

      <section className="card stack-s">
        <h2>Status</h2>
        <StatusEditor listingId={l.id} />
        <h2>Reakcje</h2>
        <Reactions listingId={l.id} />
      </section>

      <section className="card">
        <h2>Szczegóły</h2>
        <Facts l={l} />
      </section>

      {l.lat != null && l.lon != null && prefs && (
        <section className="card stack-s">
          <h2>Lokalizacja</h2>
          {l.coords_approximate && <p className="muted small">Lokalizacja przybliżona.</p>}
          <MapView listings={[l]} destinations={destinations(prefs)} center={[l.lat, l.lon]}
                   zoom={14} className="map-small" />
        </section>
      )}

      {history.length > 1 && (
        <section className="card">
          <h2>Historia ceny</h2>
          <ul className="history">
            {history.map((p) => (
              <li key={p.seen_at}><span>{new Date(p.seen_at).toLocaleDateString("pl-PL")}</span>
                <b>{money(p.price)}</b></li>
            ))}
          </ul>
        </section>
      )}

      {l.description && (
        <section className="card">
          <h2>Opis</h2>
          <p className="description">{l.description}</p>
        </section>
      )}

      <section className="card stack-s">
        <h2>Komentarze</h2>
        <Comments listingId={l.id} />
      </section>
      <p className="muted small">
        Pierwszy raz widziane {relativeTime(l.first_seen_at)} · ostatnio {relativeTime(l.last_seen_at)}
      </p>
    </article>
  );
}
