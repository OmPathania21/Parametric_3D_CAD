import sys
from typing import Any, Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from OCC.Display.backend import load_backend

try:
    load_backend("pyside6")
except Exception:
    # Fallback to auto-detection if backend is already configured externally.
    pass

from OCC.Display.qtDisplay import qtViewer3d

from bridge_model import (
    build_bridge,
    configure_display_scene,
    get_default_params,
    get_last_bridge_model,
    render_bridge_model,
)


class BridgeParametricWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Parametric Bridge CAD - pythonOCC + PySide6")
        self.resize(1520, 880)

        self.params: Dict[str, Any] = get_default_params()
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setSingleShot(True)
        self._auto_update_timer.setInterval(200)

        self._build_ui()
        self._connect_events()
        self._initialize_scene()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.viewer = qtViewer3d(root)
        self.viewer.InitDriver()
        self.display = self.viewer._display
        main_layout.addWidget(self.viewer, 1)

        self.panel = QWidget(root)
        self.panel.setFixedWidth(300)
        self.panel.setObjectName("rightPanel")

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        panel_scroll = QScrollArea(self.panel)
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        panel_content = QWidget()
        controls_layout = QVBoxLayout(panel_content)

        panel_scroll.setWidget(panel_content)
        panel_layout.addWidget(panel_scroll)

        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setSpacing(10)

        title = QLabel("PARAMETERS PANEL")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.column_group = QGroupBox("Column Settings")
        column_form = QFormLayout(self.column_group)
        column_form.setContentsMargins(10, 12, 10, 10)
        column_form.setSpacing(8)

        self.column_height_input = QDoubleSpinBox()
        self.column_height_input.setRange(1000.0, 10000.0)
        self.column_height_input.setSingleStep(100.0)
        self.column_height_input.setDecimals(0)
        self.column_height_input.setValue(float(self.params["column_height"]))

        self.column_diameter_input = QDoubleSpinBox()
        self.column_diameter_input.setRange(200.0, 2000.0)
        self.column_diameter_input.setSingleStep(50.0)
        self.column_diameter_input.setDecimals(0)
        self.column_diameter_input.setValue(float(self.params["column_diameter"]))

        column_form.addRow("Column Height (mm)", self.column_height_input)
        column_form.addRow("Column Diameter (mm)", self.column_diameter_input)

        self.superstructure_group = QGroupBox("Girder Settings")
        super_form = QFormLayout(self.superstructure_group)
        super_form.setContentsMargins(10, 12, 10, 10)
        super_form.setSpacing(8)

        self.span_length_input = QDoubleSpinBox()
        self.span_length_input.setRange(6000.0, 50000.0)
        self.span_length_input.setSingleStep(500.0)
        self.span_length_input.setDecimals(0)
        self.span_length_input.setValue(float(self.params["span_length_L"]))

        self.n_girders_input = QSpinBox()
        self.n_girders_input.setRange(1, 8)
        self.n_girders_input.setSingleStep(1)
        self.n_girders_input.setValue(int(self.params["n_girders"]))

        self.girder_spacing_input = QDoubleSpinBox()
        self.girder_spacing_input.setRange(500.0, 8000.0)
        self.girder_spacing_input.setSingleStep(100.0)
        self.girder_spacing_input.setDecimals(0)
        self.girder_spacing_input.setValue(float(self.params["girder_spacing"]))

        self.girder_depth_input = QDoubleSpinBox()
        self.girder_depth_input.setRange(300.0, 3000.0)
        self.girder_depth_input.setSingleStep(50.0)
        self.girder_depth_input.setDecimals(0)
        self.girder_depth_input.setValue(float(self.params["girder_depth"]))

        self.girder_flange_width_input = QDoubleSpinBox()
        self.girder_flange_width_input.setRange(100.0, 1500.0)
        self.girder_flange_width_input.setSingleStep(20.0)
        self.girder_flange_width_input.setDecimals(0)
        self.girder_flange_width_input.setValue(float(self.params["girder_flange_width"]))

        super_form.addRow("Span Length (mm)", self.span_length_input)
        super_form.addRow("Number of Girders", self.n_girders_input)
        super_form.addRow("Girder Spacing (mm)", self.girder_spacing_input)
        super_form.addRow("Girder Depth (mm)", self.girder_depth_input)
        super_form.addRow("Flange Width (mm)", self.girder_flange_width_input)

        self.slab_group = QGroupBox("Slab Settings")
        slab_form = QFormLayout(self.slab_group)
        slab_form.setContentsMargins(10, 12, 10, 10)
        slab_form.setSpacing(8)

        self.slab_width_input = QDoubleSpinBox()
        self.slab_width_input.setRange(2000.0, 20000.0)
        self.slab_width_input.setSingleStep(100.0)
        self.slab_width_input.setDecimals(0)
        self.slab_width_input.setValue(float(self.params["deck_width"]))

        self.slab_thickness_input = QDoubleSpinBox()
        self.slab_thickness_input.setRange(100.0, 1000.0)
        self.slab_thickness_input.setSingleStep(10.0)
        self.slab_thickness_input.setDecimals(0)
        self.slab_thickness_input.setValue(float(self.params["deck_thickness"]))

        self.rebar_diameter_input = QDoubleSpinBox()
        self.rebar_diameter_input.setRange(8.0, 50.0)
        self.rebar_diameter_input.setSingleStep(1.0)
        self.rebar_diameter_input.setDecimals(0)
        self.rebar_diameter_input.setValue(float(self.params["rebar_diameter"]))

        self.deck_cover_input = QDoubleSpinBox()
        self.deck_cover_input.setRange(10.0, 120.0)
        self.deck_cover_input.setSingleStep(5.0)
        self.deck_cover_input.setDecimals(0)
        self.deck_cover_input.setValue(float(self.params["deck_cover"]))

        self.rebar_spacing_long_input = QDoubleSpinBox()
        self.rebar_spacing_long_input.setRange(50.0, 600.0)
        self.rebar_spacing_long_input.setSingleStep(10.0)
        self.rebar_spacing_long_input.setDecimals(0)
        self.rebar_spacing_long_input.setValue(float(self.params["deck_spacing_longitudinal"]))

        self.rebar_spacing_trans_input = QDoubleSpinBox()
        self.rebar_spacing_trans_input.setRange(50.0, 600.0)
        self.rebar_spacing_trans_input.setSingleStep(10.0)
        self.rebar_spacing_trans_input.setDecimals(0)
        self.rebar_spacing_trans_input.setValue(float(self.params["deck_spacing_transverse"]))

        slab_form.addRow("Slab Width (mm)", self.slab_width_input)
        slab_form.addRow("Slab Thickness (mm)", self.slab_thickness_input)
        slab_form.addRow("Rebar Diameter (mm)", self.rebar_diameter_input)
        slab_form.addRow("Concrete Cover (mm)", self.deck_cover_input)
        slab_form.addRow("Rebar Spacing X (mm)", self.rebar_spacing_long_input)
        slab_form.addRow("Rebar Spacing Y (mm)", self.rebar_spacing_trans_input)

        self.foundation_group = QGroupBox("Foundation Settings")
        foundation_form = QFormLayout(self.foundation_group)
        foundation_form.setContentsMargins(10, 12, 10, 10)
        foundation_form.setSpacing(8)

        self.pile_cap_length_input = QDoubleSpinBox()
        self.pile_cap_length_input.setRange(1000.0, 8000.0)
        self.pile_cap_length_input.setSingleStep(100.0)
        self.pile_cap_length_input.setDecimals(0)
        self.pile_cap_length_input.setValue(float(self.params["pile_cap_length"]))

        self.pile_cap_width_input = QDoubleSpinBox()
        self.pile_cap_width_input.setRange(1000.0, 6000.0)
        self.pile_cap_width_input.setSingleStep(100.0)
        self.pile_cap_width_input.setDecimals(0)
        self.pile_cap_width_input.setValue(float(self.params["pile_cap_width"]))

        self.pile_cap_depth_input = QDoubleSpinBox()
        self.pile_cap_depth_input.setRange(300.0, 3000.0)
        self.pile_cap_depth_input.setSingleStep(50.0)
        self.pile_cap_depth_input.setDecimals(0)
        self.pile_cap_depth_input.setValue(float(self.params["pile_cap_depth"]))

        foundation_form.addRow("Block Length (mm)", self.pile_cap_length_input)
        foundation_form.addRow("Block Width (mm)", self.pile_cap_width_input)
        foundation_form.addRow("Block Depth (mm)", self.pile_cap_depth_input)

        self.pier_cap_group = QGroupBox("Pier Cap Settings")
        pier_cap_form = QFormLayout(self.pier_cap_group)
        pier_cap_form.setContentsMargins(10, 12, 10, 10)
        pier_cap_form.setSpacing(8)

        self.pier_cap_length_input = QDoubleSpinBox()
        self.pier_cap_length_input.setRange(1000.0, 8000.0)
        self.pier_cap_length_input.setSingleStep(100.0)
        self.pier_cap_length_input.setDecimals(0)
        self.pier_cap_length_input.setValue(float(self.params["pier_cap_length"]))

        self.pier_cap_width_top_input = QDoubleSpinBox()
        self.pier_cap_width_top_input.setRange(400.0, 6000.0)
        self.pier_cap_width_top_input.setSingleStep(100.0)
        self.pier_cap_width_top_input.setDecimals(0)
        self.pier_cap_width_top_input.setValue(float(self.params["pier_cap_width_top"]))

        self.pier_cap_width_bottom_input = QDoubleSpinBox()
        self.pier_cap_width_bottom_input.setRange(400.0, 8000.0)
        self.pier_cap_width_bottom_input.setSingleStep(100.0)
        self.pier_cap_width_bottom_input.setDecimals(0)
        self.pier_cap_width_bottom_input.setValue(float(self.params["pier_cap_width_bottom"]))

        self.pier_cap_depth_input = QDoubleSpinBox()
        self.pier_cap_depth_input.setRange(200.0, 3000.0)
        self.pier_cap_depth_input.setSingleStep(50.0)
        self.pier_cap_depth_input.setDecimals(0)
        self.pier_cap_depth_input.setValue(float(self.params["pier_cap_depth"]))

        self.cap_to_deck_gap_input = QDoubleSpinBox()
        self.cap_to_deck_gap_input.setRange(0.0, 2000.0)
        self.cap_to_deck_gap_input.setSingleStep(20.0)
        self.cap_to_deck_gap_input.setDecimals(0)
        self.cap_to_deck_gap_input.setValue(float(self.params["cap_to_deck_gap"]))

        pier_cap_form.addRow("Cap Length (mm)", self.pier_cap_length_input)
        pier_cap_form.addRow("Cap Top Width (mm)", self.pier_cap_width_top_input)
        pier_cap_form.addRow("Cap Bottom Width (mm)", self.pier_cap_width_bottom_input)
        pier_cap_form.addRow("Cap Depth (mm)", self.pier_cap_depth_input)
        pier_cap_form.addRow("Cap-to-Deck Gap (mm)", self.cap_to_deck_gap_input)

        self.pile_group = QGroupBox("Pile Settings")
        pile_form = QFormLayout(self.pile_group)
        pile_form.setContentsMargins(10, 12, 10, 10)
        pile_form.setSpacing(8)

        self.pile_diameter_input = QDoubleSpinBox()
        self.pile_diameter_input.setRange(200.0, 2000.0)
        self.pile_diameter_input.setSingleStep(50.0)
        self.pile_diameter_input.setDecimals(0)
        self.pile_diameter_input.setValue(float(self.params["pile_diameter"]))

        self.pile_length_input = QDoubleSpinBox()
        self.pile_length_input.setRange(1000.0, 10000.0)
        self.pile_length_input.setSingleStep(100.0)
        self.pile_length_input.setDecimals(0)
        self.pile_length_input.setValue(float(self.params["pile_length"]))

        self.pile_rows_input = QSpinBox()
        self.pile_rows_input.setRange(1, 6)
        self.pile_rows_input.setSingleStep(1)
        self.pile_rows_input.setValue(int(self.params["pile_rows"]))

        self.pile_cols_input = QSpinBox()
        self.pile_cols_input.setRange(1, 6)
        self.pile_cols_input.setSingleStep(1)
        self.pile_cols_input.setValue(int(self.params["pile_cols"]))

        self.pile_spacing_x_input = QDoubleSpinBox()
        self.pile_spacing_x_input.setRange(400.0, 5000.0)
        self.pile_spacing_x_input.setSingleStep(100.0)
        self.pile_spacing_x_input.setDecimals(0)
        self.pile_spacing_x_input.setValue(float(self.params["pile_spacing_x"]))

        self.pile_spacing_y_input = QDoubleSpinBox()
        self.pile_spacing_y_input.setRange(400.0, 5000.0)
        self.pile_spacing_y_input.setSingleStep(100.0)
        self.pile_spacing_y_input.setDecimals(0)
        self.pile_spacing_y_input.setValue(float(self.params["pile_spacing_y"]))

        pile_form.addRow("Pile Diameter (mm)", self.pile_diameter_input)
        pile_form.addRow("Pile Length (mm)", self.pile_length_input)
        pile_form.addRow("Pile Rows", self.pile_rows_input)
        pile_form.addRow("Pile Columns", self.pile_cols_input)
        pile_form.addRow("Pile Spacing X (mm)", self.pile_spacing_x_input)
        pile_form.addRow("Pile Spacing Y (mm)", self.pile_spacing_y_input)

        self.update_button = QPushButton("Update Model")
        self.reset_button = QPushButton("Reset")
        self.reset_button.setObjectName("resetButton")
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(self.update_button, 1)
        button_row.addWidget(self.reset_button, 1)

        controls_layout.addWidget(title)
        controls_layout.addWidget(self.column_group)
        controls_layout.addWidget(self.superstructure_group)
        controls_layout.addWidget(self.slab_group)
        controls_layout.addWidget(self.foundation_group)
        controls_layout.addWidget(self.pier_cap_group)
        controls_layout.addWidget(self.pile_group)
        controls_layout.addLayout(button_row)
        controls_layout.addWidget(self.status_label)
        controls_layout.addStretch(1)

        self.panel.setStyleSheet(
            "#rightPanel { background: #f4f5f7; border: 1px solid #d6d9de; color: #1f2937; }"
            "#rightPanel QScrollArea { border: none; background: transparent; }"
            "#rightPanel QScrollArea > QWidget > QWidget { background: transparent; }"
            "#rightPanel QScrollBar:vertical { width: 10px; background: #e5e7eb; margin: 6px 2px 6px 0; border-radius: 5px; }"
            "#rightPanel QScrollBar::handle:vertical { background: #9ca3af; min-height: 24px; border-radius: 5px; }"
            "#rightPanel QScrollBar::handle:vertical:hover { background: #6b7280; }"
            "#rightPanel QScrollBar::add-line:vertical, #rightPanel QScrollBar::sub-line:vertical { height: 0px; }"
            "#rightPanel QScrollBar::add-page:vertical, #rightPanel QScrollBar::sub-page:vertical { background: transparent; }"
            "#rightPanel QLabel { color: #1f2937; }"
            "#panelTitle { font-size: 14px; font-weight: 700; color: #111827; }"
            "#rightPanel QGroupBox { color: #111827; font-weight: 600; border: 1px solid #c7ccd3; margin-top: 8px; }"
            "#rightPanel QGroupBox::title { color: #111827; subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "#rightPanel QDoubleSpinBox { color: #111827; background: #ffffff; border: 1px solid #9ca3af; padding: 2px 6px; }"
            "#rightPanel QDoubleSpinBox::up-button, #rightPanel QDoubleSpinBox::down-button { width: 16px; }"
            "#rightPanel QSpinBox { color: #111827; background: #ffffff; border: 1px solid #9ca3af; padding: 2px 6px; }"
            "#rightPanel QSpinBox::up-button, #rightPanel QSpinBox::down-button { width: 16px; }"
            "#rightPanel QPushButton { color: #ffffff; background: #2563eb; border: 1px solid #1d4ed8; padding: 7px 10px; border-radius: 4px; font-weight: 600; }"
            "#rightPanel QPushButton:hover { background: #1d4ed8; }"
            "#rightPanel QPushButton:pressed { background: #1e40af; }"
            "#resetButton { color: #111827; background: #e5e7eb; border: 1px solid #9ca3af; }"
            "#resetButton:hover { background: #d1d5db; }"
            "#resetButton:pressed { background: #9ca3af; }"
            "#statusLabel { color: #334155; font-size: 11px; }"
        )

        main_layout.addWidget(self.panel, 0)

    def _connect_events(self) -> None:
        self.update_button.clicked.connect(self._on_update_model_clicked)
        self.reset_button.clicked.connect(self._on_reset_defaults_clicked)
        self.column_height_input.valueChanged.connect(self._request_auto_update)
        self.column_diameter_input.valueChanged.connect(self._request_auto_update)
        self.span_length_input.valueChanged.connect(self._request_auto_update)
        self.n_girders_input.valueChanged.connect(self._request_auto_update)
        self.girder_spacing_input.valueChanged.connect(self._request_auto_update)
        self.girder_depth_input.valueChanged.connect(self._request_auto_update)
        self.girder_flange_width_input.valueChanged.connect(self._request_auto_update)
        self.slab_width_input.valueChanged.connect(self._request_auto_update)
        self.slab_thickness_input.valueChanged.connect(self._request_auto_update)
        self.rebar_diameter_input.valueChanged.connect(self._request_auto_update)
        self.deck_cover_input.valueChanged.connect(self._request_auto_update)
        self.rebar_spacing_long_input.valueChanged.connect(self._request_auto_update)
        self.rebar_spacing_trans_input.valueChanged.connect(self._request_auto_update)
        self.pile_cap_length_input.valueChanged.connect(self._request_auto_update)
        self.pile_cap_width_input.valueChanged.connect(self._request_auto_update)
        self.pile_cap_depth_input.valueChanged.connect(self._request_auto_update)
        self.pier_cap_length_input.valueChanged.connect(self._request_auto_update)
        self.pier_cap_width_top_input.valueChanged.connect(self._request_auto_update)
        self.pier_cap_width_bottom_input.valueChanged.connect(self._request_auto_update)
        self.pier_cap_depth_input.valueChanged.connect(self._request_auto_update)
        self.cap_to_deck_gap_input.valueChanged.connect(self._request_auto_update)
        self.pile_diameter_input.valueChanged.connect(self._request_auto_update)
        self.pile_length_input.valueChanged.connect(self._request_auto_update)
        self.pile_rows_input.valueChanged.connect(self._request_auto_update)
        self.pile_cols_input.valueChanged.connect(self._request_auto_update)
        self.pile_spacing_x_input.valueChanged.connect(self._request_auto_update)
        self.pile_spacing_y_input.valueChanged.connect(self._request_auto_update)
        self._auto_update_timer.timeout.connect(self._on_update_model_clicked)

    def _initialize_scene(self) -> None:
        configure_display_scene(self.display)
        self._on_update_model_clicked()

    def _set_inputs_from_params(self, params: Dict[str, Any]) -> None:
        widget_values = [
            (self.column_height_input, float(params["column_height"])),
            (self.column_diameter_input, float(params["column_diameter"])),
            (self.span_length_input, float(params["span_length_L"])),
            (self.n_girders_input, int(params["n_girders"])),
            (self.girder_spacing_input, float(params["girder_spacing"])),
            (self.girder_depth_input, float(params["girder_depth"])),
            (self.girder_flange_width_input, float(params["girder_flange_width"])),
            (self.slab_width_input, float(params["deck_width"])),
            (self.slab_thickness_input, float(params["deck_thickness"])),
            (self.rebar_diameter_input, float(params["rebar_diameter"])),
            (self.deck_cover_input, float(params["deck_cover"])),
            (self.rebar_spacing_long_input, float(params["deck_spacing_longitudinal"])),
            (self.rebar_spacing_trans_input, float(params["deck_spacing_transverse"])),
            (self.pile_cap_length_input, float(params["pile_cap_length"])),
            (self.pile_cap_width_input, float(params["pile_cap_width"])),
            (self.pile_cap_depth_input, float(params["pile_cap_depth"])),
            (self.pier_cap_length_input, float(params["pier_cap_length"])),
            (self.pier_cap_width_top_input, float(params["pier_cap_width_top"])),
            (self.pier_cap_width_bottom_input, float(params["pier_cap_width_bottom"])),
            (self.pier_cap_depth_input, float(params["pier_cap_depth"])),
            (self.cap_to_deck_gap_input, float(params["cap_to_deck_gap"])),
            (self.pile_diameter_input, float(params["pile_diameter"])),
            (self.pile_length_input, float(params["pile_length"])),
            (self.pile_rows_input, int(params["pile_rows"])),
            (self.pile_cols_input, int(params["pile_cols"])),
            (self.pile_spacing_x_input, float(params["pile_spacing_x"])),
            (self.pile_spacing_y_input, float(params["pile_spacing_y"])),
        ]

        # Apply defaults in one batch so reset triggers only one model rebuild.
        for widget, value in widget_values:
            was_blocked = widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(was_blocked)

    def _on_reset_defaults_clicked(self) -> None:
        self._auto_update_timer.stop()
        defaults = get_default_params()
        self.params = defaults
        self._set_inputs_from_params(defaults)
        self._on_update_model_clicked()
        if not self.status_label.text().startswith("Update failed"):
            self.status_label.setText("Model reset to defaults")

    def _collect_params(self) -> Dict[str, Any]:
        return {
            "column_height": float(self.column_height_input.value()),
            "column_diameter": float(self.column_diameter_input.value()),
            "span_length_L": float(self.span_length_input.value()),
            "n_girders": int(self.n_girders_input.value()),
            "girder_spacing": float(self.girder_spacing_input.value()),
            "girder_depth": float(self.girder_depth_input.value()),
            "girder_flange_width": float(self.girder_flange_width_input.value()),
            "deck_width": float(self.slab_width_input.value()),
            "deck_thickness": float(self.slab_thickness_input.value()),
            "rebar_diameter": float(self.rebar_diameter_input.value()),
            "deck_cover": float(self.deck_cover_input.value()),
            "deck_spacing_longitudinal": float(self.rebar_spacing_long_input.value()),
            "deck_spacing_transverse": float(self.rebar_spacing_trans_input.value()),
            "pile_cap_length": float(self.pile_cap_length_input.value()),
            "pile_cap_width": float(self.pile_cap_width_input.value()),
            "pile_cap_depth": float(self.pile_cap_depth_input.value()),
            "pier_cap_length": float(self.pier_cap_length_input.value()),
            "pier_cap_width_top": float(self.pier_cap_width_top_input.value()),
            "pier_cap_width_bottom": float(self.pier_cap_width_bottom_input.value()),
            "pier_cap_depth": float(self.pier_cap_depth_input.value()),
            "cap_to_deck_gap": float(self.cap_to_deck_gap_input.value()),
            "pile_diameter": float(self.pile_diameter_input.value()),
            "pile_length": float(self.pile_length_input.value()),
            "pile_rows": int(self.pile_rows_input.value()),
            "pile_cols": int(self.pile_cols_input.value()),
            "pile_spacing_x": float(self.pile_spacing_x_input.value()),
            "pile_spacing_y": float(self.pile_spacing_y_input.value()),
        }

    def _on_update_model_clicked(self) -> None:
        params = self._collect_params()
        try:
            # Build first so invalid values do not clear the currently valid model.
            shape = build_bridge(params)
            _ = shape

            self.display.Context.RemoveAll(True)

            model = get_last_bridge_model()
            if model is not None:
                render_bridge_model(self.display, model, show_rebar=True, fit_all=True)
            else:
                self.display.DisplayShape(shape, update=True)
                self.display.FitAll()

            self.display.Context.UpdateCurrentViewer()
            self.status_label.setText("Model updated")
        except Exception as exc:
            self.status_label.setText(f"Update failed: {exc}")

    def _request_auto_update(self) -> None:
        self._auto_update_timer.start()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = BridgeParametricWindow()
    window.show()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
