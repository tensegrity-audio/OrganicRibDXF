import adsk.core
import adsk.fusion


def create_rib_bodies(comp, slices, thickness: float):
    extrudes = comp.features.extrudeFeatures
    for slice_info in slices:
        profile = get_largest_profile(slice_info.sketch)
        if not profile:
            continue
        try:
            ext_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            ext_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(thickness), True)
            ext = extrudes.add(ext_input)
            if ext and ext.bodies and ext.bodies.count > 0:
                body = adsk.fusion.BRepBody.cast(ext.bodies.item(0))
                if body:
                    body.name = slice_info.label
                    slice_info.rib_body = body
        except:
            pass


def get_largest_profile(sketch):
    best = None
    best_area = -1.0
    try:
        for i in range(sketch.profiles.count):
            profile = sketch.profiles.item(i)
            area = 0.0
            try:
                props = profile.areaProperties(adsk.fusion.CalculationAccuracy.LowCalculationAccuracy)
                area = abs(props.area)
            except:
                pass
            if area > best_area:
                best_area = area
                best = profile
    except:
        pass
    return best
