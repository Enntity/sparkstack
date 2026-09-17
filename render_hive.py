"""A three-high SparkStack, decorative panels ON, in the dark hive finish.

    Blender --background --python render_hive.py
"""
import bpy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_sparkstack as R                              # noqa: E402
import sparkstack as SS                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TIERS = 3


def mat_abs_hive():
    """Dark organic finish. Not flat black: chitin, mottled.

    Two noise scales - a broad one so the mass reads as a material rather than
    a silhouette, and a tight one for grain - plus a roughness range wide
    enough that highlights break up across a panel instead of sliding over it.
    """
    m = bpy.data.materials.new("abs_hive")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = R.node(nt, 'ShaderNodeOutputMaterial')
    bsdf = R.node(nt, 'ShaderNodeBsdfPrincipled')
    tex = R.node(nt, 'ShaderNodeTexCoord')

    broad = R.node(nt, 'ShaderNodeTexNoise', noise_dimensions='3D')
    R.set_in(broad, "Scale", 1.7); R.set_in(broad, "Detail", 5.0)
    R.set_in(broad, "Roughness", 0.62)
    ramp = R.node(nt, 'ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.009, 0.019, 0.011, 1)   # near-black, green bias
    ramp.color_ramp.elements[1].position = 0.74
    ramp.color_ramp.elements[1].color = (0.044, 0.104, 0.056, 1)   # deep moss

    grain = R.node(nt, 'ShaderNodeTexNoise', noise_dimensions='3D')
    R.set_in(grain, "Scale", 11.0); R.set_in(grain, "Detail", 6.0)
    mix = R.node(nt, 'ShaderNodeMixRGB', blend_type='OVERLAY')
    # Lower than the warm version: OVERLAY against a greyscale grain pulls the
    # hue out, and the green needs the saturation kept.
    R.set_in(mix, "Fac", 0.30)

    rgh = R.node(nt, 'ShaderNodeMapRange')
    R.set_in(rgh, "To Min", 0.28); R.set_in(rgh, "To Max", 0.62)

    fine = R.node(nt, 'ShaderNodeTexNoise', noise_dimensions='3D')
    R.set_in(fine, "Scale", 46.0); R.set_in(fine, "Detail", 3.0)
    bump = R.node(nt, 'ShaderNodeBump')
    R.set_in(bump, "Strength", 0.28); R.set_in(bump, "Distance", 0.05)

    L = nt.links.new
    L(tex.outputs["Object"], broad.inputs["Vector"])
    L(tex.outputs["Object"], grain.inputs["Vector"])
    L(tex.outputs["Object"], fine.inputs["Vector"])
    L(broad.outputs["Fac"], ramp.inputs["Fac"])
    L(broad.outputs["Fac"], rgh.inputs["Value"])
    L(ramp.outputs["Color"], mix.inputs[1])
    L(grain.outputs["Color"], mix.inputs[2])
    L(mix.outputs["Color"], bsdf.inputs["Base Color"])
    L(rgh.outputs["Result"], bsdf.inputs["Roughness"])
    L(fine.outputs["Fac"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    for k, v in (("IOR", 1.46), ("Specular IOR Level", 0.42),
                 ("Coat Weight", 0.10), ("Coat Roughness", 0.30)):
        R.set_in(bsdf, k, v)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def main():
    R.reset()
    sc = bpy.context.scene
    coll = bpy.data.collections.new("HIVE")
    sc.collection.children.link(coll)

    mats = {"pin": R.mat_pin_gold()}
    hive = mat_abs_hive()
    objs = R.build_stack_at(0.0, 0.0, TIERS, coll, mats, hive, panels=True)
    print("built %d objects, %d tiers, panels on" % (len(objs), TIERS))

    fm = bpy.data.meshes.new("floor")
    fm.from_pydata([(-9000, -9000, 0), (9000, -9000, 0),
                    (9000, 9000, 0), (-9000, 9000, 0)], [], [(0, 1, 2, 3)])
    fm.update()
    floor = bpy.data.objects.new("floor", fm)
    coll.objects.link(floor)
    floor.data.materials.append(R.mat_floor())

    cd = bpy.data.cameras.new("cam")
    cd.clip_start, cd.clip_end = 5.0, 60000.0
    cam = bpy.data.objects.new("cam", cd)
    coll.objects.link(cam)

    R.setup_studio(coll, (0.0, 0.0, 125.0), 800.0, world=1.05)

    height = SS.P["BASE_T"] + TIERS * SS.P["PITCH"] + 20.4
    t = (0.0, 0.0, height * 0.50)
    R.setup_render((1150, 1500), samples=64)
    R.shoot(cam, os.path.join(HERE, "sparkstack_render_hive.png"),
            (t[0] + 0.42 * 985, t[1] - 0.78 * 985, t[2] + 0.46 * 985), t, 85.0)

    t2 = (0.0, 0.0, height * 0.68)
    R.setup_render((1500, 1050), samples=64)
    R.shoot(cam, os.path.join(HERE, "sparkstack_render_hive_detail.png"),
            (t2[0] + 0.40 * 700, t2[1] - 0.80 * 700, t2[2] + 0.30 * 700), t2, 90.0)

    print("done  (stack height %.1f mm)" % height)


if __name__ == "__main__":
    main()
