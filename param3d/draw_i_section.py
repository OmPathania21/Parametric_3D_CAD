"""Utility to create an I-section girder solid in pythonOCC."""

from __future__ import annotations

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.gp import gp_Pnt, gp_Vec


def create_i_section(
    length: float,
    flange_width: float,
    depth: float,
    flange_thickness: float,
    web_thickness: float,
) -> TopoDS_Shape:
    """
    Create a prismatic I-section solid.

    Profile frame at x=0:
    - Y spans [0, flange_width]
    - Z spans [0, depth]
    Extrusion direction:
    - +X for 'length'
    """
    if length <= 0:
        raise ValueError("length must be > 0")
    if flange_width <= 0:
        raise ValueError("flange_width must be > 0")
    if depth <= 0:
        raise ValueError("depth must be > 0")
    if flange_thickness <= 0:
        raise ValueError("flange_thickness must be > 0")
    if web_thickness <= 0:
        raise ValueError("web_thickness must be > 0")
    if web_thickness > flange_width:
        raise ValueError("web_thickness must be <= flange_width")
    if 2.0 * flange_thickness >= depth:
        raise ValueError("2 * flange_thickness must be < depth")

    y_mid = 0.5 * flange_width
    y_web_min = y_mid - 0.5 * web_thickness
    y_web_max = y_mid + 0.5 * web_thickness
    z_bot = flange_thickness
    z_top = depth - flange_thickness

    profile_points = [
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(0.0, flange_width, 0.0),
        gp_Pnt(0.0, flange_width, z_bot),
        gp_Pnt(0.0, y_web_max, z_bot),
        gp_Pnt(0.0, y_web_max, z_top),
        gp_Pnt(0.0, flange_width, z_top),
        gp_Pnt(0.0, flange_width, depth),
        gp_Pnt(0.0, 0.0, depth),
        gp_Pnt(0.0, 0.0, z_top),
        gp_Pnt(0.0, y_web_min, z_top),
        gp_Pnt(0.0, y_web_min, z_bot),
        gp_Pnt(0.0, 0.0, z_bot),
    ]

    polygon = BRepBuilderAPI_MakePolygon()
    for point in profile_points:
        polygon.Add(point)
    polygon.Close()

    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(length, 0.0, 0.0)).Shape()
