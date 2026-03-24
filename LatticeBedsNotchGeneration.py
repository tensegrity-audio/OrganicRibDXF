import adsk.core
import adsk.fusion


def collect_modeled_notches(
    x_slices,
    y_slices,
    edge_margin: float,
    min_interval_height: float,
    body_z_mid: float,
    find_best_shared_interval,
    notch_instruction_type,
    x_rib_notches_open_from_top: bool,
    y_rib_notches_open_from_top: bool,
):
    for xs in x_slices:
        xs.modeled_notches = []
    for ys in y_slices:
        ys.modeled_notches = []

    for xs in x_slices:
        for ys in y_slices:
            x_probe = ys.offset
            y_probe = xs.offset
            interval = find_best_shared_interval(xs, x_probe, ys, y_probe, edge_margin, min_interval_height, body_z_mid)
            if not interval:
                continue
            xs.modeled_notches.append(notch_instruction_type(x_probe, interval[0], interval[1], x_rib_notches_open_from_top, xs.offset, ys.offset))
            ys.modeled_notches.append(notch_instruction_type(y_probe, interval[0], interval[1], y_rib_notches_open_from_top, xs.offset, ys.offset))


def apply_modeled_half_laps(comp, slices, thickness: float, slot_width: float, edge_margin: float, keep_tool_bodies: bool, eps: float):
    for slice_info in slices:
        if not slice_info.rib_body or not slice_info.modeled_notches:
            continue
        notch_sketch = comp.sketches.add(slice_info.plane)
        notch_sketch.name = f'{slice_info.label}_notches'
        notch_sketch.areProfilesShown = True
        slice_info.notch_sketch = notch_sketch

        profile_count_before = count_sketch_profiles(notch_sketch)
        for instr in slice_info.modeled_notches:
            slot_points = build_slice_slot_points(slice_info, instr, slot_width, eps)
            if not slot_points:
                continue
            add_closed_polyline(notch_sketch, slot_points)

        cut_new_notch_profiles(comp, slice_info, thickness, keep_tool_bodies, profile_count_before)


def count_sketch_profiles(sketch) -> int:
    try:
        return sketch.profiles.count
    except:
        return 0


def cut_new_notch_profiles(comp, slice_info, half_depth: float, keep_tool_bodies: bool, profile_count_before: int):
    if not slice_info.notch_sketch or not slice_info.rib_body:
        return

    profiles = []
    try:
        for i in range(profile_count_before, slice_info.notch_sketch.profiles.count):
            profile = slice_info.notch_sketch.profiles.item(i)
            if profile:
                profiles.append(profile)
    except:
        pass

    if not profiles:
        try:
            for i in range(slice_info.notch_sketch.profiles.count):
                profile = slice_info.notch_sketch.profiles.item(i)
                if profile:
                    profiles.append(profile)
        except:
            return

    extrudes = comp.features.extrudeFeatures
    combine_features = comp.features.combineFeatures

    for profile in profiles:
        tool_body = None
        try:
            ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            ext_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(half_depth), True)
            ext = extrudes.add(ext_input)
            if ext and ext.bodies and ext.bodies.count > 0:
                tool_body = adsk.fusion.BRepBody.cast(ext.bodies.item(0))
        except:
            tool_body = None

        if not tool_body:
            continue

        try:
            tools = adsk.core.ObjectCollection.create()
            tools.add(tool_body)
            combine_input = combine_features.createInput(slice_info.rib_body, tools)
            combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine_input.isKeepToolBodies = keep_tool_bodies
            combine_features.add(combine_input)
        except:
            pass


def add_geometry_aware_notches_to_layout(
    layout_sketch,
    x_slices,
    y_slices,
    slot_width: float,
    edge_margin: float,
    min_interval_height: float,
    body_z_mid: float,
    draw_centerlines: bool,
    find_best_shared_interval,
    eps: float,
    x_rib_notches_open_from_top: bool,
    y_rib_notches_open_from_top: bool,
):
    for xs in x_slices:
        if xs.layout_origin is None:
            continue
        for ys in y_slices:
            if ys.layout_origin is None:
                continue
            x_probe = ys.offset
            y_probe = xs.offset
            interval = find_best_shared_interval(xs, x_probe, ys, y_probe, edge_margin, min_interval_height, body_z_mid)
            if not interval:
                continue
            draw_layout_notch(layout_sketch, xs, x_probe, interval, slot_width, x_rib_notches_open_from_top, draw_centerlines, eps)
            draw_layout_notch(layout_sketch, ys, y_probe, interval, slot_width, y_rib_notches_open_from_top, draw_centerlines, eps)


