/** Typed client for POST /itineraries — mirrors backend/app/models.py exactly. */

export type PaceLevel = "easy_going" | "balanced" | "packed";
export type BudgetLevel = "budget" | "mid" | "premium";
export type TravellerType = "solo" | "couple" | "family" | "friends" | "seniors";
export type DietaryPreference = "veg" | "vegan" | "jain" | "halal" | "none";

export interface PartyComposition {
  adults: number;
  children: number;
}

export interface TripRequest {
  destination: string;
  origin_city: string;
  start_date: string | null;
  start_month: number | null;
  nights: number;
  traveller_type: TravellerType;
  party: PartyComposition;
  interests: string[];
  pace: PaceLevel;
  budget_level: BudgetLevel;
  dietary_preference: DietaryPreference;
  needs_wheelchair_access: boolean;
}

export interface TravelLeg {
  from_place_id: string | null;
  to_place_id: string;
  travel_minutes: number;
  mode: "walk" | "drive";
}

export interface ScheduledActivity {
  kind: "place" | "meal" | "transfer_note";
  place_id: string | null;
  name: string;
  category: string | null;
  lat: number | null;
  lon: number | null;
  start_time: string;
  end_time: string;
  visit_duration_minutes: number;
  indicative_cost_inr: number | null;
  cost_is_estimate: boolean;
  hours_unverified: boolean;
  why: string;
  travel_leg_before: TravelLeg | null;
}

export interface DayPlan {
  day_number: number;
  date: string | null;
  zone: string;
  theme: string;
  activities: ScheduledActivity[];
  day_travel_minutes_total: number;
  day_cost_inr_estimate: number;
}

export interface ItinerarySummary {
  total_days: number;
  total_estimated_cost_inr: number;
  narration: string | null;
}

export interface Itinerary {
  request_id: string | null;
  trip_request: TripRequest;
  days: DayPlan[];
  summary: ItinerarySummary;
  assumptions: string[];
}

export class ItineraryRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ItineraryRequestError";
    this.status = status;
  }
}

/**
 * Single typed fetch against the contract. Relative URL hits the Vite dev
 * proxy; set VITE_API_URL for a deployed backend (e.g. https://api…).
 */
export async function fetchItinerary(request: TripRequest): Promise<Itinerary> {
  const apiBase = import.meta.env.VITE_API_URL ?? "";
  let response: Response;
  try {
    response = await fetch(`${apiBase}/itineraries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ItineraryRequestError(
      0,
      "Could not reach the trip planner. Is the backend running on port 8000?",
    );
  }
  if (!response.ok) {
    throw new ItineraryRequestError(
      response.status,
      await readErrorDetail(response),
    );
  }
  return (await response.json()) as Itinerary;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.length > 0) {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((entry) => (typeof entry === "object" && entry !== null ? String((entry as { msg?: unknown }).msg ?? "") : ""))
        .filter((message) => message.length > 0);
      if (messages.length > 0) {
        return messages.join("; ");
      }
    }
  } catch {
    // Fall through to the generic message below.
  }
  return `Trip planning failed (HTTP ${response.status}). Try loosening your filters.`;
}
