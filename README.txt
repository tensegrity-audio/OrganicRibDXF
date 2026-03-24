# LatticeBedsAddin v3

This Fusion add-in creates orthogonal lattice slices from a selected solid body, arranges the resulting parts into laser-cutting beds, and exports one labeled DXF.

## What changed in v3

This build fixes the recurring unit-parsing crash:

`RuntimeError: 6 : The units parameter is not a valid unit string`

Earlier versions used Fusion's `evaluateExpression(...)` with document unit strings. On some installations, Fusion returns display-oriented unit strings that the parser then rejects. v3 no longer relies on that path for the dialog text fields.

Instead, v3 uses an internal length parser for common laser-cutting style inputs.

Supported examples:

- `3`
- `3 mm`
- `0.15 mm`
- `0.15mm`
- `32 in`
- `24"`
- `1/2 in`
- `1 1/2 in`
- `4 cm`
- `2 ft`

Bare numbers are interpreted in your current document length units.

## Important Fusion behavior

Turning the add-in slider on in **Utilities > Scripts and Add-Ins** only **loads** the add-in. It does not run the command immediately.

After enabling it, Fusion adds a button to the toolbar:

**Design workspace > Solid tab > Scripts and Add-Ins panel > Lattice Beds Export**

You must click that button to open the command dialog.

## Install / update

1. Close the add-in if it is currently running.
2. Replace the old add-in folder contents with this version.
3. In Fusion, open **Utilities > Scripts and Add-Ins**.
4. In **Add-Ins**, make sure `LatticeBedsAddin` is listed.
5. Turn it on.
6. Close the Scripts and Add-Ins dialog.
7. Go to **Design > Solid**.
8. Click **Lattice Beds Export**.

## Basic usage

1. Click **Lattice Beds Export**.
2. In **Target body**, select exactly one solid body.
3. Leave defaults for a first test:
   - Material thickness: `3 mm`
   - Slot clearance: `0.15 mm`
   - X spacing: `20 mm`
   - Y spacing: `20 mm`
   - Bed width: `32 in`
   - Bed height: `24 in`
4. Click **OK**.
5. Choose a save location for the DXF.
6. Wait for the add-in to generate the slices, arrange them into beds, and export the layout.

## What the options mean

### Core geometry

- **Material thickness**
  Thickness of the sheet stock. Also used for half-lap notch depth.

- **Slot clearance**
  Extra notch width beyond material thickness to account for fit tolerance.

- **X spacing / Y spacing**
  Distance between slice planes in each orthogonal family.

- **Edge margin**
  Keeps notches away from the ends of narrow local spans.

- **Minimum notch interval**
  Prevents tiny unstable notch intervals from being used.

### Labels and layout

- **Label text height**
  Height of the slice labels in the output sketch.

- **Bed width / Bed height**
  Default is `32 in x 24 in` for laser cutting.

- **Bed inner margin**
  Margin inside each bed before any parts are placed.

- **Gap between beds**
  Space between successive beds in the master layout sketch.

- **Gap between parts**
  Space between arranged slices on a given bed.

### Output controls

- **Draw notch rectangles in DXF**
  Adds the layout notch rectangles to the exported sketch.

- **Draw notch centerlines**
  Adds centerline references for notch locations.

- **Draw bed outlines**
  Draws rectangular bed boundaries and labels like `BED 01`.

### 3D modeling controls

- **Create rib bodies in Fusion**
  Builds actual rib bodies from the section profiles.

- **Attempt modeled half-lap cuts**
  Tries to cut modeled notch geometry into those rib bodies.

- **Keep temporary notch tool bodies**
  Keeps or deletes temporary cutter bodies used during modeled half-lap operations.

## Recommended first test

Use a simple convex or rounded form first.

Good first settings:

- coarse spacing, around `20 mm` to `30 mm`
- modeled half-laps turned on
- one clean solid body

Avoid testing first on a very fragmented or highly concave body.

## Troubleshooting

### Nothing happens when I turn the add-in on

That usually means the add-in loaded correctly, but you have not clicked the toolbar command yet.

Go to:

**Design > Solid > Scripts and Add-Ins panel > Lattice Beds Export**

### I do not see the button

- Make sure you are in the **Design** workspace.
- Make sure you are on the **Solid** tab.
- Stop and restart the add-in.
- If needed, restart Fusion.

### I get a unit parsing error

Use v3. The older builds used Fusion's expression parser and could fail on some installations.

### The selected body is rejected

The command expects exactly one **solid body**. It will not work with surfaces, meshes, or multiple selected bodies.

### The DXF looks too dense or unstable

Increase X/Y spacing and increase the minimum notch interval.

### The modeled half-laps fail or look strange

Turn off **Attempt modeled half-lap cuts** and confirm that the slice extraction and bed layout still look correct. The body-cut stage is still a beta feature for complex geometry.

## Current limitations

- Modeled half-laps are still beta for highly concave or multi-island sections.
- Bed arrangement is simple row-based packing, not true nesting.
- The exported DXF is one master sketch containing all beds.

## Files

- `LatticeBedsAddin.py` - main Fusion add-in
- `LatticeBedsAddin.manifest` - manifest for Fusion
- `README.md` - this guide
