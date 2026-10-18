import { useMemo, useState } from "react";
import { ListingCard } from "../components/ListingCard";
import { useData } from "../data";
import {
  applyFilters, DEFAULT_FILTERS, isNew, STATUS_LABELS, type Filters, type SortKey,
  type VerdictFilter,
} from "../format";
import type { StatusKey } from "../api/types";

const FILTER_KEY = "hs-filters";

function loadFilters(): Filters {
  try {
    return { ...DEFAULT_FILTERS, ...JSON.parse(localStorage.getItem(FILTER_KEY) ?? "{}") };
  } catch {
    return DEFAULT_FILTERS;
  }
}

const VERDICTS: [VerdictFilter, string][] = [
  ["match", "Pasujące"], ["review", "Do sprawdzenia"], ["negotiable", "Do negocjacji"],
  ["all", "Wszystkie"],
];

export function ListPage() {
  const { grouped, statuses, reactions, commentCounts, members, lastVisit, loading, error } =
    useData();
  const [filters, setFilters] = useState<Filters>(loadFilters);

  function update(change: Partial<Filters>) {
    const next = { ...filters, ...change };
    setFilters(next);
    try { localStorage.setItem(FILTER_KEY, JSON.stringify(next)); } catch { /* private mode */ }
  }

  const items = useMemo(() => applyFilters(grouped, filters, statuses, lastVisit),
    [grouped, filters, statuses, lastVisit]);
  const newCount = grouped.filter((g) => isNew(g.listing, lastVisit)).length;

  return (
    <div className="stack">
      <div className="segmented" role="tablist">
        {VERDICTS.map(([key, label]) => (
          <button key={key} className={filters.verdict === key ? "active" : ""}
                  onClick={() => update({ verdict: key })}>{label}</button>
        ))}
      </div>
      <div className="filters">
        <input type="search" placeholder="Szukaj: ulica, dzielnica…" value={filters.query}
               onChange={(e) => update({ query: e.target.value })} />
        <select value={filters.status}
                onChange={(e) => update({ status: e.target.value as Filters["status"] })}>
          <option value="any">Każdy status</option>
          <option value="none">Bez statusu</option>
          {(Object.keys(STATUS_LABELS) as StatusKey[]).map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <select value={filters.sort} onChange={(e) => update({ sort: e.target.value as SortKey })}>
          <option value="score">Najlepiej dopasowane</option>
          <option value="newest">Najnowsze</option>
          <option value="price">Najtańsze</option>
          <option value="price_m2">Najniższa cena za m²</option>
        </select>
        <label className="toggle">
          <input type="checkbox" checked={filters.onlyNew}
                 onChange={(e) => update({ onlyNew: e.target.checked })} />
          Tylko nowe ({newCount})
        </label>
      </div>
      {error && <p className="error">Nie udało się wczytać ofert: {error}</p>}
      <p className="muted small">{loading ? "Ładuję oferty…" : `${items.length} ofert`}</p>
      <div className="cards">
        {items.map(({ listing, duplicates }) => (
          <ListingCard key={listing.id} listing={listing} duplicates={duplicates}
                       status={statuses.get(listing.id)} reactions={reactions}
                       comments={commentCounts[listing.id] ?? 0} members={members}
                       isNew={isNew(listing, lastVisit)} />
        ))}
      </div>
      {!loading && items.length === 0 && (
        <p className="center muted">Brak ofert dla tych filtrów.</p>
      )}
    </div>
  );
}
