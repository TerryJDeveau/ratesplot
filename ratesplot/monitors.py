"""A window kept on its monitor: moved to the nearest corner if it passes an edge, then shrunk, keeping its shape (batch 39).

Terry, 2026-11-03, of the default size of his NG_analysis project's charts: as ratesplot's, "but shrink
any dimension (preserving aspect) that would blow past the monitor edge, after moving to the
optimum corner first. Probably should ask for this change in ratesplot too." The optimum corner
is the one needing the least move: the nearest to the window's middle. If the window fits as it
is placed, nothing moves.

``monitor_work_areas``, ``overlap``, ``gap`` and ``monitor_of`` began in this program's ``gui.py``
(batch 15), and NG_analysis copied them under these names; ``fitted`` and ``fit_window`` are
copied back from its ``ng_analysis/monitors.py`` at commit c1cb82b, word for word, so that the two
files can become a shared library's first piece. ``monitor_bounds`` is this program's alone so far.

No tkinter is imported here: ``fit_window`` is handed a window, so the web page and the harnesses
that never open one do not load it.
"""

from __future__ import annotations

import sys

Rect = tuple[int, int, int, int]  # left, top, right, bottom


def _monitor_rectangles(field: str) -> list[Rect]:
    """Each monitor's rectangle ``field`` of Windows' ``MONITORINFO`` (``rcWork``, ``rcMonitor``); see ``monitor_work_areas``."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    rectangles: list[Rect] = []
    user32 = ctypes.windll.user32

    def found(monitor, _dc, _rect, _data) -> int:
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rectangle = getattr(info, field)
            rectangles.append((rectangle.left, rectangle.top, rectangle.right, rectangle.bottom))
        return 1  # go on to the next monitor

    callback = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    try:
        user32.EnumDisplayMonitors(None, None, callback(found), 0)
    except (AttributeError, OSError):
        return []
    return rectangles


def monitor_work_areas() -> list[Rect]:
    """Return each monitor's work area (left, top, right, bottom, without the taskbar) in the window's coordinates.

    Windows only (``EnumDisplayMonitors``), and in the same pixels as Tk's
    geometry, the process being DPI-aware (``gui._enable_windows_dpi_awareness``).
    Empty elsewhere, or if the call fails.
    """
    return _monitor_rectangles("rcWork")


def monitor_bounds() -> list[Rect]:
    """Return each monitor's whole rectangle, the taskbar included, as ``monitor_work_areas`` does its work area.

    What tells one set of monitors from another (batch 39): a taskbar moved or set to
    hide itself changes the work areas, and the monitors are those they were.
    """
    return _monitor_rectangles("rcMonitor")


def overlap(a: Rect, b: Rect) -> int:
    """The area two rectangles share."""
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def gap(a: Rect, b: Rect) -> float:
    """How far apart two rectangles are (0 when they touch or overlap)."""
    across = max(a[0] - b[2], b[0] - a[2], 0)
    down = max(a[1] - b[3], b[1] - a[3], 0)
    return (across * across + down * down) ** 0.5


def monitor_of(rect: Rect, areas: list[Rect]) -> Rect:
    """The work area holding most of ``rect``, else the nearest one (as Windows' ``MonitorFromRect`` chooses)."""
    return max(areas, key=lambda area: (overlap(rect, area), -gap(rect, area)))


def fitted(content: tuple[int, int], chrome: tuple[int, int], place: tuple[int, int], area: Rect) -> tuple[float, tuple[int, int]]:
    """The factor a window's content must shrink by to stay inside ``area``, and where the window goes.

    ``content`` is what keeps its shape (a chart); ``chrome`` what the window adds around it (the
    frame, a toolbar), which doesn't shrink; ``place`` the window's outer left and top. A window
    inside ``area`` stays where it is. Otherwise it shrinks only if it can't fit in ``area`` at
    all, by one factor, so its shape is kept, and goes to the corner nearest the middle it then
    has where it stands: a window at a monitor's top left stays there however large it was.
    """
    width, height = content
    extra_w, extra_h = chrome
    x, y = place
    left, top, right, bottom = area
    if x >= left and y >= top and x + width + extra_w <= right and y + height + extra_h <= bottom:
        return 1.0, place
    scale = min(1.0, (right - left - extra_w) / width, (bottom - top - extra_h) / height)
    outer_w, outer_h = width * scale + extra_w, height * scale + extra_h
    middle_x, middle_y = x + outer_w / 2, y + outer_h / 2
    new_x = left if middle_x - left <= right - middle_x else right - outer_w
    new_y = top if middle_y - top <= bottom - middle_y else bottom - outer_h
    return scale, (round(new_x), round(new_y))


def fit_window(window, content=None) -> float:
    """Keep a Tk window on its monitor, where it now is: moved as ``fitted`` says; returns the factor its content must shrink by.

    ``content``: the widget that keeps its shape (a chart's canvas), or the window's whole inside.
    The caller shrinks it, since a chart must be drawn again for its size. Where the monitors
    aren't known (not Windows), nothing moves.
    """
    window.update()
    areas = monitor_work_areas()
    if not areas:
        return 1.0
    x, y = window.winfo_x(), window.winfo_y()
    border = window.winfo_rootx() - x
    title = window.winfo_rooty() - y
    outer_w = window.winfo_width() + 2 * border
    outer_h = window.winfo_height() + title + border
    inner = window if content is None else content
    width, height = inner.winfo_width(), inner.winfo_height()
    area = monitor_of((x, y, x + outer_w, y + outer_h), areas)
    scale, (new_x, new_y) = fitted((width, height), (outer_w - width, outer_h - height), (x, y), area)
    if (new_x, new_y) != (x, y):
        window.geometry(f"+{new_x}+{new_y}")
        window.update()  # before any resize, which would otherwise put it back where it was
    return scale
