"""Common interface for listing sources."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from ..http import Http
from ..models import Listing
from ..preferences import Preferences

log = logging.getLogger(__name__)


class Source:
    name: str = ""
    #: True when search results already contain everything (no detail page needed).
    complete_search_results: bool = False

    def __init__(self, http: Http):
        self.http = http
        #: Set to False when a search could not be completed, so stale listings
        #: of this source are not deactivated by mistake.
        self.search_complete = True
        self.errors: list[str] = []

    def fail(self, message: str) -> None:
        """Record a search failure: the search is incomplete, the run reports it."""
        log.error("%s: %s", self.name, message)
        self.errors.append(message)
        self.search_complete = False

    def search(self, prefs: Preferences, max_pages: int) -> Iterator[Listing]:
        raise NotImplementedError

    def fetch_details(self, listing: Listing) -> Listing:
        return listing

    def fetch_open_day(self, listing: Listing) -> dict | None:
        """Exact open day times (date, timeFrom, timeTo), for sources that have them."""
        return None
