#!/usr/bin/env python3
"""Reopen Evince with inverse search after a successful TexLab build."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse

import dbus


EV_DAEMON_NAME = "org.gnome.evince.Daemon"
EV_DAEMON_PATH = "/org/gnome/evince/Daemon"
EV_DAEMON_IFACE = "org.gnome.evince.Daemon"


def file_uri(path):
    absolute = os.path.abspath(path)
    return "file://" + urllib.parse.quote(absolute, safe="%/:=&?~#+!$,;'@()*[]")


def is_open_in_evince(pdf_path):
    try:
        bus = dbus.SessionBus()
        daemon = bus.get_object(EV_DAEMON_NAME, EV_DAEMON_PATH)
        return bool(
            daemon.FindDocument(
                file_uri(pdf_path), False, dbus_interface=EV_DAEMON_IFACE
            )
        )
    except dbus.DBusException:
        return False


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} PDF")

    pdf_path = str(Path(sys.argv[1]).resolve())
    if not Path(pdf_path).is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if is_open_in_evince(pdf_path):
        return

    helper_dir = Path(__file__).resolve().parent
    helper = helper_dir / "evince_inverse_search.py"
    texlab = helper_dir / "texlab-scoped.sh"
    editor_command = f"{texlab} inverse-search --input %f --line1 %l"

    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    digest = hashlib.sha256(pdf_path.encode()).hexdigest()[:12]
    log_path = runtime_dir / f"zed-latex-{digest}.log"
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(helper), pdf_path, editor_command],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )


if __name__ == "__main__":
    main()
