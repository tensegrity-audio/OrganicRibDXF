import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import math
import uuid
import importlib.util
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def _load_local_module(module_name: str, filename: str):
    module_path = os.path.join(os.path.dirname(__file__), filename)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if not spec or not spec.loader:
        raise ImportError(f'Could not load helper module from: {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_paged_dxf = _load_local_module('LatticeBedsPagedDxf', 'LatticeBedsPagedDxf.py')
_rib_generation = _load_local_module('LatticeBedsRibGeneration', 'LatticeBedsRibGeneration.py')
_notch_generation = _load_local_module('LatticeBedsNotchGeneration', 'LatticeBedsNotchGeneration.py')
choose_export_path = _paged_dxf.choose_export_path
export_layout_sketch = _paged_dxf.export_layout_sketch
layout_slices_into_beds = _paged_dxf.layout_slices_into_beds
create_rib_bodies = _rib_generation.create_rib_bodies
collect_modeled_notches = _notch_generation.collect_modeled_notches
apply_modeled_half_laps = _notch_generation.apply_modeled_half_laps

APP = None
UI = None
HANDLERS = []
CMD_ID = 'OpenAI_LatticeBedsExport_Command_V4'
CMD_NAME = 'Organic Rib DXF'
CMD_DESC = 'Create interlocking orthogonal ribs from an organic body and export a laser-cut-ready DXF layout.'
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
BED_LABEL_PREFIX = 'BED'
EPS = 1e-6
X_RIB_NOTCHES_OPEN_FROM_TOP = True
Y_RIB_NOTCHES_OPEN_FROM_TOP = False

DEFAULTS = {
    'material_thickness': '3 mm',
    'slot_clearance': '0.15 mm',
    'x_spacing': '20 mm',
    'y_spacing': '20 mm',
    'edge_margin': '1.5 mm',
    'text_height': '4 mm',
    'bed_width': '32 in',
    'bed_height': '24 in',
    'bed_margin': '0.5 in',
    'bed_gap': '1.0 in',
    'part_gap': '8 mm',
    'sample_points_per_curve': 64,
    'min_interval_height': '2.0 mm',
    'include_boundary_planes': True,
    'draw_bed_outlines': True,
    'arrange_on_beds': False,
    'create_paged_dxf': True,
    'create_rib_bodies': True,
    'cut_half_laps': True,
    'keep_tool_bodies': False,
    'export_filename': 'organic_rib_layout.dxf',
}


@dataclass
class Polyline2D:
    points: List[adsk.core.Point3D]


@dataclass
class NotchInstruction:
    x_probe: float
    y0: float
    y1: float
    top_open: bool
    center_world_x: float
    center_world_y: float


@dataclass
class SliceInfo:
    family: str
    index: int
    label: str
    offset: float
    sketch: adsk.fusion.Sketch
    plane: adsk.fusion.ConstructionPlane
    bbox: adsk.core.BoundingBox3D
    layout_origin: Optional[adsk.core.Point3D] = None
    source_curves: List[adsk.fusion.SketchCurve] = field(default_factory=list)
    sampled_polylines: List[Polyline2D] = field(default_factory=list)
    placed_bed_index: Optional[int] = None
    rib_body: Optional[adsk.fusion.BRepBody] = None
    export_sketch: Optional[adsk.fusion.Sketch] = None
    export_polylines: List[Polyline2D] = field(default_factory=list)
    notch_sketch: Optional[adsk.fusion.Sketch] = None
    modeled_notches: List[NotchInstruction] = field(default_factory=list)


def log_text(message: str):
    try:
        palette = UI.palettes.itemById('TextCommands')
        if palette:
            palette.isVisible = True
            palette.writeText('[LatticeBedsAddin] ' + message)
    except:
        pass


def set_input_help(input_obj, tooltip: str, description: str):
    try:
        input_obj.tooltip = tooltip
    except:
        pass
    try:
        input_obj.tooltipDescription = description
    except:
        pass


def get_default_export_filename() -> str:
    base_name = DEFAULTS['export_filename']
    try:
        document = APP.activeDocument if APP else None
        if not document:
            return base_name
        doc_name = getattr(document, 'name', '') or ''
        if not doc_name:
            return base_name
        stem = os.path.splitext(doc_name)[0].strip()
        if not stem:
            return base_name
        cleaned = sanitize_filename_stem(stem)
        if not cleaned:
            return base_name
        return f'{cleaned}_organic_ribs.dxf'
    except:
        return base_name


def sanitize_filename_stem(name: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    cleaned = []
    for ch in name:
        cleaned.append('_' if ch in invalid_chars else ch)
    return ''.join(cleaned).strip(' ._')


def run(context):
    global APP, UI
    APP = adsk.core.Application.get()
    UI = APP.userInterface
    try:
        log_text('Starting add-in...')
        cmd_defs = UI.commandDefinitions
        cmd_def = cmd_defs.itemById(CMD_ID)
        if not cmd_def:
            cmd_def = cmd_defs.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESC)
            log_text('Created command definition.')
        else:
            log_text('Reusing existing command definition.')

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        HANDLERS.append(on_created)
        log_text('Attached commandCreated handler.')

        panel = UI.allToolbarPanels.itemById(PANEL_ID)
        if not panel:
            raise RuntimeError('Could not find toolbar panel: {}'.format(PANEL_ID))

        control = panel.controls.itemById(CMD_ID)
        if not control:
            control = panel.controls.addCommand(cmd_def)
            control.isPromoted = True
            control.isPromotedByDefault = True
            log_text('Added toolbar button to Solid > Scripts and Add-Ins.')
        else:
            log_text('Toolbar button already exists.')

        UI.messageBox('''Organic Rib DXF loaded.

Go to Design > Solid > Scripts and Add-Ins and click "Organic Rib DXF".''')
    except:
        if UI:
            log_text('Startup failed.')
            UI.messageBox('Add-in start failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    global UI
    try:
        panel = UI.allToolbarPanels.itemById(PANEL_ID)
        if panel:
            control = panel.controls.itemById(CMD_ID)
            if control:
                control.deleteMe()

        cmd_def = UI.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        log_text('Add-in stopped.')
    except:
        if UI:
            UI.messageBox('Add-in stop failed:\n{}'.format(traceback.format_exc()))


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            cmd.setDialogInitialSize(620, 860)

            on_execute = CommandExecuteHandler()
            on_destroy = CommandDestroyHandler()
            cmd.execute.add(on_execute)
            cmd.destroy.add(on_destroy)
            HANDLERS.extend([on_execute, on_destroy])

            inputs = cmd.commandInputs

            body_input = inputs.addSelectionInput('targetBody', 'Target body', 'Select one solid body')
            body_input.addSelectionFilter('Bodies')
            body_input.setSelectionLimits(1, 1)
            set_input_help(body_input, 'Choose the solid body to convert into rib sections.', 'Pick the organic or sculpted form you want to slice into interlocking ribs.')

            inputs.addTextBoxCommandInput(
                'helpBlock',
                'Overview',
                'Create orthogonal rib sections from one body, optionally cut interlocking half-lap notches, then place one rib per DXF bed for laser cutting.\n\nUse Rib Generation to control section density, Notch Generation to control fit, and DXF Generation to control output size and labeling.',
                7,
                True,
            )

            inputs.addTextBoxCommandInput('ribSectionHeader', '1. Rib Generation', 'Create the rib slices and optional rib bodies.', 1, True)
            material_input = inputs.addStringValueInput('materialThickness', 'Material thickness', DEFAULTS['material_thickness'])
            x_spacing_input = inputs.addStringValueInput('xSpacing', 'X spacing', DEFAULTS['x_spacing'])
            y_spacing_input = inputs.addStringValueInput('ySpacing', 'Y spacing', DEFAULTS['y_spacing'])
            sample_input = inputs.addIntegerSpinnerCommandInput('samplePoints', 'Sample points per curve', 12, 300, 4, DEFAULTS['sample_points_per_curve'])
            boundary_input = inputs.addBoolValueInput('includeBoundaryPlanes', 'Include boundary planes', True, '', DEFAULTS['include_boundary_planes'])
            rib_bodies_input = inputs.addBoolValueInput('createRibBodies', 'Create rib bodies in Fusion', True, '', DEFAULTS['create_rib_bodies'])
            inputs.addTextBoxCommandInput('ribSpacer', '', ' ', 1, True)

            inputs.addTextBoxCommandInput('notchSectionHeader', '2. Notch Generation', 'Cut interlocking half-lap slots into the generated ribs.', 1, True)
            half_laps_input = inputs.addBoolValueInput('cutHalfLaps', 'Generate modeled half-lap notches', True, '', DEFAULTS['cut_half_laps'])
            clearance_input = inputs.addStringValueInput('slotClearance', 'Slot clearance', DEFAULTS['slot_clearance'])
            edge_margin_input = inputs.addStringValueInput('edgeMargin', 'Edge margin', DEFAULTS['edge_margin'])
            min_interval_input = inputs.addStringValueInput('minIntervalHeight', 'Minimum notch interval', DEFAULTS['min_interval_height'])
            inputs.addTextBoxCommandInput('notchSpacer', '', ' ', 1, True)

            inputs.addTextBoxCommandInput('dxfSectionHeader', '3. DXF Generation', 'Control final layout, bed size, and DXF export naming.', 1, True)
            create_dxf_input = inputs.addBoolValueInput('createPagedDxf', 'Create laser-cut DXF', True, '', DEFAULTS['create_paged_dxf'])
            arrange_input = inputs.addBoolValueInput('arrangeOnBeds', 'Stack ribs onto separate beds', True, '', DEFAULTS['arrange_on_beds'])
            text_height_input = inputs.addStringValueInput('textHeight', 'Label text height', DEFAULTS['text_height'])
            bed_width_input = inputs.addStringValueInput('bedWidth', 'Bed width', DEFAULTS['bed_width'])
            bed_height_input = inputs.addStringValueInput('bedHeight', 'Bed height', DEFAULTS['bed_height'])
            bed_margin_input = inputs.addStringValueInput('bedMargin', 'Bed inner margin', DEFAULTS['bed_margin'])
            bed_gap_input = inputs.addStringValueInput('bedGap', 'Gap between beds', DEFAULTS['bed_gap'])
            part_gap_input = inputs.addStringValueInput('partGap', 'Gap between parts', DEFAULTS['part_gap'])
            bed_outline_input = inputs.addBoolValueInput('drawBedOutlines', 'Show bed outlines in layout sketch', True, '', DEFAULTS['draw_bed_outlines'])
            export_name_input = inputs.addStringValueInput('exportFilename', 'Default DXF filename', get_default_export_filename())

            set_input_help(material_input, 'Thickness of the sheet material.', 'Used for rib thickness and for the notch width baseline before clearance is added.')
            set_input_help(x_spacing_input, 'Spacing between X-direction rib slices.', 'Smaller values create more X ribs. Larger values create fewer ribs.')
            set_input_help(y_spacing_input, 'Spacing between Y-direction rib slices.', 'Smaller values create more Y ribs. Larger values create fewer ribs.')
            set_input_help(sample_input, 'How finely each rib outline is sampled.', 'Higher values trace curves more accurately but increase processing time.')
            set_input_help(boundary_input, 'Include slices at the body extents.', 'Turn this off if you want only interior ribs and do not want edge slices.')
            set_input_help(rib_bodies_input, 'Build rib bodies in Fusion before export.', 'Needed for modeled half-lap cuts. Turn off if you only want section sketches.')

            set_input_help(half_laps_input, 'Generate modeled interlocking notches.', 'Cuts half-lap slots into the rib bodies so the laser-cut parts can slide together.')
            set_input_help(clearance_input, 'Extra width added to each slot.', 'Use this to loosen the fit for real-world material thickness and laser kerf.')
            set_input_help(edge_margin_input, 'Minimum material left near the rib edge.', 'Helps avoid very thin slivers near the top or bottom of a notch opening.')
            set_input_help(min_interval_input, 'Ignore tiny overlap regions when searching for notch locations.', 'Useful for noisy or highly organic geometry where tiny intersections are not practical to cut.')

            set_input_help(create_dxf_input, 'Export the final rib layout to a DXF file.', 'Turn this off if you only want the Fusion-side rib bodies and sketches.')
            set_input_help(arrange_input, 'Place one rib per bed and stack the beds.', 'Turn this off to lay the beds side by side instead.')
            set_input_help(text_height_input, 'Size of the rib labels in the final layout sketch.', 'Used for the rib names and bed labels in the DXF layout.')
            set_input_help(bed_width_input, 'Overall width of one DXF bed region.', 'Usually matches the usable width of your laser cutter bed or sheet size.')
            set_input_help(bed_height_input, 'Overall height of one DXF bed region.', 'Usually matches the usable height of your laser cutter bed or sheet size.')
            set_input_help(bed_margin_input, 'Unused border inside each bed.', 'Keeps ribs and labels away from the edges of the bed outline.')
            set_input_help(bed_gap_input, 'Spacing between bed regions in the final layout sketch.', 'Only affects how multiple beds are spaced inside the Fusion layout sketch.')
            set_input_help(part_gap_input, 'Reserved gap setting for future denser layouts.', 'Currently has minimal effect because the layout uses one rib per bed.')
            set_input_help(bed_outline_input, 'Show or hide the placement bed rectangles.', 'Helpful for planning layout in Fusion. Turn off if you want a cleaner exported sketch view.')
            set_input_help(export_name_input, 'Default filename used in the save dialog.', 'Starts with the current Fusion document name so exported DXFs are easier to identify.')
        except:
            if UI:
                UI.messageBox('Command creation failed:\n{}'.format(traceback.format_exc()))


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            event_args = adsk.core.CommandEventArgs.cast(args)
            cmd = event_args.command
            inputs = cmd.commandInputs
            design = adsk.fusion.Design.cast(APP.activeProduct)
            if not design:
                raise RuntimeError('No active Fusion design.')

            units = design.unitsManager

            body_sel = adsk.core.SelectionCommandInput.cast(inputs.itemById('targetBody'))
            if body_sel.selectionCount != 1:
                raise RuntimeError('Select exactly one solid body.')
            body = adsk.fusion.BRepBody.cast(body_sel.selection(0).entity)
            if not body or not body.isSolid:
                raise RuntimeError('The selected entity must be one solid body.')

            params = {
                'material_thickness': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('materialThickness')).value),
                'slot_clearance': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('slotClearance')).value),
                'x_spacing': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('xSpacing')).value),
                'y_spacing': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('ySpacing')).value),
                'edge_margin': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('edgeMargin')).value),
                'text_height': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('textHeight')).value),
                'bed_width': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('bedWidth')).value),
                'bed_height': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('bedHeight')).value),
                'bed_margin': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('bedMargin')).value),
                'bed_gap': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('bedGap')).value),
                'part_gap': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('partGap')).value),
                'min_interval_height': parse_length_input(units, adsk.core.StringValueCommandInput.cast(inputs.itemById('minIntervalHeight')).value),
                'sample_points_per_curve': adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById('samplePoints')).value,
                'include_boundary_planes': adsk.core.BoolValueCommandInput.cast(inputs.itemById('includeBoundaryPlanes')).value,
                'draw_bed_outlines': adsk.core.BoolValueCommandInput.cast(inputs.itemById('drawBedOutlines')).value,
                'arrange_on_beds': adsk.core.BoolValueCommandInput.cast(inputs.itemById('arrangeOnBeds')).value,
                'create_paged_dxf': adsk.core.BoolValueCommandInput.cast(inputs.itemById('createPagedDxf')).value,
                'create_rib_bodies': adsk.core.BoolValueCommandInput.cast(inputs.itemById('createRibBodies')).value,
                'cut_half_laps': adsk.core.BoolValueCommandInput.cast(inputs.itemById('cutHalfLaps')).value,
                'keep_tool_bodies': DEFAULTS['keep_tool_bodies'],
                'export_filename': adsk.core.StringValueCommandInput.cast(inputs.itemById('exportFilename')).value,
            }
            validate_params(params)

            export_path = None
            if params['create_paged_dxf']:
                export_path = choose_export_path(params['export_filename'])
                if not export_path:
                    return

            execute_pipeline(design, body, params, export_path)
        except:
            if UI:
                UI.messageBox('Execution failed:\n{}'.format(traceback.format_exc()))


