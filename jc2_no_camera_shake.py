#!/usr/bin/env python3
"""Disable Just Cause 2's camera shake, or restore it.

The game stores a shake amplitude on the camera manager. While that amplitude
is above zero, one function builds a random view offset and mixes it into the
camera matrix. Footsteps, the grappling hook, gunfire, and explosions all feed
that same function.

This script turns the function into an immediate return. It changes three
bytes and only does so when the surrounding instructions still match the
Steam Windows build. Framing from the run-camera and grapple-camera filters
is left alone.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Original function prologue: push ebp / mov ebp, esp / mov eax, [0x11971e4]
ORIGINAL_PROLOGUE = bytes.fromhex("558beca1e4711901")
# ret 8, with the same absolute load left in place so restore can find it.
PATCHED_PROLOGUE = bytes.fromhex("c20800a1e4711901")
PROLOGUE_LEN = 3

# movss xmm1, [ebx+0x24] / comiss xmm1, xmm0 / jbe +0x23A
AMPLITUDE_CHECK_OFFSET = 0x5C
AMPLITUDE_CHECK = bytes.fromhex("f30f104b240f2fc80f863a020000")

# Original `ret 8` at the end of the function. Patching must not land here.
FUNCTION_RET_OFFSET = 0x2A8
FUNCTION_RET = bytes.fromhex("c20800")

PATCH = bytes.fromhex("c20800")
BACKUP_SUFFIX = ".noshake-backup"


def steam_library_roots() -> list[Path]:
    roots: list[Path] = []
    candidates = [
        Path.home() / "AppData/Local/Steam",
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    for install in candidates:
        vdf = install / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith('"path"'):
                continue
            quoted = line.split('"path"', 1)[1].strip()
            if len(quoted) >= 2 and quoted[0] == '"' and quoted[-1] == '"':
                raw = quoted[1:-1].replace("\\\\", "\\")
                roots.append(Path(raw))
        roots.append(install)
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return seen


def default_game_dir() -> Path | None:
    for root in steam_library_roots():
        game = root / "steamapps" / "common" / "Just Cause 2"
        if (game / "JustCause2.exe").is_file():
            return game
    return None


def choose_exe(initial_dir: Path | None) -> Path | None:
    """Ask the user to pick JustCause2.exe. Returns None if they cancel."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    initial = initial_dir if initial_dir and initial_dir.is_dir() else None
    selected = filedialog.askopenfilename(
        title="Select JustCause2.exe",
        initialdir=str(initial) if initial else None,
        initialfile="JustCause2.exe" if initial else None,
        filetypes=[
            ("Just Cause 2 executable", "*.exe"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    if not selected:
        return None
    return Path(selected)


def prompt_for_exe(initial_dir: Path | None) -> Path | None:
    try:
        return choose_exe(initial_dir)
    except Exception as exc:
        print(
            f"Could not open the file dialog ({exc}). "
            "Pass the path to JustCause2.exe instead.",
            file=sys.stderr,
        )
        return None


def show_result(message: str, *, error: bool) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    if error:
        messagebox.showerror("JC2 no camera shake", message)
    else:
        messagebox.showinfo("JC2 no camera shake", message)
    root.destroy()


def classify(data: bytes) -> tuple[str, int | None]:
    """Return ('original'|'patched'|'unknown', offset)."""
    original_hits = _find_all(data, ORIGINAL_PROLOGUE)
    patched_hits = _find_all(data, PATCHED_PROLOGUE)
    original_ok = [off for off in original_hits if _body_matches(data, off)]
    patched_ok = [off for off in patched_hits if _body_matches(data, off)]
    if len(original_ok) == 1 and not patched_ok:
        return "original", original_ok[0]
    if len(patched_ok) == 1 and not original_ok:
        return "patched", patched_ok[0]
    if len(original_ok) + len(patched_ok) > 1:
        return "ambiguous", None
    return "unknown", None


def _find_all(data: bytes, needle: bytes) -> list[int]:
    hits: list[int] = []
    start = 0
    while True:
        found = data.find(needle, start)
        if found < 0:
            return hits
        hits.append(found)
        start = found + 1


def _body_matches(data: bytes, offset: int) -> bool:
    check = offset + AMPLITUDE_CHECK_OFFSET
    ret = offset + FUNCTION_RET_OFFSET
    if ret + len(FUNCTION_RET) > len(data):
        return False
    return (
        data[check : check + len(AMPLITUDE_CHECK)] == AMPLITUDE_CHECK
        and data[ret : ret + len(FUNCTION_RET)] == FUNCTION_RET
    )


def backup_path(exe: Path) -> Path:
    return exe.with_name(exe.name + BACKUP_SUFFIX)


def patch_file(exe: Path, restore: bool, dry_run: bool) -> str:
    data = bytearray(exe.read_bytes())
    state, offset = classify(data)
    if state == "unknown":
        return f"{exe.name}: shake function not found; left untouched"
    if state == "ambiguous":
        return f"{exe.name}: more than one match; left untouched"

    assert offset is not None
    if restore:
        if state == "original":
            return f"{exe.name}: camera shake already enabled"
        data[offset : offset + PROLOGUE_LEN] = ORIGINAL_PROLOGUE[:PROLOGUE_LEN]
        action = "restored camera shake"
    else:
        if state == "patched":
            return f"{exe.name}: camera shake already disabled"
        backup = backup_path(exe)
        if not dry_run and not backup.exists():
            shutil.copy2(exe, backup)
        data[offset : offset + PROLOGUE_LEN] = PATCH
        action = "disabled camera shake"

    if dry_run:
        return f"{exe.name}: would have {action} at file offset 0x{offset:x}"
    exe.write_bytes(data)
    return f"{exe.name}: {action} at file offset 0x{offset:x}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Disable or restore Just Cause 2 camera shake."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="JustCause2.exe. When omitted, a file dialog opens so you can "
        "select it. A folder opens the dialog there.",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Put the original shake function back.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing the executable.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    used_dialog = False
    if args.path:
        target = Path(args.path).expanduser()
        if target.is_dir():
            exe = prompt_for_exe(target)
            used_dialog = True
        elif target.is_file():
            exe = target
        else:
            print(f"Not a file or directory: {target}", file=sys.stderr)
            return 1
    else:
        exe = prompt_for_exe(default_game_dir())
        used_dialog = True

    if exe is None:
        print("No file selected.")
        return 1

    try:
        message = patch_file(exe, restore=args.restore, dry_run=args.dry_run)
        failed = "left untouched" in message or "cannot write" in message
    except PermissionError:
        message = f"{exe.name}: cannot write the file. Close the game and try again."
        failed = True

    print(message, file=sys.stderr if failed else sys.stdout)
    if used_dialog:
        show_result(message, error=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
