"""
SPARKSTACK v4 - a modular, stackable, printable rack for the NVIDIA DGX Spark.

Design constraints (sourced, not guessed)
-----------------------------------------
* Device: 150 x 150 x 50.5 mm, 1.2 kg, 240 W external brick.
  [NVIDIA DGX Spark User Guide - Hardware Overview]
* Air INTAKE is on the front face (upper + lower) and the underside; both are
  dust-filtered. Exhaust leaves through the rear heatsink fins and the QSFP fin
  stack. Two Delta NS8CC50 fans move front+bottom -> rear.  [ChargerLAB teardown]
* Sustained load: 87-88 C CPU / 80-82 C GPU. Ambient ceiling 30 C.  [StorageReview]

v4 changes
----------
1. ONE PART PER TIER. v3 built a tier from two side frames, which is why the
   corners never read as joined. A tier is now a single printable ring with four
   corner posts, so the corners are genuinely one continuous piece.
2. A real joint. v3's 6 mm spigot on a 10 mm post was decorative. The tenon is
   now 11 mm across and 11 mm deep - roughly a third of the post's height - into
   a matching socket, with vertical crush ribs for grip and an optional M3
   cross-hole so a joint can be positively pinned.
3. Sized for the load. Posts back up to 16 mm, pads to 16 mm, so a 1.2 kg
   machine is not sitting on four 12 mm pucks.
4. Base widened to 205 mm, sized for a 4-high stack.

Tiers are identical and interchangeable: print 1, 2, 3 or 4 of them.

Units: 1 Blender unit = 1 mm.
"""

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

VERSION = "3.0"

# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #
P = {
    "DEV_W": 150.0, "DEV_D": 150.0, "DEV_H": 51.2,

    "POST": 16.0, "POST_R": 6.0,
    # ABS/ASA shrink ~0.6%, and the chassis does not. 1.5 mm keeps real
    # clearance after shrinkage even with no slicer compensation.
    "SIDE_CLEAR": 1.5,
    # 76, down from 86. The stacking cables are short and the stack has to
    # fit them; this costs 10 mm of the rising air gap per tier. Watch
    # the thermals if you push the machines hard.
    "PITCH": 76.0,                      # one tier: device + rising air gap

    # PAD_D must stay a touch SMALLER than 2*ARM_R, not merely equal to it.
    # The arm is swept as a closed polygon, so its end cap is INSCRIBED: at 10
    # segments its edges cut inside radius 7.61, while a 36-segment pad still
    # reaches 7.97. Equal radii therefore left a ~0.4 mm ring of pad hanging
    # over air at z=7 - a genuine floating cantilever, and exactly what a slicer
    # flags. 15 mm keeps the pad strictly inside the arm's faceted cap.
    "ARM_R": 8.0, "ARM_T": 8.0, "ARM_SEG": 16,
    "PAD_D": 14.0, "PAD_H": 5.0, "PAD_C": 68.0,
    # 45-degree chamfer on the pad's top edge. A soft/smooth pad, with
    # nothing overhanging: a rounded-over edge droops, a chamfer cannot.
    "PAD_CHAMFER": 1.5,

    # --- corner cradle ---
    # The round pad alone gave the chassis nothing to sit AGAINST, so a nudge
    # walked it off the pads. The cradle puts a hard face on each of the
    # chassis's two sides at every corner. It is keyed off DEV_W/2, which is
    # known exactly, rather than off the corner radius, which is not - so the
    # fit does not depend on guessing the chassis's corner.
    #
    # The upper wall is deliberately much thinner than its root. That makes it
    # a ~2 N/wall cantilever: light enough to push the chassis past the lip by
    # hand (8 walls, ~9 N total), and lightly stressed enough that ABS does not
    # creep away at 50 C chamber. A stiff wall with the same lip would need
    # ~100 N to seat and would creep.
    # Bevel on the tier body. The cradles are unioned in AFTER this bevel is
    # applied, so the width is free again - at 1.1 mm against an un-beveled
    # 1.2 mm cradle wall the bevel ate the walls and left 52 non-manifold edges.
    "TIER_SOFTEN": 1.1,
    # Round-over on the cradles' vertical edges - the ones you see looking at
    # the front of the machine. Capped by cradle_bevel_limit(): a bevel wider
    # than half the wall eats the flat between the two rolled edges.
    "CRADLE_SOFTEN": 1.0,
    # 1.0 mm modelled, not 0.25. ASA shrinks about 0.6%, which over a 150 mm
    # opening is 0.45 mm per side: a 0.25 mm gap prints as a 0.20 mm
    # INTERFERENCE and the Spark will not go in. This is the same reasoning as
    # SIDE_CLEAR below, and 1.0 leaves ~0.55 mm of real clearance per side
    # whether or not the slicer compensates for shrinkage.
    "CRADLE_CLR": 1.0,       # gap from the chassis side to the wall face
    # The wall lives in the 1.5 mm slot between the chassis side (75.0) and the
    # post's inner face (76.5). Sizing it to fill that slot exactly puts a
    # coplanar face against the post and breaks the boolean, so it stops 0.05 mm
    # short and is braced by the arm instead.
    "CRADLE_WALL": 2.5,      # room for a real round-over on the top edge
    "CRADLE_LEN": 22.0,      # how far each wall runs inboard from the corner
    "CRADLE_H": 6.0,         # wall height above the seat; a stop, not a fence
    # Sized off CRADLE_CLR: the tip sits at 75.4 mm modelled, which prints at
    # about 74.95 against a 75.0 chassis side - a light kiss, not a clamp.
    "SNAP_PROUD": 0.60,      # lip reach past the wall face
    "SNAP_Z": 2.0,           # lip height above the seat
    "SNAP_H": 2.6,           # lip height

    # The ring is a rounded square minus a MUCH rounder inner cutout. That makes
    # the sides slim (12 mm) while the corners stay chunky enough to carry the
    # post and its 11.7 mm socket - and it costs about half the plastic of a
    # constant-width band.
    "RING": 196.0, "RING_R": 12.0, "RING_T": 10.0,
    "RING_IN": 168.0, "RING_IN_R": 30.0, "RING_FILLET": 3.0,

    # The joint. The male half is a straight shank with a lead-in chamfer; the
    # female half is a straight bore closed by a 45-degree CONE rather than a
    # flat roof. A flat roof is an unsupported bridge, and that is the other
    # thing slicers report as a floating cantilever.
    "TENON": 11.0, "TENON_R": 3.5, "TENON_H": 11.0, "TENON_CHAMFER": 1.2,
    # The joint is a friction fit and has to hold a stack up on its own; the
    # pins are insurance, not structure. It was neither: JOINT_CLR left 0.35 mm
    # per side, and the crush ribs only reached a half-width of 5.80 against a
    # half-bore of 5.85 - they did not touch the bore at all, so there was no
    # friction anywhere in the joint. Now the bore is 5.65 and the ribs reach
    # 5.75, giving 0.10 mm of interference per side over four ribs and a 7 mm
    # band. Both halves are the same material, so shrinkage moves them together
    # and the fit is unchanged after printing.
    "JOINT_CLR": 0.15,
    "SOCKET_STRAIGHT": 12.0, "SOCKET_TIP": 0.4,
    "RIB": 0.25, "RIB_W": 1.6, "RIB_H": 7.0,
    "PIN_D": 3.4,                        # optional M3 / printed pin cross-hole
    "PIN_Z": 5.5,                        # height of the socket-side pin hole

    # BASE_R is set so the base is proud of the tier's FOOT by the same amount
    # all the way round. At 30 the base's corner pulled in to 93.7 while the
    # tier's ring+rail corner reaches 95.9 - the tier overhung the base by
    # 2.2 mm at every corner, and 3.15 mm measured on the built meshes, while
    # the base stuck out 2.5 mm along the sides. A 14 mm corner radius makes
    # the margin uniform: 102.5 - 0.2929*14 = 98.40 against the tier's 95.90.
    # It also matches the tier's own foot radius, RING_R + RAIL_PROUD = 14.
    "BASE": 205.0, "BASE_R": 14.0, "BASE_T": 10.0,
    "BASE_IN": 168.0, "BASE_IN_R": 30.0,
    "BASE_FILLET": 3.0,

    "CAP": 196.0, "CAP_R": 12.0, "CAP_IN": 168.0, "CAP_IN_R": 30.0,
    "CAP_FILLET": 2.0,

    # front-edge marking, cut into the outer face of the cap.
    # Stroke width is measured at build time (see mark_stroke) rather than
    # guessed: an engraved groove under ~0.8 mm turns to mush at a 0.4 mm
    # nozzle. Arial Black is the boldest face on the system and lands near
    # 1.9 mm here, which is comfortably printable.
    "WORDMARK": "SparkStack",
    "FONT_CANDIDATES": (
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ),
    "MARK_H": 11.5, "LOGO_H": 11.5, "MARK_GAP": 7.0,
    "DEBOSS": 0.7,
    "MIN_STROKE": 0.85,

    "FOOT_D": 14.0, "FOOT_H": 2.5,
    "SEG": 9,

    # Decorative panel mount: one continuous groove around the ring's outer
    # face. Continuous rather than front-and-sides only, so a back panel is a
    # print away rather than a redesign. The panel carries a matching rib on
    # its inner face and drops straight in.
    #
    # OFF by default: v1 is the plain rack. Flip this to True to build the v2
    # tier that takes panels.
    "PANEL_GROOVE": False,
    # Band lies inside the ring, which is only 10 mm tall at the tier's foot.
    # A rail that poked above it would leave a 2 mm ledge underneath - the
    # very overhang this was meant to remove.
    "GROOVE_Z0": 3.0, "GROOVE_Z1": 9.0,
    "RAIL_PROUD": 2.0,       # rail standing off the ring for the panels
    "GROOVE_DEPTH": 2.5,     # kept: sparkstack_panels sizes its groove off this
}

