import { Circle, CircleMarker, MapContainer, Popup, TileLayer, Tooltip } from "react-leaflet";
import type { ReactNode } from "react";
import type { Listing } from "../api/types";

export interface Destination {
  name: string;
  lat: number;
  lon: number;
}

const POZNAN: [number, number] = [52.4064, 16.9252];

export function scoreColor(score: number): string {
  return score >= 75 ? "#1f8a5b" : score >= 55 ? "#d08a1e" : "#b04a3a";
}

interface Props {
  listings: Listing[];
  destinations: Destination[];
  center?: [number, number];
  zoom?: number;
  className?: string;
  popup?: (l: Listing) => ReactNode;
}

/** OpenStreetMap with listings as coloured dots (no marker images needed). */
export function MapView({ listings, destinations, center = POZNAN, zoom = 12, className = "",
                          popup }: Props) {
  return (
    <MapContainer center={center} zoom={zoom} className={`map ${className}`} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {destinations.map((d) => (
        <CircleMarker key={d.name} center={[d.lat, d.lon]} radius={9}
                      pathOptions={{ color: "#2b4c9a", fillColor: "#2b4c9a", fillOpacity: 0.9 }}>
          <Tooltip permanent direction="top" offset={[0, -8]}>{d.name.split(" (")[0]}</Tooltip>
        </CircleMarker>
      ))}
      {listings.filter((l) => l.lat != null && l.lon != null).map((l) =>
        l.coords_approximate ? (
          <Circle key={l.id} center={[l.lat!, l.lon!]} radius={400}
                  pathOptions={{ color: scoreColor(l.score), weight: 1, fillOpacity: 0.12 }}>
            {popup && <Popup>{popup(l)}</Popup>}
          </Circle>
        ) : (
          <CircleMarker key={l.id} center={[l.lat!, l.lon!]} radius={7}
                        pathOptions={{ color: "#fff", weight: 2, fillColor: scoreColor(l.score),
                                       fillOpacity: 1 }}>
            {popup && <Popup>{popup(l)}</Popup>}
          </CircleMarker>
        ),
      )}
    </MapContainer>
  );
}
