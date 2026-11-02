# SPDX-FileCopyrightText: 2025-2026 The French Monkey
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "Enzyme",
    "author": "The French Monkey",
    "version": (1, 0, 4),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Enzyme",
    "description": "Generate parametric enzyme",
    "category": "Add Mesh",
    "license": "GPL-3.0-or-later",
}

import bpy
import random
import math
from math import sin, cos, pi, tau
from mathutils import Vector, noise, Matrix

try:
    from . import relay_updater
except ImportError:  # the Addon Collection has its own updates
    relay_updater = None

# ----------------------------------------------------------
# MATERIALS
# ----------------------------------------------------------

CLASS_COLORS = {
    "HYDROLASE":       (0.30, 0.70, 1.00, 1.0),
    "OXIDOREDUCTASE":  (1.00, 0.45, 0.30, 1.0),
    "TRANSFERASE":     (0.40, 1.00, 0.60, 1.0),
    "LYASE":           (0.80, 0.60, 1.00, 1.0),
    "ISOMERASE":       (1.00, 0.40, 0.80, 1.0),
    "LIGASE":          (1.00, 0.90, 0.40, 1.0),
    "OTHER":           (0.85, 0.85, 0.85, 1.0),
}

def class_color(name: str):
    return CLASS_COLORS.get(name, CLASS_COLORS["OTHER"])

