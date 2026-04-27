import "maplibre-gl/dist/maplibre-gl.css";
import { LngLatBounds } from "maplibre-gl";
import { useCallback, useRef } from "react";
import MapGL, {
  Layer,
  type MapRef,
  NavigationControl,
  Source,
} from "react-map-gl/maplibre";
import type { ScannerEvent } from "../lib/types";

const LA_CENTER = { longitude: -118.35, latitude: 34.05 };
const LA_BOUNDS: [[number, number], [number, number]] = [
  [-118.67, 33.7],
  [-118.15, 34.35],
];

interface Props {
  events: ScannerEvent[];
  onEventClick?: (event: ScannerEvent) => void;
}

function eventsToGeoJSON(events: ScannerEvent[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: events.map((e) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [e.longitude, e.latitude],
      },
      properties: {
        feed_id: e.feed_id,
        event_ts: e.event_ts,
        normalized: e.normalized,
        confidence: e.confidence,
      },
    })),
  };
}

export default function Map({ events, onEventClick }: Props) {
  const mapRef = useRef<MapRef>(null);

  const fitAll = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    if (events.length === 0) {
      map.fitBounds(LA_BOUNDS, { padding: 40 });
      return;
    }
    const bounds = new LngLatBounds();
    for (const e of events) {
      bounds.extend([e.longitude, e.latitude]);
    }
    map.fitBounds(bounds, { padding: 60, maxZoom: 14 });
  }, [events]);

  const handleClick = useCallback(
    (e: maplibregl.MapLayerMouseEvent) => {
      if (!onEventClick || !e.features?.length) return;
      const props = e.features[0]?.properties;
      if (!props) return;
      const event = events.find(
        (ev) =>
          ev.event_ts === props.event_ts && ev.normalized === props.normalized,
      );
      if (event) onEventClick(event);
    },
    [events, onEventClick],
  );

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{
        ...LA_CENTER,
        zoom: 11,
      }}
      style={{ width: "100%", height: "100%" }}
      mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
      onClick={handleClick}
      interactiveLayerIds={["events-unclustered"]}
      pitchWithRotate={false}
      cursor="default"
    >
      <NavigationControl position="bottom-right" showCompass={false} />

      <div className="maplibregl-ctrl maplibregl-ctrl-group absolute right-[10px] bottom-[125px] z-10">
          <button
            onClick={fitAll}
            title={events.length > 0 ? "Fit all events" : "Show LA County"}
            type="button"
            className="maplibregl-ctrl-icon"
            style={{
              width: 29,
              height: 29,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              backgroundImage: "none",
            }}
          >
            <svg width="17" height="17" fill="none" stroke="#333" viewBox="0 0 24 24" strokeWidth={2.5} style={{ filter: "invert(0.85)" }}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4h4M20 8V4h-4M4 16v4h4M20 16v4h-4" />
            </svg>
          </button>
      </div>

      <Source
        id="events"
        type="geojson"
        data={eventsToGeoJSON(events)}
        cluster={true}
        clusterMaxZoom={14}
        clusterRadius={50}
      >
        <Layer
          id="events-clusters"
          type="circle"
          filter={["has", "point_count"]}
          paint={{
            "circle-color": [
              "step",
              ["get", "point_count"],
              "#b38030",
              10,
              "#9a6e28",
              50,
              "#7d5a20",
            ],
            "circle-radius": [
              "step",
              ["get", "point_count"],
              16,
              10,
              24,
              50,
              32,
            ],
            "circle-opacity": 0.85,
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "rgba(179, 128, 48, 0.2)",
          }}
        />

        <Layer
          id="events-cluster-count"
          type="symbol"
          filter={["has", "point_count"]}
          layout={{
            "text-field": "{point_count_abbreviated}",
            "text-size": 11,
            "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          }}
          paint={{
            "text-color": "#e6edf3",
          }}
        />

        <Layer
          id="events-unclustered"
          type="circle"
          filter={["!", ["has", "point_count"]]}
          paint={{
            "circle-color": "#e5534b",
            "circle-radius": 5,
            "circle-stroke-width": 1,
            "circle-stroke-color": "rgba(229, 83, 75, 0.25)",
            "circle-opacity": 0.9,
          }}
        />

      </Source>
    </MapGL>
  );
}