class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass


def execute_pipeline(design: adsk.fusion.Design, body: adsk.fusion.BRepBody, params: dict, export_path: Optional[str]):
    pipeline_t0 = time.perf_counter()
    timeline_start_index = get_timeline_count(design)
    root = design.rootComponent
    slot_width = params['material_thickness'] + params['slot_clearance']

    bbox = body.boundingBox
    body_min = bbox.minPoint
    body_max = bbox.maxPoint
    body_z_mid = 0.5 * (body_min.z + body_max.z)

    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = 'LatticeBedsExport_' + uuid.uuid4().hex[:8]

    x_offsets = build_offsets(body_min.x, body_max.x, params['x_spacing'], params['include_boundary_planes'])
    y_offsets = build_offsets(body_min.y, body_max.y, params['y_spacing'], params['include_boundary_planes'])

    x_slices = create_family_slices(comp, body, root.yZConstructionPlane, 'X', x_offsets, int(params['sample_points_per_curve']))
    y_slices = create_family_slices(comp, body, root.xZConstructionPlane, 'Y', y_offsets, int(params['sample_points_per_curve']))

    if not x_slices and not y_slices:
        raise RuntimeError('No valid section slices were created. Try smaller spacing or a different body.')

    all_slices = x_slices + y_slices

    if params['create_rib_bodies']:
        stage_t0 = time.perf_counter()
        log_text(f'Rib generation starting for {len(all_slices)} slices.')
        create_rib_bodies(comp, all_slices, params['material_thickness'])
        log_text(f'Rib generation finished in {time.perf_counter() - stage_t0:.2f}s.')
        if params['cut_half_laps']:
            stage_t0 = time.perf_counter()
            log_text('Modeled half-lap generation starting.')
            collect_modeled_notches(
                x_slices,
                y_slices,
                params['edge_margin'],
                params['min_interval_height'],
                body_z_mid,
                find_best_shared_interval,
                NotchInstruction,
                X_RIB_NOTCHES_OPEN_FROM_TOP,
                Y_RIB_NOTCHES_OPEN_FROM_TOP,
            )
            apply_modeled_half_laps(
                comp,
                all_slices,
                params['material_thickness'],
                slot_width,
                params['edge_margin'],
                params['keep_tool_bodies'],
                EPS,
            )
            log_text(f'Modeled half-lap generation finished in {time.perf_counter() - stage_t0:.2f}s.')
        stage_t0 = time.perf_counter()
        log_text('Export sketch refresh starting.')
        refresh_export_sketches_from_rib_bodies(comp, all_slices, params['text_height'], int(params['sample_points_per_curve']))
        log_text(f'Export sketch refresh finished in {time.perf_counter() - stage_t0:.2f}s.')

    placements = []
    if params['create_paged_dxf']:
        stage_t0 = time.perf_counter()
        log_text('DXF layout sketch creation starting.')
        layout_sketch = comp.sketches.add(root.xYConstructionPlane)
        layout_sketch.name = 'Lattice_Beds_DXF_Layout'
        layout_sketch.areProfilesShown = False

        placements = layout_slices_into_beds(
            layout_sketch=layout_sketch,
            slices=all_slices,
            part_gap=params['part_gap'],
            text_height=params['text_height'],
            bed_width=params['bed_width'],
            bed_height=params['bed_height'],
            bed_margin=params['bed_margin'],
            bed_gap=params['bed_gap'],
            arrange_on_beds=params['arrange_on_beds'],
            draw_bed_outlines=params['draw_bed_outlines'],
        )
        log_text(f'DXF layout sketch creation finished in {time.perf_counter() - stage_t0:.2f}s.')

        if not export_path:
            raise RuntimeError('DXF export was enabled, but no export path was provided.')
        stage_t0 = time.perf_counter()
        log_text(f'DXF export starting: {export_path}')
        export_layout_sketch(design, layout_sketch, export_path)
        log_text(f'DXF export finished in {time.perf_counter() - stage_t0:.2f}s.')

    modeled_count = sum(len(s.modeled_notches) for s in all_slices)
    msg = [
        'Done.',
        '',
        f'Created {len(x_slices)} X slices and {len(y_slices)} Y slices.',
        f'Modeled notch instructions: {modeled_count}.',
    ]
    if params['create_paged_dxf']:
        msg.append(f'Arranged into {len(placements)} bed(s).')
        msg.append(f'Exported DXF to:\n{export_path}')
    else:
        msg.append('Paged/labeled DXF export was skipped.')
    msg.extend([
        '',
        'Note: the body-generation and half-lap stage is a beta implementation. Check the generated rib bodies on a simple form first, then move to denser spacing or more concave shapes.'
    ])
    hide_export_sketches(all_slices)
    group_generated_timeline_entries(design, timeline_start_index, comp.name)
    log_text(f'Pipeline finished in {time.perf_counter() - pipeline_t0:.2f}s.')
    UI.messageBox('\n'.join(msg))