def get_or_make_material(name: str, color):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF") or nt.nodes.new("ShaderNodeBsdfPrincipled")
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.38
    for key in ("Specular", "Specular IOR Level", "Specular Tint"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.35
            break
    return mat

# ----------------------------------------------------------
# PROFILE OBJECTS
# ----------------------------------------------------------

def ensure_profiles(tube_radius, loop_radius, ribbon_width, ribbon_thickness, helix_elongation=1.6, parent=None):
    def make_circle(name):
        cu = bpy.data.curves.new(name + "_Curve", type="CURVE"); cu.dimensions, cu.fill_mode = '2D', 'BOTH'
        sp = cu.splines.new("NURBS"); sp.points.add(7)
        for i, (x, y) in enumerate([(1,0),(.707,.707),(0,1),(-.707,.707),(-1,0),(-.707,-.707),(0,-1),(.707,-.707)]): sp.points[i].co = (x, y, 0, 1)
        sp.use_cyclic_u = True
        obj = bpy.data.objects.new(name, cu)
        bpy.context.collection.objects.link(obj)
        return obj

    def unique_obj(base_name, make_fn):
        existing = bpy.data.objects.get(base_name)
        obj = make_fn(base_name) if not existing or (parent and existing.parent != parent) else existing
        if parent: obj.parent = parent
        return obj

    tube_helix_obj = unique_obj(f"EG_TubeProfile_Helix_{parent.name}" if parent else "EG_TubeProfile_Helix", make_circle)
    tube_loop_obj  = unique_obj(f"EG_TubeProfile_Loop_{parent.name}"  if parent else "EG_TubeProfile_Loop",  make_circle)
    rib_obj_name   = f"EG_RibbonProfile_{parent.name}" if parent else "EG_RibbonProfile"
    rib_obj = bpy.data.objects.get(rib_obj_name)
    if not rib_obj:
        cu = bpy.data.curves.new(rib_obj_name + "_Curve", type="CURVE"); cu.dimensions, cu.fill_mode = '2D', 'BOTH'
        sp = cu.splines.new("POLY"); sp.points.add(3)
        for i, co in enumerate([(-.5,-.5,0,1),(.5,-.5,0,1),(.5,.5,0,1),(-.5,.5,0,1)]): sp.points[i].co = co
        sp.use_cyclic_u = True
        rib_obj = bpy.data.objects.new(rib_obj_name, cu); bpy.context.collection.objects.link(rib_obj)
    if parent: rib_obj.parent = parent

    tube_helix_obj.scale = (tube_radius * helix_elongation, tube_radius, tube_radius)
    tube_loop_obj.scale  = (loop_radius,)*3
    rib_obj.scale        = (ribbon_width, ribbon_thickness, 1)

    for o in (tube_helix_obj, tube_loop_obj, rib_obj):
        o.hide_set(True); o.hide_render = True
    return tube_helix_obj, tube_loop_obj, rib_obj

# ----------------------------------------------------------
# CURVE HELPERS
# ----------------------------------------------------------

def new_curve(name, pts, resolution_u=24, parent=None):
    cu=bpy.data.curves.new(name,'CURVE'); cu.dimensions='3D'; cu.resolution_u=max(2,int(resolution_u))
    sp=cu.splines.new('NURBS'); sp.points.add(len(pts)-1)
    for i,p in enumerate(pts): sp.points[i].co=(p.x,p.y,p.z,1)
    sp.use_endpoint_u=True
    obj=bpy.data.objects.new(name,cu)
    coll = parent.users_collection[0] if parent and parent.users_collection else bpy.context.scene.collection
    if obj.name not in coll.objects: coll.objects.link(obj)
    if parent: obj.parent=parent
    return obj

def set_bevel_object(curve_obj, profile_obj, bevel_res=6):
    cu=curve_obj.data
    cu.bevel_mode='OBJECT'
    cu.bevel_object=profile_obj
    cu.use_fill_caps=True
    cu.bevel_resolution=max(0,int(bevel_res))
    if profile_obj and profile_obj.type=='CURVE':
        profile_obj.data.resolution_u=max(2,int(bevel_res))
        profile_obj.data.render_resolution_u=max(2,int(bevel_res))

def set_material(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
            
def get_or_create_mesh_container(parent, name):
    container = None
    for ch in parent.children:
        if ch.name.endswith("_Mesh"):
            container = ch
            break
    if not container:
        container = bpy.data.objects.new(name + "_Mesh", None)
        bpy.context.collection.objects.link(container)
        container.parent = parent
    return container

# ----------------------------------------------------------
# SECONDARY STRUCTURE GENERATORS
# ----------------------------------------------------------

def helix_points(center: Vector, axis: Vector, radius: float, pitch: float, turns: float, steps: int):
    axis = axis.normalized()
    up = Vector((0,0,1))
    if abs(axis.dot(up)) > 0.95:
        up = Vector((1,0,0))
    x = axis.cross(up).normalized()
    y = axis.cross(x).normalized()
    pts = []
    total_t = turns * tau
    for i in range(steps+1):
        t = total_t * (i/steps)
        p = center + x*(radius*cos(t)) + y*(radius*sin(t)) + axis*(pitch * (t/(2*pi)))
        pts.append(p)
    return pts

def sheet_spine_points(a: Vector, b: Vector, bow: float, waviness: float, steps: int, seed=0):
    random.seed(seed)
    v = b - a
    L = v.length
    n = v.normalized()
    up = Vector((0,0,1))
    if abs(n.dot(up)) > 0.95:
        up = Vector((1,0,0))
    x = n.cross(up).normalized()
    y = n.cross(x).normalized()
    pts = []
    tangents = []
    for i in range(steps+1):
        t = i/steps
        wobble = x * (sin(t*tau*2.0)* waviness * 0.07 * L) + y * (sin(t*tau*3.0+seed) * waviness * 0.04 * L)
        arch = y * (sin(t*tau) * bow * 0.25 * L)
        p = a + n*(t*L) + wobble + arch
        pts.append(p)
        if i > 0:
            tangents.append((p - pts[i-1]).normalized())
        else:
            tangents.append(n)
    return pts, tangents

def loop_points(a: Vector, b: Vector, slack: float, steps: int, seed=0):
    random.seed(seed+777)
    mid = (a + b) * 0.5
    dir = (b - a)
    L = dir.length
    n = dir.normalized()
    up = Vector((0,0,1))
    if abs(n.dot(up)) > 0.95:
        up = Vector((1,0,0))
    x = n.cross(up).normalized()
    y = n.cross(x).normalized()
    c = mid + (x * random.uniform(-1,1) + y * random.uniform(-1,1)) * slack * L * 0.5
    pts = []
    for i in range(steps+1):
        t = i/steps
        p = (1-t)*(1-t)*a + 2*(1-t)*t*c + t*t*b
        k = 0.03 * slack * L
        pn = Vector((
            noise.noise(p*0.5),
            noise.noise(p*0.6+Vector((1,0,0))),
            noise.noise(p*0.7+Vector((0,1,0))),
        )) * k
        pts.append(p + pn)
    return pts

def helix_points(center: Vector, axis: Vector, radius: float, pitch: float, turns: float, steps: int):
    axis = axis.normalized()
    up = Vector((0,0,1)) if abs(axis.dot(Vector((0,0,1)))) < 0.95 else Vector((1,0,0))
    x = axis.cross(up).normalized()
    y = axis.cross(x).normalized()
    pts = []
    total_t = turns * tau
    for i in range(steps+1):
        t = total_t * (i/steps)
        r = radius * (1 + random.uniform(-0.03, 0.03))
        p = center + x*(r*cos(t)) + y*(r*sin(t)) + axis*(pitch * (t/(2*pi)) * (1 + random.uniform(-0.02, 0.02)))
        pts.append(p)
    return pts

def sheet_spine_points(a: Vector, b: Vector, bow: float, waviness: float, steps: int, seed=0):
    random.seed(seed)
    v = b - a
    L = v.length
    n = v.normalized()
    up = Vector((0,0,1))
    if abs(n.dot(up)) > 0.95:
        up = Vector((1,0,0))
    x = n.cross(up).normalized()
    y = n.cross(x).normalized()
    pts, tangents = [], []
    for i in range(steps+1):
        t = i/steps
        wobble = x * (sin(t*tau*2.0 + random.uniform(-0.05, 0.05))*waviness*0.07*L) + y*(sin(t*tau*3.0+seed)*waviness*0.04*L)
        arch = y * (sin(t*tau + random.uniform(-0.1, 0.1)) * bow * 0.25 * L)
        p = a + n*(t*L) + wobble + arch
        pts.append(p)
        tangents.append((p - pts[i-1]).normalized() if i > 0 else n)
    return pts, tangents

def loop_points(a: Vector, b: Vector, slack: float, steps: int, seed=0):
    random.seed(seed+777)
    mid = (a + b) * 0.5
    dir = (b - a)
    L = dir.length
    n = dir.normalized()
    up = Vector((0,0,1)) if abs(n.dot(Vector((0,0,1)))) < 0.95 else Vector((1,0,0))
    x = n.cross(up).normalized()
    y = n.cross(x).normalized()
    control = mid + (x * random.uniform(-0.6, 0.6) + y * random.uniform(-0.6, 0.6)) * slack * L * 0.4
    pts = []
    for i in range(steps+1):
        t = i/steps
        p = (1-t)*(1-t)*a + 2*(1-t)*t*control + t*t*b
        k = 0.02 * slack * L * (1 + 0.5 * sin(t * pi))  
        pn = Vector((
            noise.noise(p*0.4 + Vector((random.uniform(-0.03, 0.03), 0, 0))),
            noise.noise(p*0.5 + Vector((0, random.uniform(-0.03, 0.03), 0))),
            noise.noise(p*0.6 + Vector((0, 0, random.uniform(-0.03, 0.03))))
        )) * k
        pts.append(p + pn)
    return pts

def get_or_make_material(name: str, color):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF") or nt.nodes.new("ShaderNodeBsdfPrincipled")
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.35
    if "Subsurface" in bsdf.inputs:
        bsdf.inputs["Subsurface"].default_value = 0.015
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (0.05, 0.05, 0.05)
    for key in ("Specular", "Specular IOR Level", "Specular Tint"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.25
            break
    return mat

def build_fold_for_class(parent, props, tube_prof_helix, tube_prof_loop, rib_prof, mat):
    rng = random.Random(props.random_seed)
    created_endpoints, size = [], props.size
    anchors, domain_spread = [], size * (1.3 - props.compactness * 0.9)
    for i in range(props.domain_count):
        t, phi = (i + 0.5) / props.domain_count, 2.39996323 * i
        z, s = 1 - 2 * t, (1 - (1 - 2 * t) ** 2) ** 0.5
        anchors.append(Vector((cos(phi) * s, sin(phi) * s, z)) * domain_spread)

    def is_position_valid(center, existing_centers, min_dist):
        return all((center - c).length > min_dist for c in existing_centers)

    def add_helix(center, axis, radius, pitch, turns, steps, name, noise=0.1):
        pts = helix_points(center, axis, radius, pitch, turns, steps)
        for i, p in enumerate(pts): pts[i] += Vector((rng.uniform(-noise, noise), rng.uniform(-noise, noise), rng.uniform(-noise, noise))) * radius
        obj = new_curve(name, pts, props.curve_resolution, parent)
        set_bevel_object(obj, tube_prof_helix, props.bevel_resolution); set_material(obj, mat)
        obj.parent = parent; created_endpoints.append((pts[0], pts[-1]))
        return center

    def add_sheet(a, b, bow, waviness, steps, name, twist_vary=0.2):
        pts, tangents = sheet_spine_points(a, b, bow, waviness, steps, seed=props.random_seed)
        obj = new_curve(name, pts, props.curve_resolution, parent); cu, sp = obj.data, obj.data.splines[0]
        for i, tvec in enumerate(tangents): sp.points[i].tilt = math.atan2(tvec.y, tvec.x) * (props.sheet_twist + rng.uniform(-twist_vary, twist_vary))
        set_bevel_object(obj, rib_prof, props.bevel_resolution); set_material(obj, mat)
        obj.parent = parent; created_endpoints.append((pts[0], pts[-1]))
        return (a + b) * 0.5

    def add_loop_path(start, end, steps, name, slack=0.6):
        pts = loop_points(start, end, slack, steps, seed=props.random_seed)
        for i, p in enumerate(pts[1:-1]): pts[i+1] += Vector((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03))) * size
        obj = new_curve(name, pts, props.curve_resolution, parent)
        set_bevel_object(obj, tube_prof_loop, props.bevel_resolution); set_material(obj, mat)
        obj.parent = parent

    et = props.enzyme_type
    centers = []  
    min_dist = size * 0.2  
    for d, anchor in enumerate(anchors):
        rng.seed(props.random_seed + d * 123)
        local_offset = anchor + Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), rng.uniform(-.3, .3))) * domain_spread * .25
        domain_scale = 1 - props.compactness * .35
        rand_rot = Matrix.Rotation(rng.uniform(0, math.tau), 4, Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized())

        if et == "OXIDOREDUCTASE": 
            hc = max(3, props.helix_count // props.domain_count)
            for i in range(hc):
                for _ in range(5):  
                    c = local_offset + rand_rot @ Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4))) * domain_scale
                    if is_position_valid(c, centers, min_dist):
                        axis = rand_rot @ Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
                        centers.append(add_helix(c, axis, props.helix_radius * (1.2 + rng.uniform(-0.1, 0.1)), 
                                                 props.helix_pitch * 0.8, props.helix_turns * 1.1, 
                                                 props.curve_resolution * 3, f"H{d}_{i}", noise=0.12))
                        break

            for s in range(props.sheet_count):
                angle = (s / max(1, props.sheet_count)) * tau
                offset = rand_rot @ Vector((cos(angle) * 0.7, sin(angle) * 0.7, (s - props.sheet_count / 2) * 0.25)) * domain_scale
                a, b = local_offset + offset, local_offset - offset * 0.8
                centers.append(add_sheet(a, b, bow=0.4 + rng.uniform(-0.1, 0.1), waviness=0.5 + rng.uniform(-0.1, 0.1), 
                                         steps=props.curve_resolution * 2, name=f"S{d}_{s}", twist_vary=0.3))

        elif et == "TRANSFERASE": 
            rows = max(2, props.sheet_count)
            for r in range(rows):
                oy = (r - rows / 2) * 0.6
                a = local_offset + rand_rot @ Vector((-1.3, oy, 0)) * domain_scale
                b = local_offset + rand_rot @ Vector((1.3, oy, 0)) * domain_scale
                centers.append(add_sheet(a, b, bow=0.5 + rng.uniform(-0.15, 0.15), waviness=0.3 + rng.uniform(-0.1, 0.1), 
                                         steps=props.curve_resolution * 3, name=f"S{d}_{r}", twist_vary=0.25))

            for i in range(max(2, props.helix_count // props.domain_count)):
                for _ in range(5):
                    c = local_offset + rand_rot @ Vector((rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8), (i % 2 - 0.5) * 1.2)) * domain_scale
                    if is_position_valid(c, centers, min_dist):
                        axis = rand_rot @ Vector((0, 0, 1)).normalized()
                        centers.append(add_helix(c, axis, props.helix_radius, props.helix_pitch * 0.9, 
                                                 props.helix_turns * 0.7, props.curve_resolution * 3, f"H{d}_{i}", noise=0.1))
                        break

        elif et == "HYDROLASE": 
            for s in range(props.sheet_count):
                oz = (s - props.sheet_count / 2) * 0.5
                a = local_offset + rand_rot @ Vector((cos(s * tau / max(1, props.sheet_count)) * 1.2, sin(s * tau / max(1, props.sheet_count)) * 1.2, oz)) * domain_scale
                b = local_offset + rand_rot @ Vector((cos((s + 0.5) * tau / max(1, props.sheet_count)) * 1.2, sin((s + 0.5) * tau / max(1, props.sheet_count)) * 1.2, oz)) * domain_scale
                centers.append(add_sheet(a, b, bow=0.6 + rng.uniform(-0.15, 0.15), waviness=0.2 + rng.uniform(-0.1, 0.1), 
                                         steps=props.curve_resolution * 3, name=f"S{d}_{s}", twist_vary=0.2))

            for i in range(max(2, props.helix_count // props.domain_count)):
                for _ in range(5):
                    c = local_offset + rand_rot @ Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(-0.6, 0.6))) * domain_scale
                    if is_position_valid(c, centers, min_dist):
                        axis = rand_rot @ Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 1)).normalized()
                        centers.append(add_helix(c, axis, props.helix_radius * 1.1, props.helix_pitch, 
                                                 props.helix_turns, props.curve_resolution * 3, f"H{d}_{i}", noise=0.15))
                        break

        elif et == "LYASE":  
            main_path = [local_offset + rand_rot @ Vector((sin(t / (props.curve_resolution * 4 - 1) * pi) * 2.2,
                                                           cos(t / (props.curve_resolution * 4 - 1) * pi * 0.6) * 1.7,
                                                           t / (props.curve_resolution * 4 - 1) * 2.0 - 1.0)) * domain_scale
                         for t in range(props.curve_resolution * 4)]
            for i, p in enumerate(main_path[1:-1]): 
                main_path[i+1] += Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08))) * domain_scale
            main_curve = new_curve(f"LyaseBackbone_{d}", main_path, props.curve_resolution, parent)
            set_bevel_object(main_curve, tube_prof_loop, props.bevel_resolution); set_material(main_curve, mat)
            main_curve.parent = parent
            centers.append(local_offset)

            for s in range(props.sheet_count):
                for _ in range(5):
                    oz = (s - props.sheet_count / 2) * 0.7
                    a = local_offset + rand_rot @ Vector((-1.1, 0, oz)) * domain_scale
                    b = local_offset + rand_rot @ Vector((1.1, 0, oz)) * domain_scale
                    c = (a + b) * 0.5
                    if is_position_valid(c, centers, min_dist):
                        centers.append(add_sheet(a, b, bow=0.5 + rng.uniform(-0.15, 0.15), waviness=0.3 + rng.uniform(-0.1, 0.1), 
                                                 steps=props.curve_resolution * 3, name=f"S{d}_{s}", twist_vary=0.25))
                        break

            for i in range(max(2, props.helix_count // props.domain_count)):
                pos_idx = int((i + 1) * len(main_path) / (props.helix_count + 2))
                base = main_path[pos_idx]
                for _ in range(5):
                    c = base + rand_rot @ Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3))) * domain_scale
                    if is_position_valid(c, centers, min_dist):
                        axis = rand_rot @ Vector((rng.uniform(-0.3, 0.3), 1.0, rng.uniform(-0.3, 0.3))).normalized()
                        centers.append(add_helix(c, axis, props.helix_radius * 0.9, props.helix_pitch * 1.2, 
                                                 props.helix_turns * 1.4, props.curve_resolution * 3, f"H{d}_{i}", noise=0.1))
                        break

        elif et == "ISOMERASE":  
            for s in range(props.sheet_count):
                angle = s * (tau / max(1, props.sheet_count))
                a = local_offset + rand_rot @ Vector((cos(angle) * 1.5, sin(angle) * 1.5, -0.7)) * domain_scale
                b = local_offset + rand_rot @ Vector((cos(angle + 0.2) * 1.5, sin(angle + 0.2) * 1.5, 0.7)) * domain_scale
                centers.append(add_sheet(a, b, bow=0.6 + rng.uniform(-0.15, 0.15), waviness=0.3 + rng.uniform(-0.1, 0.1), 
                                         steps=props.curve_resolution * 3, name=f"S{d}_{s}", twist_vary=0.25))

            for _ in range(5):
                c = local_offset
                if is_position_valid(c, centers, min_dist):
                    axis = rand_rot @ Vector((0, 0, 1)).normalized()
                    centers.append(add_helix(c, axis, props.helix_radius * 1.2, props.helix_pitch * 0.8, 
                                             props.helix_turns * 0.6, props.curve_resolution * 3, f"H{d}_core", noise=0.1))
                    break

        elif et == "LIGASE":  
            for s in range(props.sheet_count):
                oy = (s - props.sheet_count / 2) * 0.5
                a = local_offset + rand_rot @ Vector((-1.2, oy, rng.uniform(-0.3, 0.3))) * domain_scale
                b = local_offset + rand_rot @ Vector((1.2, oy, rng.uniform(-0.3, 0.3))) * domain_scale
                centers.append(add_sheet(a, b, bow=0.4 + rng.uniform(-0.15, 0.15), waviness=0.2 + rng.uniform(-0.1, 0.1), 
                                         steps=props.curve_resolution * 3, name=f"S{d}_{s}", twist_vary=0.2))

            for i in range(max(1, props.helix_count // props.domain_count)):
                for _ in range(5):
                    c = local_offset + rand_rot @ Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), i * 0.8)) * domain_scale
                    if is_position_valid(c, centers, min_dist):
                        axis = rand_rot @ Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 1)).normalized()
                        centers.append(add_helix(c, axis, props.helix_radius * 0.8, props.helix_pitch * 1.1, 
                                                 props.helix_turns * 0.9, props.curve_resolution * 3, f"H{d}_{i}", noise=0.12))
                        break

    random.shuffle(created_endpoints)
    cf, slack = 1.5 - props.compactness, props.loop_slack * (1.5 - props.compactness)
    for i in range(len(created_endpoints) - 1):
        a, b = created_endpoints[i][1], created_endpoints[i + 1][0]
        add_loop_path(a, b, steps=int(props.curve_resolution * (1.3 + (1 - props.compactness))), name=f"L{i:02d}", slack=slack + rng.uniform(-0.15, 0.15))

