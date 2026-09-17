/** Display formatting for itinerary values — no planning logic here. */

export function formatCostInr(amountInr: number | null): string {
  if (amountInr === null || amountInr === undefined) {
    return "Cost n/a";
  }
  return `₹${amountInr.toLocaleString("en-IN")}`;
}

export function formatTravelLeg(travelMinutes: number, mode: string): string {
  return `${travelMinutes} min ${mode} from the previous stop`;
}

export function formatDayCost(dayCostInr: number, dayTravelMinutes: number): string {
  return `${formatCostInr(dayCostInr)} · ${dayTravelMinutes} min on the move`;
}

/**
 * Escape text for insertion into Leaflet popup HTML. Place names come from
 * OpenStreetMap and must never be treated as trusted markup.
 */
export function escapeHtml(rawText: string): string {
  return rawText
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
