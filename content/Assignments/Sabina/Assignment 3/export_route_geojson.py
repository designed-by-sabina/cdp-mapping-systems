"""Recompute the Central Park network route (same logic as the Assignment 3
notebook, Part 2) and export it as a single ordered GeoJSON LineString,
plus the ordered attraction points, for use in the restaurants-on-route
web map."""

import json

import geopandas as gpd
import numpy as np
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import substring

gdf = gpd.read_file("Central_Park_Tourist_Attractions.geojson")
start_label = "Central Park Entry"
assert gdf.loc[0, "label"] == start_label

gdf_proj = gdf.to_crs(epsg=32618)
coords = np.column_stack([gdf_proj.geometry.x, gdf_proj.geometry.y])
n = len(coords)
dist = np.zeros((n, n))
for i in range(n):
    for j in range(n):
        dist[i, j] = np.linalg.norm(coords[i] - coords[j])


def nearest_neighbor_route(dist, start=0):
    n = dist.shape[0]
    path = [start]
    remaining = set(range(n)) - {start}
    total_distance = 0.0
    current = start
    while remaining:
        next_point = min(remaining, key=lambda j: dist[current, j])
        total_distance += dist[current, next_point]
        path.append(next_point)
        remaining.remove(next_point)
        current = next_point
    return path, total_distance


def two_opt(path, dist, max_passes=100):
    path = list(path)
    n = len(path)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = path[i - 1], path[i]
                c = path[j]
                d = path[j + 1] if j + 1 < n else None
                old_cost = dist[a, b] + (dist[c, d] if d is not None else 0)
                new_cost = dist[a, c] + (dist[b, d] if d is not None else 0)
                if new_cost < old_cost - 1e-9:
                    path[i : j + 1] = path[i : j + 1][::-1]
                    improved = True
    total_distance = sum(dist[path[k], path[k + 1]] for k in range(n - 1))
    return path, total_distance


nn_path, _ = nearest_neighbor_route(dist, start=0)
path, total_distance = two_opt(nn_path, dist)

outline_gdf = gpd.read_file("Central_Park_Outline.geojson")
west, south, east, north = outline_gdf.total_bounds
bbox = (west, south, east, north)

park_network = ox.graph_from_bbox(bbox, network_type="walk")


def snap_point_to_graph(G, point, node_id):
    u, v, k = ox.distance.nearest_edges(G, point.x, point.y)
    edge_geom = G.edges[u, v, k].get(
        "geometry",
        LineString(
            [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
        ),
    )
    frac = edge_geom.project(point, normalized=True)
    snapped_pt = edge_geom.interpolate(frac, normalized=True)
    G.add_node(node_id, x=snapped_pt.x, y=snapped_pt.y)

    def split_edge(a, b, key):
        if not G.has_edge(a, b, key):
            return
        data = dict(G.edges[a, b, key])
        geom = data.get(
            "geometry",
            LineString(
                [(G.nodes[a]["x"], G.nodes[a]["y"]), (G.nodes[b]["x"], G.nodes[b]["y"])]
            ),
        )
        f = geom.project(point, normalized=True)
        base_len = data.get("length", geom.length)
        G.remove_edge(a, b, key)
        first_half = dict(
            data, geometry=substring(geom, 0, f, normalized=True), length=base_len * f
        )
        second_half = dict(
            data,
            geometry=substring(geom, f, 1, normalized=True),
            length=base_len * (1 - f),
        )
        G.add_edge(a, node_id, key, **first_half)
        G.add_edge(node_id, b, key, **second_half)

    split_edge(u, v, k)
    split_edge(v, u, k)


gdf["node"] = [f"attraction_{i}" for i in gdf.index]
for i, row in gdf.iterrows():
    snap_point_to_graph(park_network, row.geometry, row["node"])

nodes = gdf["node"].tolist()
n = len(nodes)
net_dist = np.zeros((n, n))
for i in range(n):
    for j in range(n):
        if i == j:
            continue
        try:
            net_dist[i, j] = nx.shortest_path_length(
                park_network, nodes[i], nodes[j], weight="length"
            )
        except nx.NetworkXNoPath:
            net_dist[i, j] = np.inf

net_nn_path, _ = nearest_neighbor_route(net_dist, start=0)
net_path, net_total_distance = two_opt(net_nn_path, net_dist)

leg_gdfs = []
for start_node, end_node in zip(
    [nodes[i] for i in net_path[:-1]], [nodes[i] for i in net_path[1:]]
):
    route = nx.shortest_path(park_network, start_node, end_node, weight="length")
    leg_gdf = ox.routing.route_to_gdf(park_network, route)
    leg_gdfs.append(leg_gdf)

network_route_gdf = gpd.GeoDataFrame(
    pd.concat(leg_gdfs, ignore_index=True), crs=park_network.graph["crs"]
)

# Merge all leg geometries, in order, into one continuous LineString.
coords_out = []
for geom in network_route_gdf.geometry:
    pts = list(geom.coords)
    if coords_out and coords_out[-1] == pts[0]:
        pts = pts[1:]
    coords_out.extend(pts)

route_line = LineString(coords_out)
route_feature_collection = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "Central Park Attractions Network Route",
                "total_distance_m": net_total_distance,
                "total_distance_mi": net_total_distance / 1609.34,
            },
            "geometry": json.loads(gpd.GeoSeries([route_line], crs=network_route_gdf.crs).to_json())[
                "features"
            ][0]["geometry"],
        }
    ],
}

ordered_gdf = gdf.loc[net_path].reset_index(drop=True)
attractions_out = json.loads(ordered_gdf[["label", "geometry"]].to_json())
for i, feat in enumerate(attractions_out["features"]):
    feat["properties"]["order"] = i

out_dir = r"C:\Users\Sabri\Documents\GitHub\mapping_website_restaurants-on-route"
with open(f"{out_dir}\\central_park_route.geojson", "w") as f:
    json.dump(route_feature_collection, f)
with open(f"{out_dir}\\central_park_attractions_ordered.geojson", "w") as f:
    json.dump(attractions_out, f)

print("Route length (mi):", net_total_distance / 1609.34)
print("Wrote central_park_route.geojson and central_park_attractions_ordered.geojson")