# ----------------------------------------------------------
# BUILD / REBUILD WRAPPERS
# ----------------------------------------------------------

def clear_children(obj):
    for ch in list(obj.children):
        try:
            [col.objects.unlink(ch) for col in getattr(ch, "users_collection", []) if ch in col.objects]
            bpy.data.objects.remove(ch, do_unlink=True)
        except ReferenceError: pass
        except Exception as e: print(f"Could not remove {getattr(ch, 'name', '?')}: {e}")

def build_enzyme_parent(name):
    parent = bpy.data.objects.new(name, None)
    parent.empty_display_type = 'SPHERE'
    bpy.context.collection.objects.link(parent)
    return parent

def build_master_container(props):
    base_name = f"{props.enzyme_type}_Master"
    master = bpy.data.objects.get(base_name)
    if not master:
        master = bpy.data.objects.new(base_name, None)
        master.empty_display_type = 'SPHERE'
        bpy.context.collection.objects.link(master)
    master["enzyme_master"] = True
    return master

def safe_remove(obj):
    if not obj: return
    try:
        [col.objects.unlink(obj) for col in getattr(obj, "users_collection", []) if obj in col.objects]
        bpy.data.objects.remove(obj, do_unlink=True)
    except ReferenceError: pass
    except Exception as e: print(f"Could not remove {getattr(obj, 'name', '?')}: {e}")
        
