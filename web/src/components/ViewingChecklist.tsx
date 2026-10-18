import { useEffect, useState } from "react";
import { api } from "../api";
import type { Checklist, ChecklistItem, Listing } from "../api/types";
import { checklistFor } from "../checklist";
import { useData } from "../data";
import { personName, relativeTime } from "../format";

/** Shared checklist: everyone with access ticks items and adds notes. */
export function ViewingChecklist({ listing }: { listing: Listing }) {
  const { members } = useData();
  const [data, setData] = useState<Checklist | null>(null);
  const [items, setItems] = useState<Record<string, ChecklistItem>>({});
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    void api.checklist(listing.id).then((c) => { setData(c); setItems(c?.items ?? {}); });
  }, [listing.id]);

  /** Saves one item on top of the latest stored list, so people editing at once don't
   * overwrite each other's ticks. */
  async function save(key: string, item: ChecklistItem) {
    setItems((current) => ({ ...current, [key]: item }));
    setError(null);
    try {
      const latest = (await api.checklist(listing.id))?.items ?? {};
      await api.saveChecklist(listing.id, { ...latest, [key]: item });
      const stored = await api.checklist(listing.id);
      setData(stored);
      setItems(stored?.items ?? {});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const groups = checklistFor(listing.market);
  const total = groups.reduce((s, g) => s + g.items.length, 0);
  const done = groups.reduce((s, g) => s + g.items.filter((it) => items[it.key]?.done).length, 0);

  return (
    <div className="stack-s checklist">
      <p className="small muted">
        {done}/{total} sprawdzone
        {data?.updated_by && ` · ostatnio ${personName(data.updated_by, members)}, ` +
          relativeTime(data.updated_at)}
      </p>
      {groups.map((g) => (
        <details key={g.title} className="check-group">
          <summary>
            {g.title}
            <span className="muted small"> {g.items.filter((it) => items[it.key]?.done).length}/
              {g.items.length}</span>
          </summary>
          {g.items.map((it) => {
            const item = items[it.key] ?? { done: false };
            return (
              <div key={it.key} className="check-item">
                <div className="row between">
                  <label className="toggle">
                    <input type="checkbox" checked={item.done}
                           onChange={(e) => void save(it.key, { ...item, done: e.target.checked })} />
                    <span>{it.label}</span>
                  </label>
                  <button type="button" className="link small"
                          onClick={() => setOpen(open === it.key ? null : it.key)}>
                    {item.note ? "📝" : "+ notatka"}
                  </button>
                </div>
                {(open === it.key || item.note) && (
                  <input className="small" placeholder="Notatka" defaultValue={item.note ?? ""}
                         onBlur={(e) => {
                           if ((item.note ?? "") !== e.target.value) {
                             void save(it.key, { ...item, note: e.target.value });
                           }
                         }} />
                )}
              </div>
            );
          })}
        </details>
      ))}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
