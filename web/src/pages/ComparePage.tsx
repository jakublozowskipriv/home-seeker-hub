import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Listing } from "../api/types";
import { setCompareIds, toggleCompare, useCompare } from "../compare";
import { Photo, ScoreBadge } from "../components/ListingCard";
import { useData } from "../data";
import { defaultCommission, purchaseCosts } from "../finance";
import {
  commuteEntries, distance, floorText, HEATING_LABELS, money, redFlags, routeLines,
  shortDestination,
} from "../format";
import { loadPrefs, type Prefs } from "../preferences";

type Better = "low" | "high" | null;

interface Row {
  label: string;
  value: (l: Listing) => number | null;
  show: (l: Listing, v: number | null) => ReactNode;
  better: Better;
}

function yesNo(v: boolean | null): string {
  return v == null ? "?" : v ? "tak" : "nie";
}

export function ComparePage() {
  const ids = useCompare();
  const { medians } = useData();
  const [listings, setListings] = useState<Listing[]>([]);
  const [prefs, setPrefs] = useState<Prefs | null>(null);

  useEffect(() => { void loadPrefs().then((p) => setPrefs(p.prefs)); }, []);
  useEffect(() => {
    void Promise.all(ids.map((id) => api.listing(id)))
      .then((rows) => setListings(rows.filter((l): l is Listing => l != null)));
  }, [ids]);

  if (ids.length === 0) {
    return (
      <div className="stack">
        <h1>Porównanie</h1>
        <p className="muted">Dodaj oferty przyciskiem „⚖️ Porównaj” na stronie oferty
          (maks. 4).</p>
        <Link to="/">← Oferty</Link>
      </div>
    );
  }

  const m = prefs?.mortgage ?? {};
  const costs = (l: Listing) => l.price ? purchaseCosts({
    price: l.price, market: l.market, downPaymentPercent: m.down_payment_percent ?? 20,
    ratePercent: m.interest_rate_percent ?? 6.5, years: m.years ?? 30, firstHome: false,
    commissionPercent: defaultCommission(l),
  }) : null;
  const rent = (l: Listing) => (typeof l.raw?.rent === "number" ? l.raw.rent : null);
  const dests = [...new Set(listings.flatMap((l) => commuteEntries(l).map(([n]) => n)))].sort();
  const num = (v: number | null, f: (x: number) => string) => (v == null ? "?" : f(v));

  const rows: Row[] = [
    { label: "Cena", value: (l) => l.price, show: (_, v) => num(v, money), better: "low" },
    { label: "Cena za m²", value: (l) => l.price_per_m2, show: (_, v) => num(v, money),
      better: "low" },
    { label: "Metraż", value: (l) => l.area, show: (_, v) => num(v, (x) => `${x} m²`),
      better: "high" },
    { label: "Pokoje", value: (l) => l.rooms, show: (_, v) => num(v, String), better: "high" },
    { label: "Piętro", value: (l) => l.floor, show: (l) => floorText(l.floor, l.floors_total),
      better: "high" },
    { label: "Rok budowy", value: (l) => l.build_year, show: (_, v) => num(v, String),
      better: "high" },
    { label: "Balkon", value: () => null, show: (l) => yesNo(l.has_balcony), better: null },
    { label: "Winda", value: () => null, show: (l) => yesNo(l.has_elevator), better: null },
    { label: "Ogrzewanie", value: () => null,
      show: (l) => (l.heating ? HEATING_LABELS[l.heating] ?? l.heating : "?"), better: null },
    ...dests.map((name): Row => ({
      label: `Dojazd: ${shortDestination(name)}`,
      value: (l) => l.evaluation?.commute?.[name] ?? null,
      show: (l, v) => v == null ? "?" : <>{Math.round(v)} min<br />
        <span className="muted small">{routeLines(l.evaluation?.commute_routes?.[name])}</span></>,
      better: "low",
    })),
    { label: "Przystanek tramwajowy", value: (l) => l.evaluation?.nearby?.tram_stop?.m ?? null,
      show: (_, v) => num(v, distance), better: "low" },
    { label: "Supermarket", value: (l) => l.evaluation?.nearby?.supermarket?.m ?? null,
      show: (_, v) => num(v, distance), better: "low" },
    { label: "Rata", value: (l) => costs(l)?.payment ?? null,
      show: (_, v) => num(v, (x) => `${money(x)}/mies.`), better: "low" },
    { label: "Czynsz", value: rent, show: (_, v) => num(v, money), better: "low" },
    { label: "Koszty jednorazowe", value: (l) => costs(l)?.oneOffTotal ?? null,
      show: (_, v) => num(v, money), better: "low" },
    { label: "Gotówka na start", value: (l) => costs(l)?.cashNeeded ?? null,
      show: (_, v) => num(v, money), better: "low" },
    { label: "Dopasowanie", value: (l) => l.score, show: (l) => <ScoreBadge score={l.score} />,
      better: "high" },
  ];

  function best(row: Row): number | null {
    if (!row.better) return null;
    const values = listings.map(row.value).filter((v): v is number => v != null);
    if (values.length < 2) return null;
    return row.better === "low" ? Math.min(...values) : Math.max(...values);
  }

  return (
    <div className="stack">
      <div className="row between">
        <h1>Porównanie</h1>
        <button className="ghost small" onClick={() => setCompareIds([])}>Wyczyść</button>
      </div>
      <div className="compare-scroll">
        <table className="compare">
          <thead>
            <tr>
              <th />
              {listings.map((l) => (
                <th key={l.id}>
                  <Link to={`/oferta/${encodeURIComponent(l.id)}`}><Photo listing={l} /></Link>
                  <div className="small">{l.location_text ?? l.district}</div>
                  <button className="link small" onClick={() => toggleCompare(l.id)}>usuń</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const top = best(row);
              return (
                <tr key={row.label}>
                  <th>{row.label}</th>
                  {listings.map((l) => {
                    const v = row.value(l);
                    return (
                      <td key={l.id} className={top != null && v === top ? "best" : ""}>
                        {row.show(l, v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            <tr>
              <th>Czerwone flagi</th>
              {listings.map((l) => {
                const flags = redFlags(l, medians);
                return (
                  <td key={l.id} className="small">
                    {flags.length ? flags.map((f) => (
                      <div key={f.text}>{f.level === "high" ? "🚩" : "ℹ️"} {f.text}</div>
                    )) : "brak"}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">Rata i koszty wg założeń z Preferencji (wkład, oprocentowanie,
        okres) – dla jednej oferty zmienisz je w kalkulatorze na jej stronie.</p>
    </div>
  );
}