POST_C = (P["DEV_W"] / 2.0) + P["SIDE_CLEAR"] + (P["POST"] / 2.0)   # 84.0
POST_OUT = POST_C + (P["POST"] / 2.0)                                # 92.0
SOCKET = P["TENON"] + 2 * P["JOINT_CLR"]                             # 11.7
SOCKET_CONE_H = (SOCKET - P["SOCKET_TIP"]) / 2.0                     # 45-degree roof
SOCKET_H = P["SOCKET_STRAIGHT"] + SOCKET_CONE_H
CAP_T = SOCKET_H + 3.0


def _span(a, b):
    return (min(a, b), max(a, b))


# --------------------------------------------------------------------------- #
# geometry helpers - raw data, no bpy.ops, so nothing depends on UI context
# --------------------------------------------------------------------------- #
def _mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    # Winding flips when a primitive is mirrored for the -X/-Y side, and an
    # inside-out solid makes the EXACT boolean solver delete what it touches.
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return me


def box_mesh(name, lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
         (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return _mesh(name, v, f)


def cyl_mesh(name, cx, cy, z0, z1, r, seg=36):
    v, f = [], []
    for z in (z0, z1):
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            v.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, seg + j, seg + i))
    f.append(tuple(range(seg - 1, -1, -1)))
    f.append(tuple(range(seg, 2 * seg)))
    return _mesh(name, v, f)


def cyl_x_mesh(name, cy, cz, x0, x1, r, seg=20):
    """Cylinder along X - used for the cross-holes."""
    v, f = [], []
    for x in (x0, x1):
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            v.append((x, cy + r * math.cos(a), cz + r * math.sin(a)))
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, seg + j, seg + i))
    f.append(tuple(range(seg - 1, -1, -1)))
    f.append(tuple(range(seg, 2 * seg)))
    return _mesh(name, v, f)


