import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ReachMap } from "../api/types";
import { Link } from "react-router-dom";
import { MapView } from "../components/MapView";
import { useData } from "../data";
import { headline, money, type MarketFilter } from "../format";
import { destinations, loadPrefs, type Prefs } from "../preferences";

export function MapPage() {
  const { grouped, statuses } = useData();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [onlyMatch, setOnlyMatch] = useState(true);
  const [market, setMarket] = useState<MarketFilter>("all");
  const [showReach, setShowReach] = useState(false);
  const [reach, setReach] = useState<ReachMap | null | undefined>(undefined);
  useEffect(() => {
    if (showReach && reach === undefined) void api.reachMap().then(setReach).catch(() => setReach(null));
  }, [showReach, reach]);
  useEffect(() => { void loadPrefs().then((p) => setPrefs(p.prefs)); }, []);

  const listings = useMemo(() => grouped.map((g) => g.listing)
    .filter((l) => (!onlyMatch || l.verdict === "match")
      && (market === "all" || l.market === market)
      && statuses.get(l.id)?.status !== "rejected"), [grouped, statuses, onlyMatch, market]);

  return (
    <div className="map-page">
      <div className="map-toggle stack-s">
        <label className="toggle">
          <input type="checkbox" checked={onlyMatch}
                 onChange={(e) => setOnlyMatch(e.target.checked)} />
          Tylko pasujące ({listings.length})
        </label>
        <select value={market} onChange={(e) => setMarket(e.target.value as MarketFilter)}>
          <option value="all">Rynek: każdy</option>
          <option value="secondary">Rynek wtórny</option>
          <option value="primary">Rynek pierwotny</option>
        </select>
        <label className="toggle">
          <input type="checkbox" checked={showReach}
                 onChange={(e) => setShowReach(e.target.checked)} />
          Zasięg dojazdu
        </label>
        {showReach && reach === null && (
          <span className="small muted">Mapa zasięgu będzie po najbliższym przebiegu.</span>
        )}
        <div className="map-legend small">
          {showReach && reach && <>
            <span><i style={{ background: "#1f8a5b", opacity: 0.5 }} />≤ {reach.limit} min</span>
            <span><i style={{ background: "#d08a1e", opacity: 0.5 }} />≤ {Math.round(reach.limit * 1.25)} min</span>
          </>}
          <span><i style={{ background: "#1f8a5b" }} />wynik 75+</span>
          <span><i style={{ background: "#d08a1e" }} />55–74</span>
          <span><i style={{ background: "#b04a3a" }} />&lt;55</span>
        </div>
      </div>
      {prefs && (
        <MapView listings={listings} destinations={destinations(prefs)} className="map-full"
                 reach={showReach ? reach : null}
                 popup={(l) => (
                   <Link to={`/oferta/${encodeURIComponent(l.id)}`}>
                     <b>{money(l.price)}</b> · {l.score}/100<br />{headline(l)}<br />
                     {l.location_text}
                   </Link>
                 )} />
      )}
    </div>
  );
}
