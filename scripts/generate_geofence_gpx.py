#!/usr/bin/env python3
"""
Generate a GPX route that approaches and exits a restaurant geofence.

Use this file in Xcode Run Scheme -> Options -> Default Location
to simulate enter/exit transitions without driving.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path
from typing import Iterable, List, Tuple

EARTH_METERS_PER_DEG_LAT = 111_320.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a GPX route that crosses a geofence boundary."
    )
    parser.add_argument("--restaurant-lat", type=float, required=True, help="Restaurant latitude.")
    parser.add_argument("--restaurant-lon", type=float, required=True, help="Restaurant longitude.")
    parser.add_argument(
        "--enter-radius-m",
        type=float,
        default=150.0,
        help="Geofence entry radius in meters.",
    )
    parser.add_argument(
        "--approach-distance-m",
        type=float,
        default=1200.0,
        help="Starting distance from restaurant in meters.",
    )
    parser.add_argument(
        "--bearing-deg",
        type=float,
        default=35.0,
        help="Approach bearing in degrees (0=north, 90=east).",
    )
    parser.add_argument(
        "--speed-mps",
        type=float,
        default=8.0,
        help="Assumed simulated speed in meters/second.",
    )
    parser.add_argument(
        "--min-segment-seconds",
        type=int,
        default=12,
        help="Minimum time gap between GPX points in seconds.",
    )
    parser.add_argument(
        "--include-exit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include route points that exit geofence on the opposite side.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packages/mobile-ios/ios/AADI/GeofenceTestRoute.gpx"),
        help="Output GPX file path.",
    )
    return parser.parse_args()


def meters_to_delta_lat(meters: float) -> float:
    return meters / EARTH_METERS_PER_DEG_LAT


def meters_to_delta_lon(meters: float, at_lat: float) -> float:
    lat_scale = max(0.2, math.cos(math.radians(at_lat)))
    return meters / (EARTH_METERS_PER_DEG_LAT * lat_scale)


def offset_point(
    center_lat: float, center_lon: float, distance_m: float, bearing_deg: float
) -> Tuple[float, float]:
    radians = math.radians(bearing_deg)
    north_m = math.cos(radians) * distance_m
    east_m = math.sin(radians) * distance_m
    lat = center_lat + meters_to_delta_lat(north_m)
    lon = center_lon + meters_to_delta_lon(east_m, center_lat)
    return lat, lon


def build_signed_distances(
    radius_m: float, outer_distance_m: float, include_exit: bool
) -> List[float]:
    outer = max(outer_distance_m, radius_m * 3.0, 200.0)
    just_outside = radius_m + max(15.0, radius_m * 0.2)
    just_inside = max(5.0, radius_m - max(12.0, radius_m * 0.15))
    near_core = max(5.0, radius_m * 0.25)

    approach = [
        outer,
        outer * 0.7,
        outer * 0.4,
        just_outside,
        just_inside,
        near_core,
        0.0,
    ]
    if not include_exit:
        return approach

    exit_leg = [
        -near_core,
        -just_inside,
        -just_outside,
        -(outer * 0.4),
        -(outer * 0.7),
        -outer,
    ]
    return approach + exit_leg


def signed_distance_to_coord(
    center_lat: float, center_lon: float, signed_distance_m: float, bearing_deg: float
) -> Tuple[float, float]:
    if signed_distance_m >= 0:
        return offset_point(center_lat, center_lon, signed_distance_m, bearing_deg)
    opposite_bearing = (bearing_deg + 180.0) % 360.0
    return offset_point(center_lat, center_lon, abs(signed_distance_m), opposite_bearing)


def with_timestamps(
    signed_distances: Iterable[float], speed_mps: float, min_segment_seconds: int
) -> List[Tuple[float, dt.datetime]]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    points: List[Tuple[float, dt.datetime]] = []
    previous_distance = None
    current_time = now

    for distance in signed_distances:
        if previous_distance is None:
            points.append((distance, current_time))
            previous_distance = distance
            continue

        segment_m = abs(distance - previous_distance)
        transit_s = max(min_segment_seconds, int(round(segment_m / max(speed_mps, 0.5))))
        current_time += dt.timedelta(seconds=transit_s)
        points.append((distance, current_time))
        previous_distance = distance

    return points


def build_gpx(
    restaurant_lat: float,
    restaurant_lon: float,
    bearing_deg: float,
    radius_m: float,
    points_with_time: List[Tuple[float, dt.datetime]],
) -> str:
    boundary_entry_lat, boundary_entry_lon = offset_point(
        restaurant_lat, restaurant_lon, radius_m, bearing_deg
    )
    boundary_exit_lat, boundary_exit_lon = offset_point(
        restaurant_lat, restaurant_lon, radius_m, (bearing_deg + 180.0) % 360.0
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="AADI geofence GPX generator" xmlns="http://www.topografix.com/GPX/1/1">',
        "  <metadata>",
        "    <name>AADI Geofence Simulation Route</name>",
        f"    <time>{points_with_time[0][1].isoformat().replace('+00:00', 'Z')}</time>",
        "  </metadata>",
        f'  <wpt lat="{restaurant_lat:.7f}" lon="{restaurant_lon:.7f}"><name>Restaurant</name></wpt>',
        f'  <wpt lat="{boundary_entry_lat:.7f}" lon="{boundary_entry_lon:.7f}"><name>Enter Boundary</name></wpt>',
        f'  <wpt lat="{boundary_exit_lat:.7f}" lon="{boundary_exit_lon:.7f}"><name>Exit Boundary</name></wpt>',
        "  <trk>",
        "    <name>Approach -> Enter -> Exit</name>",
        "    <trkseg>",
    ]

    for signed_distance, timestamp in points_with_time:
        lat, lon = signed_distance_to_coord(
            restaurant_lat, restaurant_lon, signed_distance, bearing_deg
        )
        time_iso = timestamp.isoformat().replace("+00:00", "Z")
        lines.append(f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}"><time>{time_iso}</time></trkpt>')

    lines.extend(
        [
            "    </trkseg>",
            "  </trk>",
            "</gpx>",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    signed_distances = build_signed_distances(
        radius_m=float(args.enter_radius_m),
        outer_distance_m=float(args.approach_distance_m),
        include_exit=bool(args.include_exit),
    )
    points_with_time = with_timestamps(
        signed_distances,
        speed_mps=float(args.speed_mps),
        min_segment_seconds=int(args.min_segment_seconds),
    )
    gpx = build_gpx(
        restaurant_lat=float(args.restaurant_lat),
        restaurant_lon=float(args.restaurant_lon),
        bearing_deg=float(args.bearing_deg),
        radius_m=float(args.enter_radius_m),
        points_with_time=points_with_time,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gpx, encoding="utf-8")

    print(f"GPX written: {output_path}")
    print("Use in Xcode: Product -> Scheme -> Edit Scheme -> Run -> Options -> Default Location.")


if __name__ == "__main__":
    main()