def refresh_export_sketches_from_rib_bodies(comp: adsk.fusion.Component, slices: List[SliceInfo], text_height: float, sample_points: int):
    for slice_info in slices:
        if not slice_info.rib_body:
            continue
        slice_t0 = time.perf_counter()
        log_text(f'Export sketch start: {slice_info.label}')
        if slice_info.export_sketch:
            safe_delete(slice_info.export_sketch)
            slice_info.export_sketch = None

        export_sketch = comp.sketches.add(slice_info.plane)
        export_sketch.name = f'{slice_info.label}_export'
        export_sketch.areProfilesShown = True
        curves = create_section_curves(export_sketch, slice_info.rib_body)
        if not curves:
            safe_delete(export_sketch)
            log_text(f'Export sketch failed: {slice_info.label} after {time.perf_counter() - slice_t0:.2f}s (no curves)')
            continue
        export_polylines = sample_sketch_curves(curves, sample_points, slice_info.family)
        slice_info.export_polylines = export_polylines
        slice_info.export_sketch = export_sketch
        log_text(f'Export sketch finished: {slice_info.label} in {time.perf_counter() - slice_t0:.2f}s')


def hide_export_sketches(slices: List[SliceInfo]):
    for slice_info in slices:
        if not slice_info.export_sketch:
            continue
        try:
            slice_info.export_sketch.isVisible = False
        except:
            pass