def purge_orphaned_curves():
    bpy.context.view_layer.update(); removed = 0
    for cu in list(bpy.data.curves):
        if cu.users == 0:
            try: bpy.data.curves.remove(cu); removed += 1
            except Exception as e: print(f"Failed to remove curve {cu.name}: {e}")
    if removed: print(f"🧹 Purged {removed} orphaned curve datablock(s).")
    
def get_selected_enzyme(context):
    obj = context.object
    if not obj or not obj.select_get():
        return None
    if obj.type == "EMPTY" and obj.get("enzyme"):
        return obj
    if obj.parent and obj.parent.get("enzyme"):
        return obj.parent
    if "_Master" in obj.name:
        for c in obj.children:
            if c.get("enzyme"):
                return c
    return None

def get_selected_master(context):
    obj = context.object
    if not obj or not obj.select_get():
        return None
    if "_Master" in obj.name:
        return obj
    if obj.get("enzyme") and obj.parent and "_Master" in obj.parent.name:
        return obj.parent
    if obj.parent and obj.parent.get("enzyme") and obj.parent.parent and "_Master" in obj.parent.parent.name:
        return obj.parent.parent
    return None

def rebuild_selected_enzyme(obj, props):
    if not obj or obj.type != 'EMPTY' or "enzyme" not in obj: return
    clear_children(obj)
    t_h, t_l, rib = ensure_profiles(props.tube_radius, props.loop_radius, props.ribbon_width, props.sheet_thickness, props.helix_elongation)
    mat = get_or_make_material(f"{props.enzyme_type}_Mat", class_color(props.enzyme_type))
    build_fold_for_class(obj, props, t_h, t_l, rib, mat)
    obj.name, obj["enzyme_type"] = f"{props.enzyme_type}_Enzyme", props.enzyme_type
    
