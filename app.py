"""FixAtoms Studio — local Qt / 3Dmol structure editor."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QDialog, QDoubleSpinBox, QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from structure_io import demo_structure, export_poscar, has_valid_cell, load_structure, viewer_payload
from ball_settings import BallSettingsDialog, element_appearance, load_preferences
from camera_views import STANDARD_VIEWS, standard_view

ROOT = Path(__file__).resolve().parent
# PyInstaller keeps resources in _internal; portable preferences live beside EXE.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT

STYLESHEET = """
QMainWindow, QWidget#root { background: #f2f5fa; color: #1c2b43; }
QWidget { font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; color: #24344c; }
QLabel { background: transparent; padding-top: 3px; padding-bottom: 3px; }
QLabel#brand { font-size: 23px; font-weight: 700; color: #172b48; }
QLabel#subtitle, QLabel#muted { color: #8090a6; font-size: 12px; }
QLabel#section { color: #8090a6; font-size: 11px; font-weight: 600; }
QLabel#filename { font-size: 17px; font-weight: 600; }
QLabel#number { font-size: 27px; font-weight: 600; }
QFrame#card { background: white; border: 1px solid #e5ebf3; border-radius: 18px; }
QFrame#stat { background: #f5f8fc; border-radius: 12px; }
QFrame#stage { background: #f8fafc; border: 1px solid #e2e9f2; border-radius: 18px; }
QFrame#segment { background: #eaf0f7; border-radius: 12px; }
QPushButton { background: white; border: 1px solid #e0e7f0; border-radius: 10px; padding: 10px 14px; font-weight: 500; }
QPushButton:hover { background: #edf5ff; border-color: #b7d5ff; }
QPushButton:pressed { background: #dcecff; }
QPushButton:disabled { color: #adb8c7; background: #f3f5f8; border-color: #e9edf3; }
QPushButton#primary { background: #007aff; color: white; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #0068df; }
QPushButton#primary:disabled { background: #c5ddf9; color: #f5f9ff; }
QPushButton#segmentButton { border: none; background: transparent; color: #78889d; padding: 9px 14px; }
QPushButton#segmentButton:checked { background: white; color: #007aff; }
QPushButton#small { font-size: 12px; padding: 8px 9px; }
QLineEdit, QComboBox { background: #f6f8fc; border: 1px solid #e3e9f2; border-radius: 9px; padding: 9px; }
QLineEdit:focus { border-color: #75b6ff; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e5f1ff; selection-color: #007aff; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #c8d4e2; border-radius: 5px; background: #f4f7fb; }
QCheckBox::indicator:checked { background: #007aff; border-color: #007aff; image: none; }
QStatusBar { background: transparent; color: #718096; font-size: 12px; }
QToolTip { background: #24344c; color: white; border: none; padding: 6px; }
QScrollArea#sidebarScroll, QWidget#sidebarContent { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px 0; }
QScrollBar::handle:vertical { background: #cad6e5; border-radius: 4px; min-height: 35px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QDoubleSpinBox { background: #f6f8fc; border: 1px solid #e3e9f2; border-radius: 9px; padding: 6px 10px; }
QSlider::groove:horizontal { height: 5px; background: #e3ebf5; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #007aff; border-radius: 2px; }
QSlider::handle:horizontal { width: 17px; margin: -6px 0; border: 1px solid #d3deec; border-radius: 8px; background: white; }
QSlider::sub-page:horizontal:disabled { background: #ccd7e5; }
"""


class LoadSignals(QObject):
    done = Signal(object, object, object, str)
    failed = Signal(str)


class LoadJob(QRunnable):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = LoadSignals()

    def run(self):
        try:
            atoms, mask = load_structure(self.path)
            self.signals.done.emit(atoms, mask, viewer_payload(atoms), self.path)
        except Exception as error:
            self.signals.failed.emit(str(error))


class Bridge(QObject):
    stateChanged = Signal(str)
    command = Signal(str)
    viewRequested = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @Slot()
    def ready(self):
        self.window.viewer_ready = True
        self.window.send_state(full=True)
        self.window.refresh_ui()
        self.window.statusBar().showMessage("视图已就绪 · 本地离线运行")

    @Slot(str)
    def selectAtoms(self, raw: str):
        try:
            data = json.loads(raw)
            if data.get("generation") != self.window.generation or self.window.loading:
                return
            self.window.edit_indices(data["indices"], data["action"])
        except (ValueError, TypeError, KeyError) as error:
            self.window.statusBar().showMessage(f"选择未应用：{error}", 5000)

    @Slot(str)
    def requestMode(self, mode: str):
        self.window.set_mode(mode)

    @Slot(str)
    def reportError(self, message: str):
        self.window.statusBar().showMessage(f"3D 视图：{message}")
        print(f"3Dmol error: {message}", file=sys.stderr)


class LocalPage(QWebEnginePage):
    """Do not navigate to remote content inside the local application."""
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return url.scheme() in ("file", "qrc", "about", "data")

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            print(f"JavaScript {source}:{line}: {message}", file=sys.stderr)


class MainWindow(QMainWindow):
    def __init__(self, preferences_path=None):
        super().__init__()
        self.preferences_path = Path(preferences_path) if preferences_path else APP_DIR / 'ball_settings.json'
        try:
            self.ball_overrides = load_preferences(self.preferences_path)
        except (OSError, ValueError, TypeError) as error:
            self.ball_overrides = {}
            print(f'无法载入 Ball 设置，使用默认外观：{error}', file=sys.stderr)
        self.atoms = None
        self.mask = np.zeros((0, 3), dtype=bool)
        self.saved_mask = self.mask.copy()
        self.cell_dirty = False
        self.payload = None
        self.source = None
        self.generation = 0
        self.viewer_ready = False
        self.loading = False
        self.mode = "rotate"
        self.undo_stack = []
        self.redo_stack = []
        self.job = None
        self.pool = QThreadPool(self)
        self.setWindowTitle("FixAtoms Studio")
        self.setWindowIcon(QIcon(str(ROOT / 'assets' / 'fixatoms.ico')))
        self.resize(1240, 840)
        self.setMinimumSize(1000, 760)
        self.setAcceptDrops(True)
        self.build_ui()
        self.bridge = Bridge(self)
        self.channel = QWebChannel(self.web.page())
        self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.loadFinished.connect(self.page_loaded)
        self.web.renderProcessTerminated.connect(self.render_terminated)
        self.web.setUrl(QUrl.fromLocalFile(str(ROOT / "viewer.html")))
        self.setup_actions()
        self.refresh_ui()

    @staticmethod
    def label(text, name=None, wrap=False):
        label = QLabel(text)
        if name:
            label.setObjectName(name)
        label.setWordWrap(wrap)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        label.ensurePolished()
        label.setMinimumHeight(label.fontMetrics().height() + 8)
        return label

    @staticmethod
    def button(text, callback, name=None):
        button = QPushButton(text)
        if name:
            button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        button.ensurePolished()
        button.setMinimumHeight(button.fontMetrics().height() + 24)
        return button

    def card(self, parent_layout, title):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(12)
        layout.addWidget(self.label(title, "section"))
        parent_layout.addWidget(frame)
        return layout

    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 10)
        layout.setSpacing(22)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(3)
        brand.addWidget(self.label("FixAtoms Studio", "brand"))
        brand.addWidget(self.label("结构有序，探索自由。", "subtitle"))
        header.addLayout(brand)
        header.addStretch()
        self.demo_button = self.button("体验示例", self.load_demo)
        self.open_button = self.button("打开结构…", self.open_dialog)
        self.export_button = self.button("导出 POSCAR", self.save_dialog, "primary")
        for button in (self.demo_button, self.open_button, self.export_button):
            header.addWidget(button)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(20)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName('sidebarScroll')
        self.sidebar_scroll.setFixedWidth(310)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar = QWidget()
        sidebar.setObjectName('sidebarContent')
        side = QVBoxLayout(sidebar)
        side.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        side.setContentsMargins(0, 0, 5, 0)
        side.setSpacing(14)

        info = self.card(side, "01  /  当前结构")
        self.filename = self.label("尚未打开结构", "filename")
        self.filename.setWordWrap(True)
        self.formula = self.label("CIF · POSCAR · XSD", "muted", True)
        info.addWidget(self.filename)
        info.addWidget(self.formula)
        stats = QHBoxLayout()
        self.total_label, self.fixed_label = None, None
        for caption, attribute in (("原子总数", "total_label"), ("完全固定", "fixed_label")):
            box = QFrame()
            box.setObjectName("stat")
            inner = QVBoxLayout(box)
            number = self.label("—", "number")
            setattr(self, attribute, number)
            inner.addWidget(number)
            inner.addWidget(self.label(caption, "muted"))
            stats.addWidget(box)
        info.addLayout(stats)
        self.cell_label = self.label("晶胞信息将在载入后显示", "muted", True)
        self.partial_label = self.label("", "muted", True)
        info.addWidget(self.cell_label)
        info.addWidget(self.partial_label)

        editing = self.card(side, "02  /  固定约束")
        editing.addWidget(self.label("黑色外层网格 = 完全固定\n彩色实心球保留；橙色网格为部分固定", "muted", True))
        row = QHBoxLayout()
        self.fix_all = self.button("全部固定", lambda: self.edit_all("fix"), "small")
        self.release_all = self.button("全部解除", lambda: self.edit_all("release"), "small")
        row.addWidget(self.fix_all)
        row.addWidget(self.release_all)
        editing.addLayout(row)
        self.index_edit = QLineEdit()
        self.index_edit.setPlaceholderText("原子编号，例如 1-8, 12, 16")
        self.index_edit.setToolTip("编号从 1 开始，与输入文件原子顺序一致")
        self.index_edit.ensurePolished()
        self.index_edit.setMinimumHeight(self.index_edit.fontMetrics().height() + 24)
        editing.addWidget(self.index_edit)
        row = QHBoxLayout()
        self.fix_ids = self.button("固定编号", lambda: self.edit_typed("fix"), "small")
        self.release_ids = self.button("解除编号", lambda: self.edit_typed("release"), "small")
        row.addWidget(self.fix_ids)
        row.addWidget(self.release_ids)
        editing.addLayout(row)
        row = QHBoxLayout()
        self.undo_button = self.button("↶  撤销", self.undo, "small")
        self.redo_button = self.button("↷  重做", self.redo, "small")
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        editing.addLayout(row)

        display = self.card(side, "03  /  视图设置")
        self.style_combo = QComboBox()
        for text, data in (("球棍模型", "ball"), ("空间填充", "space"), ("线框模型", "line")):
            self.style_combo.addItem(text, data)
        self.style_combo.currentIndexChanged.connect(lambda: self.send_state())
        self.style_combo.ensurePolished()
        self.style_combo.setMinimumHeight(self.style_combo.fontMetrics().height() + 24)
        display.addWidget(self.style_combo)
        self.cell_check = QCheckBox("显示晶胞边界")
        self.cell_check.setChecked(True)
        self.cell_check.ensurePolished()
        self.cell_check.setMinimumHeight(self.cell_check.fontMetrics().height() + 12)
        self.cell_check.toggled.connect(lambda: self.send_state())
        display.addWidget(self.cell_check)
        display.addWidget(self.label('投影方式', 'muted'))
        self.projection_combo = QComboBox()
        self.projection_combo.addItem('正交投影  Orthographic', 'orthographic')
        self.projection_combo.addItem('透视投影  Perspective', 'perspective')
        self.projection_combo.setMinimumHeight(self.style_combo.minimumHeight())
        self.projection_combo.setToolTip('正交：原子大小不随远近变化；透视：近大远小。')
        display.addWidget(self.projection_combo)
        angle_row = QHBoxLayout()
        angle_row.addWidget(self.label('透视视角', 'muted'))
        self.view_angle = QDoubleSpinBox()
        self.view_angle.setRange(10, 90)
        self.view_angle.setDecimals(0)
        self.view_angle.setValue(45)
        self.view_angle.setSuffix(' °')
        self.view_angle.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.view_angle.setMinimumHeight(self.style_combo.minimumHeight())
        self.view_angle.setEnabled(False)
        self.view_angle.setToolTip('透视视野角度（FOV）：较大角度获得更宽视野。仅在透视模式可用。')
        angle_row.addWidget(self.view_angle)
        display.addLayout(angle_row)
        self.depth_check = QCheckBox('深度雾化  Depth cue')
        self.depth_check.setMinimumHeight(self.cell_check.minimumHeight())
        self.depth_check.setToolTip('远处逐渐淡入背景，增强纵深感；不改变投影或原子约束。')
        display.addWidget(self.depth_check)
        depth_row = QHBoxLayout()
        depth_row.addWidget(self.label('弱', 'muted'))
        self.depth_slider = QSlider(Qt.Orientation.Horizontal)
        self.depth_slider.setRange(0, 100)
        self.depth_slider.setValue(35)
        self.depth_slider.setEnabled(False)
        self.depth_slider.setMinimumHeight(26)
        depth_row.addWidget(self.depth_slider, 1)
        depth_row.addWidget(self.label('强', 'muted'))
        display.addLayout(depth_row)
        self.projection_combo.currentIndexChanged.connect(self.projection_changed)
        self.view_angle.valueChanged.connect(lambda: self.send_state())
        self.depth_check.toggled.connect(self.depth_changed)
        self.depth_slider.valueChanged.connect(lambda: self.send_state())
        self.vacuum_button = self.button("添加真空晶胞…", self.add_vacuum, "small")
        display.addWidget(self.vacuum_button)
        side.addStretch()
        self.sidebar_scroll.setWidget(sidebar)
        body.addWidget(self.sidebar_scroll)

        stage = QFrame()
        stage.setObjectName("stage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(14, 14, 14, 14)
        stage_layout.setSpacing(8)
        bar = QHBoxLayout()
        segment = QFrame()
        segment.setObjectName("segment")
        segments = QHBoxLayout(segment)
        segments.setContentsMargins(4, 4, 4, 4)
        segments.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for text, value in (("旋转  1", "rotate"), ("点选  2", "point"), ("框选  3", "box")):
            button = self.button(text, lambda checked=False, m=value: self.set_mode(m), "segmentButton")
            button.setCheckable(True)
            self.mode_group.addButton(button)
            self.mode_buttons[value] = button
            segments.addWidget(button)
        self.mode_buttons["rotate"].setChecked(True)
        bar.addWidget(segment)
        bar.addStretch()
        self.ball_button = self.button("Ball 设置", self.open_ball_settings, "small")
        bar.addWidget(self.ball_button)
        bar.addWidget(self.button("居中视图", lambda: self.bridge.command.emit("reset"), "small"))
        stage_layout.addLayout(bar)
        standard_bar = QHBoxLayout()
        standard_bar.setSpacing(6)
        self.standard_view_buttons = {}
        for name, (label, horizontal, sign, vertical) in STANDARD_VIEWS.items():
            button = self.button(label, lambda checked=False, n=name: self.set_standard_view(n), 'small')
            direction = '右' if sign > 0 else '左'
            tip = f"晶面正对屏幕；{'abc'[horizontal]} 轴向{direction}，{'abc'[vertical]} 轴向上。"
            if name == 'bottom':
                tip += '按当前定义，下视图与上视图朝向相同。'
            button.setToolTip(tip)
            self.standard_view_buttons[name] = button
            standard_bar.addWidget(button, 1)
        stage_layout.addLayout(standard_bar)
        self.web = QWebEngineView()
        self.web.setPage(LocalPage(self.web))
        self.web.page().setBackgroundColor(QColor("#f8fafc"))
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.web.setAcceptDrops(False)
        stage_layout.addWidget(self.web, 1)
        body.addWidget(stage, 1)
        layout.addLayout(body, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("正在初始化本地 3D 视图…")

    def setup_actions(self):
        for shortcut, callback in (("Ctrl+O", self.open_dialog), ("Ctrl+S", self.save_dialog),
                                   ("Ctrl+Z", self.undo), ("Ctrl+Shift+Z", self.redo), ("Ctrl+Y", self.redo),
                                   ("F11", self.toggle_fullscreen),
                                   ("Escape", lambda: self.set_mode("rotate"))):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)
        for key, mode in (("1", "rotate"), ("2", "point"), ("3", "box")):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(lambda checked=False, m=mode: self.mode_shortcut(m))
            self.addAction(action)

    def mode_shortcut(self, mode):
        if self.index_edit.hasFocus():
            self.index_edit.insert({"rotate": "1", "point": "2", "box": "3"}[mode])
        else:
            self.set_mode(mode)

    def page_loaded(self, ok):
        if not ok:
            self.statusBar().showMessage("视图加载失败，请检查 viewer.html 和 3Dmol-min.js 是否存在。")

    def render_terminated(self, status, code):
        self.viewer_ready = False
        self.refresh_ui()
        self.statusBar().showMessage(f"3D 渲染进程已退出（{code}）。请重新启动程序，并检查显卡 / WebGL 环境。")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def preview_appearance(self, overrides):
        self.ball_overrides = {key: dict(value) for key, value in overrides.items()}
        self.send_state()

    def projection_changed(self):
        self.view_angle.setEnabled(self.projection_combo.currentData() == 'perspective')
        self.send_state()

    def depth_changed(self, enabled):
        self.depth_slider.setEnabled(enabled)
        self.send_state()

    def set_standard_view(self, name):
        if self.atoms is None or self.loading or not self.viewer_ready:
            return
        try:
            view = standard_view(self.atoms.cell.array, name)
        except ValueError as error:
            self.statusBar().showMessage(str(error), 6000)
            return
        view['generation'] = self.generation
        self.bridge.viewRequested.emit(json.dumps(view))
        message = f"{view['label']} · 已按晶胞方向居中对齐"
        if view['skewed']:
            message += ' · 非正交晶胞保留真实夹角，第二条轴朝上但不强制竖直'
        if name == 'bottom':
            message += ' · 当前定义与上视图相同'
        self.statusBar().showMessage(message, 8000)

    def open_ball_settings(self):
        counts = Counter(self.atoms.get_chemical_symbols()) if self.atoms is not None else {}
        dialog = BallSettingsDialog(self.ball_overrides, counts, self.style_combo.currentData(), self)
        dialog.appearanceChanged.connect(self.preview_appearance)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preview_appearance(dialog.overrides)
            try:
                temporary = self.preferences_path.with_suffix('.json.tmp')
                temporary.write_text(json.dumps(self.ball_overrides, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(self.preferences_path)
                self.statusBar().showMessage('Ball 外观已保存，下次启动自动恢复。', 5000)
            except OSError as error:
                QMessageBox.warning(self, '外观已应用，但无法保存偏好', str(error))

    def send_state(self, full=False):
        if not self.viewer_ready:
            return
        state = {"generation": self.generation, "masks": self.mask.tolist(), "mode": self.mode,
                 "style": self.style_combo.currentData(), "showCell": self.cell_check.isChecked()}
        symbols = set(self.atoms.get_chemical_symbols()) if self.atoms is not None else set()
        state['appearance'] = {symbol: element_appearance(symbol, self.ball_overrides, self.style_combo.currentData()) for symbol in sorted(symbols)}
        state['camera'] = {'projection': self.projection_combo.currentData(), 'fov': self.view_angle.value(),
                           'depthCue': self.depth_check.isChecked(), 'depthIntensity': self.depth_slider.value()}
        if full and self.payload is not None:
            state["structure"] = self.payload
        self.bridge.stateChanged.emit(json.dumps(state, ensure_ascii=False, allow_nan=False))

    def set_mode(self, mode):
        if mode in self.mode_buttons:
            self.mode = mode
            self.mode_buttons[mode].setChecked(True)
            self.send_state()

    @property
    def dirty(self):
        return self.cell_dirty or not np.array_equal(self.mask, self.saved_mask)

    def refresh_ui(self):
        available = self.atoms is not None and not self.loading
        for button in self.standard_view_buttons.values():
            button.setEnabled(available and self.viewer_ready and has_valid_cell(self.atoms))
        for widget in (self.export_button, self.fix_all, self.release_all, self.fix_ids,
                       self.release_ids, self.index_edit):
            widget.setEnabled(available)
        self.open_button.setEnabled(not self.loading)
        self.demo_button.setEnabled(not self.loading)
        self.undo_button.setEnabled(available and bool(self.undo_stack))
        self.redo_button.setEnabled(available and bool(self.redo_stack))
        self.vacuum_button.setEnabled(available and not has_valid_cell(self.atoms))
        if self.atoms is not None:
            self.total_label.setText(str(len(self.atoms)))
            self.fixed_label.setText(str(int(self.mask.all(axis=1).sum())))
            partial = int((self.mask.any(axis=1) & ~self.mask.all(axis=1)).sum())
            self.partial_label.setText(f"另有 {partial} 个部分方向固定原子" if partial else "自由原子可继续参与结构优化")
            if has_valid_cell(self.atoms):
                a, b, c = self.atoms.cell.lengths()
                self.cell_label.setText(f"晶胞  {a:.3f} × {b:.3f} × {c:.3f} Å")
            else:
                self.cell_label.setText("无完整晶胞 · 导出前请添加真空晶胞")
        self.setWindowTitle(("● " if self.dirty else "") + "FixAtoms Studio")

    def confirm_replace(self):
        if not self.dirty:
            return True
        result = QMessageBox.question(self, "尚未导出修改", "当前修改尚未导出为 POSCAR。是否先保存？",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Save)
        if result == QMessageBox.StandardButton.Save:
            return self.save_dialog()
        return result == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        if self.loading:
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开结构", str(self.source.parent if self.source else APP_DIR),
                                             "结构文件 (*.cif *.xsd *.vasp *.poscar POSCAR* CONTCAR*);;所有文件 (*)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        if self.loading or not self.confirm_replace():
            return
        self.loading = True
        self.refresh_ui()
        self.statusBar().showMessage(f"正在读取 {Path(path).name} …")
        self.job = LoadJob(str(path))
        self.job.signals.done.connect(self.accept_structure)
        self.job.signals.failed.connect(self.load_failed)
        self.pool.start(self.job)

    @Slot(str)
    def load_failed(self, error):
        self.loading = False
        self.refresh_ui()
        QMessageBox.warning(self, "无法打开结构", error)
        self.statusBar().showMessage("读取失败")

    @Slot(object, object, object, str)
    def accept_structure(self, atoms, mask, payload, path):
        self.atoms, self.mask, self.payload = atoms, mask.copy(), payload
        self.saved_mask = mask.copy()
        self.cell_dirty = False
        self.source = Path(path) if path else None
        self.generation += 1
        self.loading = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        name = self.source.name if self.source else "Cu(111) · 四层表面"
        self.filename.setText(name if len(name) <= 32 else name[:29] + "…")
        self.filename.setToolTip(str(self.source) if self.source else name)
        self.formula.setText(atoms.get_chemical_formula() + "  ·  " + (self.source.suffix[1:].upper() or "VASP" if self.source else "示例结构"))
        self.index_edit.clear()
        self.refresh_ui()
        self.send_state(full=True)
        self.statusBar().showMessage(f"已载入 {len(atoms)} 个原子 · 原子编号从 1 开始")

    def load_demo(self):
        if self.loading or not self.confirm_replace():
            return
        atoms, mask = demo_structure()
        self.accept_structure(atoms, mask, viewer_payload(atoms), "")

    def edit_indices(self, indices, action):
        if self.atoms is None or self.loading:
            return
        if action not in ("fix", "release", "toggle"):
            raise ValueError("未知选择操作")
        if not isinstance(indices, list) or any(type(i) is not int or i < 0 or i >= len(self.atoms) for i in indices):
            raise ValueError("原子编号超出范围")
        indices = sorted(set(indices))
        if not indices:
            self.statusBar().showMessage("当前范围内没有原子", 3000)
            return
        updated = self.mask.copy()
        if action == "toggle":
            updated[indices] = (~updated[indices].all(axis=1))[:, None]
        else:
            updated[indices] = action == "fix"
        if not np.array_equal(updated, self.mask):
            self.undo_stack.append(self.mask.copy())
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
            self.mask = updated
            self.refresh_ui()
            self.send_state()
            self.statusBar().showMessage(f"已更新 {len(indices)} 个原子的约束 · Ctrl+Z 撤销", 5000)

    def edit_all(self, action):
        if self.atoms is not None:
            self.edit_indices(list(range(len(self.atoms))), action)

    def edit_typed(self, action):
        if self.atoms is None:
            return
        try:
            tokens = re.split(r"[,，\s]+", self.index_edit.text().strip())
            ids = set()
            for token in tokens:
                match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
                if not match:
                    raise ValueError("请使用原子编号或范围，例如：1-8, 12, 16。")
                start = int(match[1])
                end = int(match[2] or match[1])
                if not 1 <= start <= end <= len(self.atoms):
                    raise ValueError(f"编号应在 1 到 {len(self.atoms)} 之间，范围需从小到大。")
                ids.update(range(start - 1, end))
            self.edit_indices(sorted(ids), action)
        except ValueError as error:
            QMessageBox.warning(self, "检查原子编号", str(error))

    def undo(self):
        if self.undo_stack and not self.loading:
            self.redo_stack.append(self.mask.copy())
            self.mask = self.undo_stack.pop()
            self.refresh_ui()
            self.send_state()

    def redo(self):
        if self.redo_stack and not self.loading:
            self.undo_stack.append(self.mask.copy())
            self.mask = self.redo_stack.pop()
            self.refresh_ui()
            self.send_state()

    def add_vacuum(self):
        if self.atoms is None or has_valid_cell(self.atoms) or self.loading:
            return
        vacuum, ok = QInputDialog.getDouble(self, "添加真空晶胞", "建立正交晶胞并居中；每侧真空厚度（Å）：", 10, 1, 100, 2)
        if ok:
            self.atoms = self.atoms.copy()
            self.atoms.set_cell(np.diag(np.ptp(self.atoms.positions, axis=0) + 2 * vacuum))
            self.atoms.center()
            self.atoms.pbc = True
            self.cell_dirty = True
            self.generation += 1
            self.payload = viewer_payload(self.atoms)
            self.refresh_ui()
            self.send_state(full=True)

    def save_dialog(self):
        if self.atoms is None or self.loading:
            return False
        if not has_valid_cell(self.atoms):
            QMessageBox.warning(self, "需要晶胞", "POSCAR 需要完整晶胞。请先点击“添加真空晶胞…”，设置真空厚度。")
            return False
        folder = self.source.parent if self.source else APP_DIR
        path, _ = QFileDialog.getSaveFileName(self, "导出 POSCAR", str(folder / "POSCAR_fixed"), "POSCAR / VASP (*)")
        if not path:
            return False
        if Path(path).suffix.lower() in (".cif", ".xsd"):
            QMessageBox.warning(self, "仅支持 POSCAR 输出", "请使用 POSCAR、POSCAR_fixed 或 .vasp 文件名，避免与 CIF / XSD 格式混淆。")
            return False
        try:
            export_poscar(path, self.atoms, self.mask)
        except Exception as error:
            QMessageBox.critical(self, "导出失败", str(error))
            return False
        self.saved_mask = self.mask.copy()
        self.cell_dirty = False
        self.refresh_ui()
        self.statusBar().showMessage(f"已导出 POSCAR：{path}")
        return True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.loading:
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.load_path(urls[0].toLocalFile())
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.loading:
            self.statusBar().showMessage("正在读取结构，请等待完成后关闭。")
            event.ignore()
        elif self.confirm_replace():
            event.accept()
        else:
            event.ignore()


def main():
    parser = argparse.ArgumentParser(description="FixAtoms Studio — ASE + Qt + 3Dmol.js")
    parser.add_argument("file", nargs="?", help="CIF / POSCAR / XSD 文件")
    parser.add_argument("--demo", action="store_true", help="显示 Cu(111) 四层表面示例")
    parser.add_argument('--self-test', metavar='OUTPUT_DIR', help='运行便携包自检并保存报告后退出')
    args = parser.parse_args()
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FixAtoms.Studio.Desktop')
    app = QApplication(sys.argv[:1])
    app.setApplicationName("FixAtoms Studio")
    app.setWindowIcon(QIcon(str(ROOT / 'assets' / 'fixatoms.ico')))
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLESHEET)
    for asset in ("viewer.html", "viewer.js", "3Dmol-min.js"):
        if not (ROOT / asset).is_file():
            QMessageBox.critical(None, "缺少资源文件", f"找不到 {ROOT / asset}，请保留完整程序目录。")
            return 1
    window = MainWindow()
    window.show()
    if args.self_test:
        from portable_check import run_check
        return run_check(window, Path(args.self_test), ROOT / 'examples')
    if args.file:
        window.load_path(str(Path(args.file).resolve()))
    elif args.demo:
        window.load_demo()
    return app.exec()


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(main())
