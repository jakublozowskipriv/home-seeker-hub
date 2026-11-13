import { useEffect, useMemo, useState } from "react";
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
      </div>
      {prefs && (
        <MapView listings={listings} destinations={destinations(prefs)} className="map-full"
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