# ----------------------------------------------------------
# LIVE UPDATE
# ----------------------------------------------------------

def _maybe_rebuild(self,context):
    if not getattr(self,"rebuild_live",True):return
    e=get_selected_enzyme(context);m=get_selected_master(context)
    if not e or not m:return
    base=f"{self.enzyme_type}"
    if not m.name.startswith(base):m.name=f"{base}_Master"
    if not e.name.startswith(base):e.name=f"{base}_Enzyme"
    mc=None
    for c in e.children:
        if c.name.startswith(base+"_Mesh") or c.name.endswith("_Mesh"):mc=c;break
    if not mc:
        mc=bpy.data.objects.new(f"{base}_Mesh",None)
        bpy.context.scene.collection.objects.link(mc);mc.parent=e
    else:
        for ch in list(mc.children):
            try:bpy.data.objects.remove(ch,do_unlink=True)
            except:pass
    for o in list(bpy.data.objects):
        if o.parent==m and o.name.startswith(("EG_TubeProfile_","EG_RibbonProfile_")):
            try:bpy.data.objects.remove(o,do_unlink=True)
            except:pass
    t_h,t_l,rib=ensure_profiles(self.tube_radius,self.loop_radius,self.ribbon_width,self.sheet_thickness,self.helix_elongation,parent=m)
    mat=bpy.data.materials.get(f"{base}_Mat") or get_or_make_material(f"{base}_Mat",class_color(base))
    build_fold_for_class(mc,self,t_h,t_l,rib,mat)
    e["enzyme"]=True;e["enzyme_type"]=self.enzyme_type
    bpy.context.view_layer.update();purge_orphaned_curves()
    
