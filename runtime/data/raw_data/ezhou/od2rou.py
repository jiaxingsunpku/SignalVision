"""
Convert OD JSON to SUMO .rou.xml format.
Step 1: Generate a trips XML using fromJunction/toJunction
Step 2: Run duarouter to compute complete, valid edge routes
- trips are distributed uniformly within each time segment
- BND_JXXX_DIR nodes are mapped to their reference junction JXXX
"""

import json
import random
import subprocess
import sys
import os

NET_FILE = "ezhou.net.xml"
OD_FILE = "od_real_inference_poisson_em_segmented.json"
TRIPS_FILE = "ezhou_trips.xml"
OUT_FILE = "ezhou.rou.xml"

random.seed(42)

VTYPE = (
    '    <vType id="DEFAULT_VEHTYPE" accel="2.6" decel="4.5" sigma="0.5" '
    'length="5.0" minGap="2.5" maxSpeed="33.33" guiShape="passenger"/>\n'
)


def normalize_node_id(node_id):
    """Map BND_JXXX_DIR -> JXXX, keep regular junction IDs as-is."""
    if node_id.startswith("BND_"):
        parts = node_id.split("_")
        return parts[1]
    return node_id


def generate_depart_times(n, start_s, end_s):
    """Generate n uniformly distributed departure times in [start_s, end_s]."""
    times = sorted(random.uniform(start_s, end_s) for _ in range(n))
    return [round(t, 1) for t in times]


def main():
    print("Loading OD data...", flush=True)
    with open(OD_FILE, "r") as f:
        data = json.load(f)
    print("OD data loaded.", flush=True)

    # Collect all trips: (depart_time, from_junction, to_junction)
    trips = []
    total_pairs = sum(len(seg["inferred_od"]) for seg in data["segments"])
    processed = 0
    skipped = 0

    for seg in data["segments"]:
        start_s = seg["start_s"]
        end_s = seg["end_s"]
        label = seg["segment_label"]
        seg_count = 0

        for od in seg["inferred_od"]:
            src_raw = od["origin"]
            dst_raw = od["destination"]
            n_trips = int(round(od["trips"]))

            processed += 1
            if processed % 2000 == 0:
                print(
                    f"  Processed {processed}/{total_pairs} OD pairs, "
                    f"{len(trips)} trips so far",
                    flush=True,
                )

            if n_trips <= 0:
                continue

            src_id = normalize_node_id(src_raw)
            dst_id = normalize_node_id(dst_raw)

            if src_id == dst_id:
                skipped += 1
                continue

            depart_times = generate_depart_times(n_trips, start_s, end_s)
            for t in depart_times:
                trips.append((t, src_id, dst_id))
                seg_count += 1

        print(f"Segment {label}: {seg_count} trips", flush=True)

    # Sort by departure time
    trips.sort(key=lambda v: v[0])
    print(f"\nTotal trips: {len(trips)}, skipped OD pairs: {skipped}", flush=True)

    # Write trips XML
    print(f"Writing {TRIPS_FILE}...", flush=True)
    with open(TRIPS_FILE, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write("<trips>\n")
        f.write(VTYPE)
        for vid, (depart, src, dst) in enumerate(trips):
            f.write(
                f'    <trip id="{vid}" type="DEFAULT_VEHTYPE" depart="{depart}" '
                f'fromJunction="{src}" toJunction="{dst}"/>\n'
            )
        f.write("</trips>\n")
    print(f"{TRIPS_FILE} written.", flush=True)

    # Run duarouter
    print(f"\nRunning duarouter to compute routes...", flush=True)
    cmd = [
        "duarouter",
        "--net-file", NET_FILE,
        "--route-files", TRIPS_FILE,
        "--output-file", OUT_FILE,
        "--junction-taz",           # treat fromJunction/toJunction as TAZ
        "--ignore-errors",          # skip vehicles with no valid route
        "--no-step-log",
        "--no-warnings",
    ]
    print("CMD:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("duarouter stderr:", result.stderr[-3000:], flush=True)
        sys.exit(result.returncode)
    print(f"Done! Routes written to {OUT_FILE}", flush=True)

    # Quick stats
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            lines = f.readlines()
        vehicle_lines = sum(1 for l in lines if "<vehicle" in l)
        print(f"Output vehicles: {vehicle_lines}", flush=True)


if __name__ == "__main__":
    main()
