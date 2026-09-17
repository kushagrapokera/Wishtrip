import type { DayPlan } from "../api/fetchItinerary";

interface DayTabsProps {
  days: DayPlan[];
  activeDayNumber: number;
  onSelectDay: (dayNumber: number) => void;
}

/** One tab per trip day; the active day drives the timeline and the map. */
export function DayTabs({ days, activeDayNumber, onSelectDay }: DayTabsProps) {
  return (
    <nav className="day-tabs" aria-label="Trip days">
      {days.map((day) => (
        <button
          key={day.day_number}
          type="button"
          className={day.day_number === activeDayNumber ? "day-tab day-tab-active" : "day-tab"}
          onClick={() => onSelectDay(day.day_number)}
          aria-pressed={day.day_number === activeDayNumber}
        >
          <span className="day-tab-number">Day {day.day_number}</span>
          <span className="day-tab-theme">{day.theme}</span>
        </button>
      ))}
    </nav>
  );
}