def get_timeline_count(design: adsk.fusion.Design) -> int:
    try:
        return design.timeline.count
    except:
        return -1


def group_generated_timeline_entries(design: adsk.fusion.Design, start_index: int, group_name: str):
    try:
        timeline = design.timeline
        end_index = timeline.count - 1
        if start_index < 0 or end_index < start_index:
            return
        timeline_group = timeline.timelineGroups.add(start_index, end_index)
        if timeline_group:
            timeline_group.name = group_name
    except:
        pass


def build_offsets(vmin: float, vmax: float, spacing: float, include_boundary_planes: bool) -> List[float]:
    offsets = []
    pos = vmin if include_boundary_planes else vmin + spacing * 0.5
    tol = spacing * 0.001
    while pos <= vmax + tol:
        offsets.append(pos)
        pos += spacing
    return offsets


def create_family_slices(comp: adsk.fusion.Component, body: adsk.fusion.BRepBody, base_plane, family: str, offsets: List[float], sample_points: int) -> List[SliceInfo]:
    slices: List[SliceInfo] = []
    for i, offset in enumerate(offsets, start=1):
        plane_input = comp.constructionPlanes.createInput()
        plane_input.setByOffset(base_plane, adsk.core.ValueInput.createByReal(offset))
        plane = comp.constructionPlanes.add(plane_input)
        plane.name = f'{family}_plane_{i:03d}'

        sketch = comp.sketches.add(plane)
        sketch.name = f'{family}_slice_{i:03d}'
        sketch.areProfilesShown = True

        curves = create_section_curves(sketch, body)
        if not curves:
            safe_delete(sketch)
            safe_delete(plane)
            continue

        polylines = sample_sketch_curves(curves, sample_points, family)
        if not polylines:
            safe_delete(sketch)
            safe_delete(plane)
            continue

        slices.append(SliceInfo(
            family=family,
            index=i,
            label=f'{family}{i:03d}',
            offset=offset,
            sketch=sketch,
            plane=plane,
            bbox=sketch.boundingBox,
            source_curves=curves,
            sampled_polylines=polylines,
        ))
    return slices


