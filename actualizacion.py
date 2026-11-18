"""Descarga e instala la versión publicada del Anonimizador."""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


ARCHIVE_URL = "https://github.com/Telecampux/ANONIMIZADOR/archive/refs/heads/main.zip"
MANIFEST = "Actualizador/archivos_programa.json"
PROTECTED = {".git", ".venv", "salida", "tessdata", "tmp", "capturas", "casos"}


def _safe_path(raw: str) -> Path:
    path = PurePosixPath(raw)
    if (not raw or path.is_absolute() or "\\" in raw or ":" in raw
            or any(part in ("", ".", "..") for part in path.parts)
            or path.parts[0].lower() in PROTECTED):
        raise ValueError(f"Ruta inválida en el paquete: {raw}")
    return Path(*path.parts)


def _stage(archive: Path, staging: Path) -> list[Path]:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(roots) != 1:
            raise ValueError("El paquete de GitHub no tiene una raíz única.")
        root = roots.pop()
        entries = json.loads(bundle.read(f"{root}/{MANIFEST}"))["archivos"]
        if not isinstance(entries, list) or not entries or len(entries) != len(set(entries)):
            raise ValueError("El listado de archivos del paquete es inválido.")
        paths = [_safe_path(item) for item in entries]
        for relative in paths:
            info = bundle.getinfo(f"{root}/{relative.as_posix()}")
            if info.is_dir() or info.file_size > 100_000_000:
                raise ValueError(f"Archivo inválido: {relative}")
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        return paths


def update_direct(destination: Path) -> None:
    destination = destination.resolve()
    if not (destination / "app.py").is_file() or not (destination / "Iniciar.bat").is_file():
        raise ValueError(f"No se encuentra el Anonimizador en {destination}")
    with tempfile.TemporaryDirectory(prefix="anonimizador_actualizacion_") as temporary:
        work = Path(temporary)
        archive = work / "version.zip"
        with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        paths = _stage(archive, work / "nuevo")
        backup = work / "anterior"
        replaced: list[Path] = []
        created: list[Path] = []
        try:
            for relative in paths:
                target = destination / relative
                if target.exists():
                    if not target.is_file() or target.is_symlink():
                        raise ValueError(f"No se puede reemplazar: {target}")
                    old = backup / relative
                    old.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, old)
                    replaced.append(relative)
                else:
                    created.append(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(work / "nuevo" / relative, target)
        except Exception:
            for relative in replaced:
                shutil.copy2(backup / relative, destination / relative)
            for relative in created:
                (destination / relative).unlink(missing_ok=True)
            raise
    old_updater = destination / "Actualizador"
    if old_updater.is_dir() and not old_updater.is_symlink():
        shutil.rmtree(old_updater)
