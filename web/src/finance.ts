/**
 * Mortgage instalment and one-off purchase costs in Poland (estimates, maximum official
 * rates where a rate is regulated). Everything here is a planning aid, not an offer.
 */

export interface CostInputs {
  price: number;
  market: "primary" | "secondary" | null;
  downPaymentPercent: number;
  ratePercent: number;
  years: number;
  /** First own flat on the secondary market: exempt from the 2% PCC tax (since 2023). */
  firstHome: boolean;
  /** Estate agent's commission, net (VAT 23% is added). */
  commissionPercent: number;
}

export interface CostItem {
  label: string;
  amount: number;
  hint?: string;
}

export interface CostSummary {
  loan: number;
  downPayment: number;
  payment: number;
  items: CostItem[];
  oneOffTotal: number;
  /** Own money needed at the start: down payment + one-off costs. */
  cashNeeded: number;
}

const VAT = 1.23;

export function monthlyPayment(principal: number, ratePercent: number, years: number): number {
  const n = years * 12;
  const r = ratePercent / 100 / 12;
  if (principal <= 0 || n <= 0) return 0;
  if (r === 0) return principal / n;
  return (principal * r) / (1 - (1 + r) ** -n);
}

/** Largest loan whose instalment fits in `payment` (inverse of monthlyPayment). */
export function loanForPayment(payment: number, ratePercent: number, years: number): number {
  const n = years * 12;
  const r = ratePercent / 100 / 12;
  if (payment <= 0 || n <= 0) return 0;
  if (r === 0) return payment * n;
  return (payment * (1 - (1 + r) ** -n)) / r;
}

/** Maximum notary fee (taksa notarialna, § 3 of the 2004 regulation), net of VAT. */
export function notaryMaxFee(value: number): number {
  const steps: [number, number, number][] = [
    // [from, base fee, rate above `from`]
    [2_000_000, 6_770, 0.0025],
    [1_000_000, 4_770, 0.002],
    [60_000, 1_010, 0.004],
    [30_000, 710, 0.01],
    [10_000, 310, 0.02],
    [3_000, 100, 0.03],
  ];
  for (const [from, base, rate] of steps) {
    if (value > from) return Math.min(base + (value - from) * rate, 10_000);
  }
  return 100;
}

export function purchaseCosts(i: CostInputs): CostSummary {
  const downPayment = Math.round((i.price * i.downPaymentPercent) / 100);
  const loan = Math.max(0, i.price - downPayment);
  const items: CostItem[] = [];
  const primary = i.market === "primary";

  if (!primary) {
    items.push(i.firstHome
      ? { label: "Podatek PCC 2%", amount: 0, hint: "zwolnienie: pierwsze mieszkanie" }
      : { label: "Podatek PCC 2%", amount: i.price * 0.02, hint: "rynek wtórny" });
  }
  // Developer sales: the maximum notary fee is halved.
  const notary = notaryMaxFee(i.price) * (primary ? 0.5 : 1);
  items.push({ label: "Notariusz (taksa maks. + VAT)", amount: notary * VAT,
               hint: "często do negocjacji" });
  items.push({ label: "Wypisy aktu notarialnego", amount: 300, hint: "szacunek" });
  items.push({ label: "Wpis własności do księgi wieczystej", amount: 200 });
  if (primary) items.push({ label: "Założenie księgi wieczystej", amount: 100 });
  if (loan > 0) {
    items.push({ label: "Wpis hipoteki", amount: 200 });
    items.push({ label: "PCC od ustanowienia hipoteki", amount: 19 });
  }
  if (i.commissionPercent > 0) {
    items.push({ label: `Prowizja biura ${i.commissionPercent}% + VAT`,
                 amount: (i.price * i.commissionPercent) / 100 * VAT });
  }
  const rounded = items.map((it) => ({ ...it, amount: Math.round(it.amount) }));
  const oneOffTotal = rounded.reduce((s, it) => s + it.amount, 0);
  return {
    loan,
    downPayment,
    payment: Math.round(monthlyPayment(loan, i.ratePercent, i.years)),
    items: rounded,
    oneOffTotal,
    cashNeeded: downPayment + oneOffTotal,
  };
}

/** Commission guess: secondary-market agency listings, unless "bez prowizji" is mentioned. */
export function defaultCommission(l: {
  market: string | null; is_private_owner: boolean | null; title: string | null;
  description?: string | null;
}): number {
  if (l.market === "primary" || l.is_private_owner) return 0;
  const text = `${l.title ?? ""} ${l.description ?? ""}`.toLowerCase();
  return /bez prowizji|0\s?% prowizji|nie pobieramy prowizji/.test(text) ? 0 : 2.5;
}
