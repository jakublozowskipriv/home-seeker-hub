"""Command line interface: `homeseeker run`, `homeseeker probe`, ..."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .area import load_area
from .db import Store, init_db, make_engine, seed_owner
from .http import Http, dig
from .ics import publish as publish_calendar
from .notify.telegram import Telegram, TelegramError
from .pipeline import run
from .preferences import load_preferences
from .report import build_report
from .sources import ALL_SOURCES, build_sources

log = logging.getLogger("homeseeker")


def _telegram(store: Store | None) -> Telegram | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or (
        store.get_setting("telegram_chat_id") if store else None
    )
    tg = Telegram(token, chat_id)
    if not chat_id:
        try:
            chat_id = tg.discover_chat_id()
        except TelegramError as e:
            log.error("Telegram: %s", e)
            return None
        if not chat_id:
            log.warning("Telegram: send /start to your bot (the one named above) first")
            return None
        tg.chat_id = chat_id
        if store:
            store.set_setting("telegram_chat_id", chat_id)
        log.info("Telegram: discovered and saved chat id")
    return tg


def _write_summary(text: str, path: str | None) -> None:
    if path:
        Path(path).write_text(text, encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def cmd_run(args: argparse.Namespace) -> int:
    # Dry run: in-memory database, nothing persists, no notifications.
    engine = make_engine("sqlite://") if args.dry_run else make_engine()
    init_db(engine)
    if owner := os.environ.get("OWNER_EMAIL"):
        seed_owner(engine, owner)
    store = Store(engine)
    prefs = load_preferences(store.get_setting("preferences"))
    http = Http(delay=args.delay)
    sources = build_sources(args.sources.split(",") if args.sources else None, http)
    telegram = None if args.dry_run else _telegram(store)
    try:
        area = load_area(store, http, prefs.commute.modes)
        stats = run(
            store,
            sources,
            prefs,
            telegram,
            max_pages=args.max_pages,
            max_details=args.max_details,
            fairs_http=http,
            area=area,
        )
    finally:
        http.close()
    if not args.dry_run:
        try:
            publish_calendar(store)
        except Exception:  # the calendar is a bonus: never fail the run because of it
            log.exception("Calendar publishing failed")
    report = build_report(store, stats)
    print(report)
    _write_summary(report, args.report)
    log.info("HTTP requests: %s", http.requests)
    return 0 if any(stats.seen.values()) else 1  # nothing found at all = something is broken


# Personal data of advertisers must never end up in (public) CI logs.
REDACTED_KEYS = {
    "owner",
    "contactdetails",
    "advertowner",
    "user",
    "contact",
    "phones",
    "phone",
    "seller_id",
    "title_base64",
    "agency",
}


def _key_tree(data, prefix: str = "", depth: int = 0, max_depth: int = 4) -> list[str]:
    """Compact listing of JSON key paths with sample values - for adapting parsers."""
    out: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if str(k).lower() in REDACTED_KEYS:
                out.append(f"{path} = <redacted>")
                continue
            if isinstance(v, dict | list) and depth < max_depth:
                out += _key_tree(v, path, depth + 1, max_depth)
            else:
                out.append(f"{path} = {json.dumps(v, ensure_ascii=False)[:120]}")
    elif isinstance(data, list):
        out.append(f"{prefix} = list[{len(data)}]")
        if data:
            out += _key_tree(data[0], f"{prefix}[0]", depth + 1, max_depth)
    else:
        out.append(f"{prefix} = {json.dumps(data, ensure_ascii=False)[:120]}")
    return out


def cmd_probe(args: argparse.Namespace) -> int:
    """Print the raw structure of portal responses (debugging parsers in CI)."""
    from .sources import olx, otodom

    prefs = load_preferences()
    http = Http(delay=1.0)
    try:
        if args.source == "otodom":
            data = http.get_next_data(otodom.search_url(prefs, 1))
            search = dig(data, "props", "pageProps", "data", "searchAds") or {}
            print("pageProps keys:", list((dig(data, "props", "pageProps") or {}).keys()))
            print("pagination:", search.get("pagination"))
            items = search.get("items") or []
            if items:
                print("\n".join(_key_tree(items[0], "item", max_depth=5)))
                slug = items[0].get("slug")
                detail = http.get_next_data(f"{otodom.BASE}/pl/oferta/{slug}")
                ad = dig(detail, "props", "pageProps", "ad") or {}
                print("\n".join(_key_tree(ad, "ad", max_depth=3)))
        elif args.source == "olx":
            ids = http.get_json(f"{olx.API}/friendly-links/query-params/{olx.FRIENDLY_PATH}")
            print("friendly-links:", json.dumps(ids, ensure_ascii=False)[:1000])
            params = {**(ids.get("data") or {}), "limit": 3}
            data = http.get_json(f"{olx.API}/offers/", params=params)
            print("metadata:", json.dumps(data.get("metadata"), ensure_ascii=False)[:500])
            print("links:", json.dumps(data.get("links"), ensure_ascii=False)[:500])
            for offer in (data.get("data") or [])[:1]:
                print("\n".join(_key_tree(offer, "offer", max_depth=4)))
    finally:
        http.close()
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    from .diagnose import area, diagnose, events, otodom_investment, otodom_pagination

    if args.what == "area":
        area()
    elif args.what == "otodom-pages":
        otodom_pagination()
    elif args.what == "otodom-investment":
        otodom_investment()
    elif args.what == "events":
        events()
    else:
        diagnose()
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    init_db(make_engine())
    print("Database ready.")
    return 0


def cmd_telegram_test(args: argparse.Namespace) -> int:
    store = None
    if os.environ.get("DATABASE_URL"):
        engine = make_engine()
        init_db(engine)
        store = Store(engine)
    tg = _telegram(store)
    if tg is None:
        print("Telegram not configured (TELEGRAM_BOT_TOKEN) or no chat found.", file=sys.stderr)
        return 1
    print("Telegram:", tg.diagnostics())
    tg.send_text("✅ Home Seeker Hub: połączenie z Telegramem działa!")
    print("Test message sent.")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs every request URL at INFO; URLs can carry secrets (the calendar's file
    # name) and CI logs of this repository are public.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="homeseeker")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="search portals, store results and notify")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="in-memory database, no notifications - just print a report",
    )
    p.add_argument("--sources", help=f"comma separated, default all: {','.join(ALL_SOURCES)}")
    p.add_argument("--max-pages", type=int, default=50)
    p.add_argument("--max-details", type=int, default=60, help="detail pages per source")
    p.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    p.add_argument("--report", help="write the markdown report to this file")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("probe", help="print raw portal data structure")
    p.add_argument("source", choices=sorted(ALL_SOURCES))
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("diagnose", help="check portal reachability")
    p.add_argument(
        "what",
        nargs="?",
        default="access",
        choices=["access", "otodom-pages", "otodom-investment", "events", "area"],
    )
    p.set_defaults(func=cmd_diagnose)
    sub.add_parser("init-db", help="create tables").set_defaults(func=cmd_init_db)
    sub.add_parser("telegram-test", help="send a test message").set_defaults(func=cmd_telegram_test)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
