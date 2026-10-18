import { useState } from "react";
import { api } from "../api";
import { useData } from "../data";

export function AccessPage() {
  const { members, isOwner, me, refreshShared } = useData();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!isOwner) return <p className="muted">Tylko właściciel zarządza dostępem.</p>;

  async function add() {
    setError(null);
    try {
      await api.addMember(email, name || null);
      setEmail("");
      setName("");
      await refreshShared();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  async function remove(target: string) {
    if (!confirm(`Odebrać dostęp ${target}?`)) return;
    await api.removeMember(target);
    await refreshShared();
  }

  return (
    <div className="stack">
      <section className="card stack-s">
        <h2>Osoby z dostępem</h2>
        <ul className="members">
          {members.map((m) => (
            <li key={m.email} className="row between">
              <span><b>{m.display_name || m.email.split("@")[0]}</b>
                <span className="muted small"> {m.email}</span></span>
              {m.role === "owner" ? <span className="chip">właściciel</span>
                : m.email !== me.email && (
                  <button className="ghost small" onClick={() => void remove(m.email)}>Usuń</button>
                )}
            </li>
          ))}
        </ul>
      </section>
      <section className="card stack-s">
        <h2>Dodaj osobę</h2>
        <form className="stack-s" onSubmit={(e) => { e.preventDefault(); void add(); }}>
          <input type="email" required placeholder="e-mail" value={email}
                 onChange={(e) => setEmail(e.target.value)} />
          <input placeholder="Imię (np. Mama)" value={name} onChange={(e) => setName(e.target.value)} />
          <button type="submit">Dodaj</button>
        </form>
        {error && <p className="error">{error}</p>}
        <p className="muted small">
          Dodana osoba otwiera link do aplikacji, wpisuje swój e-mail i loguje się kodem z maila.
          Może przeglądać oferty, reagować i komentować; preferencje, statusy i dostęp zmieniasz
          tylko Ty.
        </p>
      </section>
    </div>
  );
}
