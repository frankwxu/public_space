#!/usr/bin/env python3
"""Open an Evince PDF and relay Ctrl+click SyncTeX events to an editor."""

import argparse
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import urllib.parse

import dbus
import dbus.mainloop.glib
from gi.repository import GLib


EV_DAEMON_NAME = "org.gnome.evince.Daemon"
EV_DAEMON_PATH = "/org/gnome/evince/Daemon"
EV_DAEMON_IFACE = "org.gnome.evince.Daemon"
EV_WINDOW_IFACE = "org.gnome.evince.Window"
EVINCE_PATH = "/org/gnome/evince/Evince"
EVINCE_IFACE = "org.gnome.evince.Application"
XDOTOOL = Path("/home/frank/.local/opt/xdotool/usr/bin/xdotool")
XDOTOOL_LIBRARY = "/home/frank/.local/opt/xdotool/usr/lib/x86_64-linux-gnu"


def file_uri(path):
    absolute = os.path.abspath(path)
    return "file://" + urllib.parse.quote(absolute, safe="%/:=&?~#+!$,;'@()*[]")


def preferred_window_geometry():
    """Return a centered, non-maximized geometry on the main WSLg monitor."""
    width, height = 1400, 1250
    try:
        output = subprocess.check_output(
            ["xrandr", "--current"], text=True, stderr=subprocess.DEVNULL
        )
        monitors = [
            tuple(map(int, match.groups()))
            for match in re.finditer(
                r"\bconnected(?:\s+primary)?\s+(\d+)x(\d+)([+-]\d+)([+-]\d+)",
                output,
            )
        ]
        monitor_width, monitor_height, monitor_x, monitor_y = max(
            monitors, key=lambda monitor: monitor[0] * monitor[1]
        )
        width = min(width, monitor_width - 100)
        height = min(height, monitor_height - 150)
        x = monitor_x + (monitor_width - width) // 2
        y = monitor_y + (monitor_height - height) // 2
        return width, height, x, y
    except (OSError, subprocess.SubprocessError, ValueError):
        return width, height, 2400, 120


