"""Render the SparkStack: white-ABS prints, photoreal Sparks.

Run headless:
    Blender --background --python render_sparkstack.py

Cycles, because the point is real reflections on the anodised chassis and soft
contact shadows under the prints. Everything is procedural - no HDRI or image
textures to ship - so the script is self-contained and repeatable.

Note on scale: 1 unit = 1 mm. Light positions land around 1000-2000 units, i.e.
1-2 m, so wattages are in the usual range rather than megawatts.
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sparkstack as SS                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_W = DEV_D = 150.0
DEV_H = 51.2
DEV_R = 18.0
GOLD_LO, GOLD_HI = 4.0, 47.0
# Two intake bands, not one big recess: the teardown shows the front
# face drawing air through an upper AND a lower grille, with the
# chassis between them. One 42 mm recess covered 86% of the face and
# made the whole front read black.
GRILLE_W, GRILLE_T, GRILLE_D = 126.0, 9.0, 2.2
GRILLE_Z = (13.0, 33.0)


# --------------------------------------------------------------------------- #
# scene plumbing
# --------------------------------------------------------------------------- #
def reset():
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                 bpy.data.cameras, bpy.data.node_groups):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def node(nt, kind, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def set_in(n, key, value):
    if key in n.inputs:
        n.inputs[key].default_value = value
    return n


# --------------------------------------------------------------------------- #
# materials
# --------------------------------------------------------------------------- #
def mat_white_abs():
    """White ABS. Off pure white, because pure white reads as CG."""
    m = bpy.data.materials.new("white_abs")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = node(nt, 'ShaderNodeOutputMaterial')
    bsdf = node(nt, 'ShaderNodeBsdfPrincipled')
    tex = node(nt, 'ShaderNodeTexCoord')
    broad = node(nt, 'ShaderNodeTexNoise', noise_dimensions='3D')
    set_in(broad, "Scale", 3.2); set_in(broad, "Detail", 4.0)
    set_in(broad, "Roughness", 0.55)
    ramp = node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.840, 0.840, 0.825, 1)
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[1].color = (0.918, 0.918, 0.905, 1)
    rgh = node(nt, 'ShaderNodeMapRange')
    set_in(rgh, "To Min", 0.33); set_in(rgh, "To Max", 0.49)
    wav = node(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='Z')
    set_in(wav, "Scale", 0.5); set_in(wav, "Distortion", 0.4)
    bump = node(nt, 'ShaderNodeBump')
    set_in(bump, "Strength", 0.10); set_in(bump, "Distance", 0.02)
    L = nt.links.new
    L(tex.outputs["Object"], broad.inputs["Vector"])
    L(tex.outputs["Object"], wav.inputs["Vector"])
    L(broad.outputs["Fac"], ramp.inputs["Fac"])
    L(broad.outputs["Fac"], rgh.inputs["Value"])
    L(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    L(rgh.outputs["Result"], bsdf.inputs["Roughness"])
    L(wav.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    for k, v in (("IOR", 1.46), ("Specular IOR Level", 0.5),
                 ("Coat Weight", 0.05), ("Coat Roughness", 0.32)):
        set_in(bsdf, k, v)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def _metal(name, colour, rough, aniso, scale, brush=0.10, metallic=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = node(nt, 'ShaderNodeOutputMaterial')
    bsdf = node(nt, 'ShaderNodeBsdfPrincipled')
    tex = node(nt, 'ShaderNodeTexCoord')
    noise = node(nt, 'ShaderNodeTexNoise', noise_dimensions='3D')
    set_in(noise, "Scale", scale); set_in(noise, "Detail", 2.0)
    mr = node(nt, 'ShaderNodeMapRange')
    set_in(mr, "To Min", max(0.03, rough - brush))
    set_in(mr, "To Max", rough + brush)
    bump = node(nt, 'ShaderNodeBump')
    set_in(bump, "Strength", 0.05); set_in(bump, "Distance", 0.004)
    set_in(bsdf, "Base Color", (*colour, 1.0))
    # Not 1.0. A pure metal has no diffuse term at all, so inside a shaded bay
    # with nothing bright to reflect it renders as a black hole - which is
    # exactly what the first pass looked like.
    set_in(bsdf, "Metallic", metallic)
    set_in(bsdf, "Anisotropic", aniso)
    L = nt.links.new
    L(tex.outputs["Object"], noise.inputs["Vector"])
    L(noise.outputs["Fac"], mr.inputs["Value"])
    L(mr.outputs["Result"], bsdf.inputs["Roughness"])
    L(noise.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_pin_gold():
    """The joint pins. Polished, and deliberately the brightest thing on the
    rack - they are the one part that is not printed, so they should read as
    hardware."""
    return _metal("pin_gold", (0.860, 0.660, 0.285), 0.16, 0.30, 60.0, 0.04,
                  metallic=0.97)


def mat_grille():
    """Front intake as fine horizontal slats, driven by a texture.

    Modelling 40 slats would cost more triangles than the whole rack, and at
    any sane render size the wave reads identically.
    """
    m = bpy.data.materials.new("spark_grille")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = node(nt, 'ShaderNodeOutputMaterial')
    bsdf = node(nt, 'ShaderNodeBsdfPrincipled')
    tex = node(nt, 'ShaderNodeTexCoord')
    wav = node(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='Z')
    set_in(wav, "Scale", 30.0); set_in(wav, "Distortion", 0.0)
    ramp = node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.006, 0.006, 0.008, 1)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.070, 0.066, 0.060, 1)
    bump = node(nt, 'ShaderNodeBump')
    set_in(bump, "Strength", 0.9); set_in(bump, "Distance", 0.012)
    set_in(bsdf, "Metallic", 0.85)
    set_in(bsdf, "Roughness", 0.42)
    L = nt.links.new
    L(tex.outputs["Object"], wav.inputs["Vector"])
    L(wav.outputs["Fac"], ramp.inputs["Fac"])
    L(wav.outputs["Fac"], bump.inputs["Height"])
    L(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_floor():
    m = bpy.data.materials.new("floor")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    set_in(b, "Base Color", (0.052, 0.055, 0.060, 1))
    set_in(b, "Roughness", 0.30)
    set_in(b, "Metallic", 0.0)
    return m


# --------------------------------------------------------------------------- #
# the Spark
# --------------------------------------------------------------------------- #
SPARK_GLB = os.path.join(HERE, "assets", "dgx-spark.glb")
_SPARK_MESH = [None]


def spark_mesh():
    """Import the DGX Spark GLB once and hand back its mesh.

    A real asset beats texturing a box: this one has the champagne shell, the
    sintered open-cell grille as ACTUAL geometry (827k triangles of it), the
    rubber feet and the rear connectors. Metres, front facing -Y, feet on z=0,
    so it scales by 1000 and drops straight onto the pads.
    """
    if _SPARK_MESH[0] is not None:
        return _SPARK_MESH[0]
    if not os.path.exists(SPARK_GLB):
        raise SystemExit(
            "\nSpark model not found at %s\n\n"
            "It is a third-party asset and is deliberately not committed here.\n"
            "Download it (free, no signup) and drop it in assets/:\n\n"
            "  mkdir -p assets\n"
            "  curl -L -o assets/dgx-spark.glb \\\n"
            "    https://wendy.dev/models/dgx-spark/nvidia-dgx-spark.glb\n\n"
            "The rack itself needs none of this - only these renders do.\n"
            % SPARK_GLB)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=SPARK_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("no mesh in %s" % SPARK_GLB)
    src = max(meshes, key=lambda o: len(o.data.vertices))
    me = src.data
    for o in new:
        if o.type == 'EMPTY':
            bpy.data.objects.remove(o, do_unlink=True)
    _SPARK_MESH[0] = me
    print("spark mesh: %d verts, %d materials" % (len(me.vertices), len(me.materials)))
    return me


def place_spark(coll, name, loc):
    """A LINKED duplicate - eight separate 253k-vertex meshes would be 2M verts
    of needless duplication; sharing the datablock costs nothing per copy."""
    me = spark_mesh()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.scale = (1000.0, 1000.0, 1000.0)
    # The asset's origin sits at the TOP of the device, not the bottom: its
    # local z runs about -0.049..0.0015. Placing it at the seat height would
    # bury it a full 49 mm into the rack, so lift it by its own depth.
    drop = -min(v.co.z for v in me.vertices) * 1000.0
    o.location = (loc[0], loc[1], loc[2] + drop)
    return o


def joint_pin(coll, cx, cy, z, mat):
    """One gold pin through a post joint, head outboard."""
    sgn = 1.0 if cx > 0 else -1.0
    # The pin has to reach the ring's OUTER face. The ring is 10 mm tall at each
    # tier's foot and the pin sits 5.5 mm up, so a pin that stops at the post
    # (24 mm) is buried inside the ring and invisible. The drilled hole runs
    # 40 mm through post and ring both, so the pin follows it out and the head
    # lands on the ring face at RING/2.
    face = SS.P["RING"] / 2.0
    body = SS.cyl_x_mesh("pin", cy, z, cx - sgn * 16.0, sgn * face, 1.55, seg=20)
    head = SS.cyl_x_mesh("pinhead", cy, z, sgn * face, sgn * (face + 3.6),
                         3.0, seg=24)
    o = SS.bake_seq("jointpin", [(body, 'u'), (head, 'u')], coll)
    o.data.materials.append(mat)
    return o


# --------------------------------------------------------------------------- #
# a whole stack
# --------------------------------------------------------------------------- #
def build_stack_at(x, y, tiers, coll, mats, white, panels=False):
    """One SparkStack plus a real Spark per tier, then translate the lot.

    Deliberately NOT SS.build_stack(): that calls reset_scene(), which would
    delete the stacks already built. Everything goes into `coll` directly.
    The front and side plates are left OFF for these renders so the device is
    not sitting behind 30%-coverage webbing.
    """
    import importlib
    import sparkstack_panels as SP
    importlib.reload(SP)
    SS.P["PANEL_RAIL"] = True

    objs = []
    body_mats = SS.build_materials()
    objs.append(SS.build_base(coll, body_mats))
    for i in range(tiers):
        t = SS.build_tier(coll, body_mats)
        t.location = (0.0, 0.0, SS.P["BASE_T"] + i * SS.P["PITCH"])
        objs.append(t)
    cap = SS.build_cap(coll, body_mats)
    cap.location = (0.0, 0.0, SS.P["BASE_T"] + tiers * SS.P["PITCH"])
    objs.append(cap)

    if panels:
        for p in SP.build_all(coll, tiers):
            if p is not None:
                objs.append(p)

    for i in range(tiers):
        z = SS.P["BASE_T"] + i * SS.P["PITCH"] + SS.P["ARM_T"] + SS.P["PAD_H"]
        objs.append(place_spark(coll, "spark_%d" % (i + 1), (0.0, 0.0, z)))

    # gold pins: every tier joint, plus the one under the cap. The pin holes
    # for tier k and the cap both land on BASE_T + k*PITCH + PIN_Z.
    for k in range(1, tiers + 1):
        z = SS.P["BASE_T"] + k * SS.P["PITCH"] + SS.P["PIN_Z"]
        for sx in (-1, 1):
            for sy in (-1, 1):
                objs.append(joint_pin(coll, sx * SS.POST_C, sy * SS.POST_C, z,
                                      mats["pin"]))

    for o in objs:
        # NEVER SS.cleanup() an imported Spark. That merges verts within
        # `dist`, and dist is in the MESH's units - the GLB is in metres, so
        # 0.003 is a 3 mm merge against 0.09 mm foam cells. It took the model
        # from 253,526 verts to 296 and the sintered front became a handful of
        # angular shards. The rack parts are modelled in mm, so for them the
        # same number is three microns and correct.
        if o.name.startswith("spark"):
            continue
        SS.cleanup(o)
        o.data.materials.clear()
        o.data.materials.append(white if not o.name.startswith("jointpin")
                                else mats["pin"])

    bpy.context.view_layer.update()
    M = Matrix.Translation((x, y, 0.0))
    for o in objs:
        o.matrix_world = M @ o.matrix_world
    return objs


# --------------------------------------------------------------------------- #
# studio
# --------------------------------------------------------------------------- #
def area_light(name, coll, loc, target, size, power, colour=(1, 1, 1)):
    d = bpy.data.lights.new(name, type='AREA')
    d.shape = 'RECTANGLE'
    d.size, d.size_y = size[0], size[1]
    d.energy = power
    d.color = colour
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).normalized() \
        .to_track_quat('-Z', 'Y').to_euler()
    return o


def setup_studio(coll, target, radius, world=0.72):
    w = bpy.data.worlds.new("studio")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = node(nt, 'ShaderNodeOutputWorld')
    bg = node(nt, 'ShaderNodeBackground')
    tex = node(nt, 'ShaderNodeTexCoord')
    sep = node(nt, 'ShaderNodeSeparateXYZ')
    ramp = node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.055, 0.058, 0.065, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.55, 0.58, 0.64, 1)
    set_in(bg, "Strength", world)
    L = nt.links.new
    L(tex.outputs["Generated"], sep.inputs["Vector"])
    L(sep.outputs["Z"], ramp.inputs["Fac"])
    L(ramp.outputs["Color"], bg.inputs["Color"])
    L(bg.outputs["Background"], out.inputs["Surface"])

    t = Vector(target)
    def at(*k):
        return t + Vector(k) * radius
    area_light("key", coll, at(-1.05, -1.35, 1.30), t, (900, 900), 6.0e6)
    area_light("fill", coll, at(1.45, -0.95, 0.45), t, (700, 700), 1.1e6,
               (0.85, 0.90, 1.0))
    area_light("rim", coll, at(0.25, 1.55, 0.95), t, (1400, 300), 2.0e6,
               (1.0, 0.96, 0.88))
    # A wide, low panel straight in front. Its only job is to spill through the
    # panel openings so the Sparks are lit where they sit, not just at the
    # silhouettes - the bays are otherwise a closed box.
    area_light("bay", coll, at(0.0, -1.45, 0.22), t, (2800, 900), 2.4e6,
               (1.0, 0.97, 0.93))
    # Two side fills, for the same reason: the side panels are 30% open and the
    # gold flanks are what shows through them.
    for sx in (-1, 1):
        area_light("side%d" % sx, coll, at(sx * 1.55, -0.75, 0.30), t,
                   (1500, 900), 1.5e6, (1.0, 0.98, 0.95))


def setup_render(res, samples=64, device='GPU'):
    """Configure Cycles.

    The device selection matters and is easy to get silently wrong.
    `cycles.preferences.devices` is LAZILY enumerated and stays an empty list
    until get_devices() is called, so setting cycles.device='GPU' on its own
    enables nothing and Cycles falls back to CPU without raising - which is
    exactly what happened here for several renders. Worse, it was wrapped in a
    bare try/except that would have swallowed the evidence anyway.

    Measured on this scene at 1150x1500 @32spp, M2 Max:
        CPU                     31.7 s per frame, every frame
        GPU, first of a session 152-208 s   (Metal kernel compile)
        GPU, warm                3.2 s per frame
    The compile is cached under $HOME/Library/Caches, so the first is a one-off
    - see render.sh. Warm GPU is ~10x the CPU, so GPU is the default.
    """
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.transmission_bounces = 6
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.01

    cp = bpy.context.preferences.addons['cycles'].preferences
    cp.compute_device_type = 'METAL'
    cp.get_devices()                       # without this, devices stays empty
    for d in cp.devices:
        d.use = (d.type != 'CPU')
    sc.cycles.device = device
    sc.cycles.denoising_use_gpu = (device == 'GPU')
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.render.film_transparent = False


SS_FACTOR = 2          # supersample, then downscale outside Blender


def shoot(cam, path, loc, target, lens):
    """Render at SS_FACTOR x and hand the downscale to the caller.

    The Spark's sintered front is real geometry with ~0.09 mm cells. At rack
    framing that is a quarter of a pixel per cell, so rendering at final size
    aliases the foam into big angular shards that look nothing like the model.
    Oversampling first averages it back into grain.
    """
    sc = bpy.context.scene
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).normalized() \
        .to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = rx * SS_FACTOR, ry * SS_FACTOR
    sc.render.filepath = path.replace(".png", "_ss.png")
    bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    print("rendered", os.path.basename(path), "at", rx * SS_FACTOR, "x", ry * SS_FACTOR)


def main():
    reset()
    sc = bpy.context.scene
    coll = bpy.data.collections.new("RENDER")
    sc.collection.children.link(coll)

    mats = {"pin": mat_pin_gold()}
    white = mat_white_abs()

    fm = bpy.data.meshes.new("floor")
    fm.from_pydata([(-9000, -9000, 0), (9000, -9000, 0),
                    (9000, 9000, 0), (-9000, 9000, 0)], [], [(0, 1, 2, 3)])
    fm.update()
    floor = bpy.data.objects.new("floor", fm)
    coll.objects.link(floor)
    floor.data.materials.append(mat_floor())

    cd = bpy.data.cameras.new("cam")
    cd.clip_start = 5.0
    cd.clip_end = 60000.0
    cam = bpy.data.objects.new("cam", cd)
    coll.objects.link(cam)

    # two stacks of two, side by side
    SPACING = 250.0
    pair = []
    for k, x in enumerate((-SPACING / 2.0, SPACING / 2.0)):
        pair += build_stack_at(x, 0.0, 2, coll, mats, white)
    # one tower of four, set back so the group shot reads in depth
    tower = build_stack_at(0.0, 900.0, 4, coll, mats, white)

    def show(objs):
        """Each part gets its own shot - leaving the other stack in frame puts
        a stray rack in the corner and eats half the composition."""
        for o in pair + tower:
            o.hide_render = o not in objs

    setup_studio(coll, (0.0, 420.0, 150.0), 950.0)

    # Framing. With sensor_fit AUTO the 36 mm sensor maps to whichever render
    # dimension is LARGER, so a portrait frame is limited by its height and a
    # landscape one by its width. Distance = needed_extent * lens / 36.
    def at(target, d, metres):
        return (target[0] + d[0] * metres, target[1] + d[1] * metres,
                target[2] + d[2] * metres)

    setup_render((1600, 1100))
    show(pair)
    t = (0.0, 0.0, 95.0)
    shoot(cam, os.path.join(HERE, "sparkstack_render_pair.png"),
          at(t, (0.50, -0.82, 0.28), 1320.0), t, 85.0)

    setup_render((1150, 1500))
    show(tower)
    t = (0.0, 900.0, 168.0)
    shoot(cam, os.path.join(HERE, "sparkstack_render_tower.png"),
          at(t, (0.40, -0.79, 0.46), 1020.0), t, 85.0)

    setup_render((1750, 1150))
    show(pair + tower)
    t = (0.0, 400.0, 130.0)
    shoot(cam, os.path.join(HERE, "sparkstack_render_group.png"),
          at(t, (0.42, -0.80, 0.43), 3100.0), t, 80.0)
    print("done")


if __name__ == "__main__":
    main()
