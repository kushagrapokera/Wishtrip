import type { DayPlan, ScheduledActivity } from "../api/fetchItinerary";
import { formatCostInr, formatDayCost, formatTravelLeg } from "../itineraryFormat";

interface ItineraryTimelineProps {
  day: DayPlan;
}

function ActivityFlags({ activity }: { activity: ScheduledActivity }) {
  const flags: string[] = [];
  if (activity.hours_unverified) {
    flags.push("hours not verified");
  }
  if (activity.cost_is_estimate) {
    flags.push("cost estimated");
  }
  if (flags.length === 0) {
    return null;
  }
  return <p className="activity-flags">⚠ {flags.join(" · ")}</p>;
}

/** Ordered activities with times, travel legs, costs and why-notes. */
export function ItineraryTimeline({ day }: ItineraryTimelineProps) {
  return (
    <section className="timeline" aria-label={`Day ${day.day_number} plan`}>
      <header className="timeline-header">
        <h3>
          Day {day.day_number} — {day.theme}
        </h3>
        <p className="timeline-meta">
          {formatDayCost(day.day_cost_inr_estimate, day.day_travel_minutes_total)}
        </p>
      </header>
      <ol className="timeline-list">
        {day.activities.map((activity, index) => (
          <li key={`${activity.kind}-${activity.place_id ?? activity.name}-${index}`} className="timeline-item">
            <div className="timeline-time">
              {activity.start_time}–{activity.end_time}
            </div>
            <div className="timeline-body">
              {activity.travel_leg_before !== null && activity.travel_leg_before.travel_minutes > 0 && (
                <p className="travel-leg">
                  ↓ {formatTravelLeg(
                    activity.travel_leg_before.travel_minutes,
                    activity.travel_leg_before.mode,
                  )}
                </p>
              )}
              <p className="activity-name">
                <span className={`kind-badge kind-${activity.kind}`}>{activity.kind}</span>
                {activity.name}
              </p>
              <p className="activity-meta">
                {formatCostInr(activity.indicative_cost_inr)}
                {activity.category !== null && ` · ${activity.category}`}
              </p>
              <p className="activity-why">{activity.why}</p>
              <ActivityFlags activity={activity} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
