"""
Parametric 3D CAD model of a short-span steel girder bridge using pythonOCC.

Coordinate system:
- X: span direction
- Y: bridge width direction
- Z: vertical direction
- Origin: center of span at deck top level
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_Transform,
)
from OCC.Core.BRepPrimAPI import (
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakePrism,
)
from OCC.Core.BRepTools import breptools_Write
from OCC.Core.AIS import AIS_Shape
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape
from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCC.Display.SimpleGui import init_display
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop_VolumeProperties


def _load_external_function(module_basename: str, function_name: str):
    """
    Load a required function from:
    1) normal import path
    2) current script directory
    3) current working directory
    4) ~/Downloads (including files renamed by macOS as "(1)")
    """
    search_dirs = [
        Path(__file__).resolve().parent,
        Path.cwd(),
        Path.home() / "Downloads",
    ]
    file_candidates = [f"{module_basename}.py", f"{module_basename} (1).py"]

    try:
        module = importlib.import_module(module_basename)
        return getattr(module, function_name)
    except Exception:
        pass

    for folder in search_dirs:
        for filename in file_candidates:
            module_path = folder / filename
            if not module_path.is_file():
                continue
            spec = importlib.util.spec_from_file_location(
                f"{module_basename}_{abs(hash(str(module_path)))}",
                str(module_path),
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, function_name):
                return getattr(module, function_name)

    raise ImportError(
        f"Could not import '{function_name}' from '{module_basename}'. "
        f"Place {module_basename}.py next to this script or in ~/Downloads."
    )


# Required external factories (must be reused, not reimplemented)
create_rectangular_prism = _load_external_function(
    "draw_rectangular_prism", "create_rectangular_prism"
)
create_i_section = _load_external_function("draw_i_section", "create_i_section")


# ========================
# Parameters: Geometry
# ========================
GEOMETRY = {
    "span_length_L": 12000.0,
    "n_girders": 3,
    "girder_spacing": 3000.0,
    "n_support_lines": 2,
    "support_offset_from_ends": 800.0,
}


# ========================
# Parameters: Girder section
# ========================
GIRDER_SECTION = {
    "girder_depth": 900.0,
    "girder_flange_width": 400.0,
    "flange_thickness": 25.0,
    "web_thickness": 14.0,
}


# ========================
# Parameters: Deck
# ========================
DECK = {
    "deck_width": 7000.0,
    "deck_thickness": 200.0,
    "deck_top_elevation_z": 0.0,
}


# ========================
# Parameters: Pier & cap
# ========================
PIER_AND_CAP = {
    "pier_diameter": 900.0,
    "pier_height": 3000.0,
    "pier_cap_length": 2500.0,
    "pier_cap_width_top": 1200.0,
    "pier_cap_width_bottom": 2200.0,
    "pier_cap_depth": 1000.0,
    "cap_to_deck_gap": 120.0,
}


# ========================
# Parameters: Piles
# ========================
PILES = {
    "pile_diameter": 600.0,
    "pile_length": 5000.0,
    "pile_rows": 2,
    "pile_cols": 2,
    "pile_spacing_x": 1600.0,
    "pile_spacing_y": 1500.0,
    "pile_cap_length": 3400.0,
    "pile_cap_width": 3000.0,
    "pile_cap_depth": 1200.0,
}


# ========================
# Parameters: Reinforcement
# ========================
REINFORCEMENT = {
    "rebar_diameter": 16.0,
    "deck_cover": 40.0,
    "pier_cover": 60.0,
    "deck_spacing_longitudinal": 200.0,
    "deck_spacing_transverse": 200.0,
    "pier_vertical_bar_count": 12,
}


# ========================
# Parameters: Visualization
# ========================
VISUALIZATION = {
    "concrete_transparency": 0.60,
    "concrete_opacity": 0.60,
    "background_r": 0.90,
    "background_g": 0.90,
    "background_b": 0.90,
    "enable_shaded_mode": True,
    "force_lights_on": True,
    "show_axes": True,
    "show_rebar": True,
}


# ========================
# Parameters: Export
# ========================
EXPORT = {
    "save_step": True,
    "save_brep": False,
    "step_filename": "bridge_model.step",
    "brep_filename": "bridge_model.brep",
}


# ========================
# Bonus features
# ========================
BONUS = {
    "cross_frames_enabled": True,
    "cross_frame_spacing": 3000.0,
    "cross_frame_thickness": 100.0,
    "cross_frame_depth": 300.0,
    "parapets_enabled": True,
    "parapet_height": 500.0,
    "parapet_thickness": 150.0,
}


PARAM_GROUPS: Dict[str, Dict[str, Any]] = {
    "geometry": GEOMETRY,
    "girder_section": GIRDER_SECTION,
    "deck": DECK,
    "pier_and_cap": PIER_AND_CAP,
    "piles": PILES,
    "reinforcement": REINFORCEMENT,
    "visualization": VISUALIZATION,
    "export": EXPORT,
    "bonus": BONUS,
}

BASE_PARAM_GROUPS: Dict[str, Dict[str, Any]] = {
    name: dict(group) for name, group in PARAM_GROUPS.items()
}
BASE_PARAM_TEMPLATES: Dict[str, Any] = {
    key: value
    for group in BASE_PARAM_GROUPS.values()
    for key, value in group.items()
}

_LAST_BRIDGE_MODEL: Dict[str, Any] | None = None


def get_default_params() -> Dict[str, Any]:
    params: Dict[str, Any] = {
        key: value
        for group in BASE_PARAM_GROUPS.values()
        for key, value in group.items()
    }
    params["column_height"] = float(params["pier_height"])
    params["column_diameter"] = float(params["pier_diameter"])
    return params


def get_current_params() -> Dict[str, Any]:
    params: Dict[str, Any] = {
        key: value for group in PARAM_GROUPS.values() for key, value in group.items()
    }
    params["column_height"] = float(params["pier_height"])
    params["column_diameter"] = float(params["pier_diameter"])
    return params


def _coerce_runtime_value(value: Any, template: Any) -> Any:
    if isinstance(value, str):
        return _coerce_value(value, template)
    if isinstance(template, bool):
        return bool(value)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(value)
    if isinstance(template, float):
        return float(value)
    return value


def _resolve_build_params(params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    resolved = get_default_params()
    input_params = params or {}

    for key, value in input_params.items():
        if key == "column_height":
            resolved["column_height"] = float(value)
            resolved["pier_height"] = float(value)
            continue

        if key == "column_diameter":
            resolved["column_diameter"] = float(value)
            resolved["pier_diameter"] = float(value)
            continue

        if key not in BASE_PARAM_TEMPLATES:
            raise KeyError(f"Unknown parameter '{key}'.")

        resolved[key] = _coerce_runtime_value(value, BASE_PARAM_TEMPLATES[key])

    if "column_height" not in input_params and "pier_height" in input_params:
        resolved["column_height"] = float(resolved["pier_height"])
    if "column_diameter" not in input_params and "pier_diameter" in input_params:
        resolved["column_diameter"] = float(resolved["pier_diameter"])

    resolved["pier_height"] = float(resolved["column_height"])
    resolved["pier_diameter"] = float(resolved["column_diameter"])
    return resolved


def _apply_params_to_groups(resolved: Dict[str, Any]) -> None:
    for group in PARAM_GROUPS.values():
        for key in group:
            if key in resolved:
                group[key] = resolved[key]


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value}")


def _coerce_value(raw: str, template: Any) -> Any:
    if isinstance(template, bool):
        return _parse_bool(raw)
    if isinstance(template, int) and not isinstance(template, bool):
        return int(float(raw))
    if isinstance(template, float):
        return float(raw)
    return raw


def apply_cli_overrides(override_items: Sequence[str]) -> None:
    for item in override_items:
        if "=" not in item:
            raise ValueError(
                f"Invalid override '{item}'. Use key=value or group.key=value."
            )

        lhs, rhs = item.split("=", 1)
        key_expr = lhs.strip()
        rhs = rhs.strip()

        if "." in key_expr:
            group_name, key = key_expr.split(".", 1)
            group_name = group_name.strip().lower()
            if group_name not in PARAM_GROUPS:
                raise KeyError(f"Unknown parameter group '{group_name}'.")
            group = PARAM_GROUPS[group_name]
            if key not in group:
                raise KeyError(f"Unknown parameter '{key}' in group '{group_name}'.")
            group[key] = _coerce_value(rhs, group[key])
            continue

        matches: List[Tuple[str, Dict[str, Any]]] = [
            (name, group) for name, group in PARAM_GROUPS.items() if key_expr in group
        ]
        if not matches:
            raise KeyError(f"Unknown parameter '{key_expr}'.")
        if len(matches) > 1:
            candidate_groups = ", ".join(name for name, _ in matches)
            raise KeyError(
                f"Parameter '{key_expr}' is ambiguous. Use group.key=... "
                f"(groups: {candidate_groups})."
            )

        group_name, group = matches[0]
        group[key_expr] = _coerce_value(rhs, group[key_expr])
        _ = group_name


def transform_translate(shape: TopoDS_Shape, dx: float, dy: float, dz: float) -> TopoDS_Shape:
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def make_compound(shapes: Iterable[TopoDS_Shape]) -> TopoDS_Compound:
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def linear_positions(start: float, end: float, spacing: float) -> List[float]:
    if spacing <= 0:
        raise ValueError("Spacing must be positive.")
    if end < start:
        start, end = end, start
    if math.isclose(start, end, abs_tol=1e-9):
        return [0.5 * (start + end)]

    values = [start]
    cursor = start
    while cursor + spacing < end - 1e-9:
        cursor += spacing
        values.append(cursor)

    if not math.isclose(values[-1], end, abs_tol=1e-6):
        values.append(end)
    return values


def symmetric_offsets(count: int, spacing: float) -> List[float]:
    if count <= 1:
        return [0.0]
    half_span = 0.5 * (count - 1) * spacing
    return [-half_span + i * spacing for i in range(count)]


def create_cylinder_along_axis(
    start_point: gp_Pnt, axis_dir: gp_Dir, length: float, diameter: float
) -> TopoDS_Shape:
    if length <= 0:
        raise ValueError("Cylinder length must be > 0.")
    radius = 0.5 * diameter
    return BRepPrimAPI_MakeCylinder(gp_Ax2(start_point, axis_dir), radius, length).Shape()


# ========================
# Component factories
# ========================
def create_circular_pier(diameter: float, height: float) -> TopoDS_Shape:
    return BRepPrimAPI_MakeCylinder(0.5 * diameter, height).Shape()


def create_trapezoidal_pier_cap(
    length: float, width_top: float, width_bottom: float, depth: float
) -> TopoDS_Shape:
    polygon = BRepBuilderAPI_MakePolygon()
    polygon.Add(gp_Pnt(0.0, -0.5 * width_bottom, 0.0))
    polygon.Add(gp_Pnt(0.0, 0.5 * width_bottom, 0.0))
    polygon.Add(gp_Pnt(0.0, 0.5 * width_top, depth))
    polygon.Add(gp_Pnt(0.0, -0.5 * width_top, depth))
    polygon.Close()

    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(length, 0.0, 0.0)).Shape()
    return transform_translate(prism, -0.5 * length, 0.0, 0.0)


def create_pile(diameter: float, length: float) -> TopoDS_Shape:
    return BRepPrimAPI_MakeCylinder(0.5 * diameter, length).Shape()


def create_pile_cap(length: float, width: float, depth: float) -> TopoDS_Shape:
    return create_rectangular_prism(length, width, depth)


def create_rebar_grid_for_deck(
    span_length: float,
    deck_width: float,
    deck_thickness: float,
    bar_diameter: float,
    cover: float,
    spacing_longitudinal: float,
    spacing_transverse: float,
    deck_top_z: float = 0.0,
) -> List[TopoDS_Shape]:
    x_min = -0.5 * span_length
    x_max = 0.5 * span_length
    y_min = -0.5 * deck_width
    y_max = 0.5 * deck_width
    z_min = deck_top_z - deck_thickness
    z_max = deck_top_z

    clear = cover + 0.5 * bar_diameter

    x0 = x_min + clear
    x1 = x_max - clear
    y0 = y_min + clear
    y1 = y_max - clear

    if x1 <= x0 or y1 <= y0:
        return []

    z_bottom = z_min + clear
    z_top = z_max - clear
    if z_top <= z_bottom:
        z_layers = [0.5 * (z_bottom + z_top)]
    else:
        z_layers = [z_bottom, z_top]

    rebars: List[TopoDS_Shape] = []

    y_lines = linear_positions(y0, y1, spacing_transverse)
    for z in z_layers:
        for y in y_lines:
            start = gp_Pnt(x0, y, z)
            rebars.append(
                create_cylinder_along_axis(start, gp_Dir(1.0, 0.0, 0.0), x1 - x0, bar_diameter)
            )

    x_lines = linear_positions(x0, x1, spacing_longitudinal)
    for z in z_layers:
        for x in x_lines:
            start = gp_Pnt(x, y0, z)
            rebars.append(
                create_cylinder_along_axis(start, gp_Dir(0.0, 1.0, 0.0), y1 - y0, bar_diameter)
            )

    return rebars


def create_vertical_rebars_for_circular_pier(
    center_x: float,
    center_y: float,
    pier_diameter: float,
    pier_bottom_z: float,
    pier_height: float,
    bar_diameter: float,
    cover: float,
    bar_count: int,
) -> List[TopoDS_Shape]:
    if bar_count <= 0:
        return []

    clear_radius = 0.5 * pier_diameter - cover - 0.5 * bar_diameter
    bar_length = pier_height - 2.0 * cover
    if clear_radius <= 0 or bar_length <= 0:
        return []

    z_start = pier_bottom_z + cover
    rebars: List[TopoDS_Shape] = []
    for i in range(bar_count):
        angle = (2.0 * math.pi * i) / bar_count
        x = center_x + clear_radius * math.cos(angle)
        y = center_y + clear_radius * math.sin(angle)
        start = gp_Pnt(x, y, z_start)
        rebars.append(
            create_cylinder_along_axis(start, gp_Dir(0.0, 0.0, 1.0), bar_length, bar_diameter)
        )

    return rebars


# ========================
# Assembly functions
# ========================
def get_girder_y_positions() -> List[float]:
    return symmetric_offsets(int(GEOMETRY["n_girders"]), float(GEOMETRY["girder_spacing"]))


def get_support_x_positions() -> List[float]:
    n_supports = int(GEOMETRY["n_support_lines"])
    span = float(GEOMETRY["span_length_L"])
    end_offset = float(GEOMETRY["support_offset_from_ends"])

    x_start = -0.5 * span + end_offset
    x_end = 0.5 * span - end_offset

    if n_supports <= 1 or x_end <= x_start:
        return [0.0]
    if n_supports == 2:
        return [x_start, x_end]

    step = (x_end - x_start) / (n_supports - 1)
    return [x_start + i * step for i in range(n_supports)]


def build_girders() -> List[TopoDS_Shape]:
    span = float(GEOMETRY["span_length_L"])
    girder_depth = float(GIRDER_SECTION["girder_depth"])
    flange_width = float(GIRDER_SECTION["girder_flange_width"])
    flange_thickness = float(GIRDER_SECTION["flange_thickness"])
    web_thickness = float(GIRDER_SECTION["web_thickness"])
    deck_top_z = float(DECK["deck_top_elevation_z"])
    deck_thickness = float(DECK["deck_thickness"])

    girder_proto = create_i_section(
        span,
        flange_width,
        girder_depth,
        flange_thickness,
        web_thickness,
    )

    z_base = deck_top_z - deck_thickness - girder_depth
    steel_shapes: List[TopoDS_Shape] = []

    y_positions = get_girder_y_positions()
    for y_center in y_positions:
        steel_shapes.append(
            transform_translate(
                girder_proto,
                -0.5 * span,
                y_center - 0.5 * flange_width,
                z_base,
            )
        )

    if BONUS["cross_frames_enabled"] and len(y_positions) > 1:
        frame_spacing = float(BONUS["cross_frame_spacing"])
        frame_thickness = float(BONUS["cross_frame_thickness"])
        frame_depth = float(BONUS["cross_frame_depth"])

        frame_x_min = -0.5 * span + float(GEOMETRY["support_offset_from_ends"])
        frame_x_max = 0.5 * span - float(GEOMETRY["support_offset_from_ends"])
        if frame_x_max > frame_x_min:
            frame_x_positions = linear_positions(frame_x_min, frame_x_max, frame_spacing)
            frame_z = deck_top_z - deck_thickness - 0.75 * girder_depth

            for x_center in frame_x_positions:
                for idx in range(len(y_positions) - 1):
                    y_left_face = y_positions[idx] + 0.5 * flange_width
                    y_right_face = y_positions[idx + 1] - 0.5 * flange_width
                    clear_gap = y_right_face - y_left_face
                    if clear_gap <= 0:
                        continue

                    frame = create_rectangular_prism(frame_thickness, clear_gap, frame_depth)
                    steel_shapes.append(
                        transform_translate(
                            frame,
                            x_center - 0.5 * frame_thickness,
                            y_left_face,
                            frame_z,
                        )
                    )

    return steel_shapes


def build_deck() -> TopoDS_Shape:
    span = float(GEOMETRY["span_length_L"])
    width = float(DECK["deck_width"])
    thickness = float(DECK["deck_thickness"])
    deck_top_z = float(DECK["deck_top_elevation_z"])

    deck = create_rectangular_prism(span, width, thickness)
    return transform_translate(deck, -0.5 * span, -0.5 * width, deck_top_z - thickness)


def build_parapets() -> List[TopoDS_Shape]:
    if not BONUS["parapets_enabled"]:
        return []

    span = float(GEOMETRY["span_length_L"])
    deck_width = float(DECK["deck_width"])
    deck_top_z = float(DECK["deck_top_elevation_z"])
    parapet_height = float(BONUS["parapet_height"])
    parapet_thickness = float(BONUS["parapet_thickness"])

    parapet_proto = create_rectangular_prism(span, parapet_thickness, parapet_height)
    x_origin = -0.5 * span

    y_left = -0.5 * deck_width
    y_right = 0.5 * deck_width - parapet_thickness

    return [
        transform_translate(parapet_proto, x_origin, y_left, deck_top_z),
        transform_translate(parapet_proto, x_origin, y_right, deck_top_z),
    ]


def build_piers_and_foundation(
    resolved_params: Dict[str, Any] | None = None,
) -> Tuple[List[TopoDS_Shape], List[Dict[str, float]]]:
    runtime = resolved_params or {}
    column_height = float(runtime.get("column_height", PIER_AND_CAP["pier_height"]))
    column_diameter = float(runtime.get("column_diameter", PIER_AND_CAP["pier_diameter"]))
    base_column_height = float(PIER_AND_CAP["pier_height"])

    support_x_positions = get_support_x_positions()

    deck_bottom_z = float(DECK["deck_top_elevation_z"]) - float(DECK["deck_thickness"])
    pier_cap_top_z = deck_bottom_z - float(PIER_AND_CAP["cap_to_deck_gap"])
    pier_cap_bottom_z = pier_cap_top_z - float(PIER_AND_CAP["pier_cap_depth"])

    # Keep foundation elevation fixed: only the column geometry varies with params.
    fixed_pier_bottom_z = pier_cap_bottom_z - base_column_height
    pier_bottom_z = pier_cap_bottom_z - column_height

    pile_cap_top_z = fixed_pier_bottom_z
    pile_cap_bottom_z = pile_cap_top_z - float(PILES["pile_cap_depth"])
    pile_top_z = pile_cap_bottom_z

    pier_proto = create_circular_pier(
        column_diameter,
        column_height,
    )
    pier_cap_proto = create_trapezoidal_pier_cap(
        float(PIER_AND_CAP["pier_cap_length"]),
        float(PIER_AND_CAP["pier_cap_width_top"]),
        float(PIER_AND_CAP["pier_cap_width_bottom"]),
        float(PIER_AND_CAP["pier_cap_depth"]),
    )
    pile_cap_proto = create_pile_cap(
        float(PILES["pile_cap_length"]),
        float(PILES["pile_cap_width"]),
        float(PILES["pile_cap_depth"]),
    )
    pile_proto = create_pile(float(PILES["pile_diameter"]), float(PILES["pile_length"]))

    pile_x_offsets = symmetric_offsets(int(PILES["pile_cols"]), float(PILES["pile_spacing_x"]))
    pile_y_offsets = symmetric_offsets(int(PILES["pile_rows"]), float(PILES["pile_spacing_y"]))

    concrete_shapes: List[TopoDS_Shape] = []
    pier_metadata: List[Dict[str, float]] = []

    for support_x in support_x_positions:
        concrete_shapes.append(transform_translate(pier_cap_proto, support_x, 0.0, pier_cap_bottom_z))
        concrete_shapes.append(transform_translate(pier_proto, support_x, 0.0, pier_bottom_z))

        concrete_shapes.append(
            transform_translate(
                pile_cap_proto,
                support_x - 0.5 * float(PILES["pile_cap_length"]),
                -0.5 * float(PILES["pile_cap_width"]),
                pile_cap_bottom_z,
            )
        )

        for dx in pile_x_offsets:
            for dy in pile_y_offsets:
                concrete_shapes.append(
                    transform_translate(
                        pile_proto,
                        support_x + dx,
                        dy,
                        pile_top_z - float(PILES["pile_length"]),
                    )
                )

        pier_metadata.append(
            {
                "center_x": support_x,
                "center_y": 0.0,
                "bottom_z": pier_bottom_z,
                "height": column_height,
                "diameter": column_diameter,
            }
        )

    return concrete_shapes, pier_metadata


def build_rebars(pier_metadata: Sequence[Dict[str, float]]) -> List[TopoDS_Shape]:
    bars: List[TopoDS_Shape] = []

    bars.extend(
        create_rebar_grid_for_deck(
            span_length=float(GEOMETRY["span_length_L"]),
            deck_width=float(DECK["deck_width"]),
            deck_thickness=float(DECK["deck_thickness"]),
            bar_diameter=float(REINFORCEMENT["rebar_diameter"]),
            cover=float(REINFORCEMENT["deck_cover"]),
            spacing_longitudinal=float(REINFORCEMENT["deck_spacing_longitudinal"]),
            spacing_transverse=float(REINFORCEMENT["deck_spacing_transverse"]),
            deck_top_z=float(DECK["deck_top_elevation_z"]),
        )
    )

    for item in pier_metadata:
        bars.extend(
            create_vertical_rebars_for_circular_pier(
                center_x=float(item["center_x"]),
                center_y=float(item["center_y"]),
                pier_diameter=float(item["diameter"]),
                pier_bottom_z=float(item["bottom_z"]),
                pier_height=float(item["height"]),
                bar_diameter=float(REINFORCEMENT["rebar_diameter"]),
                cover=float(REINFORCEMENT["pier_cover"]),
                bar_count=int(REINFORCEMENT["pier_vertical_bar_count"]),
            )
        )

    return bars


def assemble_bridge(resolved_params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    steel_shapes = build_girders() + build_parapets()

    deck_shape = build_deck()
    foundation_shapes, pier_metadata = build_piers_and_foundation(resolved_params)
    concrete_shapes = [deck_shape] + foundation_shapes

    rebar_shapes = build_rebars(pier_metadata)

    all_shapes: List[TopoDS_Shape] = []
    all_shapes.extend(steel_shapes)
    all_shapes.extend(concrete_shapes)
    all_shapes.extend(rebar_shapes)

    assembly = make_compound(all_shapes)
    return {
        "assembly": assembly,
        "steel": steel_shapes,
        "concrete": concrete_shapes,
        "rebar": rebar_shapes,
    }


def build_bridge_model(params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    global _LAST_BRIDGE_MODEL
    resolved = _resolve_build_params(params)
    _apply_params_to_groups(resolved)
    validate_parameters()
    model = assemble_bridge(resolved)
    model["params"] = resolved
    _LAST_BRIDGE_MODEL = model
    return model


def build_bridge(params: Dict[str, Any]) -> TopoDS_Compound:
    column_height = float(params.get("column_height", PIER_AND_CAP["pier_height"]))
    column_diameter = float(params.get("column_diameter", PIER_AND_CAP["pier_diameter"]))
    span_length = float(params.get("span_length_L", GEOMETRY["span_length_L"]))
    deck_width = float(params.get("deck_width", DECK["deck_width"]))
    deck_thickness = float(params.get("deck_thickness", DECK["deck_thickness"]))
    rebar_diameter = float(params.get("rebar_diameter", REINFORCEMENT["rebar_diameter"]))
    deck_cover = float(params.get("deck_cover", REINFORCEMENT["deck_cover"]))
    deck_spacing_longitudinal = float(
        params.get("deck_spacing_longitudinal", REINFORCEMENT["deck_spacing_longitudinal"])
    )
    deck_spacing_transverse = float(
        params.get("deck_spacing_transverse", REINFORCEMENT["deck_spacing_transverse"])
    )
    n_girders = int(params.get("n_girders", GEOMETRY["n_girders"]))
    girder_spacing = float(params.get("girder_spacing", GEOMETRY["girder_spacing"]))
    girder_depth = float(params.get("girder_depth", GIRDER_SECTION["girder_depth"]))
    girder_flange_width = float(params.get("girder_flange_width", GIRDER_SECTION["girder_flange_width"]))
    pier_cap_length = float(params.get("pier_cap_length", PIER_AND_CAP["pier_cap_length"]))
    pier_cap_width_top = float(params.get("pier_cap_width_top", PIER_AND_CAP["pier_cap_width_top"]))
    pier_cap_width_bottom = float(params.get("pier_cap_width_bottom", PIER_AND_CAP["pier_cap_width_bottom"]))
    pier_cap_depth = float(params.get("pier_cap_depth", PIER_AND_CAP["pier_cap_depth"]))
    cap_to_deck_gap = float(params.get("cap_to_deck_gap", PIER_AND_CAP["cap_to_deck_gap"]))
    pile_cap_length = float(params.get("pile_cap_length", PILES["pile_cap_length"]))
    pile_cap_width = float(params.get("pile_cap_width", PILES["pile_cap_width"]))
    pile_cap_depth = float(params.get("pile_cap_depth", PILES["pile_cap_depth"]))
    pile_diameter = float(params.get("pile_diameter", PILES["pile_diameter"]))
    pile_length = float(params.get("pile_length", PILES["pile_length"]))
    pile_rows = int(params.get("pile_rows", PILES["pile_rows"]))
    pile_cols = int(params.get("pile_cols", PILES["pile_cols"]))
    pile_spacing_x = float(params.get("pile_spacing_x", PILES["pile_spacing_x"]))
    pile_spacing_y = float(params.get("pile_spacing_y", PILES["pile_spacing_y"]))

    print("Column height:", column_height)

    runtime_overrides = {
        "column_height": column_height,
        "column_diameter": column_diameter,
        "span_length_L": span_length,
        "deck_width": deck_width,
        "deck_thickness": deck_thickness,
        "rebar_diameter": rebar_diameter,
        "deck_cover": deck_cover,
        "deck_spacing_longitudinal": deck_spacing_longitudinal,
        "deck_spacing_transverse": deck_spacing_transverse,
        "n_girders": n_girders,
        "girder_spacing": girder_spacing,
        "girder_depth": girder_depth,
        "girder_flange_width": girder_flange_width,
        "pier_cap_length": pier_cap_length,
        "pier_cap_width_top": pier_cap_width_top,
        "pier_cap_width_bottom": pier_cap_width_bottom,
        "pier_cap_depth": pier_cap_depth,
        "cap_to_deck_gap": cap_to_deck_gap,
        "pile_cap_length": pile_cap_length,
        "pile_cap_width": pile_cap_width,
        "pile_cap_depth": pile_cap_depth,
        "pile_diameter": pile_diameter,
        "pile_length": pile_length,
        "pile_rows": pile_rows,
        "pile_cols": pile_cols,
        "pile_spacing_x": pile_spacing_x,
        "pile_spacing_y": pile_spacing_y,
    }
    return build_bridge_model(runtime_overrides)["assembly"]


def get_last_bridge_model() -> Dict[str, Any] | None:
    return _LAST_BRIDGE_MODEL


# ========================
# Visualization and export
# ========================
def display_shape(
    display: Any,
    shape: TopoDS_Shape,
    color: Quantity_Color,
    transparency: float = 0.0,
) -> AIS_Shape:
    ais = AIS_Shape(shape)
    ais.SetColor(color)
    if transparency > 0.0:
        ais.SetTransparency(transparency)
    display.Context.Display(ais, True)
    return ais


def configure_display_scene(display: Any) -> None:
    if hasattr(display, "SetModeShaded"):
        display.SetModeShaded()

    if hasattr(display, "View") and hasattr(display.View, "SetBackgroundColor"):
        try:
            try:
                display.View.SetBackgroundColor(0.85, 0.85, 0.85)
            except TypeError:
                bg = Quantity_Color(0.85, 0.85, 0.85, Quantity_TOC_RGB)
                display.View.SetBackgroundColor(bg)
        except Exception:
            pass

    if hasattr(display, "View") and hasattr(display.View, "SetLightOn"):
        try:
            display.View.SetLightOn()
        except Exception:
            pass


def get_shape_volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    brepgprop_VolumeProperties(shape, props)
    return props.Mass()


def render_bridge_model(
    display: Any,
    model: Dict[str, Any],
    show_rebar: bool | None = None,
    fit_all: bool = True,
) -> Tuple[Dict[str, List[AIS_Shape]], Dict[Any, str]]:
    steel_color = Quantity_Color(0.3, 0.3, 0.35, Quantity_TOC_RGB)
    concrete_color = Quantity_Color(0.75, 0.75, 0.75, Quantity_TOC_RGB)
    rebar_color = Quantity_Color(0.8, 0.1, 0.1, Quantity_TOC_RGB)

    groups: Dict[str, List[AIS_Shape]] = {"steel": [], "concrete": [], "rebar": []}
    metadata_map: Dict[Any, str] = {}

    for shape in model["steel"]:
        ais = display_shape(display, shape, steel_color)
        groups["steel"].append(ais)
        vol = get_shape_volume(shape) / 1e9  # mm³ to m³
        metadata_map[ais] = f"Steel Component\nVolume: {vol:.2f} m³"

    concrete_shapes = list(model["concrete"])
    if concrete_shapes:
        ais = display_shape(display, concrete_shapes[0], concrete_color, transparency=0.6)
        groups["concrete"].append(ais)
        vol = get_shape_volume(concrete_shapes[0]) / 1e9
        metadata_map[ais] = f"Concrete Deck\nVolume: {vol:.2f} m³"
        
        for shape in concrete_shapes[1:]:
            ais_sub = display_shape(display, shape, concrete_color, transparency=0.5)
            groups["concrete"].append(ais_sub)
            vol_sub = get_shape_volume(shape) / 1e9
            metadata_map[ais_sub] = f"Concrete Substructure\nVolume: {vol_sub:.2f} m³"

    is_rebar_visible = bool(VISUALIZATION.get("show_rebar", True)) if show_rebar is None else bool(show_rebar)
    if is_rebar_visible:
        for shape in model["rebar"]:
            ais = display_shape(display, shape, rebar_color, transparency=0.0)
            groups["rebar"].append(ais)
            # Pre-compute simple info
            # Vol is small for rebar, maybe dm^3 
            vol = get_shape_volume(shape) / 1e6 # mm³ to dm³ (Liters)
            metadata_map[ais] = f"Rebar\nVolume: {vol:.3f} L"
    else:
        for shape in model["rebar"]:
            ais = AIS_Shape(shape)
            ais.SetColor(rebar_color)
            groups["rebar"].append(ais)
            vol = get_shape_volume(shape) / 1e6
            metadata_map[ais] = f"Rebar\nVolume: {vol:.3f} L"

    if fit_all:
        display.FitAll()

    return groups, metadata_map


def visualize_bridge(model: Dict[str, Any], screenshot_path: str = "") -> None:
    display, start_display, add_menu, add_function_to_menu = init_display()
    configure_display_scene(display)
    rebar_visible = bool(VISUALIZATION.get("show_rebar", True))
    rendered_groups, _ = render_bridge_model(display, model, show_rebar=rebar_visible, fit_all=True)
    rebar_ais = rendered_groups["rebar"]

    def toggle_rebar() -> None:
        nonlocal rebar_visible
        rebar_visible = not rebar_visible
        for ais in rebar_ais:
            if rebar_visible:
                display.Context.Display(ais, False)
            else:
                display.Context.Erase(ais, False)
        display.Context.UpdateCurrentViewer()

    if rebar_ais:
        add_menu("Bridge")
        add_function_to_menu("Bridge", toggle_rebar)

    if bool(VISUALIZATION["show_axes"]):
        if hasattr(display, "display_triedron"):
            display.display_triedron()
        elif hasattr(display, "display_trihedron"):
            display.display_trihedron()

    if screenshot_path and hasattr(display, "View") and hasattr(display.View, "Dump"):
        display.View.Dump(screenshot_path)

    start_display()


def export_bridge(shape: TopoDS_Shape) -> None:
    if bool(EXPORT["save_step"]):
        step_writer = STEPControl_Writer()
        step_writer.Transfer(shape, STEPControl_AsIs)
        status = step_writer.Write(str(EXPORT["step_filename"]))
        if status == IFSelect_RetDone:
            print(f"STEP export complete: {EXPORT['step_filename']}")
        else:
            print("STEP export failed.")

    if bool(EXPORT["save_brep"]):
        breptools_Write(shape, str(EXPORT["brep_filename"]))
        print(f"BREP export complete: {EXPORT['brep_filename']}")


# ========================
# Validation and entrypoint
# ========================
def validate_parameters() -> None:
    GEOMETRY["n_girders"] = int(GEOMETRY["n_girders"])
    GEOMETRY["n_support_lines"] = int(GEOMETRY["n_support_lines"])
    PILES["pile_rows"] = int(PILES["pile_rows"])
    PILES["pile_cols"] = int(PILES["pile_cols"])
    REINFORCEMENT["pier_vertical_bar_count"] = int(REINFORCEMENT["pier_vertical_bar_count"])

    if GEOMETRY["span_length_L"] <= 0:
        raise ValueError("span_length_L must be positive.")
    if GEOMETRY["n_girders"] < 1:
        raise ValueError("n_girders must be at least 1.")
    if GEOMETRY["girder_spacing"] <= 0 and GEOMETRY["n_girders"] > 1:
        raise ValueError("girder_spacing must be positive when n_girders > 1.")

    required_girder_width = (
        (GEOMETRY["n_girders"] - 1) * GEOMETRY["girder_spacing"]
        + GIRDER_SECTION["girder_flange_width"]
    )
    if required_girder_width > DECK["deck_width"]:
        raise ValueError(
            "Deck width is too small for specified girders and spacing. "
            f"Need at least {required_girder_width:.1f} mm."
        )

    if DECK["deck_thickness"] <= 0:
        raise ValueError("deck_thickness must be positive.")
    if PIER_AND_CAP["pier_height"] <= 0 or PIER_AND_CAP["pier_diameter"] <= 0:
        raise ValueError("Pier diameter and height must be positive.")
    if PILES["pile_length"] <= 0 or PILES["pile_diameter"] <= 0:
        raise ValueError("Pile diameter and length must be positive.")

    if REINFORCEMENT["rebar_diameter"] <= 0:
        raise ValueError("rebar_diameter must be positive.")

    concrete_transparency = float(
        VISUALIZATION.get("concrete_transparency", VISUALIZATION.get("concrete_opacity", 0.60))
    )
    if concrete_transparency < 0.0 or concrete_transparency >= 1.0:
        raise ValueError("Concrete transparency must be in [0.0, 1.0).")

    for key in ("background_r", "background_g", "background_b"):
        channel = float(VISUALIZATION.get(key, 0.90))
        if channel < 0.0 or channel > 1.0:
            raise ValueError(f"{key} must be in [0.0, 1.0].")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parametric short-span steel girder bridge model (pythonOCC)."
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="GROUP.KEY=VALUE",
        help=(
            "Override any parameter. "
            "Example: --set geometry.span_length_L=15000 --set export.save_brep=true"
        ),
    )
    parser.add_argument(
        "--no-viewer",
        action="store_true",
        help="Build and export only; do not launch the OCC viewer.",
    )
    parser.add_argument(
        "--screenshot",
        default="",
        help="Optional screenshot path (works when viewer is launched).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime_params = get_default_params()

    if args.set:
        apply_cli_overrides(args.set)
        runtime_params = get_current_params()

    model = build_bridge_model(runtime_params)
    export_bridge(model["assembly"])

    if not args.no_viewer:
        visualize_bridge(model, screenshot_path=args.screenshot)


if __name__ == "__main__":
    main()