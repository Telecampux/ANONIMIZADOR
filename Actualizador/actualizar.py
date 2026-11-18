"""Actualizador independiente del Anonimizador (Python 3, solo biblioteca estándar)."""

from __future__ import annotations

import json
import os
import sys
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


REPOSITORY = "Telecampux/ANONIMIZADOR"
BRANCH = "main"
ARCHIVE_URL = f"https://github.com/{REPOSITORY}/archive/refs/heads/{BRANCH}.zip"
MANIFEST = "Actualizador/archivos_programa.json"
PROTECTED = {".git", ".venv", "salida", "tessdata", "tmp", "capturas", "casos"}
SAVED_FOLDER = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Anonimizador" / "carpeta_programa.txt"


def valid_path(raw: str) -> Path:
    posix = PurePosixPath(raw)
    if (not raw or posix.is_absolute() or "\\" in raw or
            any(part in ("", ".", "..") for part in posix.parts) or
            posix.parts[0].lower() in PROTECTED or ":" in raw):
        raise ValueError(f"Ruta no permitida en el manifiesto: {raw}")
    return Path(*posix.parts)


def read_package(archive: Path, staging: Path) -> list[Path]:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        if len(roots) != 1:
            raise ValueError("El paquete descargado no tiene una raíz única.")
        root = roots.pop()
        manifest_name = f"{root}/{MANIFEST}"
        manifest = json.loads(bundle.read(manifest_name))
        entries = manifest.get("archivos")
        if not isinstance(entries, list) or not entries or len(entries) != len(set(entries)):
            raise ValueError("El manifiesto de archivos es inválido.")
        paths = [valid_path(item) for item in entries if isinstance(item, str)]
        if len(paths) != len(entries):
            raise ValueError("El manifiesto contiene una ruta inválida.")
        for relative in paths:
            source = f"{root}/{relative.as_posix()}"
            info = bundle.getinfo(source)
            if info.is_dir() or info.file_size > 100_000_000:
                raise ValueError(f"Archivo inválido: {relative}")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as stream, destination.open("wb") as output:
                shutil.copyfileobj(stream, output)
        return paths


def install(staging: Path, destination: Path, paths: list[Path]) -> None:
    """Reemplaza solo archivos declarados; recupera la versión anterior ante un error."""
    with tempfile.TemporaryDirectory(prefix="anonimizador_respaldo_") as backup_name:
        backup = Path(backup_name)
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
                shutil.copy2(staging / relative, target)
        except Exception:
            for relative in replaced:
                shutil.copy2(backup / relative, destination / relative)
            for relative in created:
                (destination / relative).unlink(missing_ok=True)
            raise


def update_direct(destination: Path) -> None:
    destination = destination.resolve()
    if not (destination / "app.py").is_file() or not (destination / "Iniciar.bat").is_file():
        raise ValueError(f"No se encuentra el Anonimizador en {destination}")
    print("Descargando la version actual de GitHub...", flush=True)
    with tempfile.TemporaryDirectory(prefix="anonimizador_actualizacion_") as work_name:
        work = Path(work_name)
        archive = work / "version.zip"
        with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        paths = read_package(archive, work / "nuevo")
        print(f"Actualizando {len(paths)} archivos en {destination}...", flush=True)
        install(work / "nuevo", destination, paths)
    print("Actualizacion terminada.", flush=True)


def main() -> None:
    window = tk.Tk()
    window.title("Actualizar Anonimizador")
    window.geometry("620x230")
    try:
        remembered = SAVED_FOLDER.read_text(encoding="utf-8").strip()
    except OSError:
        remembered = ""
    folder = tk.StringVar(value=remembered)
    status = tk.StringVar(value="Seleccione la carpeta donde ya está instalado el Anonimizador.")
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Carpeta actual del Anonimizador:").pack(anchor="w")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=8)
    ttk.Entry(row, textvariable=folder).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Examinar…", command=lambda: folder.set(filedialog.askdirectory() or folder.get())).pack(side="left", padx=(8, 0))
    ttk.Label(frame, textvariable=status, wraplength=570).pack(anchor="w", pady=8)

    def update() -> None:
        target = Path(folder.get()).expanduser()
        if not target.is_dir() or not (target / "app.py").is_file() or not (target / "Iniciar.bat").is_file():
            messagebox.showerror("Carpeta incorrecta", "Elija la carpeta que contiene app.py e Iniciar.bat.")
            return
        target = target.resolve()
        SAVED_FOLDER.parent.mkdir(parents=True, exist_ok=True)
        SAVED_FOLDER.write_text(str(target), encoding="utf-8")
        status.set("Descargando y comprobando la nueva versión…")
        window.update_idletasks()
        try:
            with tempfile.TemporaryDirectory(prefix="anonimizador_actualizacion_") as work_name:
                work = Path(work_name)
                archive = work / "version.zip"
                with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as response, archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
                paths = read_package(archive, work / "nuevo")
                existing = sum((target / path).is_file() for path in paths)
                prompt = (f"Carpeta seleccionada:\n{target}\n\n"
                          f"Se reemplazarán {existing} archivos del programa y se añadirán "
                          f"{len(paths) - existing}.\n\n"
                          "Los demás archivos de esa carpeta y los datos del usuario se conservarán. "
                          "Cierre el Anonimizador antes de continuar.\n\n¿Autoriza la actualización?")
                if not messagebox.askyesno("Autorizar reemplazo", prompt):
                    status.set("Actualización cancelada. No se cambió la instalación.")
                    return
                install(work / "nuevo", target, paths)
            status.set("Actualización terminada.")
            messagebox.showinfo("Actualización terminada", "El software se actualizó en la carpeta seleccionada.")
        except Exception as error:
            status.set("No se completó la actualización.")
            messagebox.showerror("Error de actualización", str(error))

    ttk.Button(frame, text="Descargar y actualizar", command=update).pack(anchor="e", pady=12)
    window.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--direct":
        try:
            update_direct(Path(sys.argv[2]))
        except Exception as error:
            print(f"Error de actualizacion: {error}", file=sys.stderr)
            sys.exit(1)
    else:
        main()
