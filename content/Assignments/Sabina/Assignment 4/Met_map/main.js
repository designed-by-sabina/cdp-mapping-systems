var map = new maplibregl.Map({
  container: "map", // container id
  style: "https://demotiles.maplibre.org/style.json",
  center: [-98, 39],
  zoom: 3,
});

map.addControl(new maplibregl.NavigationControl());

map.on("load", () => {
  map.addSource("ip-locations", {
    type: "geojson",
    data: "../ip_locations.geojson",
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 50,
  });

  map.addLayer({
    id: "clusters",
    type: "circle",
    source: "ip-locations",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": "#ff7800",
      "circle-opacity": 0.7,
      "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 25, 30],
      "circle-stroke-width": 2,
      "circle-stroke-color": "white",
    },
  });

  map.addLayer({
    id: "cluster-count",
    type: "symbol",
    source: "ip-locations",
    filter: ["has", "point_count"],
    layout: {
      "text-field": "{point_count_abbreviated}",
      "text-size": 13,
    },
  });


  map.addLayer({
    id: "ip-locations-layer",
    type: "circle",
    source: "ip-locations",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-radius": 6,
      "circle-stroke-width": 2,
      "circle-color": "#ff7800",
      "circle-stroke-color": "white",
    },
  });


  map.on("click", "clusters", (e) => {
    const features = map.queryRenderedFeatures(e.point, { layers: ["clusters"] });
    const clusterId = features[0].properties.cluster_id;
    map
      .getSource("ip-locations")
      .getClusterExpansionZoom(clusterId)
      .then((zoom) => {
        map.easeTo({ center: features[0].geometry.coordinates, zoom });
      });
  });


  map.on("click", "ip-locations-layer", (e) => {
    const coordinates = e.features[0].geometry.coordinates.slice();
    const { ip, url } = e.features[0].properties;
    new maplibregl.Popup()
      .setLngLat(coordinates)
      .setHTML(`<strong>IP:</strong> ${ip}<br><strong>URL:</strong> ${url}`)
      .addTo(map);
  });

  map.on("mouseenter", "clusters", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "clusters", () => (map.getCanvas().style.cursor = ""));
  map.on("mouseenter", "ip-locations-layer", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "ip-locations-layer", () => (map.getCanvas().style.cursor = ""));
});
