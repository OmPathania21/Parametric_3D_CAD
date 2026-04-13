import sys
import warnings
warnings.simplefilter("ignore", DeprecationWarning)

from typing import Any, Dict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QToolTip,
)

from OCC.Display.backend import load_backend

try:
    load_backend("pyside6")
except Exception:
    # Fallback to auto-detection if backend is already configured externally.
    pass

from OCC.Display.qtDisplay import qtViewer3d
from OCC.Core.Quantity import Quantity_Color, Quantity_NOC_CYAN1, Quantity_TOC_RGB

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
        self._dark_mode = False
        self._panel_visible = True
        self._panel_saved_width = 340
        self._param_history: list[Dict[str, Any]] = []
        self._param_history_index = -1
        self._max_param_history = 120
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setSingleShot(True)
        self._auto_update_timer.setInterval(200)

        self._build_ui()
        self._connect_events()
        self._initialize_scene()
        self._initialize_parameter_history()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, root)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        main_layout.addWidget(self.main_splitter, 1)

        self.viewer = qtViewer3d(self.main_splitter)
        self.viewer.InitDriver()
        self.display = self.viewer._display
        self.metadata_map = {}
        
        self._orig_mouseMoveEvent = self.viewer.mouseMoveEvent
        
        def _on_mouse_move(event):
            self._orig_mouseMoveEvent(event)
            self._handle_hover(event)
            
        self.viewer.mouseMoveEvent = _on_mouse_move
        
        # High-performance hovering tooltip 
        self.hover_tooltip = QLabel(self.viewer)
        self.hover_tooltip.setStyleSheet("background-color: #222; color: #fff; padding: 6px; border: 1px solid #555; border-radius: 4px; font-size: 11px;")
        self.hover_tooltip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hover_tooltip.hide()

        self.top_toolbar = QWidget(self.viewer)
        self.top_toolbar.setObjectName("topToolbar")
        top_toolbar_layout = QHBoxLayout(self.top_toolbar)
        top_toolbar_layout.setContentsMargins(8, 8, 8, 8)
        top_toolbar_layout.setSpacing(6)

        self.toolbar_update_button = QPushButton("Update", self.top_toolbar)
        self.toolbar_update_button.setObjectName("toolbarUpdateButton")
        self.toolbar_reset_button = QPushButton("Reset", self.top_toolbar)
        self.toolbar_reset_button.setObjectName("toolbarResetButton")
        self.toolbar_undo_button = QPushButton("Undo", self.top_toolbar)
        self.toolbar_undo_button.setObjectName("toolbarUndoButton")
        self.toolbar_redo_button = QPushButton("Redo", self.top_toolbar)
        self.toolbar_redo_button.setObjectName("toolbarRedoButton")
        self.toolbar_fit_button = QPushButton("Fit", self.top_toolbar)
        self.toolbar_fit_button.setObjectName("toolbarFitButton")
        self.toolbar_zoom_in_button = QPushButton("Zoom +", self.top_toolbar)
        self.toolbar_zoom_in_button.setObjectName("toolbarZoomInButton")
        self.toolbar_zoom_out_button = QPushButton("Zoom -", self.top_toolbar)
        self.toolbar_zoom_out_button.setObjectName("toolbarZoomOutButton")
        self.panel_toggle_button = QPushButton("Hide Panel", self.top_toolbar)
        self.panel_toggle_button.setObjectName("panelToggleButton")
        self.panel_toggle_button.setCheckable(True)
        self.panel_toggle_button.setChecked(True)
        self.theme_toggle_button = QPushButton("Dark Mode", self.top_toolbar)
        self.theme_toggle_button.setObjectName("themeToggleButton")

        for toolbar_button in (
            self.toolbar_update_button,
            self.toolbar_reset_button,
            self.toolbar_undo_button,
            self.toolbar_redo_button,
            self.toolbar_fit_button,
            self.toolbar_zoom_in_button,
            self.toolbar_zoom_out_button,
            self.panel_toggle_button,
            self.theme_toggle_button,
        ):
            toolbar_button.setCursor(Qt.CursorShape.PointingHandCursor)
            toolbar_button.setMinimumHeight(28)
            top_toolbar_layout.addWidget(toolbar_button)

        self.toolbar_undo_button.setToolTip("Undo last parameter edit")
        self.toolbar_redo_button.setToolTip("Redo parameter edit")

        self.camera_toolbar = QWidget(self.viewer)
        self.camera_toolbar.setObjectName("cameraToolbar")
        camera_toolbar_layout = QGridLayout(self.camera_toolbar)
        camera_toolbar_layout.setContentsMargins(8, 8, 8, 8)
        camera_toolbar_layout.setHorizontalSpacing(4)
        camera_toolbar_layout.setVerticalSpacing(4)

        self.camera_top_button = QPushButton("Top", self.camera_toolbar)
        self.camera_left_button = QPushButton("Left", self.camera_toolbar)
        self.camera_front_button = QPushButton("Front", self.camera_toolbar)
        self.camera_right_button = QPushButton("Right", self.camera_toolbar)
        self.camera_back_button = QPushButton("Back", self.camera_toolbar)
        self.camera_bottom_button = QPushButton("Bottom", self.camera_toolbar)
        self.camera_iso_button = QPushButton("Iso", self.camera_toolbar)

        camera_toolbar_layout.addWidget(self.camera_top_button, 0, 1)
        camera_toolbar_layout.addWidget(self.camera_left_button, 1, 0)
        camera_toolbar_layout.addWidget(self.camera_front_button, 1, 1)
        camera_toolbar_layout.addWidget(self.camera_right_button, 1, 2)
        camera_toolbar_layout.addWidget(self.camera_back_button, 2, 1)
        camera_toolbar_layout.addWidget(self.camera_bottom_button, 3, 1)
        camera_toolbar_layout.addWidget(self.camera_iso_button, 2, 2)

        self._camera_buttons = (
            self.camera_top_button,
            self.camera_left_button,
            self.camera_front_button,
            self.camera_right_button,
            self.camera_back_button,
            self.camera_bottom_button,
            self.camera_iso_button,
        )

        for camera_button in self._camera_buttons:
            camera_button.setCursor(Qt.CursorShape.PointingHandCursor)
            camera_button.setCheckable(True)
            camera_button.setMinimumHeight(24)
            camera_button.setMinimumWidth(52)

        self.camera_iso_button.setChecked(True)

        self._position_top_toolbar()
        self._position_camera_toolbar()

        self._orig_viewer_resize_event = self.viewer.resizeEvent

        def _on_viewer_resize(event):
            self._orig_viewer_resize_event(event)
            self._position_top_toolbar()
            self._position_camera_toolbar()

        self.viewer.resizeEvent = _on_viewer_resize

        highlight_style = self.display.Context.HighlightStyle()
        highlight_style.SetDisplayMode(1)  # Shaded
        highlight_style.SetColor(Quantity_Color(Quantity_NOC_CYAN1))

        self.panel = QWidget(self.main_splitter)
        self.panel.setMinimumWidth(280)
        self.panel.setMaximumWidth(520)
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

        self._configure_collapsible_group(self.column_group, expanded=True)
        self._configure_collapsible_group(self.superstructure_group, expanded=True)
        self._configure_collapsible_group(self.slab_group, expanded=True)
        self._configure_collapsible_group(self.foundation_group, expanded=True)
        self._configure_collapsible_group(self.pier_cap_group, expanded=True)
        self._configure_collapsible_group(self.pile_group, expanded=True)

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

        self._light_panel_stylesheet = (
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
            "#rightPanel QGroupBox::indicator { width: 12px; height: 12px; border-radius: 6px; }"
            "#rightPanel QGroupBox::indicator:checked { background: #2563eb; border: 1px solid #1d4ed8; }"
            "#rightPanel QGroupBox::indicator:unchecked { background: #d1d5db; border: 1px solid #9ca3af; }"
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

        self._dark_panel_stylesheet = (
            "#rightPanel { background: #111827; border: 1px solid #374151; color: #e5e7eb; }"
            "#rightPanel QScrollArea { border: none; background: transparent; }"
            "#rightPanel QScrollArea > QWidget > QWidget { background: transparent; }"
            "#rightPanel QScrollBar:vertical { width: 10px; background: #1f2937; margin: 6px 2px 6px 0; border-radius: 5px; }"
            "#rightPanel QScrollBar::handle:vertical { background: #4b5563; min-height: 24px; border-radius: 5px; }"
            "#rightPanel QScrollBar::handle:vertical:hover { background: #6b7280; }"
            "#rightPanel QScrollBar::add-line:vertical, #rightPanel QScrollBar::sub-line:vertical { height: 0px; }"
            "#rightPanel QScrollBar::add-page:vertical, #rightPanel QScrollBar::sub-page:vertical { background: transparent; }"
            "#rightPanel QLabel { color: #e5e7eb; }"
            "#panelTitle { font-size: 14px; font-weight: 700; color: #f9fafb; }"
            "#rightPanel QGroupBox { color: #f3f4f6; font-weight: 600; border: 1px solid #4b5563; margin-top: 8px; }"
            "#rightPanel QGroupBox::title { color: #f3f4f6; subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "#rightPanel QGroupBox::indicator { width: 12px; height: 12px; border-radius: 6px; }"
            "#rightPanel QGroupBox::indicator:checked { background: #2563eb; border: 1px solid #1d4ed8; }"
            "#rightPanel QGroupBox::indicator:unchecked { background: #4b5563; border: 1px solid #6b7280; }"
            "#rightPanel QDoubleSpinBox { color: #f9fafb; background: #1f2937; border: 1px solid #4b5563; padding: 2px 6px; }"
            "#rightPanel QDoubleSpinBox::up-button, #rightPanel QDoubleSpinBox::down-button { width: 16px; }"
            "#rightPanel QSpinBox { color: #f9fafb; background: #1f2937; border: 1px solid #4b5563; padding: 2px 6px; }"
            "#rightPanel QSpinBox::up-button, #rightPanel QSpinBox::down-button { width: 16px; }"
            "#rightPanel QPushButton { color: #ffffff; background: #2563eb; border: 1px solid #1d4ed8; padding: 7px 10px; border-radius: 4px; font-weight: 600; }"
            "#rightPanel QPushButton:hover { background: #1d4ed8; }"
            "#rightPanel QPushButton:pressed { background: #1e40af; }"
            "#resetButton { color: #f3f4f6; background: #374151; border: 1px solid #6b7280; }"
            "#resetButton:hover { background: #4b5563; }"
            "#resetButton:pressed { background: #6b7280; }"
            "#statusLabel { color: #cbd5e1; font-size: 11px; }"
        )

        self._apply_theme()

        self.main_splitter.addWidget(self.viewer)
        self.main_splitter.addWidget(self.panel)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([1200, 340])
        self._panel_saved_width = 340

    def _connect_events(self) -> None:
        self.update_button.clicked.connect(self._on_update_model_clicked)
        self.reset_button.clicked.connect(self._on_reset_defaults_clicked)
        self.toolbar_update_button.clicked.connect(self._on_update_model_clicked)
        self.toolbar_reset_button.clicked.connect(self._on_reset_defaults_clicked)
        self.toolbar_undo_button.clicked.connect(self._undo_parameter_change)
        self.toolbar_redo_button.clicked.connect(self._redo_parameter_change)
        self.toolbar_fit_button.clicked.connect(self._fit_view)
        self.toolbar_zoom_in_button.clicked.connect(self._zoom_in_view)
        self.toolbar_zoom_out_button.clicked.connect(self._zoom_out_view)
        self.panel_toggle_button.toggled.connect(self._on_panel_toggle_toggled)
        self.theme_toggle_button.clicked.connect(self._toggle_dark_mode)
        self.camera_top_button.clicked.connect(lambda: self._set_camera_preset("top"))
        self.camera_left_button.clicked.connect(lambda: self._set_camera_preset("left"))
        self.camera_front_button.clicked.connect(lambda: self._set_camera_preset("front"))
        self.camera_right_button.clicked.connect(lambda: self._set_camera_preset("right"))
        self.camera_back_button.clicked.connect(lambda: self._set_camera_preset("back"))
        self.camera_bottom_button.clicked.connect(lambda: self._set_camera_preset("bottom"))
        self.camera_iso_button.clicked.connect(lambda: self._set_camera_preset("iso"))
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

    def _initialize_parameter_history(self) -> None:
        self._param_history = []
        self._param_history_index = -1
        self._capture_parameter_history(force=True)

    def _capture_parameter_history(self, force: bool = False) -> None:
        current_state = self._collect_params()

        if 0 <= self._param_history_index < len(self._param_history):
            if not force and current_state == self._param_history[self._param_history_index]:
                self._update_history_controls()
                return

        if self._param_history_index < len(self._param_history) - 1:
            # Drop redo branch after a fresh edit.
            self._param_history = self._param_history[: self._param_history_index + 1]

        self._param_history.append(dict(current_state))
        if len(self._param_history) > self._max_param_history:
            overflow = len(self._param_history) - self._max_param_history
            self._param_history = self._param_history[overflow:]

        self._param_history_index = len(self._param_history) - 1
        self._update_history_controls()

    def _update_history_controls(self) -> None:
        can_undo = self._param_history_index > 0
        can_redo = 0 <= self._param_history_index < (len(self._param_history) - 1)
        self.toolbar_undo_button.setEnabled(can_undo)
        self.toolbar_redo_button.setEnabled(can_redo)

    def _restore_parameter_state(self, status_message: str) -> None:
        if not (0 <= self._param_history_index < len(self._param_history)):
            self._update_history_controls()
            return

        self._auto_update_timer.stop()
        target_state = dict(self._param_history[self._param_history_index])
        self.params = target_state
        self._set_inputs_from_params(target_state)
        self._on_update_model_clicked()
        if not self.status_label.text().startswith("Update failed"):
            self.status_label.setText(status_message)
        self._update_history_controls()

    def _undo_parameter_change(self) -> None:
        if self._param_history_index <= 0:
            self._update_history_controls()
            return

        self._param_history_index -= 1
        self._restore_parameter_state("Undo applied")

    def _redo_parameter_change(self) -> None:
        if self._param_history_index >= len(self._param_history) - 1:
            self._update_history_controls()
            return

        self._param_history_index += 1
        self._restore_parameter_state("Redo applied")

    def _set_layout_items_visible(self, layout, visible: bool) -> None:
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setVisible(visible)
            elif child_layout is not None:
                self._set_layout_items_visible(child_layout, visible)

    def _set_group_expanded(self, group: QGroupBox, expanded: bool) -> None:
        layout = group.layout()
        if layout is None:
            return

        self._set_layout_items_visible(layout, expanded)
        if expanded:
            group.setMinimumHeight(0)
            group.setMaximumHeight(16777215)
        else:
            collapsed_height = group.fontMetrics().height() + 24
            group.setMinimumHeight(collapsed_height)
            group.setMaximumHeight(collapsed_height)

    def _configure_collapsible_group(self, group: QGroupBox, expanded: bool = True) -> None:
        group.setCheckable(True)
        group.setChecked(expanded)
        self._set_group_expanded(group, expanded)
        group.toggled.connect(lambda checked, target=group: self._set_group_expanded(target, checked))

    def _on_panel_toggle_toggled(self, checked: bool) -> None:
        self._set_panel_visibility(checked)

    def _set_panel_visibility(self, visible: bool) -> None:
        if visible == self._panel_visible:
            return

        if visible:
            self.panel.setVisible(True)
            self.main_splitter.setHandleWidth(8)

            splitter_sizes = self.main_splitter.sizes()
            total_width = max(sum(splitter_sizes), 800)
            panel_width = max(
                self.panel.minimumWidth(),
                min(self.panel.maximumWidth(), int(self._panel_saved_width)),
            )
            viewer_width = max(200, total_width - panel_width)
            self.main_splitter.setSizes([viewer_width, panel_width])
            self.status_label.setText("Parameters panel expanded")
        else:
            splitter_sizes = self.main_splitter.sizes()
            if len(splitter_sizes) > 1 and splitter_sizes[1] > 0:
                self._panel_saved_width = splitter_sizes[1]

            self.panel.setVisible(False)
            self.main_splitter.setHandleWidth(0)
            self.main_splitter.setSizes([max(200, sum(splitter_sizes)), 0])
            self.status_label.setText("Parameters panel collapsed (full structure view)")

        self._panel_visible = visible
        was_blocked = self.panel_toggle_button.blockSignals(True)
        self.panel_toggle_button.setChecked(visible)
        self.panel_toggle_button.blockSignals(was_blocked)
        self.panel_toggle_button.setText("Hide Panel" if visible else "Show Panel")
        self._position_top_toolbar()
        self._position_camera_toolbar()

    def _position_top_toolbar(self) -> None:
        self.top_toolbar.adjustSize()
        self.top_toolbar.move(12, 12)
        self.top_toolbar.raise_()

    def _position_camera_toolbar(self) -> None:
        self.camera_toolbar.adjustSize()
        bottom_margin = 12
        y_pos = max(12, self.viewer.height() - self.camera_toolbar.height() - bottom_margin)
        self.camera_toolbar.move(12, y_pos)
        self.camera_toolbar.raise_()

    def _set_active_camera_chip(self, preset: str) -> None:
        preset_map = {
            "top": self.camera_top_button,
            "left": self.camera_left_button,
            "front": self.camera_front_button,
            "right": self.camera_right_button,
            "back": self.camera_back_button,
            "bottom": self.camera_bottom_button,
            "iso": self.camera_iso_button,
        }
        active_button = preset_map.get(preset)
        for button in self._camera_buttons:
            button.setChecked(button is active_button)

    def _set_camera_preset(self, preset: str) -> None:
        try:
            if preset == "top" and hasattr(self.display, "View_Top"):
                self.display.View_Top()
            elif preset == "bottom" and hasattr(self.display, "View_Bottom"):
                self.display.View_Bottom()
            elif preset == "front" and hasattr(self.display, "View_Front"):
                self.display.View_Front()
            elif preset == "back":
                if hasattr(self.display, "View_Rear"):
                    self.display.View_Rear()
                elif hasattr(self.display, "View_Back"):
                    self.display.View_Back()
            elif preset == "left" and hasattr(self.display, "View_Left"):
                self.display.View_Left()
            elif preset in ("right", "side"):
                if hasattr(self.display, "View_Right"):
                    self.display.View_Right()
                elif hasattr(self.display, "View_Left"):
                    self.display.View_Left()
                if preset == "side":
                    preset = "right"
            elif preset == "iso" and hasattr(self.display, "View_Iso"):
                self.display.View_Iso()

            if hasattr(self.display, "FitAll"):
                self.display.FitAll()
            self.display.Context.UpdateCurrentViewer()
        except Exception:
            pass

        self._set_active_camera_chip(preset)
        self._position_top_toolbar()
        self._position_camera_toolbar()

    def _fit_view(self) -> None:
        try:
            self.display.FitAll()
            self.display.Context.UpdateCurrentViewer()
            self._position_top_toolbar()
            self._position_camera_toolbar()
        except Exception:
            pass

    def _zoom_in_view(self) -> None:
        try:
            self.display.ZoomFactor(1.20)
            self.display.Context.UpdateCurrentViewer()
            self._position_top_toolbar()
            self._position_camera_toolbar()
        except Exception:
            pass

    def _zoom_out_view(self) -> None:
        try:
            self.display.ZoomFactor(1.0 / 1.20)
            self.display.Context.UpdateCurrentViewer()
            self._position_top_toolbar()
            self._position_camera_toolbar()
        except Exception:
            pass

    def _handle_hover(self, event) -> None:
        ais = None
        if self.display.Context.HasDetected():
            ais = self.display.Context.DetectedInteractive()

        if ais is not None:
            details = self.metadata_map.get(ais)
            if details:
                # Fast floating QLabel update
                self.hover_tooltip.setText(details)
                self.hover_tooltip.adjustSize()
                
                # Use local pos for widget overlaying mapping
                pos = event.pos() if hasattr(event, "pos") else event.position().toPoint()
                self.hover_tooltip.move(pos.x() + 15, pos.y() + 15)
                self.hover_tooltip.show()
                self.hover_tooltip.raise_()
                
                if ais != getattr(self, "_last_hovered_ais", None):
                    self.status_label.setText(f"Hovering: {details.splitlines()[0]}")
                    self._last_hovered_ais = ais
            else:
                self.hover_tooltip.hide()
                if getattr(self, "_last_hovered_ais", None) is not None:
                    self.status_label.setText("Ready")
                    self._last_hovered_ais = None
        else:
            self.hover_tooltip.hide()
            if getattr(self, "_last_hovered_ais", None) is not None:
                self.status_label.setText("Ready")
                self._last_hovered_ais = None

    def _set_view_background(self, red: float, green: float, blue: float) -> None:
        if not (hasattr(self.display, "View") and hasattr(self.display.View, "SetBackgroundColor")):
            return

        try:
            try:
                self.display.View.SetBackgroundColor(red, green, blue)
            except TypeError:
                bg_color = Quantity_Color(red, green, blue, Quantity_TOC_RGB)
                self.display.View.SetBackgroundColor(bg_color)
            self.display.Context.UpdateCurrentViewer()
        except Exception:
            pass

    def _apply_theme(self) -> None:
        if self._dark_mode:
            self.panel.setStyleSheet(self._dark_panel_stylesheet)
            self.theme_toggle_button.setText("Light Mode")
            self.top_toolbar.setStyleSheet(
                "#topToolbar {"
                "background: rgba(15, 23, 42, 220);"
                "border: 1px solid #475569;"
                "border-radius: 10px;"
                "}"
                "#topToolbar QPushButton {"
                "background: #1f2937;"
                "color: #e5e7eb;"
                "border: 1px solid #475569;"
                "border-radius: 6px;"
                "padding: 5px 10px;"
                "font-size: 11px;"
                "font-weight: 600;"
                "}"
                "#topToolbar QPushButton:hover { background: #334155; }"
                "#topToolbar QPushButton:pressed { background: #475569; }"
                "#topToolbar QPushButton#panelToggleButton:checked {"
                "background: #0369a1;"
                "border: 1px solid #0284c7;"
                "color: #ecfeff;"
                "}"
                "#topToolbar QPushButton#themeToggleButton {"
                "background: #2563eb;"
                "border: 1px solid #1d4ed8;"
                "color: #ffffff;"
                "}"
                "#topToolbar QPushButton#themeToggleButton:hover { background: #1d4ed8; }"
                "#topToolbar QPushButton#themeToggleButton:pressed { background: #1e40af; }"
            )
            self.camera_toolbar.setStyleSheet(
                "#cameraToolbar {"
                "background: rgba(15, 23, 42, 220);"
                "border: 1px solid #475569;"
                "border-radius: 10px;"
                "}"
                "#cameraToolbar QPushButton {"
                "background: #1f2937;"
                "color: #e5e7eb;"
                "border: 1px solid #475569;"
                "border-radius: 4px;"
                "padding: 3px 6px;"
                "font-size: 10px;"
                "font-weight: 600;"
                "}"
                "#cameraToolbar QPushButton:hover { background: #334155; }"
                "#cameraToolbar QPushButton:checked {"
                "background: #0ea5e9;"
                "border: 1px solid #0284c7;"
                "color: #ecfeff;"
                "}"
            )
            self.main_splitter.setStyleSheet(
                "QSplitter::handle {"
                "background: #0f172a;"
                "border-left: 1px solid #374151;"
                "border-right: 1px solid #374151;"
                "}"
            )
            self.hover_tooltip.setStyleSheet(
                "background-color: #0f172a;"
                "color: #f8fafc;"
                "padding: 6px;"
                "border: 1px solid #475569;"
                "border-radius: 4px;"
                "font-size: 11px;"
            )
            self._set_view_background(0.12, 0.13, 0.16)
        else:
            self.panel.setStyleSheet(self._light_panel_stylesheet)
            self.theme_toggle_button.setText("Dark Mode")
            self.top_toolbar.setStyleSheet(
                "#topToolbar {"
                "background: rgba(255, 255, 255, 228);"
                "border: 1px solid #cbd5e1;"
                "border-radius: 10px;"
                "}"
                "#topToolbar QPushButton {"
                "background: #ffffff;"
                "color: #1f2937;"
                "border: 1px solid #cbd5e1;"
                "border-radius: 6px;"
                "padding: 5px 10px;"
                "font-size: 11px;"
                "font-weight: 600;"
                "}"
                "#topToolbar QPushButton:hover { background: #f1f5f9; }"
                "#topToolbar QPushButton:pressed { background: #e2e8f0; }"
                "#topToolbar QPushButton#panelToggleButton:checked {"
                "background: #0284c7;"
                "border: 1px solid #0369a1;"
                "color: #ffffff;"
                "}"
                "#topToolbar QPushButton#themeToggleButton {"
                "background: #2563eb;"
                "border: 1px solid #1d4ed8;"
                "color: #ffffff;"
                "}"
                "#topToolbar QPushButton#themeToggleButton:hover { background: #1d4ed8; }"
                "#topToolbar QPushButton#themeToggleButton:pressed { background: #1e40af; }"
            )
            self.camera_toolbar.setStyleSheet(
                "#cameraToolbar {"
                "background: rgba(255, 255, 255, 228);"
                "border: 1px solid #cbd5e1;"
                "border-radius: 10px;"
                "}"
                "#cameraToolbar QPushButton {"
                "background: #ffffff;"
                "color: #1f2937;"
                "border: 1px solid #cbd5e1;"
                "border-radius: 4px;"
                "padding: 3px 6px;"
                "font-size: 10px;"
                "font-weight: 600;"
                "}"
                "#cameraToolbar QPushButton:hover { background: #f1f5f9; }"
                "#cameraToolbar QPushButton:checked {"
                "background: #0284c7;"
                "border: 1px solid #0369a1;"
                "color: #ffffff;"
                "}"
            )
            self.main_splitter.setStyleSheet(
                "QSplitter::handle {"
                "background: #f3f4f6;"
                "border-left: 1px solid #d1d5db;"
                "border-right: 1px solid #d1d5db;"
                "}"
            )
            self.hover_tooltip.setStyleSheet(
                "background-color: #222;"
                "color: #fff;"
                "padding: 6px;"
                "border: 1px solid #555;"
                "border-radius: 4px;"
                "font-size: 11px;"
            )
            self._set_view_background(0.85, 0.85, 0.85)

        self._position_top_toolbar()
        self._position_camera_toolbar()

    def _toggle_dark_mode(self) -> None:
        self._dark_mode = not self._dark_mode
        self._apply_theme()

    def _initialize_scene(self) -> None:
        configure_display_scene(self.display)
        self._apply_theme()
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
        self._capture_parameter_history()
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
                _, self.metadata_map = render_bridge_model(self.display, model, show_rebar=True, fit_all=True)
            else:
                self.display.DisplayShape(shape, update=True)
                self.display.FitAll()

            self.display.Context.UpdateCurrentViewer()
            self._position_top_toolbar()
            self._position_camera_toolbar()
            self.status_label.setText("Model updated")
        except Exception as exc:
            self.status_label.setText(f"Update failed: {exc}")

    def _request_auto_update(self) -> None:
        self._capture_parameter_history()
        self._auto_update_timer.start()


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = BridgeParametricWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()