def create_section_curves(sketch: adsk.fusion.Sketch, body: adsk.fusion.BRepBody) -> List[adsk.fusion.SketchCurve]:
    for candidate in ([body], adsk.core.ObjectCollection.create()):
        try:
            if hasattr(candidate, 'add'):
                candidate.add(body)
            ents = sketch.intersectWithSketchPlane(candidate)
            curves = collect_sketch_curves(ents)
            if curves:
                return curves
        except:
            pass
    try:
        ents = sketch.projectCutEdges(body)
        curves = collect_sketch_curves(ents)
        if curves:
            return curves
    except:
        pass
    return []


def collect_sketch_curves(ents) -> List[adsk.fusion.SketchCurve]:
    out = []
    if not ents:
        return out
    try:
        for i in range(ents.count):
            c = adsk.fusion.SketchCurve.cast(ents.item(i))
            if c:
                out.append(c)
        return out
    except:
        pass
    try:
        for e in ents:
            c = adsk.fusion.SketchCurve.cast(e)
            if c:
                out.append(c)
    except:
        pass
    return out


def sample_sketch_curves(curves: List[adsk.fusion.SketchCurve], sample_points: int, family: str) -> List[Polyline2D]:
    out: List[Polyline2D] = []
    for c in curves:
        pts = sample_sketch_curve_to_2d(c, sample_points, family)
        if len(pts) >= 2:
            out.append(Polyline2D(points=pts))
    return out