def rrect_profile(x0, y0, x1, y1, r, seg=7):
    r = max(0.01, min(r, (x1 - x0) / 2.0 - 1e-4, (y1 - y0) / 2.0 - 1e-4))
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -math.pi / 2),
                       (x1 - r, y1 - r, 0.0),
                       (x0 + r, y1 - r, math.pi / 2),
                       (x0 + r, y0 + r, math.pi)):
        for i in range(seg + 1):
            a = a0 + (math.pi / 2.0) * i / seg
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def cone_mesh(name, cx, cy, z0, z1, r0, r1, seg=36):
    """Tapered cylinder. Used for pad chamfers, which must be self-supporting."""
    v, f = [], []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        v.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a), z0))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        v.append((cx + r1 * math.cos(a), cy + r1 * math.sin(a), z1))
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, seg + j, seg + i))
    f.append(tuple(range(seg - 1, -1, -1)))
    f.append(tuple(range(seg, 2 * seg)))
    return _mesh(name, v, f)


def prism_mesh(name, profile, z0, z1):
    n = len(profile)
    v = [(px, py, z0) for px, py in profile] + [(px, py, z1) for px, py in profile]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return _mesh(name, v, f)


def rrect_mesh(name, x0, y0, x1, y1, z0, z1, r, seg=7):
    return prism_mesh(name, rrect_profile(x0, y0, x1, y1, r, seg), z0, z1)


def capsule_profile(p0, p1, r, seg=10):
    """Stadium outline from p0 to p1, with a semicircular cap at each end.

    The cap angle must start at the perpendicular whose half-plane CONTAINS the
    axis. `atan2(-uy, ux)` is 90 degrees off that: it puts each cap on the
    inward-facing side, so the capsule is truncated at both ends and never
    extends r past them. That silently left the pads resting on air.
    """
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    a0 = math.atan2(-ux, uy)
    pts = []
    for i in range(seg + 1):
        a = a0 + math.pi * i / seg
        pts.append((x1 + r * math.cos(a), y1 + r * math.sin(a)))
    for i in range(seg + 1):
        a = a0 + math.pi + math.pi * i / seg
        pts.append((x0 + r * math.cos(a), y0 + r * math.sin(a)))
    return pts


def capsule_mesh(name, p0, p1, r, z0, z1, seg=10):
    return prism_mesh(name, capsule_profile(p0, p1, r, seg), z0, z1)


def loft_profiles(name, prof_a, z_a, prof_b, z_b):
    """Bridge two profiles with the same vertex count - a tapered prism."""
    n = len(prof_a)
    v = [(p[0], p[1], z_a) for p in prof_a] + [(p[0], p[1], z_b) for p in prof_b]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return _mesh(name, v, f)


def centred_profile(cx, cy, size, r, seg=6):
    h = size / 2.0
    return rrect_profile(cx - h, cy - h, cx + h, cy + h, r, seg)


def teardrop_x_mesh(name, cy, cz, x0, x1, r, seg=12):
    """A hole running along X with a 45-degree point on top.

    A round horizontal hole is a bridge with nothing under it, and ABS/ASA has
    no part cooling to freeze it, so the roof droops. A teardrop is
    self-supporting.
    """
    prof = []
    for i in range(seg + 1):
        a = math.pi + math.pi * i / seg
        prof.append((cy + r * math.cos(a), cz + r * math.sin(a)))
    prof.append((cy, cz + r))
    n = len(prof)
    v = [(x0, py, pz) for py, pz in prof] + [(x1, py, pz) for py, pz in prof]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return _mesh(name, v, f)


def new_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def bake_seq(name, ops, collection, material=None):
    made = [new_object(f"_o{i}", m, collection) for i, (m, _) in enumerate(ops)]
    base = made[0]
    for o, (_, op) in zip(made[1:], ops[1:]):
        mod = base.modifiers.new(op, 'BOOLEAN')
        mod.operation = 'UNION' if op == 'u' else 'DIFFERENCE'
        mod.object, mod.solver = o, 'EXACT'

    dg = bpy.context.evaluated_depsgraph_get()
    flat = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    flat.name = name
    for o in made:
        bpy.data.objects.remove(o, do_unlink=True)

    obj = new_object(name, flat, collection)
    if material:
        obj.data.materials.append(material)
    return obj


