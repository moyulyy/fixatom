"""Element appearance preferences and a Qt periodic-table editor."""
from __future__ import annotations

import json
import math
from pathlib import Path

from ase.data import atomic_names, atomic_numbers, chemical_symbols, covalent_radii, vdw_radii
from ase.data.colors import jmol_colors
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QColorDialog, QDialog, QDoubleSpinBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


def default_color(symbol):
    number = atomic_numbers[symbol]
    rgb = jmol_colors[number] if number < len(jmol_colors) else (.60, .65, .76)
    return '#' + ''.join(f'{round(float(value) * 255):02x}' for value in rgb)


def default_diameter(symbol, style='ball'):
    if style == 'space':
        number = atomic_numbers[symbol]
        radius = float(vdw_radii[number]) if number < len(vdw_radii) else float('nan')
        if not math.isfinite(radius):
            radius = max(1., float(covalent_radii[number]) * 1.5)
        return round(radius * 1.3, 3)
    return .36 if style == 'line' else .86


def element_appearance(symbol, overrides, style='ball'):
    return {'color': default_color(symbol), 'diameter': default_diameter(symbol, style), **overrides.get(symbol, {})}


def load_preferences(path):
    if not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError('Ball 设置文件必须是元素字典。')
    result = {}
    for symbol, entry in raw.items():
        if symbol not in atomic_numbers or symbol == 'X' or not isinstance(entry, dict):
            continue
        color = entry.get('color', default_color(symbol))
        diameter = float(entry.get('diameter', .86))
        if not QColor.isValidColor(color) or not math.isfinite(diameter) or not .1 <= diameter <= 10:
            raise ValueError(f'{symbol} 的颜色或直径设置无效。')
        result[symbol] = {'color': QColor(color).name(), 'diameter': diameter}
    return result


def periodic_positions():
    """All 118 elements, with La–Lu and Ac–Lr on separate rows."""
    periods = [
        [(1, 0), (2, 17)],
        list(zip(range(3, 11), [0, 1, 12, 13, 14, 15, 16, 17])),
        list(zip(range(11, 19), [0, 1, 12, 13, 14, 15, 16, 17])),
        list(zip(range(19, 37), range(18))),
        list(zip(range(37, 55), range(18))),
        [(55, 0), (56, 1)] + list(zip(range(72, 87), range(3, 18))),
        [(87, 0), (88, 1)] + list(zip(range(104, 119), range(3, 18))),
        list(zip(range(57, 72), range(2, 17))),
        list(zip(range(89, 104), range(2, 17))),
    ]
    return {chemical_symbols[number]: (row, col) for row, period in enumerate(periods) for number, col in period}


