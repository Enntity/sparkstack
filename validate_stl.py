#!/usr/bin/env python3
"""Validate exported STLs: parse, bounds, and watertightness.

Reading the files back is the point. A mesh can be manifold in Blender and still
export badly, so this checks the artefact that actually goes to the slicer.
"""

import glob
import os
import struct
import sys
from collections import defaultdict


def read_stl(path):
    with open(path, "rb") as fh:
        head = fh.read(84)
        if len(head) < 84:
            raise ValueError("file too short for binary STL")
        count = struct.unpack("<I", head[80:84])[0]
        expect = 84 + count * 50
        size = os.path.getsize(path)
        if size != expect:
            raise ValueError(f"size {size} != expected {expect} for {count} triangles")
        tris = []
        for _ in range(count):
            rec = fh.read(50)
            vals = struct.unpack("<12fH", rec)
            tris.append(((vals[3], vals[4], vals[5]),
                         (vals[6], vals[7], vals[8]),
                         (vals[9], vals[10], vals[11])))
    return tris


def check(path):
    tris = read_stl(path)
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]

    # watertight: every directed edge must have exactly one opposite twin
    edges = defaultdict(int)
    for a, b, c in tris:
        for p, q in ((a, b), (b, c), (c, a)):
            edges[(p, q)] += 1
    unmatched = sum(1 for (p, q), n in edges.items() if edges.get((q, p), 0) != n)
    degenerate = sum(1 for t in tris if len(set(t)) < 3)

    # Connectivity. Edge pairing alone passes a mesh made of several separate
    # closed shells - which is exactly what a slicer calls a floating island.
    # Union-find triangles through shared edges.
    parent = list(range(len(tris)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    owner = {}
    for ti, (a, b, c) in enumerate(tris):
        for p, q in ((a, b), (b, c), (c, a)):
            key = (p, q) if p <= q else (q, p)
            if key in owner:
                union(ti, owner[key])
            else:
                owner[key] = ti
    comps = len({find(i) for i in range(len(tris))})

    return {
        "tris": len(tris),
        "size": (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)),
        "unmatched_edges": unmatched,
        "degenerate": degenerate,
        "components": comps,
    }


def main(patterns):
    """Accept one or many arguments. It used to read argv[1] only, so
    `validate_stl.py stl/*.stl` quietly checked a single file and reported
    "1/1 files valid" - which looks like a pass."""
    if isinstance(patterns, str):
        patterns = [patterns]
    files = []
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if not hits and os.path.exists(pat):
            hits = [pat]                      # an explicit path, not a glob
        files.extend(hits)
    files = sorted(set(files))
    if not files:
        print("no files matched %s" % ", ".join(patterns))
        return 1
    print(f"{'file':40s} {'tris':>8s} {'size (mm)':>24s} {'closed':>7s} {'shells':>7s}")
    bad = 0
    for path in files:
        try:
            r = check(path)
        except Exception as exc:
            print(f"{os.path.basename(path):40s}  FAILED: {exc}")
            bad += 1
            continue
        dx, dy, dz = r["size"]
        ok = (r["unmatched_edges"] == 0 and r["degenerate"] == 0
              and r["components"] == 1)
        bad += 0 if ok else 1
        print(f"{os.path.basename(path):40s} {r['tris']:8d} "
              f"{dx:7.1f} x{dy:6.1f} x{dz:5.1f}  "
              f"{'yes' if r['unmatched_edges'] == 0 and r['degenerate'] == 0 else 'NO':>7s} "
              f"{r['components']:7d}")
        if not ok:
            why = []
            if r["unmatched_edges"]:
                why.append(f"{r['unmatched_edges']} unmatched edges")
            if r["degenerate"]:
                why.append(f"{r['degenerate']} degenerate tris")
            if r["components"] != 1:
                why.append(f"{r['components']} SEPARATE SHELLS - slicer will call "
                           f"the extras floating islands")
            print(f"{'':40s}   -> " + "; ".join(why))
    print(f"\n{len(files) - bad}/{len(files)} files valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] if len(sys.argv) > 1 else ["stl/*.stl"]))
