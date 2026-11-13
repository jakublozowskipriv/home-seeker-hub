import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useCompare } from "../compare";
import { ListingCard } from "../components/ListingCard";
import { useData } from "../data";
import {
  applyFilters, DEFAULT_FILTERS, isNew, STATUS_LABELS, type Filters, type MarketFilter,
  type ReactionFilter, type SortKey,
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
  const { grouped, statuses, reactions, commentCounts, members, lastVisit, loading, error, me,
          history } = useData();
  const [filters, setFilters] = useState<Filters>(loadFilters);
  const compare = useCompare();

  function update(change: Partial<Filters>) {
    const next = { ...filters, ...change };
    setFilters(next);
    try { localStorage.setItem(FILTER_KEY, JSON.stringify(next)); } catch { /* private mode */ }
  }

  const ctx = useMemo(() => ({ statuses, lastVisit, reactions, me: me.email, history }),
    [statuses, lastVisit, reactions, me.email, history]);
  const items = useMemo(() => applyFilters(grouped, filters, ctx), [grouped, filters, ctx]);
  // Liked listings can sit in another tab (e.g. "do sprawdzenia"): say how many.
  const elsewhere = useMemo(() => (filters.reaction === "any" || filters.verdict === "all" ? 0
    : applyFilters(grouped, { ...filters, verdict: "all" }, ctx).length - items.length),
    [grouped, filters, ctx, items.length]);
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
          <option value="drop">Największa obniżka</option>
        </select>
        <select value={filters.market}
                onChange={(e) => update({ market: e.target.value as MarketFilter })}>
          <option value="all">Rynek: każdy</option>
          <option value="secondary">Rynek wtórny</option>
          <option value="primary">Rynek pierwotny</option>
        </select>
        <select value={filters.reaction}
                onChange={(e) => update({ reaction: e.target.value as ReactionFilter })}>
          <option value="any">Reakcje: każde</option>
          <option value="liked">👍 Polubione</option>
          <option value="liked_by_me">👍 Polubione przeze mnie</option>
          <option value="disliked">👎 Na nie</option>
          <option value="none">Bez reakcji</option>
        </select>
        <label className="toggle">
          <input type="checkbox" checked={filters.onlyNew}
                 onChange={(e) => update({ onlyNew: e.target.checked })} />
          Tylko nowe ({newCount})
        </label>
        <label className="toggle">
          <input type="checkbox" checked={filters.sunny}
                 onChange={(e) => update({ sunny: e.target.checked })} />
          ☀️ Okna na płd./zach.
        </label>
      </div>
      {error && <p className="error">Nie udało się wczytać ofert: {error}</p>}
      <p className="muted small">
        {loading ? "Ładuję oferty…" : `${items.length} ofert`}
        {elsewhere > 0 && (
          <> · <button className="link small" onClick={() => update({ verdict: "all" })}>
            +{elsewhere} w innych zakładkach – pokaż wszystkie</button></>
        )}
      </p>
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
      {compare.length > 0 && (
        <Link to="/porownaj" className="compare-bar button">
          ⚖️ Porównaj wybrane ({compare.length})
        </Link>
      )}
    </div>
  );
}