def sample_sketch_curve_to_2d(curve: adsk.fusion.SketchCurve, sample_points: int, family: str) -> List[adsk.core.Point3D]:
    result: List[adsk.core.Point3D] = []
    try:
        geom3d = curve.worldGeometry
        evaluator = geom3d.evaluator
        ok, pmin, pmax = evaluator.getParameterExtents()
        if not ok:
            return result
        steps = max(2, sample_points)
        params = [pmin + (pmax - pmin) * i / float(steps - 1) for i in range(steps)]
        ok, pts3d = evaluator.getPointsAtParameters(params)
        if not ok or not pts3d:
            return result
        for p in pts3d:
            if family == 'X':
                sample_pt = adsk.core.Point3D.create(p.y, p.z, 0)
            else:
                sample_pt = adsk.core.Point3D.create(p.x, p.z, 0)
            if not result or distance2d(result[-1], sample_pt) > EPS:
                result.append(sample_pt)
        is_closed = getattr(curve, 'isClosed', False)
        if is_closed and len(result) > 2 and distance2d(result[0], result[-1]) > EPS:
            result.append(adsk.core.Point3D.create(result[0].x, result[0].y, 0))
    except:
        pass
    return result


def map_world_point_to_slice_sketch(slice_info: SliceInfo, world_x: float, world_y: float, world_z: float) -> Tuple[Optional[float], Optional[float]]:
    try:
        p = adsk.core.Point3D.create(world_x, world_y, world_z)
        sp = slice_info.sketch.modelToSketchSpace(p)
        return sp.x, sp.y
    except:
        return None, None


