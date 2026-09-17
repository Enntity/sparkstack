"""
SPARKSTACK v2 decorative panels - gothic hive tracery, printed flat.

The design goal is that the panelled tower does not read as "a rack with
accessories clipped on". So the panels are not frames with a pattern inside
them; they are a gothic arcade whose vertical members run the full height of
each panel and line up with the panel above and below. Stack four tiers and the
mullions and lancets continue across every seam, so the seams stop being joints
and become transoms.

Structure of one panel
----------------------
    mullions    vertical members, full height, at a fixed pitch
    arcades     two rows of pointed (ogival) arches between adjacent mullions
    rails       thin horizontal members top and bottom, the bottom one carrying
                the mounting rib
    portal      front panel only: the centre bays merge into one tall opening
                that frames the machine, flanked by lancets
    webbing     organic struts woven through the whole thing, dense at the
                sides, sparse across the front portal so the intake still breathes

Everything is a 2D ribbon extruded to a constant thickness, so the whole panel
prints flat with vertical walls and nothing to support.

The pointed arch is the load-bearing idea, geometrically: two circular arcs
whose radius is set by span and height, meeting at an apex. That is what makes
it read as gothic rather than as a rounded slot.
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #
Q = {
    "T": 4.0,                    # panel thickness (print Z)
    "GAP": 0.6,                  # standoff from the ring's outer face

    "Z0": 2.5, "Z1": 75.0,       # vertical span in tier-local Z (tracks PITCH)
    # The slot in the panel's inner face, which drops over the tier's rail.
    # It has to sit clear of the panel's bottom edge or it is a rebate, not a
    # slot, and the panel just lifts off. Z1 tracks sparkstack's PITCH - ten
    # millimetres came out of the columns for the stacking cables.
    # The hook. Open at the panel's bottom edge, so the panel drops over the
    # rail and hangs on it: located in/out and up/down, and it cannot come
    # off without being lifted. No overhang when printed - the panel's
    # inner face is up, so this is a step in the top surface.
    "RIB_Z0": 3.0, "RIB_Z1": 9.0, "RIB_PROUD": 2.4,

    "FRONT_W": 194.0,
    "SIDE_W": 205.0,

    # --- gothic tracery ---
    # Member sizes set the coverage more than anything else: the first pass at
    # 6.8 mm mullions plus two 7 mm rails came out 67% solid, which is a wall
    # with holes rather than tracery.
    "BAYS": 6,
    "EDGE": 0.5,                 # gap from the panel edge to the outer mullion
    "MULLION_HW": 2.2,           # half-width of a mullion
    "ARCH_HW": 2.0,              # half-width of an arch rib
    "RAIL_BOT": 6.0,             # bottom rail thickness
    "RAIL_TOP": 6.5,             # top rail thickness
    "ARCADE1": (8.0, 40.0),      # (spring height, apex height) lower arcade
    "ARCADE2": (43.0, 74.0),     # upper arcade
    "ARCADE_HW_VAR": 0.7,        # organic swell along the arches
    "PORTAL_APEX": 74.0,

    # --- front portal ---
    # The front is built from the SAME tracery and the SAME web as the sides,
    # at the same density. The only difference is a portal: the mullions inside
    # it are dropped and one wide arch spans it. Twelve bays put a mullion at
    # 18.4 and 175.6 mm, so a portal from bay 1 to bay 11 comes out 157.2 mm
    # wide - a 150 mm machine framed with 3.6 mm of air on each side.
    #
    # The portal arch springs ABOVE the machine's face (10.5..61.7) and peaks at
    # 74, so it arcs over the spark instead of across it. An earlier version
    # sprang it at 8 and the arch swept straight through the gold.
    "BAYS_FRONT": 12,
    "PORTAL_FRONT": (1, 11),
    "PORTAL_SPRING": 63.0,       # just clear of the machine's top edge
    "FRAME_OPEN_TOP": 63.0,      # portal head height
    "FRAME_SILL": 9.0,           # portal sill; the machine's face starts at 10.5
    "FRONT_PAD": 3.0,            # web keep-out margin around the portal
    "RAIL_SEEDS": 14,            # extra web seeds along the top rail
    "CROWN_DRIPS": 13,           # strands hanging over the portal head
    "DRIP_LEN": (7.0, 26.0),     # their length, measured down from the rail
    # Measured on the built mesh, not assumed from these numbers: a 1.62 mm
    # design tip came out of the 0.95 mm voxel remesh as a 1.10 mm shank, which
    # is under three extrusion widths and thin enough to snap in a hand. These
    # numbers are set so the BUILT drip clears ~1.8 mm.
    "DRIP_ROOT": 2.4, "DRIP_TIP": 1.30,
    "COWL_LOBE_FRONT": 0.30,

    # --- funnel ---
    # Printed flat, the panel's THICKNESS is the build direction, so a rise in
    # thickness is an upward-facing slope - no overhang, no support, no matter
    # how steep. The front's opening gets a trumpet that gathers air into the
    # machine's intake bands; the sides get a gentler pillow so the shell swells
    # out of the structure rather than sitting on it.
    "COWL_FRONT": 9.0,
    "COWL_SIDE": 5.0,
    "COWL_SCALE": 16.0,          # how fast the throat flares away from the lip
    "COWL_SCALE_SIDE": 58.0,     # the sides swell as one broad dome instead
    "COWL_LOBES": 9,             # hive lobes around the throat
    "COWL_LOBE_AMT": 0.22,

    # --- organic webbing ---
    "SPACING": 32.0,
    "SPACING_FRONT": 22.0,
    "JITTER": 7.5,
    "LINK_MAX": 42.0,
    "LINK_N": 3,
    "HW_NODE": 2.3,
    "HW_MID": 0.95,
    "BORDER_HW": 2.4,
    "BORDER_HW_VAR": 1.0,

    "VOXEL": 0.95,
    "FLATTEN": 1.10,             # snap the bed face flat within this height; 0 disables
    "SEED": 11,
}

RING_HALF = 98.0                 # ring outer half-width, from sparkstack.py


# --------------------------------------------------------------------------- #
# gothic geometry
# --------------------------------------------------------------------------- #
def ogive_path(x0, x1, y0, apex_y, n=20):
    """Centreline of an arch from (x0, y0) to (x1, y0) with its apex at apex_y.

    Two circular arcs, each radius r = (a^2 + h^2) / 2a where a is the half-span
    and h the rise. r > a gives a lancet; r == a gives an equilateral arch.

    That construction puts each arc's centre ON the springing line, which is
    what makes the arch pointed - but it only holds while the rise is at least
    the half-span. A shallower arch forces r < a, the centre ends up inboard of
    the apex, and reaching the apex means sweeping up over the top of the arc's
    own circle: the front's portal arch (rise 11.6, half-span 78.6) came out
    peaking 28 mm above where it was asked to, taking the panel to 103 mm tall
    instead of 82.5. Shallow arches therefore fall back to a plain circular
    segment with its centre on the vertical axis.
    """
    a = (x1 - x0) / 2.0
    cx = (x0 + x1) / 2.0
    hh = apex_y - y0
    if a <= 1e-6 or hh <= 1e-6:
        return [Vector((x0, y0)), Vector((x1, y0))]

    if hh < a:                                   # segmental, not pointed
        r = (a * a + hh * hh) / (2.0 * hh)
        cy = y0 + hh - r
        lo, hi = math.atan2(r - hh, -a), math.atan2(r - hh, a)
        return [Vector((cx + r * math.cos(lo + (hi - lo) * i / float(2 * n)),
                        cy + r * math.sin(lo + (hi - lo) * i / float(2 * n))))
                for i in range(2 * n + 1)]

    r = (a * a + hh * hh) / (2.0 * a)
    pts = []
    clx, cly = x0 + r, y0
    aL = math.atan2(hh, cx - clx)
    for i in range(n + 1):
        t = math.pi + (aL - math.pi) * (i / float(n))
        pts.append(Vector((clx + r * math.cos(t), cly + r * math.sin(t))))

    crx, cry = x1 - r, y0
    aR = math.atan2(hh, cx - crx)
    for i in range(1, n + 1):
        t = aR + (0.0 - aR) * (i / float(n))
        pts.append(Vector((crx + r * math.cos(t), cry + r * math.sin(t))))
    return pts


def mullion_x(width, bays):
    """x centreline of each mullion, outermost ones flush with the panel edges."""
    lo = Q["EDGE"] + Q["MULLION_HW"]
    hi = width - Q["EDGE"] - Q["MULLION_HW"]
    return [lo + (hi - lo) * i / float(bays) for i in range(bays + 1)]


# --------------------------------------------------------------------------- #
# mesh helpers
# --------------------------------------------------------------------------- #
def _mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return me


def prism(name, profile, z0, z1):
    n = len(profile)
    v = [(p[0], p[1], z0) for p in profile] + [(p[0], p[1], z1) for p in profile]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return _mesh(name, v, f)


def ribbon(name, pts, halfw, z0, z1):
    """Closed prism swept along a polyline with a per-point half-width."""
    left, right = [], []
    n = len(pts)
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        if t.length < 1e-9:
            t = Vector((1.0, 0.0))
        t.normalize()
        nrm = Vector((-t.y, t.x))
        left.append(pts[i] + nrm * halfw[i])
        right.append(pts[i] - nrm * halfw[i])
    outline = left + list(reversed(right))
    return prism(name, [(p.x, p.y) for p in outline], z0, z1)


def box(name, lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
         (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return _mesh(name, v, f)


def merge(meshes, name):
    verts, faces = [], []
    for me in meshes:
        base = len(verts)
        verts += [tuple(v.co) for v in me.vertices]
        faces += [tuple(i + base for i in p.vertices) for p in me.polygons]
    return _mesh(name, verts, faces)


def cut(obj, tool, coll):
    """Subtract `tool` from obj in place."""
    t = bpy.data.objects.new("_tool", tool)
    coll.objects.link(t)
    mod = obj.modifiers.new("cut", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = t
    mod.solver = 'EXACT'
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    me.name = obj.name
    obj.modifiers.clear()
    obj.data = me
    bpy.data.objects.remove(t, do_unlink=True)
    return obj


def panel_slot(width):
    """The channel in the panel's inner face that drops over the tier's rail.

    Printed flat, the panel's inner face is UP, so this is an open channel in
    the top surface - no overhang anywhere. That is the whole point of moving
    the location feature off the tier: the same slot cut into the tier's
    vertical wall has a flat ceiling, and with ABS/ASA at near-zero part cooling
    that ceiling strings and never cures.
    """
    d = Q["RIB_PROUD"]
    return box("slot", (Q["EDGE"] + 2.0, Q["RIB_Z0"] - Q["Z0"] - 1.0, Q["T"] - d),
               (width - Q["EDGE"] - 2.0, Q["RIB_Z1"] - Q["Z0"], Q["T"] + 1.0))


def remesh(obj, voxel):
    mod = obj.modifiers.new("remesh", 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    mod.use_smooth_shade = True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    me.name = obj.name
    obj.modifiers.clear()
    old = obj.data
    obj.data = me
    bpy.data.meshes.remove(old)
    return obj


def _flatten_bottom(obj, tol=None):
    """Snap the bed face dead flat.

    Voxel fusing leaves the bottom a stair-step within about half a voxel of
    nominal, which shows up as shallow depressions that have nothing under them.
    They are laterally supported so they would print, but a first layer wants a
    genuinely flat face, so anything within tolerance goes to zero.
    """
    tol = Q["FLATTEN"] if tol is None else tol
    if tol <= 0:
        return obj
    me = obj.data
    for v in me.vertices:
        if v.co.z < tol:
            v.co.z = 0.0
    me.update()
    return obj


def _cleanup(obj, dist=0.0008):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Drop specks. Where two members graze each other the voxel fuse can leave a
    # tiny island of a handful of verts floating a few tenths off the surface -
    # small enough to miss by eye, large enough to fail a single-shell check and
    # to make a slicer report a stray region.
    bm.verts.ensure_lookup_table()
    seen, groups = set(), []
    for v in bm.verts:
        if v in seen:
            continue
        stack, grp = [v], []
        seen.add(v)
        while stack:
            c = stack.pop()
            grp.append(c)
            for e in c.link_edges:
                w = e.other_vert(c)
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        groups.append(grp)

    dropped = 0
    if len(groups) > 1:
        groups.sort(key=len, reverse=True)
        keep = max(24, int(len(bm.verts) * 0.002))
        for grp in groups[1:]:
            if len(grp) < keep:
                bmesh.ops.delete(bm, geom=grp, context='VERTS')
                dropped += 1

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    obj["dropped_specks"] = dropped
    return obj


def new_object(name, mesh, coll):
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


# --------------------------------------------------------------------------- #
# organic webbing
# --------------------------------------------------------------------------- #
def bezier(p0, p1, bow, n):
    d = p1 - p0
    mid = (p0 + p1) * 0.5
    nrm = Vector((-d.y, d.x))
    if nrm.length > 1e-9:
        nrm.normalize()
    ctrl = mid + nrm * bow
    return [p0 * (1 - t) ** 2 + ctrl * (2 * (1 - t) * t) + p1 * t * t
            for t in (i / (n - 1.0) for i in range(n))]


def strut_halfwidths(n):
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        out.append(Q["HW_NODE"] + (Q["HW_MID"] - Q["HW_NODE"]) * math.sin(math.pi * t) ** 0.7)
    return out


def _inside(rect, x, y, pad=0.0):
    x0, y0, x1, y1 = rect
    return (x0 - pad) <= x <= (x1 + pad) and (y0 - pad) <= y <= (y1 + pad)


def _connect(nodes, n_free):
    """Nearest-neighbour links, then force the graph to be ONE component."""
    cand = set()
    for i in range(n_free):
        near = sorted(((nodes[k] - nodes[i]).length, k)
                      for k in range(len(nodes)) if k != i)
        for d, k in near[:Q["LINK_N"]]:
            if d <= Q["LINK_MAX"]:
                cand.add((min(i, k), max(i, k)))
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i, k in cand:
        union(i, k)
    for _ in range(len(nodes)):
        comps = {}
        for i in range(len(nodes)):
            comps.setdefault(find(i), []).append(i)
        if len(comps) <= 1:
            break
        groups = sorted(comps.values(), key=len, reverse=True)
        main = set(groups[0])
        best = None
        for grp in groups[1:]:
            for i in grp:
                for j in main:
                    d = (nodes[i] - nodes[j]).length
                    if best is None or d < best[0]:
                        best = (d, i, j)
            if best:
                cand.add((min(best[1], best[2]), max(best[1], best[2])))
                union(best[1], best[2])
                break
        else:
            break
    return cand


def web_struts(width, height, anchors, opening=None, spacing=None, seed=0, pad=12.0,
               mask=None):
    """Jittered nodes joined to their nearest neighbours, tied into the tracery.

    `pad` is the keep-out margin around `opening`. It matters more than it looks:
    at 12 mm the front's 19.5 mm jambs and 13.5 mm crown fell entirely inside the
    keep-out and got no webbing at all, which is why the frame read as bare.
    """
    rng = random.Random(seed)
    sp = spacing or Q["SPACING"]
    cols = max(2, int(round(width / sp)))
    rows = max(2, int(round(height / sp)))
    margin = Q["BORDER_HW"] + Q["BORDER_HW_VAR"] + 2.0

    nodes = []
    for i in range(cols):
        for j in range(rows):
            x = (i + 0.5) * width / cols + rng.uniform(-Q["JITTER"], Q["JITTER"])
            y = (j + 0.5) * height / rows + rng.uniform(-Q["JITTER"], Q["JITTER"])
            x = min(max(x, margin), width - margin)
            y = min(max(y, margin), height - margin)
            if mask is not None:
                if mask(x, y):
                    continue
            elif opening and _inside(opening, x, y, pad):
                continue
            nodes.append(Vector((x, y)))
    n_free = len(nodes)
    nodes += anchors                      # tracery centrelines become web anchors

    links = _connect(nodes, n_free)
    struts = []
    for i, k in sorted(links):
        a, b = nodes[i], nodes[k]
        d = (b - a).length
        if d < 1e-6:
            continue
        pts = bezier(a, b, rng.uniform(-0.16, 0.16) * d, 11)
        if mask is not None:
            if mask((a.x + b.x) / 2, (a.y + b.y) / 2, 3.0):
                continue
        elif opening and _inside(opening, (a.x + b.x) / 2, (a.y + b.y) / 2, 4.0):
            continue
        struts.append((pts, strut_halfwidths(11)))
    return struts


# --------------------------------------------------------------------------- #
# tracery
# --------------------------------------------------------------------------- #
def arch_specs(bays, opening=None, seed=0):
    """(mullion index A, mullion index B, spring, apex) for every arch to draw."""
    out = []
    rows = (Q["ARCADE1"], Q["ARCADE2"])
    if opening is None:
        for spring, apex in rows:
            for i in range(bays):
                out.append((i, i + 1, spring, apex))
    else:
        i0, i1 = opening
        for spring, apex in rows:
            for i in range(bays):
                if i >= i0 and i + 1 <= i1:
                    continue               # swallowed by the portal
                out.append((i, i + 1, spring, apex))
        # The portal arch is the front's one big repeated motif, so it is the
        # one thing that must NOT repeat: a stack of four identical arches
        # reads as a stamped part. Spring and apex wander a couple of mm per
        # seed, which is enough to break the rhyme without crowding the machine
        # (its face tops out at 61.5) or the top rail.
        r = random.Random(seed * 7919 + 13)
        out.append((i0, i1, Q["PORTAL_SPRING"] + r.uniform(-1.8, 1.4),
                    Q["PORTAL_APEX"] + r.uniform(-2.4, 3.0)))
    return out


def build_tracery(width, height, bays, opening=None, seed=0, arches=True):
    """Rails, mullions and arches. Returns (meshes, anchor points for the web).

    """
    rng = random.Random(seed + 4242)
    xs = mullion_x(width, bays)
    parts, anchors = [], []

    def emit(name, pts, hw):
        parts.append(ribbon(name, pts, hw, 0.0, Q["T"]))

    skip = set()
    if opening:
        i0, i1 = opening
        skip = set(range(i0 + 1, i1))      # only the portal's jambs survive

    for i, x in enumerate(xs):
        if i in skip:
            continue
        y0, y1 = Q["EDGE"] + Q["MULLION_HW"], height - Q["EDGE"] - Q["MULLION_HW"]
        pts = [Vector((x, y0)), Vector((x, (y0 + y1) / 2)), Vector((x, y1))]
        hw = []
        for k in range(3):
            hw.append(Q["MULLION_HW"] + 0.5 * math.sin(seed * 1.7 + i * 2.1 + k))
        emit("mull%d" % i, pts, hw)
        anchors += [Vector((x, y)) for y in (y0 + 4, (y0 + y1) / 2, y1 - 4)]

    for name, yc, thick in (("railb", Q["RAIL_BOT"] / 2.0 + Q["EDGE"], Q["RAIL_BOT"]),
                            ("railt", height - Q["RAIL_TOP"] / 2.0 - Q["EDGE"], Q["RAIL_TOP"])):
        pts = [Vector((Q["EDGE"] + Q["MULLION_HW"], yc)),
               Vector((width / 2.0, yc)),
               Vector((width - Q["EDGE"] - Q["MULLION_HW"], yc))]
        emit(name, pts, [thick / 2.0] * 3)
        anchors += [Vector((width * f, yc)) for f in (0.2, 0.4, 0.6, 0.8)]

    specs = arch_specs(bays, opening, seed)
    if not arches:
        # Keep only the portal. The front's jamb slots are 15.7 mm wide, and an
        # ogive rising 32 mm inside a slot that narrow has its ribs all but
        # touching the mullions either side - the "arch" fills the slot instead
        # of making a void, which is what left the front a solid slab with a
        # row of near-identical holes in it.
        specs = [sp for sp in specs if opening and (sp[0], sp[1]) == tuple(opening)]

    for n, (ia, ib, spring, apex) in enumerate(specs):
        pts = ogive_path(xs[ia], xs[ib], spring, apex)
        hw = [Q["ARCH_HW"] + Q["ARCADE_HW_VAR"]
              * math.sin(seed * 1.3 + n * 1.9 + i * 0.35) * (1.0 if n else 1.7)
              for i in range(len(pts))]
        emit("arch%d" % n, pts, hw)
        anchors += [pts[k] for k in range(0, len(pts), 4)]
    return parts, anchors


# --------------------------------------------------------------------------- #
# panel
# --------------------------------------------------------------------------- #
def _funnel(obj, width, height, amt, opening=None, scale=None, seed=0,
            lobe_amt=None):
    """Sculpt the outer face into an organic throat.

    Printed flat, thickness IS the build direction, so any rise in thickness is
    an upward-facing slope: no overhang, no support, however deep it gets. That
    makes a real funnel free.

    Around the front's opening the face swells away from the lip, so the frame
    gathers air toward the machine's intake bands instead of standing in front
    of them. The sides swell as one broad dome. Both carry hive lobes around
    the throat so they read as grown rather than turned.

    Only the OUTER face moves. The inner face stays on z=0, so the mounting rib
    and the fit in the ring groove are untouched.
    """
    me = obj.data
    top = Q["T"]
    lobes = Q["COWL_LOBES"]
    lamt = Q["COWL_LOBE_AMT"] if lobe_amt is None else lobe_amt
    phase = (seed % 7) * 0.73

    if opening:
        scale = scale or Q["COWL_SCALE"]
        cx = (opening[0] + opening[2]) / 2.0
        cy = (opening[1] + opening[3]) / 2.0
    else:
        scale = scale or Q["COWL_SCALE_SIDE"]
        cx, cy = width / 2.0, height / 2.0

    for v in me.vertices:
        if v.co.z < top * 0.5:
            continue                        # inner face and rib stay flat
        if opening:
            dx = max(opening[0] - v.co.x, 0.0, v.co.x - opening[2])
            dy = max(opening[1] - v.co.y, 0.0, v.co.y - opening[3])
            d = math.hypot(dx, dy)
            base = 1.0 - math.exp(-d / scale)
        else:
            d = math.hypot(v.co.x - cx, v.co.y - cy)
            base = math.exp(-(d / scale) ** 1.15)
        ang = math.atan2(v.co.y - cy, v.co.x - cx)
        lobe = 1.0 + lamt * math.sin(lobes * ang + phase)
        v.co.z = top + amt * base * lobe
    me.update()
    return obj


def build_front(name, width, coll, seed=0):
    """The side panel's construction, with a portal cut to frame the machine.

    Same tracery, same web spacing, same funnel language - the only difference
    is `opening`, which drops the mullions inside the portal bays and springs a
    single wide arch over the top. Everything about the front that used to be
    bespoke (its own frame, its own webbing density, clipped members, a solid
    backing over the corner columns) is gone; it is now the side panel with a
    hole in the middle, which is what makes it match.
    """
    height = Q["Z1"] - Q["Z0"]
    bays = Q["BAYS_FRONT"]
    i0, i1 = Q["PORTAL_FRONT"]
    xs = mullion_x(width, bays)
    opening = (xs[i0], Q["FRAME_SILL"], xs[i1], Q["FRAME_OPEN_TOP"])

    parts, anchors = build_tracery(width, height, bays, (i0, i1), seed,
                                    arches=False)

    # Overhanging web in the crown. The web's node grid runs at SPACING 32 mm,
    # so over a crown band this shallow it lands barely one row - and the portal
    # keep-out eats most of that row, which left the band above the arch as
    # empty sky over the machine.
    #
    # Seeding that band directly does not work: the only route from a cluster
    # floating there back to the rest of the panel crosses the portal, and
    # web_struts culls any strut whose midpoint falls inside the opening, so
    # the cluster ends up detached. The strands are therefore hung from the top
    # rail itself, which makes them connected by construction, and they taper to
    # a point as they descend over the opening.
    crng = random.Random(seed + 2027)
    for _ in range(Q["RAIL_SEEDS"]):
        anchors.append(Vector((crng.uniform(7.0, width - 7.0),
                               height - Q["EDGE"] - Q["MULLION_HW"]
                               + crng.uniform(-2.5, 1.5))))

    for k in range(Q["CROWN_DRIPS"]):
        x0 = crng.uniform(8.0, width - 8.0)
        y_top = height - Q["EDGE"] - Q["MULLION_HW"]
        y_end = y_top - crng.uniform(*Q["DRIP_LEN"])
        sway, ph, n = crng.uniform(-8.0, 8.0), crng.uniform(0.0, 6.283), 11
        pts, hw = [], []
        for j in range(n):
            t = j / (n - 1.0)
            pts.append(Vector((x0 + sway * math.sin(ph + t * 2.6) * t,
                               y_top - (y_top - y_end) * t)))
            hw.append(Q["HW_MID"] * (Q["DRIP_ROOT"]
                                     - (Q["DRIP_ROOT"] - Q["DRIP_TIP"]) * t))
        parts.append(ribbon("drip%d" % k, pts, hw, 0.0, Q["T"]))
    for i, (pts, halfw) in enumerate(web_struts(width, height, anchors, opening,
                                                Q["SPACING"], seed,
                                                pad=Q["FRONT_PAD"])):
        parts.append(ribbon(f"w{i}", pts, halfw, 0.0, Q["T"]))


    obj = new_object(name, merge(parts, name), coll)
    # No funnel - see the note in build_panel. It drove the inner face inboard
    # of the ring's outer face, so the panel could not be fitted at all.
    off = Vector((Q["VOXEL"] * 0.37, Q["VOXEL"] * 0.41, Q["VOXEL"] * 0.53))
    obj.data.transform(Matrix.Translation(off))
    remesh(obj, Q["VOXEL"])
    obj.data.transform(Matrix.Translation(-off))
    cut(obj, panel_slot(width), coll)
    _flatten_bottom(obj)
    return _cleanup(obj)


def build_panel(name, width, opening=None, opening_bays=None, seed=0, coll=None):
    """Returns a flat panel object: local X = width, Y = height, Z = thickness."""
    height = Q["Z1"] - Q["Z0"]
    parts, anchors = build_tracery(width, height, Q["BAYS"], opening_bays, seed)

    spacing = Q["SPACING_FRONT"] if opening_bays else Q["SPACING"]
    for i, (pts, halfw) in enumerate(web_struts(width, height, anchors, opening,
                                                spacing, seed)):
        parts.append(ribbon(f"w{i}", pts, halfw, 0.0, Q["T"]))


    obj = new_object(name, merge(parts, name), coll)
    # Every member's bottom face lies exactly on z=0, which is also a voxel grid
    # plane, and the isosurface degenerates there into non-manifold pinches.
    # Shifting the mesh a fraction of a voxel off the grid clears it, and the
    # shift is undone afterwards so the part still sits on z=0.
    off = Vector((Q["VOXEL"] * 0.37, Q["VOXEL"] * 0.41, Q["VOXEL"] * 0.53))
    obj.data.transform(Matrix.Translation(off))
    remesh(obj, Q["VOXEL"])
    obj.data.transform(Matrix.Translation(-off))
    cut(obj, panel_slot(width), coll)
    _flatten_bottom(obj)
    return _cleanup(obj)


def basis(ex, ey, ez):
    return Matrix(((ex[0], ey[0], ez[0]),
                   (ex[1], ey[1], ez[1]),
                   (ex[2], ey[2], ez[2]))).to_4x4()


def place_front(obj, z, width):
    """Flat panel -> vertical. Local z=0 is the OUTER face - the one that lies
    flat on the bed - and local +Z runs inward, toward the machine."""
    obj.matrix_world = (Matrix.Translation((0.0, -(RING_HALF + Q["GAP"] + Q["T"]), z))
                        @ basis((1, 0, 0), (0, 0, 1), (0, 1, 0))
                        @ Matrix.Translation((-width / 2.0, 0.0, 0.0)))
    return obj


def place_side(obj, side, z, width):
    """Same convention: local z=0 outward, +Z inward toward the machine."""
    obj.matrix_world = (Matrix.Translation((side * (RING_HALF + Q["GAP"] + Q["T"]), 0.0, z))
                        @ basis((0, side, 0), (0, 0, 1), (-side, 0, 0))
                        @ Matrix.Translation((-width / 2.0, 0.0, 0.0)))
    return obj


def build_all(coll, tiers=1):
    """One front and two side panels PER TIER, each in its own ring groove."""
    import sparkstack as SS
    base_t, pitch = SS.P["BASE_T"], SS.P["PITCH"]

    out = []
    for i in range(tiers):
        z = base_t + i * pitch + Q["Z0"]
        # Each tier's front gets its own seed. Four identical fronts stacked
        # read as a repeating unit, which is the one thing the whole hive
        # language is trying to avoid. All ten seeds 11..74 build as a single
        # printable shell.
        f = build_front(f"panel_front_T{i+1}", Q["FRONT_W"], coll,
                        seed=Q["SEED"] + 7 * i)
        out.append(place_front(f, z, Q["FRONT_W"]))
        for side in (-1, 1):
            p = build_panel(f"panel_side_{'R' if side > 0 else 'L'}_T{i+1}",
                            Q["SIDE_W"], seed=Q["SEED"] + side, coll=coll)
            out.append(place_side(p, side, z, Q["SIDE_W"]))
    return out


def export_panels(objs, outdir, version="2.0"):
    os.makedirs(outdir, exist_ok=True)
    tag = "v" + version.replace(".", "_")
    rows = []
    for o in objs:
        saved = o.matrix_world.copy()
        o.matrix_world = Matrix.Identity(4)
        bpy.context.view_layer.update()
        path = os.path.join(outdir, f"sparkstack_{tag}_{o.name}.stl")
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        try:
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True,
                                  global_scale=1.0)
        except AttributeError:
            bpy.ops.export_mesh.stl(filepath=path, use_selection=True, global_scale=1.0)
        o.matrix_world = saved
        rows.append((path, os.path.getsize(path)))
    return rows


def report(objs):
    print("\n=== PANELS ===")
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        dx = max(v.x for v in bb) - min(v.x for v in bb)
        dy = max(v.y for v in bb) - min(v.y for v in bb)
        dz = max(v.z for v in bb) - min(v.z for v in bb)
        print(f"  {o.name:22s} {dx:6.1f} x {dy:6.1f} x {dz:6.1f} mm  "
              f"{len(me.loop_triangles):6d} tris")
