import { useCallback, useState } from "react";
import {
  fetchItinerary,
  ItineraryRequestError,
  type Itinerary,
  type TripRequest,
} from "../api/fetchItinerary";

export type ItineraryStatus = "idle" | "loading" | "ready" | "error";

/** Owns the form → itinerary request lifecycle; components never fetch directly. */
export function useItinerary() {
  const [status, setStatus] = useState<ItineraryStatus>("idle");
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submitTripRequest = useCallback(async (request: TripRequest) => {
    setStatus("loading");
    setErrorMessage(null);
    try {
      const plannedItinerary = await fetchItinerary(request);
      setItinerary(plannedItinerary);
      setStatus("ready");
    } catch (error) {
      setStatus("error");
      setErrorMessage(
        error instanceof ItineraryRequestError
          ? error.message
          : "Something went wrong while planning your trip.",
      );
    }
  }, []);

  const resetItinerary = useCallback(() => {
    setStatus("idle");
    setItinerary(null);
    setErrorMessage(null);
  }, []);

  return { status, itinerary, errorMessage, submitTripRequest, resetItinerary };
}