def find_best_profile_interval(slice_info: SliceInfo, x_probe: float, y_ref: float, edge_margin: float, min_interval_height: float) -> Optional[Tuple[float, float]]:
    intervals = get_profile_intervals(slice_info, x_probe, edge_margin, min_interval_height)
    if not intervals:
        return None
    for a, b in intervals:
        if (y_ref >= a - EPS) and (y_ref <= b + EPS):
            return (a, b)
    best = None
    best_dist = None
    for a, b in intervals:
        mid = 0.5 * (a + b)
        d = abs(mid - y_ref)
        if best is None or d < best_dist:
            best = (a, b)
            best_dist = d
    return best


def get_profile_intervals(slice_info: SliceInfo, x_probe: float, edge_margin: float, min_interval_height: float) -> List[Tuple[float, float]]:
    ys = vertical_intersections_from_polylines(slice_info.sampled_polylines, x_probe)
    if len(ys) < 2:
        return []
    intervals = []
    min_height = max(min_interval_height, EPS * 10.0)
    for i in range(0, len(ys) - 1, 2):
        a = ys[i]
        b = ys[i + 1]
        if (b - a) >= min_height:
            intervals.append((a, b))
    return intervals


def find_best_shared_interval(x_slice: SliceInfo, x_probe: float, y_slice: SliceInfo, y_probe: float, edge_margin: float, min_interval_height: float, z_hint: float) -> Optional[Tuple[float, float]]:
    x_intervals = get_profile_intervals(x_slice, x_probe, edge_margin, min_interval_height)
    y_intervals = get_profile_intervals(y_slice, y_probe, edge_margin, min_interval_height)
    if not x_intervals or not y_intervals:
        return None

    overlaps: List[Tuple[float, float]] = []
    min_height = max(min_interval_height, EPS * 10.0)
    for xa, xb in x_intervals:
        for ya, yb in y_intervals:
            a = max(xa, ya)
            b = min(xb, yb)
            if (b - a) >= min_height:
                overlaps.append((a, b))
    if not overlaps:
        return None

    best = None
    best_height = None
    best_dist = None
    for a, b in overlaps:
        height = b - a
        mid = 0.5 * (a + b)
        d = abs(mid - z_hint)
        if best is None or height > best_height + EPS or (abs(height - best_height) <= EPS and d < best_dist):
            best = (a, b)
            best_height = height
            best_dist = d
    return best


def vertical_intersections_from_polylines(polylines: List[Polyline2D], x_probe: float) -> List[float]:
    hits: List[float] = []
    for poly in polylines:
        pts = poly.points
        if len(pts) < 2:
            continue
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            x0, y0 = p0.x, p0.y
            x1, y1 = p1.x, p1.y
            if abs(x1 - x0) < EPS:
                if abs(x_probe - x0) < EPS:
                    hits.append(y0)
                    hits.append(y1)
                continue
            xmin = min(x0, x1)
            xmax = max(x0, x1)
            if x_probe < xmin - EPS or x_probe > xmax + EPS:
                continue
            t = (x_probe - x0) / (x1 - x0)
            if t < -EPS or t > 1.0 + EPS:
                continue
            y = y0 + t * (y1 - y0)
            hits.append(y)
    hits.sort()
    return dedupe_sorted_values(hits, tol=1e-4)


def dedupe_sorted_values(vals: List[float], tol: float) -> List[float]:
    if not vals:
        return []
    out = [vals[0]]
    for v in vals[1:]:
        if abs(v - out[-1]) > tol:
            out.append(v)
    return out


