import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import { useData } from "../data";
import { DEFAULT_PREFS, loadPrefs, type Prefs } from "../preferences";

type Path = (string | number)[];

function getPath(obj: Prefs, path: Path): any { // eslint-disable-line @typescript-eslint/no-explicit-any
  return path.reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function setPath(obj: Prefs, path: Path, value: unknown): Prefs {
  const copy = structuredClone(obj);
  let cur = copy;
  for (const k of path.slice(0, -1)) cur = cur[k] ??= {};
  cur[path[path.length - 1]] = value;
  return copy;
}

const WEIGHT_LABELS: Record<string, string> = {
  location: "Lokalizacja", commute: "Dojazd", floor: "Piętro", build_year: "Rok budowy",
  price: "Cena", elevator: "Winda", area: "Metraż", rooms: "Pokoje",
};

export function PreferencesPage() {
  const { isOwner } = useData();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [stored, setStored] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void loadPrefs().then((p) => { setPrefs(p.prefs); setStored(p.stored); }); },
    []);
  if (!prefs) return <p className="muted">Ładuję…</p>;
  const p = prefs;

  const set = (path: Path, value: unknown) => { setPrefs(setPath(p, path, value)); setSaved(null); };
  const num = (path: Path, label: string, step = 1, suffix = "") => (
    <label className="field">{label}
      <span className="row gap-s">
        <input type="number" step={step} value={getPath(p, path) ?? ""}
               onChange={(e) => set(path, e.target.value === "" ? null : Number(e.target.value))} />
        {suffix && <span className="muted small">{suffix}</span>}
      </span>
    </label>
  );
  const check = (path: Path, label: string) => (
    <label className="toggle">
      <input type="checkbox" checked={!!getPath(p, path)}
             onChange={(e) => set(path, e.target.checked)} />{label}
    </label>
  );
  const list = (path: Path, label: string) => (
    <label className="field">{label}
      <textarea rows={2} value={(getPath(p, path) ?? []).join(", ")}
                onChange={(e) => set(path, e.target.value.split(",").map((s) => s.trim())
                  .filter(Boolean))} />
    </label>
  );
  const section = (title: string, children: ReactNode) => (
    <section className="card stack-s"><h2>{title}</h2>{children}</section>
  );

  async function save(next: Prefs) {
    setError(null);
    try {
      await api.savePreferences(next);
      setPrefs(next);
      setStored(true);
      setSaved("Zapisane. Zmiany zadziałają przy najbliższym przebiegu (co 3 godziny) – " +
        "wszystkie oferty zostaną wtedy ocenione od nowa.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const markets: string[] = p.markets ?? [];
  const toggleMarket = (m: string, on: boolean) =>
    set(["markets"], on ? [...new Set([...markets, m])] : markets.filter((x) => x !== m));
  const dests: { name: string; lat: number; lon: number }[] = p.destinations ?? [];

  return (
    <form className="stack prefs" onSubmit={(e) => { e.preventDefault(); void save(p); }}>
      {!isOwner && <p className="muted">Podgląd – preferencje zmienia właściciel.</p>}
      {!stored && <p className="muted small">Używane są ustawienia domyślne.</p>}
      <fieldset disabled={!isOwner} className="stack">
        {section("Budżet", <div className="grid2">
          {num(["budget", "max_price"], "Cena maks.", 5000, "zł")}
          {num(["budget", "negotiable_max_price"], "„Do negocjacji” do", 5000, "zł")}
          {num(["budget", "monthly_payment_min"], "Rata od", 100, "zł")}
          {num(["budget", "monthly_payment_max"], "Rata do", 100, "zł")}
        </div>)}
        {section("Mieszkanie", <>
          <div className="grid2">
            {num(["area", "min"], "Metraż od", 1, "m²")}
            {num(["area", "max"], "Metraż do", 1, "m²")}
            {num(["rooms", "min"], "Pokoje od")}
            {num(["rooms", "max"], "Pokoje do")}
            {num(["floor", "min"], "Najniższe piętro", 1, "0 = parter")}
            {num(["build_year_preferred_min"], "Preferowany rok budowy od")}
          </div>
          {check(["balcony_required"], "Balkon / loggia wymagany")}
          {check(["exclude_gas_heating"], "Bez pieca gazowego")}
          {check(["floor", "elevator_preferred"], "Winda mile widziana")}
          <label className="toggle"><input type="checkbox" checked={markets.includes("primary")}
            onChange={(e) => toggleMarket("primary", e.target.checked)} />Rynek pierwotny</label>
          <label className="toggle"><input type="checkbox" checked={markets.includes("secondary")}
            onChange={(e) => toggleMarket("secondary", e.target.checked)} />Rynek wtórny</label>
          <label className="field">Oddanie (rynek pierwotny) najpóźniej
            <input type="date" value={p.completion_deadline ?? ""}
                   onChange={(e) => set(["completion_deadline"], e.target.value || null)} />
          </label>
        </>)}
        {section("Lokalizacja", <>
          {list(["locations", "preferred"], "Ulubione dzielnice (bonus)")}
          {list(["locations", "allowed"], "Dopuszczalne dzielnice")}
          {list(["locations", "excluded"], "Wykluczone (krańce)")}
          {num(["commute", "max_minutes"], "Maks. dojazd (tramwaj + pieszo)", 1, "min")}
          <h3>Ważne miejsca</h3>
          {dests.map((d, i) => (
            <div key={i} className="dest">
              <input value={d.name} onChange={(e) => set(["destinations", i, "name"], e.target.value)} />
              <input type="number" step="0.0001" value={d.lat}
                     onChange={(e) => set(["destinations", i, "lat"], Number(e.target.value))} />
              <input type="number" step="0.0001" value={d.lon}
                     onChange={(e) => set(["destinations", i, "lon"], Number(e.target.value))} />
              <button type="button" className="ghost small"
                      onClick={() => set(["destinations"], dests.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button type="button" className="ghost small" onClick={() => set(["destinations"],
            [...dests, { name: "Nowe miejsce", lat: 52.4064, lon: 16.9252 }])}>+ Dodaj miejsce</button>
          <p className="muted small">Współrzędne skopiujesz z Google Maps (przytrzymaj punkt na mapie).</p>
        </>)}
        {section("Co jest ważniejsze (wagi oceny)", <div className="weights">
          {Object.keys(WEIGHT_LABELS).map((k) => (
            <label key={k} className="field">{WEIGHT_LABELS[k]}: {getPath(p, ["weights", k]) ?? 0}
              <input type="range" min={0} max={40} value={getPath(p, ["weights", k]) ?? 0}
                     onChange={(e) => set(["weights", k], Number(e.target.value))} />
            </label>
          ))}
        </div>)}
        {section("Powiadomienia (Telegram)", <>
          {check(["notifications", "notify_review"], "Oferty z brakującymi danymi")}
          {check(["notifications", "notify_negotiable"], "Oferty „do negocjacji”")}
          {num(["notifications", "max_per_run"], "Więcej naraz → jedno podsumowanie")}
        </>)}
      </fieldset>
      {isOwner && (
        <div className="row gap sticky-actions">
          <button type="submit">Zapisz</button>
          <button type="button" className="ghost"
                  onClick={() => { if (confirm("Przywrócić ustawienia domyślne?")) {
                    void save(structuredClone(DEFAULT_PREFS));
                  } }}>Przywróć domyślne</button>
        </div>
      )}
      {saved && <p className="success">{saved}</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