def fillet_rims(obj, width, segments=4):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    sel = [e for e in bm.edges
           if len(e.link_faces) == 2 and abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-4]
    if sel:
        bmesh.ops.bevel(bm, geom=sel, offset=width, segments=segments,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def cleanup(obj, dist=0.003):
    """Merge coincident verts, drop zero-area faces and zero-length edges.

    `dist` is set above the solver's own sliver size, but not just above it:
    the tier's second bake leaves vertex pairs a micron or two apart, and
    merging at 1.2 or 1.5 microns is WORSE than not merging at all - it splits
    faces and leaves hundreds of boundary edges. Measured across both tiers,
    0.8 microns gives 0/4, 1.2 gives 422/392, 1.5 gives 116/63, and 3 microns
    gives 0/0. Still four orders of magnitude below any real feature.

    The EXACT boolean solver leaves sliver triangles wherever cuts graze a
    surface. Slicers usually ignore them, but they fail a strict watertight
    check, so they are removed before anything is exported.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges)
    # Wire edges - edges with no face on either side. The solver leaves a few
    # wherever a cut grazes an arc; they carry no geometry but they do make the
    # mesh non-manifold, and a strict watertight check counts them.
    wires = [e for e in bm.edges if not e.link_faces]
    if wires:
        bmesh.ops.delete(bm, geom=wires, context='EDGES')
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def soften(obj, width=1.2, segments=3, angle_limit=math.radians(28)):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    sel = [e for e in bm.edges
           if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > angle_limit]
    if sel:
        bmesh.ops.bevel(bm, geom=sel, offset=width, segments=segments,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def roll_top(obj, z, width, segments=4, tol=0.06):
    """Round over just the edges sitting at height z.

    soften() bevels every edge it can find, then clamps hard against the snap
    lip only 0.25 mm away - measured, that cut a 1.0 mm round-over down to
    0.10 mm, which is why the cradles still read square from the front. Turning
    clamping off would let the lip, which is 0.8 mm thick, intersect itself.

    So this selects the top edge loop only and bevels that with clamping off.
    The top edge is the one that matters: it is the edge whose 90 degrees lies
    in a VERTICAL plane, which is the one you see occluding the front of the
    machine. The plan stays square, because nothing in plan is touched.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    sel = [e for e in bm.edges
           if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(28)
           and abs(e.verts[0].co.z - z) < tol and abs(e.verts[1].co.z - z) < tol]
    if sel:
        bmesh.ops.bevel(bm, geom=sel, offset=width, segments=segments,
                        profile=0.5, affect='EDGES', clamp_overlap=False)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def tenon_solids(cx, cy, z0, z1):
    """Male half: a straight shank with a lead-in chamfer, plus crush ribs."""
    size, r = P["TENON"], P["TENON_R"]
    ch = min(P["TENON_CHAMFER"], (z1 - z0) * 0.35)
    out = [prism_mesh("shank", centred_profile(cx, cy, size, r), z0, z1 - ch),
           loft_profiles("lead", centred_profile(cx, cy, size, r), z1 - ch,
                         centred_profile(cx, cy, size - 2 * ch, max(r - ch, 0.6)), z1)]

    t = P["TENON"] / 2.0
    w, d = P["RIB_W"] / 2.0, P["RIB"]
    zr0, zr1 = z0 + 1.5, z0 + 1.5 + P["RIB_H"]
    out.append(box_mesh("rib", (cx + t - 0.6, cy - w, zr0), (cx + t + d, cy + w, zr1)))
    out.append(box_mesh("rib", (cx - t - d, cy - w, zr0), (cx - t + 0.6, cy + w, zr1)))
    out.append(box_mesh("rib", (cx - w, cy + t - 0.6, zr0), (cx + w, cy + t + d, zr1)))
    out.append(box_mesh("rib", (cx - w, cy - t - d, zr0), (cx + w, cy - t + 0.6, zr1)))
    return out


def socket_solids(cx, cy, z0):
    """Female half: a straight bore closed by a 45-degree cone.

    A flat roof over a blind socket is an unsupported bridge, and that is what a
    slicer reports as a floating cantilever. A cone needs no support, and it
    centres the tenon on the way in. The cone stops just shy of a true point to
    avoid degenerate geometry - a 0.4 mm cap is one extrusion width.
    """
    r = P["TENON_R"] + P["JOINT_CLR"]
    tip = P["SOCKET_TIP"]
    straight = P["SOCKET_STRAIGHT"]
    return [prism_mesh("bore", centred_profile(cx, cy, SOCKET, r), z0, z0 + straight),
            loft_profiles("roof", centred_profile(cx, cy, SOCKET, r), z0 + straight,
                          centred_profile(cx, cy, tip, tip / 2.0),
                          z0 + straight + SOCKET_CONE_H)]


# --------------------------------------------------------------------------- #
# materials
# --------------------------------------------------------------------------- #
def material(name, color, metallic=0.0, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        for key, val in (("Base Color", (*color, 1.0)),
                         ("Metallic", metallic), ("Roughness", roughness)):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = val
    m.diffuse_color = (*color, 1.0)
    m.metallic = metallic
    m.roughness = roughness
    return m


def build_materials():
    return {
        "body": material("stack_body", (0.055, 0.058, 0.065), 0.15, 0.55),
        "accent": material("stack_accent", (0.36, 0.63, 0.02), 0.0, 0.42),
        "device": material("device_placeholder", (0.62, 0.52, 0.34), 0.85, 0.26),
    }


# --------------------------------------------------------------------------- #
# parts
# --------------------------------------------------------------------------- #
def _square_l(face, th, lo):
    """Plan outline of the L wall - square everywhere.

    The corner fit is square because the footprint it fits IS square: the
    chassis's sides meet at a corner and the cradle has to match them. Nothing
    in plan is rounded. The round-over that keeps 90 degree edges out of the
    front view goes on the wall's top and end edges instead, which is what
    soften() puts there.
    """
    hi = face + th
    return [(face, face), (lo, face), (lo, hi), (hi, hi), (hi, lo), (face, lo)]


def cradle_bevel_limit():
    """Widest round-over a wall this thick can take and still have a flat face."""
    return P["CRADLE_WALL"] / 2.5


def cradle_solids(sx, sy):
    """Locating walls + snap lip around the chassis corner at (sx, sy)."""
    half = P["DEV_W"] / 2.0
    face = half + P["CRADLE_CLR"]
    th = P["CRADLE_WALL"]
    lo = half - P["CRADLE_LEN"]
    seat = P["ARM_T"] + P["PAD_H"]
    ztop = seat + P["CRADLE_H"]

    def mir(pts):
        if sx * sy < 0:
            pts = pts[::-1]
        return [(sx * px, sy * py) for px, py in pts]

    # No snap lip. It was a 0.6 mm ledge hanging over open air at z=15 - four
    # downward-facing faces, one per corner, and precisely the kind of overhang
    # that strings and stays uncured in ABS/ASA with no part cooling. It bought
    # a little friction against lift and nothing else, so it is gone and the
    # cradle is now a plain wall with nothing overhanging anywhere.
    return [prism_mesh("cradle", mir(_square_l(face, th, lo)), 0.0, ztop)]


def ring_solids(half, r, t, inner_half, inner_r):
    """Rounded square minus a rounder inner cutout: slim sides, chunky corners."""
    return [
        (rrect_mesh("outer", -half, -half, half, half, 0.0, t, r, P["SEG"]), 'u'),
        (rrect_mesh("inner", -inner_half, -inner_half, inner_half, inner_half,
                    -1.0, t + 1.0, inner_r, P["SEG"]), 'd'),
    ]


def build_tier(coll, mats):
    """ONE part: ring + four corner posts + pad arms + joint features.

    This is the whole reason v4 exists - in v3 a tier was two side frames, so
    the corners were two separate pieces meeting at a seam and never locked.
    """
    lh = P["PITCH"]
    ph = P["POST"] / 2.0

    ops = ring_solids(P["RING"] / 2.0, P["RING_R"], P["RING_T"],
                      P["RING_IN"] / 2.0, P["RING_IN_R"])

    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * POST_C, sy * POST_C
            ops.append((rrect_mesh("post", cx - ph, cy - ph, cx + ph, cy + ph,
                                   0.0, lh, P["POST_R"], 6), 'u'))
            # male tenon on top, with crush ribs
            for m in tenon_solids(cx, cy, lh - 1.0, lh + P["TENON_H"]):
                ops.append((m, 'u'))
            # Pin hole through the TENON as well as the socket. Without this
            # pair the pin had nothing to pass through in the tier below, so
            # the joint could never actually be pinned.
            ops.append((teardrop_x_mesh("pin_tenon", cy, lh + P["PIN_Z"],
                                        cx - 20.0, cx + 20.0, P["PIN_D"] / 2.0), 'd'))
            # arm out to the pad that actually carries the machine
            ops.append((capsule_mesh("arm", (cx, cy), (sx * P["PAD_C"], sy * P["PAD_C"]),
                                     P["ARM_R"], 0.0, P["ARM_T"],
                                     seg=P["ARM_SEG"]), 'u'))
            # Pad with a 45-degree top chamfer built in, not a rounded bevel
            # left to soften(). A softened square edge is a quarter-round whose
            # lower half faces downwards - 424 mm2 of overhang across the four
            # pads. A 45-degree cone stays self-supporting however it is
            # beveled afterwards.
            pr = P["PAD_D"] / 2.0
            cz = P["ARM_T"] + P["PAD_H"] - P["PAD_CHAMFER"]
            ops.append((cyl_mesh("pad", sx * P["PAD_C"], sy * P["PAD_C"],
                                 P["ARM_T"] - 1.0, cz, pr, seg=36), 'u'))
            if P["PAD_CHAMFER"] > 0:
                ops.append((cone_mesh("padc", sx * P["PAD_C"], sy * P["PAD_C"],
                                      cz, P["ARM_T"] + P["PAD_H"], pr,
                                      pr - P["PAD_CHAMFER"], seg=36), 'u'))

    # female socket underneath, and the optional pin hole through it
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * POST_C, sy * POST_C
            for m in socket_solids(cx, cy, -1.0):
                ops.append((m, 'd'))
            ops.append((teardrop_x_mesh("pin", cy, P["PIN_Z"], cx - 20.0, cx + 20.0,
                                        P["PIN_D"] / 2.0), 'd'))

    # Panel groove, cut as its own compound tool (outer ring minus inner ring)
    # because bake_seq applies all unions before all differences, so it cannot
    # express a cut that is itself a ring.
    # The panel location is now a RAIL that sticks OUT, not a groove cut IN.
    #
    # A 2.5 mm deep groove in a vertical wall has a flat ceiling, and that
    # ceiling is an unsupported bridge in open air - with ABS/ASA at near-zero
    # part cooling it strings and never cures. A rib that projects outward has
    # its overhang on the UNDERside instead, where a 45 degree ramp makes it
    # self-supporting. The matching groove moves to the panel, where it is a
    # recess in the top face during printing and therefore not an overhang at
    # all. The panels are decorative; they only have to stay put.
    rail_op = None
    if P["PANEL_GROOVE"]:
        half = P["RING"] / 2.0
        proud = P["RAIL_PROUD"]
        z0, z1 = P["GROOVE_Z0"], P["GROOVE_Z1"]
        # The rail runs from the BED up to z1, so it has no underside at all -
        # nothing overhangs anywhere. A ramp on its underside was the first
        # attempt; a stepped ramp still leaves a horizontal ledge per step, and
        # a real 45 degree ramp is not expressible with the primitives here.
        # Starting at z=0 costs a little plastic and removes the question.
        rail = bake_to_mesh("_rail", [
            (rrect_mesh("ro", -half - proud, -half - proud, half + proud, half + proud,
                        0.0, z1, P["RING_R"] + proud, P["SEG"]), 'u'),
            (rrect_mesh("ri", -half + 0.5, -half + 0.5, half - 0.5, half - 0.5,
                        -1.0, z1 + 1.0, max(P["RING_R"] - 0.5, 1.0), P["SEG"]), 'd'),
        ])
        rail_op = (rail, 'u')
        del z0

    obj = bake_seq("tier", ops, coll, mats["body"])
    soften(obj, P["TIER_SOFTEN"], segments=3)

    # The cradles are unioned in AFTER the bevel. soften() at 1.1 mm is wider
    # than the cradle walls are thick, so beveling them together ate the walls
    # and left 52 non-manifold edges. Their base is coplanar with the ring's bed
    # face at z=0, though, which is why the groove is held back and cut in this
    # same pass rather than in the first one.
    second = [(obj.data, 'u')]
    for sx in (-1, 1):
        for sy in (-1, 1):
            cr = cradle_solids(sx, sy)
            if cr:
                second.append((bake_to_mesh("cradle", [(x, 'u') for x in cr]), 'u'))
    if rail_op:
        second.append(rail_op)
    if len(second) > 1:
        # Free the name first, or Blender renames the merged object tier.001 and
        # everything downstream that looks "tier" up by name fails.
        obj.name = "_tier_body"
        obj = bake_seq("tier", second, coll, mats["body"])
        bpy.data.objects.remove(bpy.data.objects["_tier_body"], do_unlink=True)
        # Round-over AFTER the union, never before: beveling the cradles on
        # their own first left seven 2-face slivers floating inside each tier,
        # because unioning a heavily faceted solid against the body makes
        # slivers that remove_doubles cannot merge away.
        roll_top(obj, P["ARM_T"] + P["PAD_H"] + P["CRADLE_H"], P["CRADLE_SOFTEN"])
    return obj


def build_base(coll, mats):
    """Wide low ring, sized so a 4-high stack cannot be knocked over easily."""
    half = P["BASE"] / 2.0
    t = P["BASE_T"]

    ops = ring_solids(half, P["BASE_R"], t, P["BASE_IN"] / 2.0, P["BASE_IN_R"])

    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * POST_C, sy * POST_C
            for m in tenon_solids(cx, cy, t - 1.0, t + P["TENON_H"]):
                ops.append((m, 'u'))
            ops.append((teardrop_x_mesh("pin", cy, t + P["PIN_Z"], cx - 20.0, cx + 20.0,
                                        P["PIN_D"] / 2.0), 'd'))
            ops.append((cyl_mesh("foot", cx, cy, -1.0, P["FOOT_H"],
                                 P["FOOT_D"] / 2.0), 'd'))

    obj = bake_seq("base", ops, coll, mats["body"])
    return fillet_rims(obj, P["BASE_FILLET"], segments=4)


def bake_to_mesh(name, ops):
    """Bake a boolean stack into a bare mesh, leaking no objects into the scene."""
    tmp = bpy.data.collections.new("_tmp_mark")
    bpy.context.scene.collection.children.link(tmp)
    obj = bake_seq(name, ops, tmp)
    me = obj.data.copy()
    me.name = name
    for o in list(tmp.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(tmp)
    return me


def mark_bounds(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs),
            (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, min(zs))


def place_mark(me, target_h, depth, pos):
    """Stand a flat mark up facing -Y, scale it to `target_h`, drop it at `pos`."""
    w, h, d, cx, cy, zmin = mark_bounds(me)
    if h <= 1e-6 or d <= 1e-6:
        raise ValueError(f"mark {me.name!r} has no extent (w={w} h={h} d={d}) - "
                         f"a font curve needs extrude set to gain depth")
    s = target_h / h
    me.transform(Matrix.Translation((-cx, -cy, -zmin)))
    me.transform(Matrix.Diagonal((s, s, depth / d, 1.0)))
    me.transform(Matrix.Rotation(math.radians(90), 4, 'X'))   # +Z depth -> -Y
    me.transform(Matrix.Translation(pos))
    return w * s


def _font_used():
    for path in P["FONT_CANDIDATES"]:
        if os.path.exists(path):
            try:
                return bpy.data.fonts.load(path)
            except Exception:
                continue
    return None          # falls back to Blender's built-in Bfont


def wordmark_mesh(body):
    """Tessellate a text object down to a mesh. No bpy.ops, so no context risk."""
    curve = bpy.data.curves.new("_wm_curve", type='FONT')
    curve.body = body
    curve.align_x = 'CENTER'
    curve.align_y = 'CENTER'
    # Without extrude the font tessellates to a flat sheet with zero depth, and
    # place_mark then divides by that zero depth.
    curve.extrude = 0.5
    curve.resolution_u = 6
    font = _font_used()
    if font is not None:
        curve.font = font
    obj = bpy.data.objects.new("_wm_src", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    me.name = "wordmark"
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.curves.remove(curve)
    return me


def mark_stroke(body, target_h):
    """Mean stroke width in mm at print size, via area over boundary perimeter.

    Measured on a FLAT tessellation. On the extruded solid every edge is shared
    by two faces, so a boundary-edge perimeter collapses to zero and the ratio
    blows up. Only edges belonging to a single polygon count, which also avoids
    double-counting the internal tessellation.
    """
    import numpy as np
    from collections import defaultdict

    curve = bpy.data.curves.new("_ms_curve", type='FONT')
    curve.body = body
    curve.extrude = 0.0
    curve.resolution_u = 6
    font = _font_used()
    if font is not None:
        curve.font = font
    obj = bpy.data.objects.new("_ms_src", curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.curves.remove(curve)

    V = np.array([[v.co.x, v.co.y] for v in me.vertices])
    area = 0.0
    cnt, ln = defaultdict(int), {}
    for p in me.polygons:
        idx = list(p.vertices)
        pts = V[idx]
        x, y = pts[:, 0], pts[:, 1]
        area += 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        for i in range(len(idx)):
            a, b = idx[i], idx[(i + 1) % len(idx)]
            k = (min(a, b), max(a, b))
            cnt[k] += 1
            ln[k] = float(np.linalg.norm(V[a] - V[b]))
    per = sum(ln[k] for k, c in cnt.items() if c == 1)
    h = float(V[:, 1].max() - V[:, 1].min())
    w = float(V[:, 0].max() - V[:, 0].min())
    bpy.data.meshes.remove(me)
    if per <= 0 or h <= 0:
        return 0.0, 0.0, 0.0
    return 2.0 * area / per * (target_h / h), w * (target_h / h), h


def logo_solids():
    """Three tiers under a spark - a stack of Sparks, drawn as a mark."""
    solids = []
    width = 11.0
    bar_h, gap = 1.9, 1.6
    z = 0.0
    for frac in (1.0, 0.74, 0.50):
        bw = width * frac
        solids.append(rrect_mesh("bar", -bw / 2.0, z, bw / 2.0, z + bar_h,
                                 0.0, 1.0, bar_h / 2.0, 6))
        z += bar_h + gap
    half = 2.4
    cz = z + half - 0.3
    v = [(0, cz - half, 0), (half, cz, 0), (0, cz + half, 0), (-half, cz, 0),
         (0, cz - half, 1), (half, cz, 1), (0, cz + half, 1), (-half, cz, 1)]
    f = [(0, 1, 2), (0, 2, 3), (7, 6, 5), (7, 5, 4),
         (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    solids.append(_mesh("spark", v, f))
    return solids


def cut_into(obj, holes, coll):
    """Subtract extra solids from an object that already exists in the scene."""
    made = [new_object(f"_c{i}", m, coll) for i, m in enumerate(holes)]
    for o in made:
        mod = obj.modifiers.new('d', 'BOOLEAN')
        mod.operation, mod.object, mod.solver = 'DIFFERENCE', o, 'EXACT'
    dg = bpy.context.evaluated_depsgraph_get()
    flat = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    flat.name = obj.name
    for o in made:
        bpy.data.objects.remove(o, do_unlink=True)
    old = obj.data
    if not flat.materials:
        for m in old.materials:
            flat.materials.append(m)
    obj.data = flat
    bpy.data.meshes.remove(old)
    return obj


def build_cap(coll, mats):
    """Closes the top, with a socket over each post and the mark on the front edge."""
    half = P["CAP"] / 2.0
    t = CAP_T

    ops = ring_solids(half, P["CAP_R"], t, P["CAP_IN"] / 2.0, P["CAP_IN_R"])
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = sx * POST_C, sy * POST_C
            for m in socket_solids(cx, cy, -1.0):
                ops.append((m, 'd'))
            ops.append((teardrop_x_mesh("pin", cy, P["PIN_Z"], cx - 20.0, cx + 20.0,
                                        P["PIN_D"] / 2.0), 'd'))

    obj = bake_seq("cap", ops, coll, mats["body"])
    # Fillet first, THEN engrave - the fillet eats the top and bottom of the
    # front face, so a mark placed before it would run off the flat.
    obj = fillet_rims(obj, P["CAP_FILLET"], segments=4)

    depth = 1.0
    face_y = -half + P["DEBOSS"]        # 0.8 mm into the wall, 0.2 mm proud
    z_mid = t / 2.0

    logo = bake_to_mesh("logo", [(m, 'u') for m in logo_solids()])
    wm = wordmark_mesh(P["WORDMARK"])
    lw = mark_bounds(logo)[0] * (P["LOGO_H"] / mark_bounds(logo)[1])
    ww = mark_bounds(wm)[0] * (P["MARK_H"] / mark_bounds(wm)[1])

    total = lw + P["MARK_GAP"] + ww
    x0 = -total / 2.0
    # place_mark mutates each mesh in place and returns its placed width,
    # so cut with the meshes themselves, not its return value.
    place_mark(logo, P["LOGO_H"], depth, (x0 + lw / 2.0, face_y, z_mid))
    place_mark(wm, P["MARK_H"], depth,
               (x0 + lw + P["MARK_GAP"] + ww / 2.0, face_y, z_mid))
    obj = cut_into(obj, [logo, wm], coll)

    flat_h = t - 2.0 * P["CAP_FILLET"]
    stroke, wm_true_w, _ = mark_stroke(P["WORDMARK"], P["MARK_H"])
    font = _font_used()
    print(f"  cap mark: logo {lw:.1f} + gap {P['MARK_GAP']:.1f} + '{P['WORDMARK']}' "
          f"{ww:.1f} = {total:.1f} mm wide, carved {P['DEBOSS']:.1f} mm deep "
          f"into a {flat_h:.1f} mm flat face")
    print(f"    font {font.name if font else 'Bfont'}   mean stroke {stroke:.2f} mm"
          f"   ({'printable' if stroke >= P['MIN_STROKE'] else 'TOO THIN - go bolder or bigger'})")
    if total > 2 * (half - P["CAP_R"]) - 8:
        print("  WARNING: mark is wider than the flat part of the front edge")
    return obj


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def reset_scene():
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def build_stack(tiers=4, with_device=True):
    reset_scene()
    coll = bpy.data.collections.new("SparkStack")
    bpy.context.scene.collection.children.link(coll)
    mats = build_materials()

    build_base(coll, mats)

    z = P["BASE_T"]
    for i in range(tiers):
        build_tier(coll, mats).location = (0.0, 0.0, z)
        if with_device:
            dobj = new_object(f"DGX_Spark_placeholder_T{i + 1}",
                              rrect_mesh("d", -P["DEV_W"] / 2, -P["DEV_D"] / 2,
                                         P["DEV_W"] / 2, P["DEV_D"] / 2,
                                         0.0, P["DEV_H"], 18.0, 8), coll)
            dobj.data.materials.append(mats["device"])
            soften(dobj, 3.0, segments=4)
            dobj.location = (0.0, 0.0, z + P["ARM_T"] + P["PAD_H"])
        z += P["PITCH"]

    build_cap(coll, mats).location = (0.0, 0.0, z)
    for o in coll.objects:
        if o.type == 'MESH':
            cleanup(o)
    return coll, z + CAP_T


def occlusion():
    """Fraction of the device underside shadowed by pads and arms."""
    step = 0.4
    dev = P["DEV_W"]
    pad_r = P["PAD_D"] / 2.0
    hits = total = 0
    n = int(dev / step)
    for i in range(n):
        x = -dev / 2.0 + (i + 0.5) * step
        for j in range(n):
            y = -dev / 2.0 + (j + 0.5) * step
            total += 1
            shadow = False
            for sx in (-1, 1):
                for sy in (-1, 1):
                    if math.hypot(x - sx * P["PAD_C"], y - sy * P["PAD_C"]) <= pad_r:
                        shadow = True
                    ax, ay = sx * POST_C, sy * POST_C
                    bx, by = sx * P["PAD_C"], sy * P["PAD_C"]
                    vx, vy = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy)))
                    if math.hypot(x - (ax + t * vx), y - (ay + t * vy)) <= P["ARM_R"]:
                        shadow = True
            hits += shadow
    return 100.0 * hits / total


def report(coll, total_h, tiers):
    tris = 0
    names = []
    for o in sorted(coll.objects, key=lambda x: (x.name.startswith("DGX"), x.name)):
        if o.name.startswith("DGX"):
            continue
        me = o.data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        dx = max(v.x for v in bb) - min(v.x for v in bb)
        dy = max(v.y for v in bb) - min(v.y for v in bb)
        dz = max(v.z for v in bb) - min(v.z for v in bb)
        names.append(o.name)
        print(f"  {o.name:8s} {dx:6.1f} x {dy:6.1f} x {dz:6.1f} mm   {len(me.loop_triangles):6d} tris")

    opening = P["BASE_IN"]
    print(f"\n  tiers: {tiers}   parts to print: 1 base + {tiers} tier + 1 cap")
    print(f"  tier envelope {P['RING']:.0f} mm   base {P['BASE']:.0f} mm"
          f"   (device {P['DEV_W']:.0f} mm)")
    print(f"  ring opens to {opening:.0f} x {opening:.0f} mm - clear of the device silhouette")
    print(f"  stack height for {tiers}: {total_h:.0f} mm")
    print(f"  air gap between tiers: {P['PITCH'] - (P['ARM_T'] + P['PAD_H']) - P['DEV_H']:.1f} mm")
    print(f"  joint: tenon {P['TENON']:.0f} x {P['TENON']:.0f} x {P['TENON_H']:.0f} mm"
          f" into a {SOCKET:.1f} mm socket  ({P['TENON_H'] / P['POST']:.0%} of post height)")
    print(f"  underside shadowed by pads + arms: {occlusion():.1f}%")

    # tipping angle at full height
    cg = 0.0
    for i in range(tiers):
        cg += P["BASE_T"] + i * P["PITCH"] + P["ARM_T"] + P["PAD_H"] + P["DEV_H"] / 2.0
    cg /= max(tiers, 1)
    print(f"  centre of mass ~{cg:.0f} mm up; tipping angle "
          f"{math.degrees(math.atan((P['BASE'] / 2.0) / cg)):.1f} deg")


def export_stls(coll, outdir, version=None):
    """One STL per unique part, each dropped onto its own origin for slicing."""
    os.makedirs(outdir, exist_ok=True)
    parts, counts = {}, {}
    for o in coll.objects:
        if o.name.startswith("DGX") or o.name.startswith("panel"):
            continue      # panels export flat, via sparkstack_panels.export_panels
        base = o.name.split(".")[0]
        counts[base] = counts.get(base, 0) + 1
        parts.setdefault(base, o)

    tag = "v" + (version or VERSION).replace(".", "_")
    written = []
    for name, obj in sorted(parts.items()):
        saved = obj.location.copy()
        obj.location = (0.0, 0.0, 0.0)
        path = os.path.join(outdir, f"sparkstack_{tag}_{name}.stl")
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True,
                                  global_scale=1.0)
        except AttributeError:
            bpy.ops.export_mesh.stl(filepath=path, use_selection=True, global_scale=1.0)
        obj.location = saved
        written.append((path, counts[name], os.path.getsize(path)))
    return written, counts


def write_spec(path, tiers, version=None):
    """Freeze the resolved parameter set so a version can be rebuilt exactly."""
    import json
    cg = sum(P["BASE_T"] + i * P["PITCH"] + P["ARM_T"] + P["PAD_H"] + P["DEV_H"] / 2.0
             for i in range(tiers)) / max(tiers, 1)
    spec = {
        "version": version or VERSION,
        "panel_groove": P["PANEL_GROOVE"],
        "generated_by": "sparkstack.py",
        "units": "mm",
        "device": {
            "width": P["DEV_W"], "depth": P["DEV_D"], "height": P["DEV_H"],
            "source": "NVIDIA DGX Spark User Guide - Hardware Overview "
                      "(150 x 150 x 50.5 mm, 1.2 kg); height 51.2 mm as measured "
                      "in the ChargerLAB teardown",
        },
        "derived": {
            "post_centre": POST_C,
            "tier_envelope": P["RING"],
            "base_envelope": P["BASE"],
            "level_pitch": P["PITCH"],
            "socket_bore": SOCKET,
            "socket_depth": SOCKET_H,
            "cap_thickness": CAP_T,
            "underside_occlusion_pct": round(occlusion(), 2),
            "centre_of_mass_mm": round(cg, 1),
            "tipping_angle_deg": round(math.degrees(math.atan((P["BASE"] / 2.0) / cg)), 1),
        },
        "parameters": {k: (list(v) if isinstance(v, tuple) else v) for k, v in P.items()},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    return spec


if __name__ == "__main__":
    TIERS = 4
    HERE = os.path.dirname(os.path.abspath(__file__))
    c, h = build_stack(tiers=TIERS)
    report(c, h, TIERS)

    print(f"\n=== exporting SPARKSTACK v{VERSION} ===")
    rows, counts = export_stls(c, os.path.join(HERE, "stl"))
    for path, n, size in rows:
        print(f"  {os.path.basename(path):38s} x{n}  {size/1024:7.1f} KB")
    print("\n  bill of materials:")
    for name, n in sorted(counts.items()):
        print(f"    {n} x {name}")
    spec = write_spec(os.path.join(HERE, "sparkstack_v1_parameters.json"), TIERS)
    print(f"\n  spec frozen -> sparkstack_v1_parameters.json "
          f"(tip angle {spec['derived']['tipping_angle_deg']} deg, "
          f"occlusion {spec['derived']['underside_occlusion_pct']}%)")
