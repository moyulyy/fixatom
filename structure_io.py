"""ASE-backed structure I/O. Indices always refer to the original atom order."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms, FixScaled
from ase.data import covalent_radii, vdw_radii
from ase.io import read, write
from ase.neighborlist import neighbor_list


def constraint_mask(atoms: Atoms) -> np.ndarray:
    """True means fixed along a POSCAR lattice direction, including partial locks."""
    mask = np.zeros((len(atoms), 3), dtype=bool)
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            mask[constraint.index] = True
        elif isinstance(constraint, FixScaled):
            mask[constraint.index] |= constraint.mask
        else:
            raise ValueError(f"不支持的约束类型：{type(constraint).__name__}，无法安全转换为 POSCAR。")
    return mask


def load_structure(path: str | Path) -> tuple[Atoms, np.ndarray]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".cif":
        fmt = "cif"
    elif suffix == ".xsd":
        fmt = "xsd"
    elif suffix in (".vasp", ".poscar") or path.name.upper().startswith(("POSCAR", "CONTCAR")) or not suffix:
        fmt = "vasp"
    else:
        raise ValueError("支持 CIF、POSCAR / CONTCAR（.vasp、.poscar）和 XSD 文件。")
    atoms = read(str(path), format=fmt, index=0)
    if not len(atoms) or not np.isfinite(atoms.positions).all() or not np.isfinite(atoms.cell.array).all():
        raise ValueError("结构为空，或坐标 / 晶胞包含无效数值。")
    return atoms, constraint_mask(atoms)


def has_valid_cell(atoms: Atoms) -> bool:
    return bool(atoms.cell.rank == 3 and abs(np.linalg.det(atoms.cell.array)) > 1e-8)


def export_poscar(path: str | Path, atoms: Atoms, mask: np.ndarray) -> None:
    """Atomic replacement, explicit VASP format, no sorting or coordinate wrapping."""
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != (len(atoms), 3):
        raise ValueError("固定状态与原子数量不匹配。")
    if not has_valid_cell(atoms):
        raise ValueError("POSCAR 需要三个线性独立的晶胞向量。请先使用“添加真空晶胞”。")
    output = atoms.copy()
    fully_fixed = np.all(mask, axis=1)
    constraints = [FixAtoms(indices=np.flatnonzero(fully_fixed))]
    constraints.extend(FixScaled(int(i), mask=mask[i]) for i in np.flatnonzero(mask.any(axis=1) & ~fully_fixed))
    output.set_constraint(constraints)
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".fixatoms-", suffix=".vasp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            write(stream, output, format="vasp", direct=True, sort=False, vasp5=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def viewer_payload(atoms: Atoms) -> dict:
    """Send exact coordinates and explicit bonds; never use lossy PDB formatting."""
    symbols = atoms.get_chemical_symbols()
    bonds: list[list[int]] = [[] for _ in atoms]
    # Render just the supplied cell. Exclude bonds to periodic images.
    nonperiodic = atoms.copy()
    nonperiodic.pbc = False
    left, right = neighbor_list("ij", nonperiodic, 1.15 * covalent_radii[atoms.numbers])
    for i, j in zip(left, right):
        bonds[int(i)].append(int(j))
    records = []
    for i, (symbol, xyz, number) in enumerate(zip(symbols, atoms.positions, atoms.numbers)):
        radius = float(vdw_radii[number]) if number < len(vdw_radii) else float('nan')
        if not np.isfinite(radius):
            radius = max(1.0, float(covalent_radii[number]) * 1.5)
        records.append({"index": i, "serial": i, "elem": symbol,
                        "x": float(xyz[0]), "y": float(xyz[1]), "z": float(xyz[2]),
                        "bonds": bonds[i], "bondOrder": [1] * len(bonds[i]), "vdw": radius})
    return {"atoms": records, "cell": atoms.cell.array.tolist(), "validCell": has_valid_cell(atoms)}


def demo_structure() -> tuple[Atoms, np.ndarray]:
    from ase.build import fcc111

    atoms = fcc111("Cu", size=(4, 4, 4), vacuum=9.0, orthogonal=True)
    mask = np.zeros((len(atoms), 3), dtype=bool)
    mask[atoms.get_tags() >= 3] = True
    return atoms, mask
