import adsk.core
import adsk.fusion
import time
from dataclasses import dataclass
from typing import Any, List, Optional

EPS = 1e-6
BED_LABEL_PREFIX = 'BED'


def _log(message: str):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface if app else None
        if not ui:
            return
        palette = ui.palettes.itemById('TextCommands')
        if palette:
            palette.isVisible = True
            palette.writeText('[LatticeBedsPagedDxf] ' + message)
    except:
        pass


@dataclass
class BedPlacement:
    bed_index: int
    origin_x: float
    origin_y: float
    inner_x: float
    inner_y: float
    inner_width: float
    inner_height: float


@dataclass
class GeometryBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def layout_slices_into_beds(layout_sketch: adsk.fusion.Sketch, slices: List[Any], part_gap: float, text_height: float, bed_width: float, bed_height: float, bed_margin: float, bed_gap: float, arrange_on_beds: bool, draw_bed_outlines: bool) -> List[BedPlacement]:
    if not slices:
        return []
    inner_width = bed_width - 2.0 * bed_margin
    inner_height = bed_height - 2.0 * bed_margin
    if inner_width <= 0 or inner_height <= 0:
        raise RuntimeError('Bed width/height must be larger than twice the bed margin.')
    placements: List[BedPlacement] = []
    bed_index = 1
    current_bed_origin_x = 0.0
    current_bed_origin_y = 0.0

    for slice_info in slices:
        source_sketch = get_layout_source_sketch(slice_info)
        bounds = get_curve_bounds(source_sketch)
        width = max(EPS, bounds.max_x - bounds.min_x)
        height = max(EPS, bounds.max_y - bounds.min_y)

        if width > inner_width + EPS or height > inner_height + EPS:
            raise RuntimeError(f'Slice {slice_info.label} is too large for the bed. Increase bed size or spacing.')

        bed = BedPlacement(
            bed_index=bed_index,
            origin_x=current_bed_origin_x,
            origin_y=current_bed_origin_y,
            inner_x=current_bed_origin_x + bed_margin,
            inner_y=current_bed_origin_y + bed_margin,
            inner_width=inner_width,
            inner_height=inner_height,
        )
        placements.append(bed)

        target_origin = adsk.core.Point3D.create(
            bed.inner_x + 0.5 * (bed.inner_width - width) - bounds.min_x,
            bed.inner_y + 0.5 * (bed.inner_height - height) - bounds.min_y,
            0,
        )
        part_t0 = time.perf_counter()
        _log(f'Layout draw start: {slice_info.label}')
        copy_sketch_into_layout(slice_info, source_sketch, layout_sketch, target_origin)
        _log(f'Layout draw finish: {slice_info.label} in {time.perf_counter() - part_t0:.2f}s')
        label_t0 = time.perf_counter()
        _log(f'Label start: {slice_info.label}')
        add_label_top_left(layout_sketch, slice_info.label, bed, text_height)
        _log(f'Label finish: {slice_info.label} in {time.perf_counter() - label_t0:.2f}s')

        slice_info.layout_origin = target_origin
        slice_info.placed_bed_index = bed_index

        bed_index += 1
        if arrange_on_beds:
            current_bed_origin_y += bed_height + bed_gap
        else:
            current_bed_origin_x += bed_width + bed_gap

    if draw_bed_outlines:
        for bed in placements:
            bed_t0 = time.perf_counter()
            _log(f'Bed outline start: {bed.bed_index:02d}')
            draw_bed_outline(layout_sketch, bed, bed_width, bed_height, text_height)
            _log(f'Bed outline finish: {bed.bed_index:02d} in {time.perf_counter() - bed_t0:.2f}s')
    return placements


def get_layout_polylines(slice_info: Any):
    polylines = getattr(slice_info, 'export_polylines', None)
    if polylines:
        return polylines
    polylines = getattr(slice_info, 'sampled_polylines', None)
    if polylines:
        return polylines
    raise RuntimeError(f'Slice {slice_info.label} has no layout polylines.')


def get_polyline_bounds(polylines) -> GeometryBounds:
    min_x = min(point.x for poly in polylines for point in poly.points)
    min_y = min(point.y for poly in polylines for point in poly.points)
    max_x = max(point.x for poly in polylines for point in poly.points)
    max_y = max(point.y for poly in polylines for point in poly.points)
    return GeometryBounds(min_x, min_y, max_x, max_y)


def get_layout_source_sketch(slice_info: Any):
    export_sketch = getattr(slice_info, 'export_sketch', None)
    return export_sketch if export_sketch else slice_info.sketch


def get_curve_bounds(sketch: adsk.fusion.Sketch) -> GeometryBounds:
    minx, miny, maxx, maxy = None, None, None, None
    try:
        for curve in sketch.sketchCurves:
            bb = curve.boundingBox
            minx = bb.minPoint.x if minx is None else min(minx, bb.minPoint.x)
            miny = bb.minPoint.y if miny is None else min(miny, bb.minPoint.y)
            maxx = bb.maxPoint.x if maxx is None else max(maxx, bb.maxPoint.x)
            maxy = bb.maxPoint.y if maxy is None else max(maxy, bb.maxPoint.y)
    except:
        pass
    if minx is None:
        bb = sketch.boundingBox
        return GeometryBounds(bb.minPoint.x, bb.minPoint.y, bb.maxPoint.x, bb.maxPoint.y)
    return GeometryBounds(minx, miny, maxx, maxy)


