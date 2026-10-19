"""Record a GetMap response body into ``data/MapRT/maps/`` so the simulator can serve it back.

Two sources:

``--from-emulator`` (default)
    Snapshot the synthetic model. This is **circular** — the simulator serving back a map it
    computed — and exists only so the recorded-map code path is exercised by the shipped data and
    a notebook can see ``X-Sim-Map-Source: recorded`` without anyone owning an appliance. Such
    entries are labelled as snapshots in ``index.json``, and the label is not decoration: a
    student who cannot tell invented data from measured data has learnt the wrong thing.

``--from-url``
    Capture a **real** appliance's response. This is the one that matters. The bytes are written
    verbatim, so what the simulator later serves is exactly what the appliance sent. Point it at
    ``data/MapRT/local/maps`` (git-ignored) — a real recording is patient-derived and does not belong
    in a public repository.

    uv run python scripts/record_map.py --from-url https://maprt:5000 --token "$TOKEN" \
        --surface <guid> --room <guid> --out data/MapRT/local/maps
"""

import argparse
import json
from pathlib import Path

from maprt_emulator.mapgen import SurfaceModel, compute_map, map_text
from maprt_emulator.schemas import GetMapRequest


def build_request(args):
    return GetMapRequest.model_validate({
        "PatientSurfaceId": args.surface,
        "TreatmentRoomId": args.room,
        "PatientPosition": args.position,
        "CouchBuffer": args.couch_buffer,
        "PatientBuffer": args.patient_buffer,
        "HighResolution": args.high_resolution,
        "Isocenter": {"x": args.isocenter[0], "y": args.isocenter[1], "z": args.isocenter[2]},
    })


def from_emulator(args, request):
    surface_path = Path(args.data_dir) / "surfaces" / f"{args.surface}.obj"
    if not surface_path.is_file():
        raise SystemExit(f"record_map: no surface mesh at {surface_path}")
    model = SurfaceModel.from_obj_bytes(surface_path.read_bytes(), args.surface)
    couch, gantry, safe = compute_map(model, request, seed=args.seed)
    note = (f"Synthetic snapshot from maprt_emulator.mapgen (seed {args.seed}), NOT a real appliance "
            f"response. {safe.mean():.1%} of angles clear.")
    return map_text(couch, gantry, safe), note


def from_url(args, request):
    import httpx2

    body = request.model_dump(by_alias=True)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {args.token}",
        "User-Agent": "VisionRT.Integration.Saturn/2.0.record-map",
    }
    with httpx2.Client(verify=False, timeout=600.0) as client:
        response = client.post(args.from_url.rstrip("/") + "/integration/GetMap",
                               json=body, headers=headers)
    if response.status_code >= 400:
        raise SystemExit(f"record_map: HTTP {response.status_code}\n{response.text[:400]}")
    text = response.text
    if text.lstrip().startswith("{"):
        # GetMap reports failure as the JSON envelope, not as a map. Saving that as a recording
        # would produce a file that looks fine until something tries to parse it as a map.
        raise SystemExit(f"record_map: the server returned an error envelope, not a map:\n{text}")
    return text, f"Recorded from {args.from_url} on request {body}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--surface", required=True, help="PatientSurfaceId (a GUID)")
    parser.add_argument("--room", required=True, help="TreatmentRoomId (a GUID)")
    parser.add_argument("--position", default="HFS", help="patient position (default HFS)")
    parser.add_argument("--couch-buffer", type=float, default=20.0, help="mm (default 20)")
    parser.add_argument("--patient-buffer", type=float, default=20.0, help="mm (default 20)")
    parser.add_argument("--isocenter", type=float, nargs=3, default=[0.0, 0.0, 0.0],
                        metavar=("X", "Y", "Z"), help="mm, DICOM patient coordinates")
    parser.add_argument("--high-resolution", action="store_true", help="1 degree instead of coarse")
    parser.add_argument("--seed", type=int, default=0, help="--from-emulator only")
    parser.add_argument("--data-dir", default="data/MapRT", help="--from-emulator only")
    parser.add_argument("--from-url", default=None, help="capture from a real appliance instead")
    parser.add_argument("--token", default=None, help="API token, with --from-url")
    parser.add_argument("--out", default="data/MapRT/maps", help="directory to write into")
    parser.add_argument("--name", default=None, help="filename stem (default: generated)")
    args = parser.parse_args(argv)

    if args.from_url and not args.token:
        raise SystemExit("record_map: --from-url needs --token")

    request = build_request(args)
    text, note = (from_url(args, request) if args.from_url
                  else from_emulator(args, request))

    resolution = "high" if args.high_resolution else "low"
    stem = args.name or (f"{args.surface[:8]}_{args.room[:8]}_{args.position.lower()}_"
                         f"cb{args.couch_buffer:g}_pb{args.patient_buffer:g}_{resolution}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    body_path = out_dir / f"{stem}.txt"
    body_path.write_text(text, encoding="utf-8")

    entry = {
        "file": body_path.name,
        "surfaceId": args.surface,
        "roomId": args.room,
        "patientPosition": args.position.upper(),
        "couchBuffer": args.couch_buffer,
        "patientBuffer": args.patient_buffer,
        "isocenter": list(args.isocenter),
        "highResolution": bool(args.high_resolution),
        "note": note,
    }

    index_path = out_dir / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    entries = [e for e in entries if e.get("file") != entry["file"]]
    entries.append(entry)
    index_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    header = text.split("\n", 1)[0]
    print(f"{body_path}: header {header!r}, {len(text) / 1024:,.0f} KB")
    print(f"{index_path}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
