"""Utility to create an axis-aligned rectangular prism in pythonOCC."""

from __future__ import annotations

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.TopoDS import TopoDS_Shape
from OCC.Core.gp import gp_Pnt


def create_rectangular_prism(length: float, width: float, depth: float) -> TopoDS_Shape:
    """
    Create a rectangular prism with one corner at the origin.

    The resulting solid spans:
    - X: [0, length]
    - Y: [0, width]
    - Z: [0, depth]
    """
    if length <= 0:
        raise ValueError("length must be > 0")
    if width <= 0:
        raise ValueError("width must be > 0")
    if depth <= 0:
        raise ValueError("depth must be > 0")

    return BRepPrimAPI_MakeBox(gp_Pnt(0.0, 0.0, 0.0), length, width, depth).Shape()
