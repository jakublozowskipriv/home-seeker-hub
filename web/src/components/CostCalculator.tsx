import { useState } from "react";
import type { Listing } from "../api/types";
import { defaultCommission, loanForPayment, purchaseCosts } from "../finance";
import { money } from "../format";
import type { Prefs } from "../preferences";

const KEY = "hs-calc";

interface Assumptions {
  downPaymentPercent: number;
  ratePercent: number;
  years: number;
  firstHome: boolean;
}

function loadAssumptions(prefs: Prefs | null): Assumptions {
  const m = prefs?.mortgage ?? {};
  const defaults: Assumptions = {
    downPaymentPercent: m.down_payment_percent ?? 20,
    ratePercent: m.interest_rate_percent ?? 6.5,
    years: m.years ?? 30,
    firstHome: false,
  };
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return defaults;
  }
}

/** Instalment, one-off costs and cash needed; assumptions are remembered on this device. */
export function CostCalculator({ listing: l, prefs }: { listing: Listing; prefs: Prefs | null }) {
  const [a, setA] = useState<Assumptions>(() => loadAssumptions(prefs));
  const [commission, setCommission] = useState(() => defaultCommission(l));
  if (!l.price) return <p className="muted">Brak ceny – nie da się policzyć kosztów.</p>;

  function update(change: Partial<Assumptions>) {
    const next = { ...a, ...change };
    setA(next);
    try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* private mode */ }
  }

  const costs = purchaseCosts({ price: l.price, market: l.market, commissionPercent: commission,
                                ...a });
  const rent = typeof l.raw?.rent === "number" ? l.raw.rent : null;
  const min = prefs?.budget?.monthly_payment_min as number | undefined;
  const max = prefs?.budget?.monthly_payment_max as number | undefined;
  const fits = max == null || costs.payment <= max;
  const neededDown = max ? Math.max(0, l.price - loanForPayment(max, a.ratePercent, a.years)) : 0;
  const field = (label: string, value: number, step: number, suffix: string,
                 onChange: (v: number) => void) => (
    <label className="field">{label}
      <span className="row gap-s">
        <input type="number" step={step} min={0} value={value}
               onChange={(e) => onChange(Number(e.target.value))} />
        <span className="muted small">{suffix}</span>
      </span>
    </label>
  );

  return (
    <div className="stack-s">
      <div className="grid2">
        {field("Wkład własny", a.downPaymentPercent, 5, "%",
               (v) => update({ downPaymentPercent: Math.min(100, v) }))}
        {field("Oprocentowanie", a.ratePercent, 0.1, "%", (v) => update({ ratePercent: v }))}
        {field("Okres", a.years, 1, "lat", (v) => update({ years: Math.max(1, v) }))}
        {field("Prowizja biura", commission, 0.5, "% netto", setCommission)}
      </div>
      {l.market !== "primary" && (
        <label className="toggle">
          <input type="checkbox" checked={a.firstHome}
                 onChange={(e) => update({ firstHome: e.target.checked })} />
          Pierwsze własne mieszkanie (bez PCC 2%)
        </label>
      )}

      <dl className="facts">
        <div><dt>Wkład własny</dt><dd>{money(costs.downPayment)}</dd></div>
        <div><dt>Kredyt</dt><dd>{money(costs.loan)}</dd></div>
        <div>
          <dt>Rata (równe raty)</dt>
          <dd className={fits ? "success" : "warn-text"}>{money(costs.payment)}/mies.</dd>
        </div>
        {rent != null && (
          <div><dt>Rata + czynsz ({money(rent)})</dt><dd>{money(costs.payment + rent)}/mies.</dd></div>
        )}
      </dl>
      {max != null && (
        <p className="small">
          {fits
            ? `Rata mieści się w Twoim zakresie${min ? ` ${money(min)}–` : " do "}${money(max)}.`
            : `Żeby rata zmieściła się w ${money(max)}, potrzeba ok. ${money(neededDown)} ` +
              `wkładu (${Math.round((neededDown / l.price) * 100)}% ceny).`}
        </p>
      )}

      <h3>Koszty jednorazowe</h3>
      <ul className="costs">
        {costs.items.map((it) => (
          <li key={it.label}><span>{it.label}{it.hint && <span className="muted"> · {it.hint}</span>}
          </span><b>{money(it.amount)}</b></li>
        ))}
        <li className="total"><span>Razem</span><b>{money(costs.oneOffTotal)}</b></li>
      </ul>
      <p className="cash">Gotówka na start (wkład + koszty): <b>{money(costs.cashNeeded)}</b></p>
      <p className="muted small">
        Szacunek: notariusz według stawek maksymalnych (zwykle można negocjować), bez wyceny
        nieruchomości, ubezpieczeń i prowizji banku. Oprocentowanie sprawdź w aktualnych
        ofertach banków.
      </p>
    </div>
  );
}