def configure_pdf_window(pdf_path, logger):
    """Resize and center the X11 Evince window."""
    if not XDOTOOL.is_file():
        logger.warning("The local xdotool helper was not found.")
        return

    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = XDOTOOL_LIBRARY
    width, height, x, y = preferred_window_geometry()
    subprocess.Popen(
        [
            str(XDOTOOL),
            "search",
            "--sync",
            "--limit",
            "1",
            "--name",
            rf"^{re.escape(Path(pdf_path).name)}$",
            "windowsize",
            str(width),
            str(height),
            "windowmove",
            str(x),
            str(y),
            "windowactivate",
            "--sync",
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def resolve_pdf(document):
    """Resolve a standalone or included TeX file to its generated PDF."""
    path = Path(document).resolve()
    if path.suffix.lower() == ".pdf" and path.is_file():
        return path

    sibling = path.with_suffix(".pdf")
    if sibling.is_file():
        return sibling

    if path.suffix.lower() == ".tex" and path.is_file():
        try:
            header = "\n".join(path.read_text(errors="replace").splitlines()[:50])
            match = re.search(
                r"^\s*%\s*!TeX\s+root\s*=\s*(.+?)\s*$",
                header,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if match:
                root_tex = (path.parent / match.group(1).strip()).resolve()
                root_pdf = root_tex.with_suffix(".pdf")
                if root_pdf.is_file():
                    return root_pdf
        except OSError:
            pass

    for directory in (path.parent, *path.parents):
        main_pdf = directory / "main.pdf"
        if main_pdf.is_file():
            return main_pdf

        candidates = [
            pdf
            for pdf in directory.glob("*.pdf")
            if pdf.with_suffix(".synctex.gz").is_file()
        ]
        if candidates:
            return max(candidates, key=lambda pdf: pdf.stat().st_mtime)

    raise FileNotFoundError(f"No generated PDF found for {path}")


class InverseSearchListener:
    def __init__(self, uri, editor_command, loop, logger):
        self.uri = uri
        self.editor_command = editor_command
        self.loop = loop
        self.logger = logger
        self.bus = dbus.SessionBus()
        self.daemon = self.bus.get_object(EV_DAEMON_NAME, EV_DAEMON_PATH)
        self.window_handler = None

        self.bus.add_signal_receiver(
            self._document_loaded,
            signal_name="DocumentLoaded",
            dbus_interface=EV_WINDOW_IFACE,
            sender_keyword="sender",
        )
        self._find_document()

    def _find_document(self):
        self.daemon.FindDocument(
            self.uri,
            False,
            reply_handler=self._found_document,
            error_handler=lambda error: self.logger.error(
                "Could not query Evince: %s", error
            ),
            dbus_interface=EV_DAEMON_IFACE,
        )

    def _document_loaded(self, uri, **kwargs):
        if uri == self.uri and self.window_handler is None:
            self._found_document(kwargs["sender"])

    def _found_document(self, bus_name):
        if not bus_name:
            return

        application = self.bus.get_object(bus_name, EVINCE_PATH)
        application.GetWindowList(
            reply_handler=lambda windows: self._attach(bus_name, windows),
            error_handler=lambda error: self.logger.error(
                "Could not get the Evince window: %s", error
            ),
            dbus_interface=EVINCE_IFACE,
        )

    def _attach(self, bus_name, windows):
        if not windows or self.window_handler is not None:
            return

        window_object = self.bus.get_object(bus_name, windows[0])
        window = dbus.Interface(window_object, EV_WINDOW_IFACE)
        self.window_handler = window.connect_to_signal(
            "SyncSource", self._inverse_search
        )
        window.connect_to_signal("Closed", self.loop.quit)
        self.logger.info("Inverse search is ready. Ctrl+click text in Evince.")

    def _inverse_search(self, input_file, source_link, _timestamp):
        source_path = urllib.parse.unquote(str(input_file).removeprefix("file://"))
        line = int(source_link[0])
        command = self.editor_command.replace("%f", shlex.quote(source_path))
        command = command.replace("%l", str(line))
        self.logger.info("Opening %s:%s in Zed", source_path, line)
        completed = subprocess.run(command, shell=True, check=False)
        if completed.returncode:
            self.logger.error("Inverse-search command exited with %s", completed.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document")
    parser.add_argument("editor_command")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("evince-inverse-search")
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    try:
        pdf_path = str(resolve_pdf(args.document))
    except FileNotFoundError as error:
        parser.error(str(error))

    uri = file_uri(pdf_path)
    # WSLg converts Evince's stored zoom using its effective display DPI. On
    # this 5120x1440 display at 125% scale, 1.87 renders as a visible 70.1%.
    # Set it before asking Evince to create the document window so a previous
    # fit-to-page value (about 20%) cannot become the new default.
    subprocess.run(
        ["gsettings", "set", "org.gnome.Evince.Default", "sizing-mode", "free"],
        check=False,
    )
    subprocess.run(
        ["gsettings", "set", "org.gnome.Evince.Default", "zoom", "1.87"],
        check=False,
    )
    bus = dbus.SessionBus()
    daemon = bus.get_object(EV_DAEMON_NAME, EV_DAEMON_PATH)
    already_open = daemon.FindDocument(uri, False, dbus_interface=EV_DAEMON_IFACE)

    loop = GLib.MainLoop()
    listener = InverseSearchListener(uri, args.editor_command, loop, logger)
    if not already_open:
        environment = os.environ.copy()
        environment.update({"GDK_BACKEND": "x11", "GDK_SCALE": "1"})
        subprocess.Popen(["evince", uri], env=environment)
    else:
        logger.info("Attaching inverse search to the existing Evince window.")
    configure_pdf_window(pdf_path, logger)

    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    # Keep the listener alive until the Evince window closes.
    _ = listener


if __name__ == "__main__":
    main()
