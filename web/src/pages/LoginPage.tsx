import { useState } from "react";
import { api } from "../api";

export function LoginPage({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <div className="card narrow">
        <h1>🏠 Mieszkania</h1>
        {!sent ? (
          <form onSubmit={(e) => {
            e.preventDefault();
            void run(async () => { await api.sendCode(email); setSent(true); });
          }}>
            <p className="muted">Podaj e-mail – wyślemy kod logowania.</p>
            <input type="email" required autoComplete="email" placeholder="twoj@email.pl"
                   value={email} onChange={(e) => setEmail(e.target.value)} />
            <button type="submit" disabled={busy}>{busy ? "Wysyłam…" : "Wyślij kod"}</button>
          </form>
        ) : (
          <form onSubmit={(e) => {
            e.preventDefault();
            void run(async () => { await api.verifyCode(email, code); onSignedIn(); });
          }}>
            <p className="muted">
              Wpisz kod z maila wysłanego na <b>{email}</b> albo kliknij link w mailu
              (działa w tej samej przeglądarce). W aplikacji na ekranie początkowym iPhone'a
              użyj kodu – link otworzyłby się w Safari.
            </p>
            <input inputMode="numeric" autoComplete="one-time-code" placeholder="123456"
                   value={code} onChange={(e) => setCode(e.target.value)} required />
            <button type="submit" disabled={busy}>{busy ? "Sprawdzam…" : "Zaloguj"}</button>
            <button type="button" className="ghost" onClick={() => setSent(false)}>
              Zmień e-mail
            </button>
          </form>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