class BallSettingsDialog(QDialog):
    appearanceChanged = Signal(object)

    def __init__(self, overrides, counts, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Ball 设置 · 元素周期表')
        screen = self.screen().availableGeometry()
        self.resize(min(1100, screen.width() - 40), min(820, screen.height() - 45))
        self.setMinimumSize(850, 580)
        self.original = {key: dict(value) for key, value in overrides.items()}
        self.overrides = {key: dict(value) for key, value in overrides.items()}
        self.counts, self.style = counts, style
        self.selected = min(counts, key=lambda s: atomic_numbers[s]) if counts else 'C'
        self.setStyleSheet('QDialog { background: #f2f5fa; }')
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)
        title = QLabel('为每一种元素，设定自己的颜色。')
        title.setStyleSheet('font-size: 21px; font-weight: 600; padding: 4px 0;')
        root.addWidget(title)
        description = QLabel('点击周期表元素，编辑球的颜色与直径。蓝点表示当前结构含有该元素；修改实时预览。')
        description.setWordWrap(True)
        description.setStyleSheet('color: #728299; padding: 3px 0;')
        root.addWidget(description)
        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setFrameShape(QFrame.Shape.NoFrame)
        table_scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }')
        table = QWidget()
        grid = QGridLayout(table)
        grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(4)
        for col in range(18):
            label = QLabel(str(col + 1))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet('color: #97a4b6; font-size: 11px; padding: 2px;')
            grid.addWidget(label, 0, col)
        self.element_buttons = {}
        for symbol, (row, col) in periodic_positions().items():
            number = atomic_numbers[symbol]
            marker = ' •' if symbol in counts else ''
            button = QPushButton(f'{number}{marker}\n{symbol}')
            button.setMinimumSize(47, 40)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f'{symbol} · {atomic_names[number]}\n当前结构：{counts.get(symbol, 0)} 个原子')
            button.clicked.connect(lambda checked=False, s=symbol: self.select_element(s))
            self.element_buttons[symbol] = button
            grid.addWidget(button, row + 1 + (1 if row >= 7 else 0), col)
        for row, text in ((6, '57–71'), (7, '89–103')):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet('color: #97a4b6; font-size: 10px;')
            grid.addWidget(label, row, 2)
        grid.setRowMinimumHeight(8, 12)
        table_scroll.setWidget(table)
        root.addWidget(table_scroll, 1)
        self.only_present = QCheckBox('只突出当前结构中的元素')
        self.only_present.setChecked(True)
        self.only_present.toggled.connect(self.refresh_tiles)
        root.addWidget(self.only_present)

        editor = QFrame()
        editor.setObjectName('card')
        edit = QHBoxLayout(editor)
        edit.setContentsMargins(18, 14, 18, 14)
        edit.setSpacing(16)
        self.element_label = QLabel()
        self.element_label.setMinimumWidth(180)
        edit.addWidget(self.element_label)
        color_column = QVBoxLayout()
        color_column.addWidget(QLabel('球颜色'))
        self.color_button = QPushButton()
        self.color_button.setMinimumHeight(40)
        self.color_button.clicked.connect(self.choose_color)
        color_column.addWidget(self.color_button)
        edit.addLayout(color_column)
        size_column = QVBoxLayout()
        size_column.addWidget(QLabel('球直径（Å）'))
        self.diameter = QDoubleSpinBox()
        self.diameter.setRange(.1, 10.)
        self.diameter.setDecimals(3)
        self.diameter.setSingleStep(.1)
        self.diameter.setSuffix(' Å')
        self.diameter.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.diameter.setMinimumHeight(40)
        self.diameter.setStyleSheet('QDoubleSpinBox { background: #f6f8fc; border: 1px solid #dce5f0; border-radius: 9px; padding: 5px 12px; }')
        self.diameter.valueChanged.connect(self.change_diameter)
        size_column.addWidget(self.diameter)
        edit.addLayout(size_column)
        reset = QPushButton('恢复此元素默认值')
        reset.clicked.connect(self.reset_element)
        edit.addWidget(reset)
        root.addWidget(editor)
        foot = QHBoxLayout()
        reset_all = QPushButton('全部恢复默认')
        reset_all.clicked.connect(self.reset_all)
        foot.addWidget(reset_all)
        foot.addStretch()
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        done = QPushButton('保存设置')
        done.setObjectName('primary')
        done.clicked.connect(self.accept)
        foot.addWidget(cancel)
        foot.addWidget(done)
        root.addLayout(foot)
        self.select_element(self.selected)

    def refresh_tiles(self):
        for symbol, button in self.element_buttons.items():
            color = QColor(element_appearance(symbol, self.overrides, self.style)['color'])
            muted = self.only_present.isChecked() and symbol not in self.counts
            # Keep the periodic table quiet; actual colors appear in the editor and legend.
            tint = QColor.fromRgbF(*[.84 + .16 * component for component in (color.redF(), color.greenF(), color.blueF())])
            border = '#007aff' if symbol == self.selected else '#dfe7f1'
            background = '#f1f4f8' if muted else tint.name()
            foreground = '#95a1b1' if muted else '#21354f'
            button.setStyleSheet(f'QPushButton {{ background: {background}; color: {foreground}; border: 2px solid {border}; border-radius: 8px; padding: 2px; font-size: 12px; }} QPushButton:hover {{ border-color: #77b6ff; }}')

    def select_element(self, symbol):
        self.selected = symbol
        appearance = element_appearance(symbol, self.overrides, self.style)
        self.element_label.setText(f'<b style="font-size:22px">{symbol}</b>　{atomic_names[atomic_numbers[symbol]]}<br>当前结构中 {self.counts.get(symbol, 0)} 个原子')
        self.element_label.setMinimumHeight(58)
        self.diameter.blockSignals(True)
        self.diameter.setValue(appearance['diameter'])
        self.diameter.blockSignals(False)
        color = QColor(appearance['color'])
        text_color = '#ffffff' if color.lightnessF() < .48 else '#182b43'
        self.color_button.setText(color.name().upper() + '  选择…')
        self.color_button.setStyleSheet(f'background: {color.name()}; color: {text_color}; border: 1px solid #b7c7da;')
        self.refresh_tiles()

    def choose_color(self):
        old = element_appearance(self.selected, self.overrides, self.style)
        color = QColorDialog.getColor(QColor(old['color']), self, f'{self.selected} · 设置球颜色')
        if color.isValid():
            self.overrides[self.selected] = {**old, 'color': color.name()}
            self.changed()

    def change_diameter(self, value):
        old = element_appearance(self.selected, self.overrides, self.style)
        self.overrides[self.selected] = {**old, 'diameter': value}
        self.changed()

    def reset_element(self):
        self.overrides.pop(self.selected, None)
        self.changed()

    def reset_all(self):
        self.overrides.clear()
        self.changed()

    def changed(self):
        self.select_element(self.selected)
        self.appearanceChanged.emit({key: dict(value) for key, value in self.overrides.items()})

    def reject(self):
        self.appearanceChanged.emit(self.original)
        super().reject()
