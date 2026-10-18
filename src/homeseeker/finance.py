"""Mortgage payment estimate (equal instalments). The full purchase-cost calculator lives
in the web app, where the numbers can be adjusted per listing."""

from __future__ import annotations


def monthly_payment(principal: float, annual_rate_percent: float, years: int) -> float:
    n = years * 12
    r = annual_rate_percent / 100 / 12
    if principal <= 0:
        return 0.0
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)
