import { downloadIcs, googleCalendarUrl, type CalendarItem } from "../calendar";

export function AddToCalendar({ item }: { item: CalendarItem }) {
  return (
    <span className="row gap-s">
      <button type="button" className="ghost small" onClick={() => downloadIcs(item)}>
        📅 Apple / iCal
      </button>
      <a className="button ghost small" href={googleCalendarUrl(item)} target="_blank"
         rel="noreferrer">Google</a>
    </span>
  );
}