# ----------------------------------------------------------
# PROPERTIES 
# ----------------------------------------------------------

class EG_Props(bpy.types.PropertyGroup):
    rebuild_live: bpy.props.BoolProperty(name="Live Update", description="Automatically rebuild enzyme when parameters change", default=True)
    enzyme_type: bpy.props.EnumProperty(
        name="Class",
        items=[
            ("HYDROLASE", "Hydrolase", ""),
            ("OXIDOREDUCTASE", "Oxidoreductase", ""),
            ("TRANSFERASE", "Transferase", ""),
            ("LYASE", "Lyase", ""),
            ("ISOMERASE", "Isomerase", ""),
            ("LIGASE", "Ligase", ""),
        ],
        default="HYDROLASE",
        update=_maybe_rebuild)

    size: bpy.props.FloatProperty(name="Size", default=3.0, min=0.5, max=12.0, subtype='FACTOR', update=_maybe_rebuild)
    compactness: bpy.props.FloatProperty(name="Compactness", default=0.5, min=0.0, max=1.0, subtype='FACTOR', update=_maybe_rebuild)
    domain_count: bpy.props.IntProperty(name="Domains", default=5, min=2, max=12, subtype='FACTOR', update=_maybe_rebuild)
    random_seed: bpy.props.IntProperty(name="Seed", default=2025, min=0, max=100000, subtype='FACTOR', update=_maybe_rebuild)

    helix_count: bpy.props.IntProperty(name="Helices", default=8, min=2, max=32, subtype='FACTOR', update=_maybe_rebuild)
    helix_radius: bpy.props.FloatProperty(name="Helix Radius", default=0.2, min=0.02, max=0.5, subtype='FACTOR', update=_maybe_rebuild)
    helix_pitch: bpy.props.FloatProperty(name="Helix Pitch", default=0.5, min=0.03, max=1.0, subtype='FACTOR', update=_maybe_rebuild)
    helix_turns: bpy.props.FloatProperty(name="Helix Turns", default=6.0, min=2.0, max=15.0, subtype='FACTOR', update=_maybe_rebuild)
    helix_elongation: bpy.props.FloatProperty(name="Helix Elongation", default=1.6, min=1.0, max=2.0, subtype='FACTOR', update=_maybe_rebuild)

    tube_radius: bpy.props.FloatProperty(name="Tube Radius", default=0.05, min=0.005, max=0.15, subtype='FACTOR', update=_maybe_rebuild)
    ribbon_width: bpy.props.FloatProperty(name="Ribbon Width", default=0.3, min=0.02, max=0.7, subtype='FACTOR', update=_maybe_rebuild)
    curve_resolution: bpy.props.IntProperty(name="Curve Resolution", default=18, min=6, max=36, subtype='FACTOR', update=_maybe_rebuild)
    bevel_resolution: bpy.props.IntProperty(name="Bevel Resolution", default=6, min=2, max=10, subtype='FACTOR', update=_maybe_rebuild)

    sheet_count: bpy.props.IntProperty(name="Sheets", default=5, min=1, max=16, subtype='FACTOR', update=_maybe_rebuild)
    sheet_thickness: bpy.props.FloatProperty(name="Sheet Thickness", default=0.04, min=0.002, max=0.1, subtype='FACTOR', update=_maybe_rebuild)
    sheet_twist: bpy.props.FloatProperty(name="Sheet Twist", default=1.0, min=0.0, max=2.0, subtype='FACTOR', update=_maybe_rebuild)

    loop_slack: bpy.props.FloatProperty(name="Loop Slack", default=0.8, min=0.0, max=1.5, subtype='FACTOR', update=_maybe_rebuild)
    loop_radius: bpy.props.FloatProperty(name="Loop Radius", default=0.04, min=0.005, max=0.12, subtype='FACTOR', update=_maybe_rebuild)

