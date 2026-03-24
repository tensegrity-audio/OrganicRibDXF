# Organic Rib DXF

Organic Rib DXF is an Autodesk Fusion add-in that turns one solid body into two orthogonal rib families, optionally cuts modeled half-lap joints, and exports a laser-cut-ready DXF layout.

## Getting Started

### 1. Download and unzip

1. Download the project `.zip` from GitHub.
2. Extract it somewhere permanent on your computer.
3. Make sure the extracted folder contains these files:
   - `OrganicRibDXF.py`
   - `OrganicRibDXF.manifest`
   - `LatticeBedsRibGeneration.py`
   - `LatticeBedsNotchGeneration.py`
   - `LatticeBedsPagedDxf.py`

### 2. Add it to Fusion

1. Open Fusion.
2. Go to **Utilities > Scripts and Add-Ins**.
3. Open the **Add-Ins** tab.
4. Click the green `+` button or use the add/link option to add the extracted `OrganicRibDXF` folder.
5. You should now see **Organic Rib DXF** in the add-in list.

### 3. Load the add-in

1. Turn the add-in on in **Utilities > Scripts and Add-Ins**.
2. This only loads the add-in. It does not run the tool yet.

### 4. Run the tool

1. Go to **Design > Solid**.
2. Open the **Scripts and Add-Ins** panel.
3. Click **Organic Rib DXF**.

### 5. First test

For a first test, use:

- one clean solid body
- `Material thickness`: `3 mm`
- `Slot clearance`: `0.15 mm`
- `X spacing`: `20 mm`
- `Y spacing`: `20 mm`
- `Bed width`: `32 in`
- `Bed height`: `24 in`

Then:

1. Select exactly one solid body.
2. Click **OK**.
3. Choose a save location for the DXF.
4. Wait for Fusion to generate the ribs, optional joints, and final layout.

## Important Fusion behavior

Turning the add-in slider on only loads the add-in. You still need to click the **Organic Rib DXF** button in the toolbar to open the command dialog.

## What The Tool Does

- Creates orthogonal X and Y rib slices from one body
- Optionally builds rib bodies in Fusion
- Optionally cuts modeled half-lap joints into those ribs
- Lays out one rib per bed region in a final XY sketch
- Exports the result as a DXF

## Dialog Guide

### 1. Rib Generation

- **Target body**  
  The solid body that will be converted into ribs.

- **Material thickness**  
  Thickness of your sheet material. Also used as the basis for rib thickness and notch width.

- **X spacing / Y spacing**  
  Distance between slice planes for the two rib families. Smaller values create more ribs.

- **Sample points per curve**  
  How finely curved edges are sampled. Higher values can improve shape fidelity but increase processing time.

- **Include boundary planes**  
  Adds slices at the outside limits of the body.

- **Create rib bodies in Fusion**  
  Builds actual rib bodies from the section profiles. Required if you want modeled half-lap cuts.

### 2. Notch Generation

- **Generate modeled half-lap notches**  
  Cuts interlocking half-lap slots into the rib bodies.

- **Slot clearance**  
  Extra width added to each slot so the final parts fit more easily after cutting.

- **Edge margin**  
  Keeps notch openings away from razor-thin edge conditions.

- **Minimum notch interval**  
  Ignores very small overlap regions that are not practical for laser cutting.

### 3. DXF Generation

- **Create laser-cut DXF**  
  Exports the final layout as a DXF file.

- **Stack ribs onto separate beds**  
  Places one rib per bed and stacks the beds in the final layout sketch. Turn this off to lay the beds out side by side.

- **Label text height**  
  Controls the size of rib labels and bed labels in the final layout.

- **Bed width / Bed height**  
  The size of one placement bed. Usually matches your laser bed or sheet format.

- **Bed inner margin**  
  Keeps the rib away from the edges of the bed.

- **Gap between beds**  
  Spacing between bed regions in the final sketch.

- **Gap between parts**  
  Reserved for future denser layouts. It currently has minimal effect because the layout uses one rib per bed.

- **Show bed outlines in layout sketch**  
  Displays the bed rectangles in Fusion so you can see how parts are being placed.

- **Default DXF filename**  
  The default name shown in Fusion's save dialog. It uses the current Fusion document name when available.

## Recommended First Test

Use a simple convex or rounded form first.

Good first settings:

- spacing around `20 mm` to `30 mm`
- modeled half-laps turned on
- one clean solid body

Avoid testing first on a very fragmented or highly concave body.

## Troubleshooting

### The add-in loads, but nothing happens

That usually means the add-in loaded successfully but the command button was not clicked yet.

Go to:

**Design > Solid > Scripts and Add-Ins panel > Organic Rib DXF**

### I do not see the button

- Make sure you are in the **Design** workspace.
- Make sure you are on the **Solid** tab.
- Stop and restart the add-in.
- If needed, restart Fusion.

### The selected body is rejected

The tool expects exactly one **solid body**. It will not work with surfaces, meshes, or multiple selected bodies.

### The DXF looks too dense

Increase X/Y spacing and increase the minimum notch interval.

### The modeled half-laps fail or look strange

Turn off **Generate modeled half-lap notches** and confirm that rib extraction and DXF layout still look correct. The modeled body-cut stage is still a beta feature for complex geometry.

### I click Run and the Scripts and Add-Ins window closes, but no button appears

That usually means the add-in failed during startup before it finished creating the toolbar button.

Use this checklist:

1. Make sure the extracted folder contains both `OrganicRibDXF.py` and `OrganicRibDXF.manifest`.
2. Start the add-in again and watch for a startup message box.
3. Open **View > Text Commands** and look for lines beginning with `[LatticeBedsAddin]`.
4. If the button still does not appear, stop the add-in, remove the linked folder from Fusion, then add the folder again as a fresh link.

## Current Limitations

- Modeled half-laps are still beta for highly concave or multi-island sections.
- Layout is intentionally simple and prioritizes clear non-overlapping placement over true nesting.
- The exported DXF is one master sketch containing all bed regions.

## Files

- `OrganicRibDXF.py` - main Fusion add-in
- `OrganicRibDXF.manifest` - Fusion manifest
- `LatticeBedsRibGeneration.py` - rib body generation helpers
- `LatticeBedsNotchGeneration.py` - half-lap notch generation helpers
- `LatticeBedsPagedDxf.py` - DXF layout and export helpers
- `README.md` - this guide