def validate_params(params: dict):
    for key in ['material_thickness', 'x_spacing', 'y_spacing', 'bed_width', 'bed_height', 'bed_margin', 'part_gap']:
        if params[key] <= 0:
            raise RuntimeError(f'{key} must be greater than zero.')
    if params['slot_clearance'] < 0:
        raise RuntimeError('slot_clearance cannot be negative.')
    if params['edge_margin'] < 0:
        raise RuntimeError('edge_margin cannot be negative.')
    if params['sample_points_per_curve'] < 12:
        raise RuntimeError('sample_points_per_curve must be at least 12.')
    if params['cut_half_laps'] and not params['create_rib_bodies']:
        raise RuntimeError('Generate modeled half-lap notches requires Create rib bodies in Fusion to be enabled.')



def parse_length_input(units_mgr, expr):
    """Parse a user-entered length value into Fusion internal length units.

    This implementation intentionally avoids FusionUnitsManager.evaluateExpression because
    some installations return display-oriented unit strings that can trigger
    `The units parameter is not a valid unit string` at runtime.

    Supported examples:
    - 3
    - 3 mm
    - 0.15mm
    - 32 in
    - 1/2 in
    - 1.25 cm
    - 2 ft
    - 24" or 24 in
    """
    expr = (expr or '').strip()
    if not expr:
        raise RuntimeError('A required length field is blank.')

    default_units = normalize_length_unit_string(getattr(units_mgr, 'defaultLengthUnits', 'cm'))
    value_cm = parse_length_expression_to_cm(expr, default_units)
    if value_cm < 0:
        raise RuntimeError(f'Could not parse length expression: {expr}')
    return value_cm


def normalize_length_unit_string(unit_str: str) -> str:
    u = (unit_str or 'cm').strip().lower()
    aliases = {
        'mm': 'mm', 'millimeter': 'mm', 'millimeters': 'mm', 'millimetre': 'mm', 'millimetres': 'mm',
        'cm': 'cm', 'centimeter': 'cm', 'centimeters': 'cm', 'centimetre': 'cm', 'centimetres': 'cm',
        'm': 'm', 'meter': 'm', 'meters': 'm', 'metre': 'm', 'metres': 'm',
        'in': 'in', 'inch': 'in', 'inches': 'in', '"': 'in',
        'ft': 'ft', 'foot': 'ft', 'feet': 'ft', "'": 'ft',
    }
    return aliases.get(u, 'cm')


def unit_scale_to_cm(unit_key: str) -> float:
    scales = {
        'mm': 0.1,
        'cm': 1.0,
        'm': 100.0,
        'in': 2.54,
        'ft': 30.48,
    }
    if unit_key not in scales:
        raise RuntimeError(f'Unsupported length unit: {unit_key}')
    return scales[unit_key]


def safe_eval_fraction(text: str) -> float:
    s = (text or '').strip()
    if not s:
        raise RuntimeError('Blank numeric value.')

    # Handle mixed fractions like: 1 1/2
    if ' ' in s and '/' in s:
        parts = s.split()
        if len(parts) == 2:
            whole = float(parts[0])
            num, den = parts[1].split('/')
            frac = float(num) / float(den)
            return whole + frac

    if '/' in s:
        num, den = s.split('/')
        return float(num) / float(den)

    return float(s)


def parse_length_expression_to_cm(expr: str, default_units: str) -> float:
    import re

    s = expr.strip().lower()
    s = s.replace('”', '"').replace('“', '"').replace('′', "'").replace('’', "'")
    s = re.sub(r'\s+', ' ', s)

    m = re.fullmatch(r"([+-]?[0-9]*\.?[0-9]+(?:\s+[0-9]+/[0-9]+|/[0-9]+)?)\s*([a-z\"]+|')?\s*", s)
    if not m:
        raise RuntimeError(f'Could not parse length expression: {expr}')

    num_text = m.group(1)
    unit_text = m.group(2) or default_units
    unit_key = normalize_length_unit_string(unit_text)
    numeric_value = safe_eval_fraction(num_text)
    return numeric_value * unit_scale_to_cm(unit_key)

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


def add_centerline(sketch: adsk.fusion.Sketch, x: float, y0: float, y1: float):
    line = sketch.sketchCurves.sketchLines.addByTwoPoints(adsk.core.Point3D.create(x, y0, 0), adsk.core.Point3D.create(x, y1, 0))
    try:
        line.isConstruction = True
    except:
        pass


def distance2d(p0, p1) -> float:
    return math.hypot(p1.x - p0.x, p1.y - p0.y)


def safe_delete(obj):
    try:
        obj.deleteMe()
    except:
        pass
