import { describe, expect, it } from "vitest";
import {
  defaultCommission, loanForPayment, monthlyPayment, notaryMaxFee, purchaseCosts,
} from "./finance";

describe("mortgage", () => {
  it("computes an annuity instalment and its inverse", () => {
    expect(Math.round(monthlyPayment(480_000, 6.5, 30))).toBe(3034);
    expect(Math.round(loanForPayment(3034, 6.5, 30))).toBeCloseTo(480_000, -2);
    expect(monthlyPayment(120_000, 0, 10)).toBe(1000);
  });
});

describe("purchase costs", () => {
  it("uses the official maximum notary rates", () => {
    expect(notaryMaxFee(700_000)).toBe(3570); // 1 010 + 0.4% above 60 000
    expect(notaryMaxFee(50_000)).toBe(910);
    expect(notaryMaxFee(5_000_000)).toBe(10_000); // cap
  });

  const base = { price: 700_000, downPaymentPercent: 20, ratePercent: 6.5, years: 30,
                 firstHome: false, commissionPercent: 0 } as const;

  it("adds PCC on the secondary market, unless it is the first flat", () => {
    const secondary = purchaseCosts({ ...base, market: "secondary" });
    expect(secondary.items.find((i) => i.label.startsWith("Podatek PCC"))?.amount).toBe(14_000);
    expect(secondary.loan).toBe(560_000);
    const first = purchaseCosts({ ...base, market: "secondary", firstHome: true });
    expect(secondary.oneOffTotal - first.oneOffTotal).toBe(14_000);
  });

  it("halves the notary fee for developer sales and adds a new land register", () => {
    const primary = purchaseCosts({ ...base, market: "primary" });
    expect(primary.items.some((i) => i.label.startsWith("Podatek PCC"))).toBe(false);
    expect(primary.items.find((i) => i.label.startsWith("Notariusz"))?.amount)
      .toBe(Math.round(3570 * 0.5 * 1.23));
    expect(primary.items.some((i) => i.label === "Założenie księgi wieczystej")).toBe(true);
    expect(primary.cashNeeded).toBe(140_000 + primary.oneOffTotal);
  });

  it("guesses the agency commission", () => {
    const l = { market: "secondary", is_private_owner: false, title: "2 pokoje" };
    expect(defaultCommission(l)).toBe(2.5);
    expect(defaultCommission({ ...l, title: "2 pokoje BEZ PROWIZJI" })).toBe(0);
    expect(defaultCommission({ ...l, is_private_owner: true })).toBe(0);
    expect(defaultCommission({ ...l, market: "primary" })).toBe(0);
  });
});
