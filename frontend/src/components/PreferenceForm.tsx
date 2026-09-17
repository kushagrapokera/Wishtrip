import { useState, type FormEvent } from "react";
import type {
  BudgetLevel,
  DietaryPreference,
  PaceLevel,
  TravellerType,
  TripRequest,
} from "../api/fetchItinerary";

const INTEREST_OPTIONS = [
  "beaches",
  "food",
  "culture",
  "nature",
  "wellness",
  "adventure",
  "nightlife",
] as const;

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const PACE_OPTIONS: { value: PaceLevel; label: string; hint: string }[] = [
  { value: "easy_going", label: "Easy-going", hint: "≈3 stops a day" },
  { value: "balanced", label: "Balanced", hint: "≈4–5 stops a day" },
  { value: "packed", label: "Packed", hint: "≈6 stops a day" },
];

const BUDGET_OPTIONS: { value: BudgetLevel; label: string }[] = [
  { value: "budget", label: "Budget" },
  { value: "mid", label: "Mid" },
  { value: "premium", label: "Premium" },
];

interface PreferenceFormProps {
  onSubmitRequest: (request: TripRequest) => void;
  isSubmitting: boolean;
}

/** Collects the 6 required inputs + diet/mobility; validates like TripRequest. */
export function PreferenceForm({ onSubmitRequest, isSubmitting }: PreferenceFormProps) {
  const [originCity, setOriginCity] = useState("");
  const [startMonth, setStartMonth] = useState("12");
  const [startDate, setStartDate] = useState("");
  const [nights, setNights] = useState("4");
  const [travellerType, setTravellerType] = useState<TravellerType>("couple");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [interests, setInterests] = useState<string[]>(["beaches", "food"]);
  const [pace, setPace] = useState<PaceLevel>("balanced");
  const [budgetLevel, setBudgetLevel] = useState<BudgetLevel>("mid");
  const [dietaryPreference, setDietaryPreference] = useState<DietaryPreference>("none");
  const [needsWheelchairAccess, setNeedsWheelchairAccess] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function toggleInterest(interest: string) {
    setInterests((current) =>
      current.includes(interest)
        ? current.filter((item) => item !== interest)
        : [...current, interest],
    );
  }

  function handleFormSubmit(event: FormEvent) {
    event.preventDefault();
    const parsedNights = Number.parseInt(nights, 10);
    const parsedAdults = Number.parseInt(adults, 10);
    const parsedChildren = Number.parseInt(children, 10);

    if (originCity.trim().length === 0) {
      setFormError("Tell us your origin city so we can plan your arrival day.");
      return;
    }
    if (!Number.isInteger(parsedNights) || parsedNights < 1 || parsedNights > 21) {
      setFormError("Nights must be between 1 and 21.");
      return;
    }
    if (!Number.isInteger(parsedAdults) || parsedAdults < 1 || parsedAdults > 12) {
      setFormError("Adults must be between 1 and 12.");
      return;
    }
    if (!Number.isInteger(parsedChildren) || parsedChildren < 0 || parsedChildren > 8) {
      setFormError("Children must be between 0 and 8.");
      return;
    }
    if (interests.length === 0) {
      setFormError("Pick at least one interest so the plan reflects you.");
      return;
    }
    setFormError(null);
    onSubmitRequest({
      destination: "goa",
      origin_city: originCity.trim(),
      start_date: startDate === "" ? null : startDate,
      start_month: startDate === "" ? Number.parseInt(startMonth, 10) : null,
      nights: parsedNights,
      traveller_type: travellerType,
      party: { adults: parsedAdults, children: parsedChildren },
      interests,
      pace,
      budget_level: budgetLevel,
      dietary_preference: dietaryPreference,
      needs_wheelchair_access: needsWheelchairAccess,
    });
  }

  return (
    <form className="preference-form" onSubmit={handleFormSubmit}>
      <h2>Plan your Goa trip</h2>

      <div className="form-grid">
        <label>
          Destination
          <input type="text" value="Goa, India" disabled title="The prototype covers Goa in depth" />
        </label>
        <label>
          Origin city
          <input
            type="text"
            value={originCity}
            onChange={(event) => setOriginCity(event.target.value)}
            placeholder="e.g. Delhi"
          />
        </label>
        <label>
          Travel month
          <select value={startMonth} onChange={(event) => setStartMonth(event.target.value)}>
            {MONTH_NAMES.map((monthName, index) => (
              <option key={monthName} value={index + 1}>
                {monthName}
              </option>
            ))}
          </select>
        </label>
        <label>
          Exact start date <span className="optional-tag">(optional)</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          Nights (1–21)
          <input
            type="number"
            min={1}
            max={21}
            value={nights}
            onChange={(event) => setNights(event.target.value)}
          />
        </label>
        <label>
          Traveller type
          <select
            value={travellerType}
            onChange={(event) => setTravellerType(event.target.value as TravellerType)}
          >
            <option value="solo">Solo</option>
            <option value="couple">Couple</option>
            <option value="family">Family</option>
            <option value="friends">Friends</option>
            <option value="seniors">Seniors</option>
          </select>
        </label>
        <label>
          Adults (1–12)
          <input
            type="number"
            min={1}
            max={12}
            value={adults}
            onChange={(event) => setAdults(event.target.value)}
          />
        </label>
        <label>
          Children (0–8)
          <input
            type="number"
            min={0}
            max={8}
            value={children}
            onChange={(event) => setChildren(event.target.value)}
          />
        </label>
      </div>

      <fieldset>
        <legend>Interests</legend>
        <div className="chip-row">
          {INTEREST_OPTIONS.map((interest) => (
            <label key={interest} className={interests.includes(interest) ? "chip chip-active" : "chip"}>
              <input
                type="checkbox"
                checked={interests.includes(interest)}
                onChange={() => toggleInterest(interest)}
              />
              {interest}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Pace</legend>
        <div className="chip-row">
          {PACE_OPTIONS.map((option) => (
            <label key={option.value} className={pace === option.value ? "chip chip-active" : "chip"}>
              <input
                type="radio"
                name="pace"
                checked={pace === option.value}
                onChange={() => setPace(option.value)}
              />
              {option.label} <span className="chip-hint">{option.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Budget</legend>
        <div className="chip-row">
          {BUDGET_OPTIONS.map((option) => (
            <label key={option.value} className={budgetLevel === option.value ? "chip chip-active" : "chip"}>
              <input
                type="radio"
                name="budget"
                checked={budgetLevel === option.value}
                onChange={() => setBudgetLevel(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="form-grid">
        <label>
          Dietary preference <span className="optional-tag">(optional)</span>
          <select
            value={dietaryPreference}
            onChange={(event) => setDietaryPreference(event.target.value as DietaryPreference)}
          >
            <option value="none">No preference</option>
            <option value="veg">Vegetarian</option>
            <option value="vegan">Vegan</option>
            <option value="jain">Jain</option>
            <option value="halal">Halal</option>
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={needsWheelchairAccess}
            onChange={(event) => setNeedsWheelchairAccess(event.target.checked)}
          />
          Step-free access needed
        </label>
      </div>

      {formError !== null && <p className="form-error">{formError}</p>}
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Planning your days…" : "Build my itinerary"}
      </button>
    </form>
  );
}
