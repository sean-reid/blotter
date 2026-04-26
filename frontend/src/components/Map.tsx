import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useRef } from "react";
import MapGL, {
  Layer,
  type MapRef,
  NavigationControl,
  Source,
} from "react-map-gl/maplibre";
import type { ScannerEvent } from "../lib/types";

const SCC_CENTER = { longitude: -121.9, latitude: 37.35 };

interface Props {
  events: ScannerEvent[];
  onBoundsChange?: (bounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  }) => void;
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

export default function Map({ events, onBoundsChange, onEventClick }: Props) {
  const mapRef = useRef<MapRef>(null);

  const handleMoveEnd = useCallback(() => {
    const map = mapRef.current;
    if (!map || !onBoundsChange) return;
    const b = map.getBounds();
    onBoundsChange({
      west: b.getWest(),
      south: b.getSouth(),
      east: b.getEast(),
      north: b.getNorth(),
    });
  }, [onBoundsChange]);

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
        ...SCC_CENTER,
        zoom: 11,
      }}
      style={{ width: "100%", height: "100%" }}
      mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
      onMoveEnd={handleMoveEnd}
      onClick={handleClick}
      interactiveLayerIds={["events-unclustered"]}
      pitchWithRotate={false}
      cursor="default"
    >
      <NavigationControl position="top-right" showCompass={false} />

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
              "#6366f1",
              10,
              "#818cf8",
              50,
              "#a5b4fc",
            ],
            "circle-radius": [
              "step",
              ["get", "point_count"],
              18,
              10,
              26,
              50,
              34,
            ],
            "circle-opacity": 0.85,
            "circle-stroke-width": 2,
            "circle-stroke-color": "rgba(99, 102, 241, 0.3)",
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
            "text-color": "#ffffff",
          }}
        />

        <Layer
          id="events-unclustered"
          type="circle"
          filter={["!", ["has", "point_count"]]}
          paint={{
            "circle-color": "#f43f5e",
            "circle-radius": 6,
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "rgba(244, 63, 94, 0.35)",
            "circle-opacity": 0.9,
          }}
        />

      </Source>
    </MapGL>
  );
}