def draw_layout_notch(layout_sketch, slice_info, cross_world: float, interval, slot_width: float, top_open: bool, draw_centerlines: bool, eps: float):
    if slice_info.layout_origin is None:
        return
    instr = _LayoutNotchInstruction(cross_world, interval[0], interval[1], top_open)
    slot_points = build_slice_slot_points(slice_info, instr, slot_width, eps)
    if not slot_points:
        return

    shifted_points = []
    for point in slot_points:
        shifted_points.append(adsk.core.Point3D.create(point.x + slice_info.layout_origin.x, point.y + slice_info.layout_origin.y, 0))

    add_closed_polyline(layout_sketch, shifted_points)
    if draw_centerlines:
        center_low = world_to_slice_sketch_point(slice_info, cross_world, interval[0])
        center_high = world_to_slice_sketch_point(slice_info, cross_world, interval[1])
        if center_low and center_high:
            layout_sketch.sketchCurves.sketchLines.addByTwoPoints(
                adsk.core.Point3D.create(center_low.x + slice_info.layout_origin.x, center_low.y + slice_info.layout_origin.y, 0),
                adsk.core.Point3D.create(center_high.x + slice_info.layout_origin.x, center_high.y + slice_info.layout_origin.y, 0),
            )


class _LayoutNotchInstruction:
    def __init__(self, x_probe: float, y0: float, y1: float, top_open: bool):
        self.x_probe = x_probe
        self.y0 = y0
        self.y1 = y1
        self.top_open = top_open


def build_slice_slot_points(slice_info, instr, slot_width: float, eps: float):
    z_mid = 0.5 * (instr.y0 + instr.y1)
    open_overshoot = max(eps * 10.0, slot_width * 0.02)
    cross0 = instr.x_probe - 0.5 * slot_width
    cross1 = instr.x_probe + 0.5 * slot_width

    boundary_z = find_slot_open_boundary(slice_info, cross0, cross1, z_mid, instr.top_open)
    if instr.top_open:
        z0 = z_mid
        z1 = boundary_z + open_overshoot
    else:
        z0 = boundary_z - open_overshoot
        z1 = z_mid

    if z1 - z0 <= eps:
        return None

    p1 = world_to_slice_sketch_point(slice_info, cross0, z0)
    p2 = world_to_slice_sketch_point(slice_info, cross1, z0)
    p3 = world_to_slice_sketch_point(slice_info, cross1, z1)
    p4 = world_to_slice_sketch_point(slice_info, cross0, z1)
    if not p1 or not p2 or not p3 or not p4:
        return None
    return [p1, p2, p3, p4]


def find_slot_open_boundary(slice_info, cross0: float, cross1: float, z_mid: float, top_open: bool) -> float:
    sample_count = 7
    best_value = None
    for i in range(sample_count):
        t = i / float(sample_count - 1) if sample_count > 1 else 0.5
        cross = cross0 + (cross1 - cross0) * t
        interval = find_interval_covering_z(slice_info, cross, z_mid)
        if not interval:
            continue
        candidate = interval[1] if top_open else interval[0]
        if best_value is None:
            best_value = candidate
        elif top_open and candidate > best_value:
            best_value = candidate
        elif (not top_open) and candidate < best_value:
            best_value = candidate

    if best_value is not None:
        return best_value
    return z_mid


def find_interval_covering_z(slice_info, cross: float, z_ref: float):
    intersections = vertical_intersections_from_polylines(slice_info.sampled_polylines, cross)
    if len(intersections) < 2:
        return None

    best_interval = None
    best_distance = None
    for i in range(0, len(intersections) - 1, 2):
        z0 = intersections[i]
        z1 = intersections[i + 1]
        if z_ref >= z0 and z_ref <= z1:
            return (z0, z1)
        mid = 0.5 * (z0 + z1)
        distance = abs(mid - z_ref)
        if best_interval is None or distance < best_distance:
            best_interval = (z0, z1)
            best_distance = distance
    return best_interval


def world_to_slice_sketch_point(slice_info, cross_world: float, z_world: float):
    try:
        if slice_info.family == 'X':
            world_point = adsk.core.Point3D.create(slice_info.offset, cross_world, z_world)
        else:
            world_point = adsk.core.Point3D.create(cross_world, slice_info.offset, z_world)
        sketch_point = slice_info.sketch.modelToSketchSpace(world_point)
        return adsk.core.Point3D.create(sketch_point.x, sketch_point.y, 0)
    except:
        return None


def add_closed_polyline(sketch, points):
    if not points or len(points) < 3:
        return
    lines = sketch.sketchCurves.sketchLines
    for i in range(len(points)):
        lines.addByTwoPoints(points[i], points[(i + 1) % len(points)])


def vertical_intersections_from_polylines(polylines, cross: float):
    hits = []
    for poly in polylines:
        points = poly.points
        if len(points) < 2:
            continue
        for i in range(len(points) - 1):
            p0 = points[i]
            p1 = points[i + 1]
            x0, z0 = p0.x, p0.y
            x1, z1 = p1.x, p1.y
            if abs(x1 - x0) < 1e-6:
                if abs(cross - x0) < 1e-6:
                    hits.append(z0)
                    hits.append(z1)
                continue
            xmin = min(x0, x1)
            xmax = max(x0, x1)
            if cross < xmin - 1e-6 or cross > xmax + 1e-6:
                continue
            t = (cross - x0) / (x1 - x0)
            if t < -1e-6 or t > 1.0 + 1e-6:
                continue
            hits.append(z0 + t * (z1 - z0))
    hits.sort()
    return dedupe_sorted_values(hits, tol=1e-4)


def dedupe_sorted_values(values, tol: float):
    if not values:
        return []
    out = [values[0]]
    for value in values[1:]:
        if abs(value - out[-1]) > tol:
            out.append(value)
    return out
