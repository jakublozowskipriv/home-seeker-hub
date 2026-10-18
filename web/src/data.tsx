import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { Listing, ListingStatus, Me, Member, Reaction } from "./api/types";
import { groupDuplicates, type Grouped } from "./format";

interface Data {
  me: Me;
  isOwner: boolean;
  listings: Listing[];
  grouped: Grouped[];
  byId: Map<string, Listing>;
  statuses: Map<string, ListingStatus>;
  reactions: Reaction[];
  commentCounts: Record<string, number>;
  members: Member[];
  lastVisit: string | null;
  lastRunAt: string | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Re-read only the small shared tables after a change (statuses, reactions, comments). */
  refreshShared: () => Promise<void>;
}

const DataContext = createContext<Data | null>(null);

export function DataProvider({ me, children }: { me: Me; children: ReactNode }) {
  const [listings, setListings] = useState<Listing[]>([]);
  const [statusRows, setStatusRows] = useState<ListingStatus[]>([]);
  const [reactions, setReactions] = useState<Reaction[]>([]);
  const [commentCounts, setCommentCounts] = useState<Record<string, number>>({});
  const [members, setMembers] = useState<Member[]>([]);
  const [lastVisit, setLastVisit] = useState<string | null>(null);
  const [lastRunAt, setLastRunAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshShared = useCallback(async () => {
    const [s, r, c, m] = await Promise.all([
      api.statuses(), api.reactions(), api.commentCounts(), api.members(),
    ]);
    setStatusRows(s);
    setReactions(r);
    setCommentCounts(c);
    setMembers(m);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [l, run] = await Promise.all([api.listings(true), api.lastRunAt(), refreshShared()]);
      setListings(l);
      setLastRunAt(run);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [refreshShared]);

  useEffect(() => {
    api.touchVisit().then(setLastVisit).catch(() => setLastVisit(null));
    void refresh();
  }, [refresh]);

  const value = useMemo<Data>(() => {
    const active = listings.filter((l) => l.verdict !== "rejected");
    return {
      me,
      isOwner: me.member?.role === "owner",
      listings,
      grouped: groupDuplicates(active),
      byId: new Map(listings.map((l) => [l.id, l])),
      statuses: new Map(statusRows.map((s) => [s.listing_id, s])),
      reactions,
      commentCounts,
      members,
      lastVisit,
      lastRunAt,
      loading,
      error,
      refresh,
      refreshShared,
    };
  }, [me, listings, statusRows, reactions, commentCounts, members, lastVisit, lastRunAt, loading,
      error, refresh, refreshShared]);

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): Data {
  const data = useContext(DataContext);
  if (!data) throw new Error("useData outside DataProvider");
  return data;
}
