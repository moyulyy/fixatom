"""Render the editable SVG into a Windows ICO with seven embedded PNG sizes."""
from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def build_icon():
    app = QGuiApplication.instance() or QGuiApplication([])
    root = Path(__file__).resolve().parents[1]
    renderer = QSvgRenderer(str(root / 'assets' / 'fixatoms.svg'))
    if not renderer.isValid():
        raise ValueError('Invalid icon SVG')
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries, chunks = [], []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        bitmap = QImage(size, size, QImage.Format.Format_ARGB32)
        bitmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not bitmap.save(buffer, 'PNG'):
            raise RuntimeError('Could not encode icon')
        chunk = bytes(data)
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(chunk), offset))
        chunks.append(chunk)
        offset += len(chunk)
        if size == 256:
            bitmap.save(str(root / 'assets' / 'fixatoms.png'))
    target = root / 'assets' / 'fixatoms.ico'
    target.write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(entries) + b''.join(chunks))
    print(f'Created {target} ({len(sizes)} sizes)')


if __name__ == '__main__':
    build_icon()