def copy_sketch_into_layout(slice_info: Any, source_sketch: adsk.fusion.Sketch, layout_sketch: adsk.fusion.Sketch, target_origin: adsk.core.Point3D):
    coll = adsk.core.ObjectCollection.create()
    try:
        for curve in source_sketch.sketchCurves:
            coll.add(curve)
    except:
        pass
    if coll.count == 0:
        return
    copied = layout_sketch.copy(coll, adsk.core.Matrix3D.create())
    moved = adsk.core.ObjectCollection.create()
    minx, miny, maxx, maxy = None, None, None, None
    try:
        for i in range(copied.count):
            entity = copied.item(i)
            curve = adsk.fusion.SketchCurve.cast(entity)
            if not curve:
                continue
            moved.add(curve)
            bb = curve.boundingBox
            minx = bb.minPoint.x if minx is None else min(minx, bb.minPoint.x)
            miny = bb.minPoint.y if miny is None else min(miny, bb.minPoint.y)
            maxx = bb.maxPoint.x if maxx is None else max(maxx, bb.maxPoint.x)
            maxy = bb.maxPoint.y if maxy is None else max(maxy, bb.maxPoint.y)
    except:
        return
    if moved.count == 0 or minx is None or miny is None or maxx is None or maxy is None:
        return

    rotation_angle = get_layout_rotation_angle(slice_info)
    if abs(rotation_angle) > EPS:
        center_x = 0.5 * (minx + maxx)
        center_y = 0.5 * (miny + maxy)
        rotation = adsk.core.Matrix3D.create()
        rotation.setToRotation(rotation_angle, adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(center_x, center_y, 0))
        try:
            layout_sketch.move(moved, rotation)
        except:
            pass

        minx, miny = None, None
        try:
            for i in range(moved.count):
                curve = adsk.fusion.SketchCurve.cast(moved.item(i))
                if not curve:
                    continue
                bb = curve.boundingBox
                minx = bb.minPoint.x if minx is None else min(minx, bb.minPoint.x)
                miny = bb.minPoint.y if miny is None else min(miny, bb.minPoint.y)
        except:
            return
        if minx is None or miny is None:
            return

    translation = adsk.core.Matrix3D.create()
    translation.translation = adsk.core.Vector3D.create(target_origin.x - minx, target_origin.y - miny, 0)
    layout_sketch.move(moved, translation)


def get_layout_rotation_angle(slice_info: Any) -> float:
    family = getattr(slice_info, 'family', '')
    if family == 'X':
        return -0.5 * 3.141592653589793
    if family == 'Y':
        return 3.141592653589793
    return 0.0


def add_label_top_left(sketch: adsk.fusion.Sketch, text: str, bed: BedPlacement, text_height: float):
    add_label(
        sketch,
        text,
        bed.inner_x + text_height * 0.25,
        bed.origin_y + bed.inner_height + (bed.inner_y - bed.origin_y) - text_height * 0.35,
        text_height,
    )


def draw_bed_outline(sketch: adsk.fusion.Sketch, bed: BedPlacement, bed_width: float, bed_height: float, text_height: float):
    add_rect(sketch, bed.origin_x, bed.origin_y, bed.origin_x + bed_width, bed.origin_y + bed_height, construction=True)
    add_label(sketch, f'{BED_LABEL_PREFIX} {bed.bed_index:02d}', bed.origin_x + text_height * 0.5, bed.origin_y + bed_height - text_height * 1.7, text_height)


def add_label(sketch: adsk.fusion.Sketch, text: str, x: float, y: float, text_height: float):
    texts = sketch.sketchTexts
    corner = adsk.core.Point3D.create(x, y, 0)
    diagonal = adsk.core.Point3D.create(x + text_height * max(6, len(text) * 0.7), y + text_height * 1.8, 0)
    input_ = texts.createInput2(text, text_height)
    input_.setAsMultiLine(
        corner,
        diagonal,
        adsk.core.HorizontalAlignments.LeftHorizontalAlignment,
        adsk.core.VerticalAlignments.TopVerticalAlignment,
        0.0,
    )
    texts.add(input_)


def choose_export_path(default_name: str) -> Optional[str]:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    if not ui:
        return None
    dlg = ui.createFileDialog()
    dlg.title = 'Export lattice beds DXF'
    dlg.filter = 'DXF Files (*.dxf)'
    dlg.filterIndex = 0
    dlg.initialFilename = default_name
    if dlg.showSave() != adsk.core.DialogResults.DialogOK:
        return None
    path = dlg.filename
    if not path.lower().endswith('.dxf'):
        path += '.dxf'
    return path


def export_layout_sketch(design: adsk.fusion.Design, sketch: adsk.fusion.Sketch, filename: str):
    export_mgr = design.exportManager
    try:
        opts = export_mgr.createDXFSketchExportOptions(filename, sketch)
        if not opts:
            raise RuntimeError('Could not create DXF export options.')
        export_mgr.execute(opts)
        return
    except:
        pass
    ok = sketch.saveAsDXF(filename)
    if not ok:
        raise RuntimeError('DXF export failed.')


def add_rect(sketch: adsk.fusion.Sketch, x0: float, y0: float, x1: float, y1: float, construction: bool = False):
    lines = sketch.sketchCurves.sketchLines
    p1 = adsk.core.Point3D.create(x0, y0, 0)
    p2 = adsk.core.Point3D.create(x1, y0, 0)
    p3 = adsk.core.Point3D.create(x1, y1, 0)
    p4 = adsk.core.Point3D.create(x0, y1, 0)
    l1 = lines.addByTwoPoints(p1, p2)
    l2 = lines.addByTwoPoints(p2, p3)
    l3 = lines.addByTwoPoints(p3, p4)
    l4 = lines.addByTwoPoints(p4, p1)
    if construction:
        try:
            l1.isConstruction = True
            l2.isConstruction = True
            l3.isConstruction = True
            l4.isConstruction = True
        except:
            pass
