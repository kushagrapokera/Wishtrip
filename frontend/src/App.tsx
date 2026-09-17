import { useState } from "react";
import "./App.css";
import type { TripRequest } from "./api/fetchItinerary";
import { DayTabs } from "./components/DayTabs";
import { ItineraryTimeline } from "./components/ItineraryTimeline";
import { PreferenceForm } from "./components/PreferenceForm";
import { TripMap } from "./components/TripMap";
import { useItinerary } from "./hooks/useItinerary";
import { formatCostInr } from "./itineraryFormat";

function formatPartyGroupLabel(adults: number, children?: number): string {
  const childCount = children ?? 0;
  if (childCount > 0) {
    return `for ${adults} adult(s) + ${childCount} child(ren)`;
  }
  return `for ${adults} adult(s)`;
}

function App() {
  const { status, itinerary, errorMessage, submitTripRequest, resetItinerary } =
    useItinerary();
  const [activeDayNumber, setActiveDayNumber] = useState(1);

  function handleSubmitRequest(request: TripRequest) {
    setActiveDayNumber(1);
    void submitTripRequest(request);
  }

  const activeDay =
    itinerary?.days.find((day) => day.day_number === activeDayNumber) ??
    itinerary?.days[0];

  return (
    <main className="wishtrip-app">
      <header className="app-header">
        <h1>Wishtrip Trip Planner</h1>
        <p>Turn your preferences into a practical, day-by-day Goa itinerary.</p>
      </header>

      {status !== "ready" && (
        <PreferenceForm onSubmitRequest={handleSubmitRequest} isSubmitting={status === "loading"} />
      )}

      {status === "loading" && <p className="status-note">Planning your days…</p>}

      {status === "error" && (
        <div className="error-box" role="alert">
          <p>{errorMessage}</p>
          <button type="button" onClick={resetItinerary}>
            Adjust your preferences
          </button>
        </div>
      )}

      {status === "ready" && itinerary !== null && activeDay !== undefined && (
        <section className="itinerary-view">
          <div className="itinerary-summary">
            <h2>
              Your {itinerary.summary.total_days}-day trip ·{" "}
              {formatCostInr(itinerary.summary.total_estimated_cost_inr)} estimated{" "}
              {formatPartyGroupLabel(
                itinerary.trip_request.party.adults,
                itinerary.trip_request.party.children,
              )}
            </h2>
            {itinerary.summary.narration !== null && <p>{itinerary.summary.narration}</p>}
            <button type="button" className="secondary-button" onClick={resetItinerary}>
              Plan another trip
            </button>
          </div>

          <DayTabs
            days={itinerary.days}
            activeDayNumber={activeDay.day_number}
            onSelectDay={setActiveDayNumber}
          />

          <div className="day-layout">
            <ItineraryTimeline day={activeDay} />
            <TripMap day={activeDay} />
          </div>

          {itinerary.assumptions.length > 0 && (
            <section className="assumptions" aria-label="Trip assumptions">
              <h3>Good to know (assumptions)</h3>
              <ul>
                {itinerary.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </section>
          )}
        </section>
      )}
    </main>
  );
}

export default App;
