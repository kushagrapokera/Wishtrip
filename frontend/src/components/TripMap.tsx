import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DayPlan } from "../api/fetchItinerary";
import { escapeHtml } from "../itineraryFormat";

interface TripMapProps {
  day: DayPlan;
}

function numberedIcon(stopNumber: number, kind: string): L.DivIcon {
  return L.divIcon({
    className: `map-marker map-marker-${kind}`,
    html: `<span>${stopNumber}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

/** Leaflet map: numbered markers in route order with the day's path. */
export function TripMap({ day }: TripMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.FeatureGroup | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    const map = L.map(container).setView([15.45, 73.9], 10);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    markersRef.current = L.featureGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const markers = markersRef.current;
    if (map === null || markers === null) {
      return;
    }
    markers.clearLayers();
    const mappedStops = day.activities.filter(
      (activity) => activity.lat !== null && activity.lon !== null,
    );
    if (mappedStops.length === 0) {
      return;
    }
    const routePoints: L.LatLngExpression[] = [];
    mappedStops.forEach((activity, index) => {
      const point: L.LatLngExpression = [activity.lat as number, activity.lon as number];
      routePoints.push(point);
      L.marker(point, { icon: numberedIcon(index + 1, activity.kind) })
        .bindPopup(`<strong>${index + 1}. ${escapeHtml(activity.name)}</strong><br/>${activity.start_time}–${activity.end_time}`)
        .addTo(markers);
    });
    if (routePoints.length > 1) {
      L.polyline(routePoints, { weight: 3, opacity: 0.6 }).addTo(markers);
    }
    map.fitBounds(markers.getBounds().pad(0.2), { maxZoom: 14 });
  }, [day]);

  return (
    <section className="trip-map" aria-label={`Map for day ${day.day_number}`}>
      <div ref={containerRef} className="map-container" />
      <p className="map-caption">
        Numbered stops follow the day&apos;s route order; the line is the visit sequence.
      </p>
    </section>
  );
}
