import { Link } from "react-router-dom";
import type { Listing, ListingStatus, Member, Reaction } from "../api/types";
import { useData } from "../data";
import {
  commuteEntries, headline, initials, isEstimate, money, personName, reactionSummary, redFlags,
  scoreClass, shortDestination, sourceName, STATUS_LABELS,
} from "../format";

export function Photo({ listing, className = "" }: { listing: Listing; className?: string }) {
  const src = listing.images?.[0];
  return src ? (
    <img className={`photo ${className}`} src={src} alt="" loading="lazy"
         referrerPolicy="no-referrer" />
  ) : (
    <div className={`photo placeholder ${className}`} aria-hidden>🏢</div>
  );
}

export function ScoreBadge({ score }: { score: number }) {
  return <span className={`score ${scoreClass(score)}`} title="Dopasowanie">{score}</span>;
}

export function Avatars({ emails, members }: { emails: string[]; members: Member[] }) {
  return (
    <span className="avatars">
      {emails.map((e) => {
        const name = personName(e, members);
        return <span key={e} className="avatar" title={name}>{initials(name)}</span>;
      })}
    </span>
  );
}

interface Props {
  listing: Listing;
  duplicates: Listing[];
  status?: ListingStatus;
  reactions: Reaction[];
  comments: number;
  members: Member[];
  isNew: boolean;
}

export function ListingCard({ listing: l, duplicates, status, reactions, comments, members,
                              isNew }: Props) {
  const { up, down } = reactionSummary(l.id, reactions);
  const { medians } = useData();
  const flags = redFlags(l, medians).filter((f) => f.level === "high");
  return (
    <Link to={`/oferta/${encodeURIComponent(l.id)}`} className="listing-card">
      <Photo listing={l} />
      <div className="listing-body">
        <div className="row between">
          <strong className="price">{money(l.price)}</strong>
          <ScoreBadge score={l.score} />
        </div>
        <div className="headline">{headline(l)}</div>
        <div className="muted small ellipsis">{l.location_text ?? l.district}</div>
        <div className="chips">
          {isNew && <span className="chip new">NOWE</span>}
          {l.verdict === "review" && <span className="chip warn">do sprawdzenia</span>}
          {l.verdict === "negotiable" && <span className="chip warn">do negocjacji</span>}
          {l.market === "primary" && <span className="chip">pierwotny</span>}
          {flags.length > 0 && (
            <span className="chip flag" title={flags.map((f) => f.text).join("\n")}>
              🚩 {flags.length}
            </span>
          )}
          {commuteEntries(l).map(([name, min]) => (
            <span key={name} className="chip">
              🚋 {isEstimate(l) ? "~" : ""}{Math.round(min)} min {shortDestination(name)}
            </span>
          ))}
        </div>
        <div className="row between small">
          <span>
            {status && <span className="status">{STATUS_LABELS[status.status]}</span>}
          </span>
          <span className="row gap-s muted">
            {up.length > 0 && <span>👍<Avatars emails={up.map((r) => r.email)} members={members} /></span>}
            {down.length > 0 && <span>👎<Avatars emails={down.map((r) => r.email)} members={members} /></span>}
            {comments > 0 && <span>💬 {comments}</span>}
            <span>{[l, ...duplicates].map((x) => sourceName(x.source))
              .filter((v, i, a) => a.indexOf(v) === i).join(" · ")}</span>
          </span>
        </div>
      </div>
    </Link>
  );
}
