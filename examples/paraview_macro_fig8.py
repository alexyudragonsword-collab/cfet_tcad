# ParaView macro: one-click Fig.8-style eMobility rendering of a
# STACKED CMOS TCAD result, with optional OSPRay ray tracing.
#
# This file runs inside YOUR ParaView (it is not part of the cfet_tcad
# Python environment):
#   1. ParaView -> Macros -> Import new macro... -> pick this file
#   2. Open a result collection (File -> Open -> <run>/vtk/cfet_idvg.pvd)
#      and click Apply
#   3. Run the macro (Macros -> paraview_macro_fig8)
#
# What it does: colors the active source by the CVT electron mobility
# (mu_n_cvt, present in lombardi_vsat runs), applies a Clip to open the
# device like the paper's Fig. 8, switches to the Turbo colormap, and -
# if your ParaView build ships OSPRay - offers publication-grade ray
# traced shading (uncomment the two lines at the bottom).
#
# cfet_tcad itself does NOT depend on ParaView/pvpython; this macro is
# executable documentation for users who want ParaView's rendering on
# top of the standard .pvd/.vtu outputs.

from paraview.simple import (Clip, ColorBy, GetActiveSource,
                             GetActiveViewOrCreate, GetColorTransferFunction,
                             GetDisplayProperties, Hide, Render, Show)

source = GetActiveSource()
if source is None:
    raise RuntimeError("open a vtk/cfet_idvg.pvd (or structure.vtm) first")

view = GetActiveViewOrCreate("RenderView")

# clip the device open at the mid-plane, like the paper's cutaway
clip = Clip(Input=source)
clip.ClipType = "Plane"
clip.ClipType.Normal = [0.0, 0.0, 1.0]
bounds = source.GetDataInformation().GetBounds()
clip.ClipType.Origin = [(bounds[0] + bounds[1]) / 2,
                        (bounds[2] + bounds[3]) / 2,
                        (bounds[4] + bounds[5]) / 2]

Hide(source, view)
display = Show(clip, view)

# color by the CVT electron mobility (cell data in lombardi_vsat runs);
# fall back to NetDoping for structure-only exports
info = clip.GetDataInformation()
field = ("mu_n_cvt" if info.GetCellDataInformation()
         .GetArrayInformation("mu_n_cvt") else "NetDoping")
assoc = "CELLS" if field == "mu_n_cvt" else "POINTS"
ColorBy(display, (assoc, field))
display.RescaleTransferFunctionToDataRange(True)
display.SetScalarBarVisibility(view, True)
GetColorTransferFunction(field).ApplyPreset("Turbo", True)

view.ResetCamera()
Render()

# --- optional: OSPRay path-traced shading (needs an OSPRay-enabled
# ParaView build; this is the capability PyVista's pip wheel lacks) ---
# view.EnableRayTracing = 1
# view.BackEnd = "OSPRay pathtracer"
