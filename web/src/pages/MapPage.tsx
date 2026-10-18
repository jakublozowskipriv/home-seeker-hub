import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MapView } from "../components/MapView";
import { useData } from "../data";
import { headline, money } from "../format";
import { destinations, loadPrefs, type Prefs } from "../preferences";

export function MapPage() {
  const { grouped, statuses } = useData();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [onlyMatch, setOnlyMatch] = useState(true);
  useEffect(() => { void loadPrefs().then((p) => setPrefs(p.prefs)); }, []);

  const listings = useMemo(() => grouped.map((g) => g.listing)
    .filter((l) => (!onlyMatch || l.verdict === "match")
      && statuses.get(l.id)?.status !== "rejected"), [grouped, statuses, onlyMatch]);

  return (
    <div className="map-page">
      <label className="toggle map-toggle">
        <input type="checkbox" checked={onlyMatch} onChange={(e) => setOnlyMatch(e.target.checked)} />
        Tylko pasujące ({listings.length})
      </label>
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
