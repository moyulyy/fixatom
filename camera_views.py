"""Crystal-relative camera orientations (screen +x right, screen +y down)."""
from __future__ import annotations

import numpy as np

# name: (label, horizontal lattice vector, sign, upward lattice vector)
# Bottom intentionally matches top, as specified by the user.
STANDARD_VIEWS = {
    'front': ('前视图', 0, 1, 2),
    'back': ('后视图', 0, -1, 2),
    'left': ('左视图', 1, -1, 2),
    'right': ('右视图', 1, 1, 2),
    'top': ('上视图', 0, 1, 1),
    'bottom': ('下视图', 0, 1, 1),
}


def standard_view(cell, name):
    """Return an SO(3) quaternion (x,y,z,w), never a reflection or atom transform.

    For skew cells, keep the chosen plane parallel to the screen and its first
    axis horizontal. The second axis keeps its real angle and points upward.
    """
    cell = np.asarray(cell, dtype=float)
    if cell.shape != (3, 3) or not np.isfinite(cell).all() or abs(np.linalg.det(cell)) <= 1e-8:
        raise ValueError('标准视图需要三个线性独立的晶胞向量。')
    if name not in STANDARD_VIEWS:
        raise ValueError('未知标准视图。')
    label, horizontal, sign, vertical = STANDARD_VIEWS[name]
    right = cell[horizontal] * sign
    right /= np.linalg.norm(right)
    up_target = cell[vertical] / np.linalg.norm(cell[vertical])
    toward_camera = np.cross(right, up_target)
    toward_camera /= np.linalg.norm(toward_camera)
    up = np.cross(toward_camera, right)
    rotation = np.array([right, up, toward_camera])
    # Choose the largest quaternion component for numerical stability at 180°.
    candidates = np.array([
        1 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2],
        1 - rotation[0, 0] + rotation[1, 1] - rotation[2, 2],
        1 - rotation[0, 0] - rotation[1, 1] + rotation[2, 2],
        1 + np.trace(rotation),
    ])
    biggest = int(candidates.argmax())
    q = np.zeros(4)
    q[biggest] = .5 * np.sqrt(max(0., candidates[biggest]))
    scale = 4 * q[biggest]
    if biggest == 3:
        q[:3] = [rotation[2, 1] - rotation[1, 2], rotation[0, 2] - rotation[2, 0], rotation[1, 0] - rotation[0, 1]]
        q[:3] /= scale
    else:
        j, k = (biggest + 1) % 3, (biggest + 2) % 3
        q[j] = (rotation[biggest, j] + rotation[j, biggest]) / scale
        q[k] = (rotation[biggest, k] + rotation[k, biggest]) / scale
        q[3] = (rotation[k, j] - rotation[j, k]) / scale
    q /= np.linalg.norm(q)
    return {'name': name, 'label': label, 'quaternion': q.tolist(),
            'skewed': bool(abs(np.dot(right, up_target)) > 1e-7)}