# ----------------------------------------------------------
# OPERATOR
# ----------------------------------------------------------

class EG_OT_generate(bpy.types.Operator):
    bl_idname, bl_label, bl_options = "mesh.eg_generate_enzyme", "Generate Enzyme", {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        p = context.scene.eg_props

        base_master = f"{p.enzyme_type}_Master"
        name_master = base_master
        idx = 1
        while bpy.data.objects.get(name_master):
            name_master = f"{base_master}.{idx:03d}"
            idx += 1
        m = bpy.data.objects.new(name_master, None)
        m.empty_display_type = 'SPHERE'
        bpy.context.collection.objects.link(m)

        e = bpy.data.objects.new(f"{p.enzyme_type}_Enzyme", None)
        e.empty_display_type = 'SPHERE'
        e.parent = m
        e["enzyme"] = True
        bpy.context.collection.objects.link(e)

        mc = bpy.data.objects.new(f"{p.enzyme_type}_Mesh", None)
        mc.parent = e
        bpy.context.collection.objects.link(mc)

        t_h, t_l, rib = ensure_profiles(
            p.tube_radius, p.loop_radius, p.ribbon_width,
            p.sheet_thickness, p.helix_elongation, parent=m
        )
        mat = bpy.data.materials.get(f"{p.enzyme_type}_Mat") or get_or_make_material(
            f"{p.enzyme_type}_Mat", class_color(p.enzyme_type)
        )
        build_fold_for_class(mc, p, t_h, t_l, rib, mat)

        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = e
        e.select_set(True)

        self.report({'INFO'}, f"Generated {name_master}")
        return {'FINISHED'}
    
class EG_OT_delete_selected(bpy.types.Operator):
    bl_idname,bl_label,bl_options="mesh.eg_delete_selected_enzyme","Delete Selected Enzyme",{"REGISTER","UNDO"}
    def execute(self,context):
        m=get_selected_master(context)
        if not m: self.report({'WARNING'},"Select a master or its enzyme"); return {'CANCELLED'}
        m_name=m.name
        names=set()
        def collect(o):
            if o and o.name not in names:
                names.add(o.name)
                for c in list(o.children): collect(c)
        collect(m)
        for n in sorted(names,reverse=True):
            o=bpy.data.objects.get(n)
            if not o: continue
            for col in bpy.data.collections:
                if o.name in col.objects: col.objects.unlink(o)
            try: bpy.data.objects.remove(o,do_unlink=True)
            except: pass
        bpy.context.view_layer.update(); purge_orphaned_curves()
        self.report({'INFO'},f"Deleted enzyme: {m_name}")
        return {'FINISHED'}
    
class EG_OT_update_enzyme(bpy.types.Operator):
    bl_idname, bl_label, bl_options = "mesh.eg_update_enzyme", "Update Enzyme", {"REGISTER", "UNDO"}

    def execute(self, context):
        p = context.scene.eg_props
        e = get_selected_enzyme(context)
        m = get_selected_master(context)
        if not e or not m:
            self.report({'WARNING'}, "Select an enzyme or its master")
            return {'CANCELLED'}

        base = f"{p.enzyme_type}"
        if not m.name.startswith(base):
            m.name = f"{base}_Master"
        if not e.name.startswith(base):
            e.name = f"{base}_Enzyme"

        mc = None
        for c in e.children:
            if c.name.startswith(f"{base}_Mesh"):
                mc = c
                break

        if not mc:
            mc_name = f"{base}_Mesh"
            while bpy.data.objects.get(mc_name):
                mc_name = f"{base}_Mesh.{len([o for o in bpy.data.objects if o.name.startswith(f'{base}_Mesh')]):03d}"
            mc = bpy.data.objects.new(mc_name, None)
            (e.users_collection[0] if e.users_collection else bpy.context.collection).objects.link(mc)
            mc.parent = e

        for ch in list(mc.children):
            try:
                [col.objects.unlink(ch) for col in getattr(ch, "users_collection", []) if ch in col.objects]
                bpy.data.objects.remove(ch, do_unlink=True)
            except Exception:
                pass
        for o in list(bpy.data.objects):
            if o.parent == mc and o.type == 'CURVE':
                try:
                    bpy.data.objects.remove(o, do_unlink=True)
                except Exception:
                    pass

        for o in list(bpy.data.objects):
            if o.parent == m and o.name.startswith(("EG_TubeProfile_", "EG_RibbonProfile_")):
                try:
                    bpy.data.objects.remove(o, do_unlink=True)
                except Exception:
                    pass

        t_h, t_l, rib = ensure_profiles(
            p.tube_radius, p.loop_radius, p.ribbon_width,
            p.sheet_thickness, p.helix_elongation, parent=m
        )
        mat = bpy.data.materials.get(f"{base}_Mat") or get_or_make_material(
            f"{base}_Mat", class_color(base)
        )
        build_fold_for_class(mc, p, t_h, t_l, rib, mat)

        e.name, e["enzyme"] = f"{base}_Enzyme", True
        e["enzyme_type"] = p.enzyme_type
        bpy.context.view_layer.update()
        purge_orphaned_curves()

        self.report({'INFO'}, f"Updated: {e.name}")
        return {'FINISHED'}
    
class EG_OT_reset_settings(bpy.types.Operator):
    bl_idname = "mesh.eg_reset_enzyme_settings"
    bl_label = "Reset Settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.eg_props
        old_live = props.rebuild_live 

        for prop_name, prop_def in EG_Props.__annotations__.items():
            rna_prop = EG_Props.bl_rna.properties.get(prop_name)
            if rna_prop and hasattr(props, prop_name):
                default_value = rna_prop.default
                setattr(props, prop_name, default_value)

        props.rebuild_live = old_live

        self.report({'INFO'}, "Enzyme Generator settings reset to defaults")
        return {'FINISHED'}

# ----------------------------------------------------------
# UI
# ----------------------------------------------------------

class VIEW3D_PT_enzyme_generator(bpy.types.Panel):
    bl_label = "Enzyme"
    bl_idname = "VIEW3D_PT_enzyme_generator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Enzyme"

    def draw(self, context):
        if relay_updater:
            relay_updater.draw(self.layout)
        layout = self.layout
        p = context.scene.eg_props
        o = context.object

        layout.operator("mesh.eg_generate_enzyme", text="Generate Enzyme", icon="MOD_ENVELOPE")

        row = layout.row(align=True)
        row.prop(p, "rebuild_live", toggle=True)
        row.operator("mesh.eg_reset_enzyme_settings", text="Reset", icon="LOOP_BACK")

        if not p.rebuild_live:
            layout.operator("mesh.eg_update_enzyme", text="Update Enzyme", icon="FILE_REFRESH")

        layout.separator(factor=0.6)

        layout.prop(p, "enzyme_type", text="Type")
        layout.prop(p, "size")
        layout.prop(p, "compactness")
        layout.prop(p, "domain_count")
        layout.prop(p, "random_seed")

        layout.separator(factor=0.5)

        layout.prop(p, "helix_count")
        layout.prop(p, "helix_radius")
        layout.prop(p, "helix_pitch")
        layout.prop(p, "helix_turns")
        layout.prop(p, "helix_elongation")

        layout.separator(factor=0.5)

        layout.prop(p, "sheet_count")
        layout.prop(p, "sheet_twist")
        layout.prop(p, "sheet_thickness")

        layout.separator(factor=0.5)

        layout.prop(p, "loop_radius")
        layout.prop(p, "loop_slack")

        layout.separator(factor=0.5)

        layout.prop(p, "tube_radius")
        layout.prop(p, "ribbon_width")

        layout.separator(factor=0.5)

        layout.prop(p, "curve_resolution")
        layout.prop(p, "bevel_resolution")

        layout.separator(factor=0.6)

        is_editing = False
        editing_name = None

        if o and o.select_get():
            if o.type == "EMPTY" and "enzyme" in o:
                if o.parent and "_Master" in o.parent.name:
                    is_editing, editing_name = True, o.parent.name

            elif o.parent and "enzyme" in o.parent:
                if o.parent.parent and "_Master" in o.parent.parent.name:
                    is_editing, editing_name = True, o.parent.parent.name

            elif "_Master" in o.name:
                is_editing, editing_name = True, o.name

        if is_editing:
            layout.operator("mesh.eg_delete_selected_enzyme", text="Delete Enzyme", icon="TRASH")
            layout.separator(factor=0.3)
            layout.label(text=f"Editing: {editing_name}", icon="MOD_ENVELOPE")
        else:
            layout.label(text="No enzyme selected", icon="INFO")

# ----------------------------------------------------------
# REGISTER
# ----------------------------------------------------------

classes = (
    EG_Props,
    EG_OT_generate,
    EG_OT_delete_selected,
    EG_OT_update_enzyme,
    EG_OT_reset_settings,
    VIEW3D_PT_enzyme_generator,  
)

def register():
    if relay_updater:
        relay_updater.register("blender-enzyme")
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.eg_props = bpy.props.PointerProperty(type=EG_Props)

def unregister():
    if relay_updater:
        relay_updater.unregister()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.eg_props

if __name__ == "__main__":
    register()
