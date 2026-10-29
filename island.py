#!/usr/bin/env python3
import base64
import ctypes
import math
import os
import random
import time
import datetime
import fcntl
import json
import re
import subprocess
import threading
import urllib.parse
import urllib.request

import cairo
import dbus
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo

DBusGMainLoop(set_as_default=True)

COMPACT_W = 190
COMPACT_H = 42
EXPANDED_W = 498
EXPANDED_H = 182
LYRICS_W = 414
LYRICS_H = 390
TOP_MARGIN = 4
ANIM_MS = 12
CLOSE_SECONDS = 0.17
CLOSE_FADE = 0.55
COMPACT_FADE_SECONDS = 0.09
SLEEP_AFTER = 15.0
SHELF_MAX = 60
SHELF_TARGET_URI = 101
SHELF_TARGET_TEXT = 102
WEATHER_TTL = 30 * 60
SLIDE_ORDER = ("media", "timer", "shelf", "weather")

_XLIB = None
_XDISPLAY = None


def x_button1_pressed():
    global _XLIB, _XDISPLAY
    try:
        if _XLIB is None:
            _XLIB = ctypes.CDLL("libX11.so.6")
            _XLIB.XOpenDisplay.restype = ctypes.c_void_p
            _XLIB.XOpenDisplay.argtypes = [ctypes.c_char_p]
            _XLIB.XDefaultRootWindow.restype = ctypes.c_ulong
            _XLIB.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            _XLIB.XQueryPointer.restype = ctypes.c_int
            _XLIB.XQueryPointer.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_uint),
            ]
            _XDISPLAY = _XLIB.XOpenDisplay(None)
        if not _XDISPLAY:
            return False
        rr = ctypes.c_ulong()
        cr = ctypes.c_ulong()
        rx = ctypes.c_int()
        ry = ctypes.c_int()
        wx = ctypes.c_int()
        wy = ctypes.c_int()
        mask = ctypes.c_uint()
        root = _XLIB.XDefaultRootWindow(_XDISPLAY)
        ok = _XLIB.XQueryPointer(
            _XDISPLAY,
            root,
            ctypes.byref(rr),
            ctypes.byref(cr),
            ctypes.byref(rx),
            ctypes.byref(ry),
            ctypes.byref(wx),
            ctypes.byref(wy),
            ctypes.byref(mask),
        )
        return bool(ok and (mask.value & (1 << 8)))
    except Exception:
        return False


DAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

WMO_LABELS = {
    0: "Cerah",
    1: "Cerah berawan",
    2: "Berawan",
    3: "Mendung",
    45: "Kabut",
    48: "Kabut beku",
    51: "Gerimis ringan",
    53: "Gerimis",
    55: "Gerimis lebat",
    56: "Gerimis beku",
    57: "Gerimis beku lebat",
    61: "Hujan ringan",
    63: "Hujan",
    65: "Hujan lebat",
    66: "Hujan beku",
    67: "Hujan beku lebat",
    71: "Salju ringan",
    73: "Salju",
    75: "Salju lebat",
    77: "Butir salju",
    80: "Hujan lokal",
    81: "Hujan lokal lebat",
    82: "Hujan lokal deras",
    85: "Hujan salju",
    86: "Hujan salju lebat",
    95: "Badai petir",
    96: "Badai petir hujan es",
    99: "Badai petir hujan es lebat",
}

WMO_ICONS = {
    0: "weather-clear-symbolic",
    1: "weather-few-clouds-symbolic",
    2: "weather-few-clouds-symbolic",
    3: "weather-overcast-symbolic",
    45: "weather-fog-symbolic",
    48: "weather-fog-symbolic",
    51: "weather-showers-scattered-symbolic",
    53: "weather-showers-scattered-symbolic",
    55: "weather-showers-symbolic",
    56: "weather-showers-symbolic",
    57: "weather-showers-symbolic",
    61: "weather-showers-symbolic",
    63: "weather-showers-symbolic",
    65: "weather-showers-symbolic",
    66: "weather-showers-symbolic",
    67: "weather-showers-symbolic",
    71: "weather-snow-symbolic",
    73: "weather-snow-symbolic",
    75: "weather-snow-symbolic",
    77: "weather-snow-symbolic",
    80: "weather-showers-symbolic",
    81: "weather-showers-symbolic",
    82: "weather-showers-symbolic",
    85: "weather-snow-symbolic",
    86: "weather-snow-symbolic",
    95: "weather-severe-alert-symbolic",
    96: "weather-severe-alert-symbolic",
    99: "weather-severe-alert-symbolic",
}

CSS = b"""
window, #root { background-color: transparent; }
label { color: #f5f5f7; font-family: "Ubuntu", "Cantarell", "DejaVu Sans", sans-serif; }
.clock { font-size: 14px; font-weight: 700; letter-spacing: 0.3px; }
.batt { font-size: 11px; color: rgba(255,255,255,0.6); }
.batt.charging { color: #34d399; }
.batt.low { color: #f87171; }
.meta { font-size: 11px; color: rgba(255,255,255,0.55); }
.title { font-size: 14px; font-weight: 600; }
.artist { font-size: 10px; color: rgba(255,255,255,0.6); }
.time { font-size: 9px; color: rgba(255,255,255,0.55); }
.lyric { font-size: 12px; color: #e6e6ec; }
.lyric-title { font-size: 14px; font-weight: 600; }
.lyric-sub { font-size: 11px; color: rgba(255,255,255,0.55); }
.preview-current { font-size: 15px; font-weight: 700; color: #ffffff; }
.preview-next { font-size: 13px; color: #ff6b81; }
.lyrics-line { font-size: 14px; color: #8f8f99; }
.lyrics-line.active { font-size: 18px; color: #ffffff; font-weight: 700; }
.lyrics-line.edge { color: rgba(255,255,255,0.3); }
.timer-heading { font-size: 15px; font-weight: 700; }
.shelf-heading { font-size: 15px; font-weight: 800; }
.timer-stamp { font-size: 10px; color: rgba(255,255,255,0.5); }
.timer-clock { font-size: 34px; font-weight: 700; letter-spacing: 0.8px; }
.timer-label { font-size: 11px; color: rgba(255,255,255,0.55); }
.timer-chip { font-size: 10px; font-weight: 600; background-color: rgba(255,255,255,0.08); color: #f5f5f7; padding: 5px 11px; border-radius: 999px; }
.timer-chip:hover { background-color: rgba(255,255,255,0.16); }
.timer-chip.active { background-color: #ff5b6e; color: #ffffff; }
.timer-play { background-color: #ff5b6e; border-radius: 999px; min-width: 52px; min-height: 30px; padding: 3px 14px; color: #ffffff; }
.timer-play:hover { background-color: #ff7283; }
.timer-reset { color: rgba(255,255,255,0.55); border-radius: 999px; min-width: 22px; min-height: 22px; padding: 2px; }
.timer-reset:hover { background-color: rgba(255,255,255,0.12); color: #ffffff; }
.nav { color: rgba(255,255,255,0.45); border-radius: 999px; min-width: 20px; min-height: 20px; padding: 1px; }
.nav:hover { background-color: rgba(255,255,255,0.12); color: #ffffff; }
button { background-image: none; background-color: transparent; border: none; box-shadow: none; padding: 3px 9px; border-radius: 10px; min-height: 26px; min-width: 30px; }
button:hover { background-color: rgba(255,255,255,0.12); }
button:active { background-color: rgba(255,255,255,0.2); }
button:disabled { opacity: 0.3; }
progressbar.track trough { min-height: 3px; border-radius: 999px; background-color: rgba(255,255,255,0.16); border: none; }
progressbar.track progress { min-height: 3px; border-radius: 999px; background-color: #f5f5f7; border: none; }
progressbar.track text { color: transparent; font-size: 0; }
.shelf-hint { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.85); }
.shelf-clear { font-size: 10px; font-weight: 600; color: rgba(255,255,255,0.6); background-color: rgba(255,255,255,0.1); border-radius: 999px; padding: 2px 10px; min-height: 18px; min-width: 0; }
.shelf-clear label { color: rgba(255,255,255,0.6); }
.shelf-clear:hover { background-color: rgba(248,113,113,0.16); color: #f87171; }
.shelf-clear:hover label { color: #f87171; }
.shelf-card { background-color: rgba(255,255,255,0); border-radius: 12px; }
.shelf-card:hover { background-color: rgba(255,255,255,0.07); }
.shelf-card-name { font-size: 10px; font-weight: 700; color: #ffffff; }
.shelf-card-name.missing { color: #f87171; }
.shelf-card-size { font-size: 9px; color: rgba(255,255,255,0.5); }
.shelf-remove { background-color: rgba(0,0,0,0.55); color: #ffffff; border-radius: 999px; min-width: 17px; min-height: 17px; padding: 0; font-size: 12px; font-weight: 700; }
.shelf-remove:hover { background-color: rgba(235,60,60,0.9); }
.weather-heading { font-size: 15px; font-weight: 700; }
.weather-temp { font-size: 36px; font-weight: 800; letter-spacing: 0.4px; }
.weather-cond { font-size: 12px; color: rgba(255,255,255,0.78); }
.weather-detail { font-size: 10px; color: rgba(255,255,255,0.55); }
.weather-day { font-size: 10px; font-weight: 600; color: rgba(255,255,255,0.6); }
.weather-range { font-size: 11px; font-weight: 600; color: #f5f5f7; }
.navbox { background-color: rgba(0,0,0,0); }
.shelf-dest { background-color: rgba(0,0,0,0); }
.shelf-dest.drag-hover { background-color: rgba(255,255,255,0.12); border-radius: 21px; }
menu { background-color: rgba(28,28,32,0.97); border-radius: 8px; }
menu > menuitem { min-height: 22px; color: #f5f5f7; font-size: 11px; border-radius: 6px; padding: 3px 12px; }
menu > menuitem:hover { background-color: rgba(255,255,255,0.12); }
"""


def rounded_path(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def fmt_us(us):
    seconds = int(us // 1000000)
    return "%d:%02d" % (seconds // 60, seconds % 60)


def fmt_clock(us):
    seconds = max(0, int(us // 1000000))
    return "%02d:%02d" % (seconds // 60, seconds % 60)


class AlbumArt(Gtk.DrawingArea):
    def __init__(self, size):
        Gtk.DrawingArea.__init__(self)
        self.pixbuf = None
        self.set_size_request(size, size)
        self.connect("draw", self.on_draw)

    def set_pixbuf(self, pixbuf):
        self.pixbuf = pixbuf
        self.queue_draw()

    def on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        radius = 12
        cr.save()
        rounded_path(cr, 0, 0, w, h, radius)
        cr.clip()
        if self.pixbuf is not None:
            pw, ph = self.pixbuf.get_width(), self.pixbuf.get_height()
            if pw > 0 and ph > 0:
                scale = max(w / pw, h / ph)
                sw = max(1, int(round(pw * scale)))
                sh = max(1, int(round(ph * scale)))
                scaled = self.pixbuf.scale_simple(
                    sw, sh, GdkPixbuf.InterpType.BILINEAR
                )
                if scaled is not None:
                    Gdk.cairo_set_source_pixbuf(
                        cr, scaled, (w - sw) / 2, (h - sh) / 2
                    )
                    cr.paint()
        else:
            gradient = cairo.LinearGradient(0, 0, w, h)
            gradient.add_color_stop_rgb(0, 0.16, 0.16, 0.18)
            gradient.add_color_stop_rgb(1, 0.07, 0.07, 0.08)
            cr.set_source(gradient)
            cr.paint()
            layout = PangoCairo.create_layout(cr)
            layout.set_text("\u266b", -1)
            layout.set_font_description(Pango.FontDescription("Ubuntu 24"))
            tw, th = layout.get_pixel_size()
            cr.move_to((w - tw) / 2, (h - th) / 2 - 1)
            cr.set_source_rgba(1, 1, 1, 0.32)
            PangoCairo.show_layout(cr, layout)
        cr.restore()
        rounded_path(cr, 0.5, 0.5, w - 1, h - 1, radius)
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(1)
        cr.stroke()
        return False


class Eyes(Gtk.DrawingArea):
    SCALE = 0.88

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.set_size_request(64, 24)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.target_x = 0.0
        self.target_y = 0.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.blink_start = 0.0
        self.next_blink = time.monotonic() + random.uniform(3.0, 6.0)
        self.sleeping = False
        self.sleep_amount = 0.0
        self.connect("draw", self.on_draw)

    def set_sleeping(self, sleeping):
        if sleeping == self.sleeping:
            return
        self.sleeping = sleeping
        self.queue_draw()

    def look_at(self, dx, dy):
        distance = math.hypot(dx, dy)
        if distance < 6:
            self.target_x = 0.0
            self.target_y = 0.0
            return
        scale = min(1.0, distance / 180.0)
        self.target_x = dx / distance * 2.0 * scale
        self.target_y = dy / distance * 1.5 * scale

    def step(self):
        old_x = self.offset_x
        old_y = self.offset_y
        self.offset_x += (self.target_x - self.offset_x) * 0.3
        self.offset_y += (self.target_y - self.offset_y) * 0.3
        sleep_target = 1.0 if self.sleeping else 0.0
        sleep_old = self.sleep_amount
        self.sleep_amount += (sleep_target - self.sleep_amount) * 0.18
        if abs(sleep_target - self.sleep_amount) < 0.003:
            self.sleep_amount = sleep_target
        now = time.monotonic()
        if now >= self.next_blink:
            self.blink_start = now
            self.next_blink = now + random.uniform(3.0, 7.0)
        moving = abs(self.offset_x - old_x) > 0.005 or abs(self.offset_y - old_y) > 0.005
        settling = abs(self.sleep_amount - sleep_old) > 0.001
        if moving or settling or self.sleeping or now - self.blink_start < 0.25:
            self.queue_draw()

    def lid_scale(self, now):
        elapsed = now - self.blink_start
        if 0.0 <= elapsed <= 0.16:
            return 1.0 - 0.94 * math.sin(math.pi * elapsed / 0.16)
        return 1.0

    def draw_z(self, cr, x, y, size, alpha):
        cr.set_line_width(max(0.8, size * 0.16))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgba(0.96, 0.96, 0.98, alpha)
        cr.move_to(x, y)
        cr.line_to(x + size, y)
        cr.line_to(x, y + size)
        cr.line_to(x + size, y + size)
        cr.stroke()

    def eye_path(self, cr, side):
        cr.move_to(side * 11.7, 1.2)
        cr.curve_to(side * 8.0, -2.8, side * 0.8, -7.2, side * -6.0, -7.6)
        cr.curve_to(side * -9.2, -7.8, side * -11.6, -6.0, side * -11.8, -3.0)
        cr.curve_to(side * -11.2, 2.9, side * -7.4, 9.0, side * -1.5, 9.6)
        cr.curve_to(side * 4.2, 9.9, side * 9.8, 5.9, side * 11.7, 1.2)
        cr.close_path()

    def draw_closed_eye(self, cr, cx, cy, side):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(self.SCALE, self.SCALE)
        cr.move_to(side * -9.2, -0.8)
        cr.curve_to(side * -3.0, -0.3, side * 4.0, 1.0, side * 8.8, 2.2)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(0.96, 0.96, 0.98, 0.86)
        cr.stroke()
        cr.restore()

    def draw_eye(self, cr, cx, cy, side, lid):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(self.SCALE, self.SCALE * lid)
        self.eye_path(cr, side)
        gradient = cairo.LinearGradient(0, -8.0, 0, 10.0)
        gradient.add_color_stop_rgba(0.0, 0.46, 0.47, 0.52, 1.0)
        gradient.add_color_stop_rgba(0.3, 0.83, 0.84, 0.88, 1.0)
        gradient.add_color_stop_rgba(0.6, 1.0, 1.0, 1.0, 1.0)
        gradient.add_color_stop_rgba(1.0, 0.6, 0.62, 0.67, 1.0)
        cr.set_source(gradient)
        cr.fill()
        px = side * -1.0 + self.offset_x
        py = -2.0 + self.offset_y
        cr.arc(px, py, 5.6, 0, 2 * math.pi)
        cr.set_source_rgba(0.008, 0.008, 0.012, 1.0)
        cr.fill()
        cr.arc(px - 1.9, py - 2.0, 0.84, 0, 2 * math.pi)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.97)
        cr.fill()
        cr.arc(px + 1.7, py + 2.2, 0.34, 0, 2 * math.pi)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.28)
        cr.fill()
        cr.move_to(side * 11.7, 1.2)
        cr.curve_to(side * 8.0, -2.8, side * 0.8, -7.2, side * -6.0, -7.6)
        cr.set_line_width(0.9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.55)
        cr.stroke()
        cr.restore()

    def on_draw(self, widget, cr):
        now = time.monotonic()
        lid = self.lid_scale(now) * (1.0 - 0.94 * self.sleep_amount)
        for cx, side in ((18.4, 1.0), (45.6, -1.0)):
            cy = 12.0
            if lid < 0.22:
                self.draw_closed_eye(cr, cx, cy, side)
                continue
            self.draw_eye(cr, cx, cy, side, lid)
        if self.sleep_amount > 0.35:
            fade = min(1.0, (self.sleep_amount - 0.35) / 0.65)
            bob = math.sin(now * 2.2) * 0.55
            pulse = 0.72 + 0.2 * math.sin(now * 2.0 + 0.6)
            self.draw_z(cr, 56.2, 1.0 + bob, 5.8, fade * pulse)
        return False


class Equalizer(Gtk.DrawingArea):
    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.active = False
        self.set_size_request(22, 16)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self.on_draw)
        GLib.timeout_add(80, self.step)

    def set_active(self, active):
        self.active = active
        self.queue_draw()

    def step(self):
        if self.active and self.get_visible():
            self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        if not self.active:
            return False
        alloc = widget.get_allocation()
        height = alloc.height
        now = time.monotonic()
        bar_width = 3.0
        gap = 3.0
        total = 4 * bar_width + 3 * gap
        x = (alloc.width - total) / 2
        cr.set_source_rgba(0.204, 0.827, 0.6, 0.95)
        for i in range(4):
            level = 0.28 + 0.72 * abs(
                math.sin(now * (2.4 + 0.55 * i) + 1.3 * i)
            )
            bar_height = max(3.0, height * level)
            rounded_path(cr, x, height - bar_height, bar_width, bar_height, 1.5)
            cr.fill()
            x += bar_width + gap
        return False


class PageDots(Gtk.DrawingArea):
    def __init__(self, count):
        Gtk.DrawingArea.__init__(self)
        self.count = count
        self.index = 0
        self.set_size_request(count * 10 + 6, 8)
        self.set_valign(Gtk.Align.END)
        self.set_no_show_all(True)
        self.connect("draw", self.on_draw)

    def set_index(self, index):
        if index == self.index:
            return
        self.index = index
        self.queue_draw()

    def on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        spacing = 9.0
        total = spacing * (self.count - 1)
        x = (alloc.width - total) / 2
        y = alloc.height / 2
        for i in range(self.count):
            if i == self.index:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.92)
            else:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.26)
            cr.arc(x, y, 1.8, 0, 2 * math.pi)
            cr.fill()
            x += spacing
        return False


class TimerRing(Gtk.DrawingArea):
    def __init__(self, size):
        Gtk.DrawingArea.__init__(self)
        self.progress = 1.0
        self.running = False
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self.on_draw)

    def set_progress(self, progress):
        progress = max(0.0, min(1.0, progress))
        if abs(progress - self.progress) < 0.0005:
            return
        self.progress = progress
        self.queue_draw()

    def set_running(self, running):
        if running == self.running:
            return
        self.running = running
        self.queue_draw()

    def on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        cx = alloc.width / 2
        cy = alloc.height / 2
        radius = min(alloc.width, alloc.height) / 2 - 5
        start = -math.pi / 2
        end = start + 2 * math.pi * self.progress
        cr.set_line_width(4.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.08)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        if self.progress > 0:
            if self.running:
                cr.set_line_width(9.0)
                cr.set_source_rgba(1.0, 0.28, 0.38, 0.13)
                cr.arc(cx, cy, radius, start, end)
                cr.stroke()
            gradient = cairo.LinearGradient(0, cy - radius, 0, cy + radius)
            gradient.add_color_stop_rgba(0.0, 1.0, 0.55, 0.62, 0.98)
            gradient.add_color_stop_rgba(1.0, 1.0, 0.23, 0.35, 0.98)
            cr.set_line_width(4.5)
            cr.set_source(gradient)
            cr.arc(cx, cy, radius, start, end)
            cr.stroke()
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.94)
        cr.arc(cx, cy + 1.5, 8.0, 0, 2 * math.pi)
        cr.stroke()
        cr.move_to(cx, cy - 8.0)
        cr.line_to(cx, cy - 11.0)
        cr.stroke()
        cr.move_to(cx - 2.2, cy - 10.6)
        cr.line_to(cx + 2.2, cy - 10.6)
        cr.stroke()
        cr.move_to(cx, cy + 1.5)
        cr.line_to(cx, cy - 3.0)
        cr.move_to(cx, cy + 1.5)
        cr.line_to(cx + 3.4, cy + 3.0)
        cr.stroke()
        return False


class ShelfZone(Gtk.DrawingArea):
    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.hover = False
        self.show_border = True
        self.set_size_request(-1, 96)
        self.connect("draw", self.on_draw)

    def on_draw(self, widget, cr):
        if not (self.show_border or self.hover):
            return False
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.25)
        rounded_path(cr, 29.5, 0.5, w - 59, h - 1, 12)
        cr.fill()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.5 if self.hover else 0.18)
        cr.set_line_width(1.2)
        cr.set_dash([5.0, 4.0])
        rounded_path(cr, 29.5, 0.5, w - 59, h - 1, 12)
        cr.stroke()
        cr.set_dash([])
        return False


class Thumb(Gtk.DrawingArea):
    def __init__(self, path, width=64, height=46):
        Gtk.DrawingArea.__init__(self)
        self.set_size_request(width, height)
        self.pixbuf = None
        self.icon = None
        exists = os.path.exists(path)
        ext = os.path.splitext(path)[1].lower()
        if exists and not os.path.isdir(path) and ext in IMAGE_EXTS:
            try:
                self.pixbuf = self.load_cover(path, width, height)
            except Exception:
                self.pixbuf = None
        if self.pixbuf is None:
            if not exists:
                icon_name = "dialog-warning"
            elif ext in IMAGE_EXTS:
                icon_name = "image-x-generic"
            else:
                icon_name = shelf_color_icon_name(path)
            theme = Gtk.IconTheme.get_default()
            try:
                self.icon = theme.load_icon(
                    icon_name,
                    min(width, height) - 10,
                    Gtk.IconLookupFlags.FORCE_SIZE,
                )
            except Exception:
                try:
                    self.icon = theme.load_icon(
                        "text-x-generic",
                        min(width, height) - 10,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
                except Exception:
                    self.icon = None
        self.connect("draw", self.on_draw)

    @staticmethod
    def load_cover(path, width, height):
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            path, width * 2, height * 2, True
        )
        pw, ph = pb.get_width(), pb.get_height()
        scale = max(width / float(pw), height / float(ph))
        nw = max(width, int(pw * scale + 0.5))
        nh = max(height, int(ph * scale + 0.5))
        pb = pb.scale_simple(nw, nh, GdkPixbuf.InterpType.BILINEAR)
        x = (nw - width) // 2
        y = (nh - height) // 2
        return pb.new_subpixbuf(x, y, width, height)

    def on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        rounded_path(cr, 0, 0, w, h, 8)
        cr.clip()
        if self.pixbuf is not None:
            Gdk.cairo_set_source_pixbuf(
                cr,
                self.pixbuf,
                (w - self.pixbuf.get_width()) / 2,
                (h - self.pixbuf.get_height()) / 2,
            )
            cr.paint()
        else:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.07)
            cr.paint()
            if self.icon is not None:
                Gdk.cairo_set_source_pixbuf(
                    cr,
                    self.icon,
                    (w - self.icon.get_width()) / 2,
                    (h - self.icon.get_height()) / 2,
                )
                cr.paint()
        return False


LRC_TAG = re.compile(r"\[(\d+):(\d+)(?:[.:](\d+))?\]")


def parse_lrc(text):
    offset = 0.0
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        offset_match = re.match(r"\[offset:([+-]?\d+)\]", line, re.IGNORECASE)
        if offset_match:
            offset = int(offset_match.group(1)) / 1000.0
            continue
        stamps = list(LRC_TAG.finditer(line))
        if not stamps:
            continue
        content = line[stamps[-1].end():].strip()
        for stamp in stamps:
            fraction = 0.0
            if stamp.group(3):
                fraction = int(stamp.group(3)) / (10 ** len(stamp.group(3)))
            seconds = int(stamp.group(1)) * 60 + int(stamp.group(2)) + fraction + offset
            lines.append((seconds, content))
    lines.sort(key=lambda item: item[0])
    return lines


AUDIO_EXTS = (".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".wma", ".mka")
NOISE_RE = re.compile(
    r"[\(\[]\s*(?:"
    r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video)?|"
    r"lyrics?|lyric\s*video|audio|video|visuali[sz]er|"
    r"hd|hq|4k|8k|explicit|clean|remaster(?:ed)?(?:\s*\d{4})?|"
    r"color\s*coded(?:\s*lyrics)?|with\s*lyrics"
    r")\s*[\)\]]",
    re.IGNORECASE,
)
TRAILING_NOISE_RE = re.compile(
    r"\s+(?:official\s*(?:music\s*)?(?:video|audio)|lyrics?|lyric\s*video|audio|video|visuali[sz]er)\s*$",
    re.IGNORECASE,
)


def strip_audio_ext(name):
    base, ext = os.path.splitext(name)
    return base if ext.lower() in AUDIO_EXTS else name


def clean_track_text(text):
    text = strip_audio_ext(text)
    text = re.sub(r"^\s*\d{1,3}\s*[.\-–—)]\s*", "", text)
    text = text.replace("_", " ")
    text = NOISE_RE.sub(" ", text)
    text = TRAILING_NOISE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -–—")


def split_artist_title(text):
    cleaned = clean_track_text(text)
    for sep in (" - ", " – ", " — "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            left = left.strip()
            right = right.strip()
            if left and right:
                return right, left
    return cleaned, ""


def filename_from_url(url):
    if not url.startswith("file://"):
        return ""
    try:
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    except (ValueError, TypeError):
        return ""
    return os.path.basename(path)


def uri_to_path(uri):
    uri = (uri or "").strip()
    if not uri.startswith("file:"):
        return None
    try:
        path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
    except (ValueError, TypeError):
        return None
    return path or None


def path_to_uri(path):
    try:
        return GLib.filename_to_uri(path)
    except (GLib.Error, TypeError):
        return "file://" + urllib.parse.quote(path)


def fmt_size(size):
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d B" % int(value)
            text = "%.1f %s" % (value, unit)
            return text.replace(".0 ", " ")
        value /= 1024.0
    return ""


SHELF_ICON_MAP = (
    (".mp3|.m4a|.flac|.wav|.ogg|.opus|.aac|.wma|.mka", "audio-x-generic-symbolic"),
    (".png|.jpg|.jpeg|.gif|.webp|.svg|.bmp|.ico|.tiff", "image-x-generic-symbolic"),
    (".mp4|.mkv|.avi|.mov|.webm|.wmv|.m4v|.ts", "video-x-generic-symbolic"),
    (".zip|.tar|.gz|.xz|.bz2|.7z|.rar|.tgz", "package-x-generic-symbolic"),
    (".pdf|.doc|.docx|.txt|.md|.odt|.odp|.ods", "text-x-generic-symbolic"),
    (".py|.js|.c|.cpp|.h|.sh|.json|.yml|.yaml|.html|.css", "text-x-generic-symbolic"),
)


def shelf_icon_name(path):
    if os.path.isdir(path):
        return "folder-symbolic"
    ext = os.path.splitext(path)[1].lower()
    for ext_list, icon in SHELF_ICON_MAP:
        if ext in ext_list.split("|"):
            return icon
    return "text-x-generic-symbolic"


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".svg")

SHELF_COLOR_ICONS = (
    (".mp3|.m4a|.flac|.wav|.ogg|.opus|.aac|.wma|.mka", "audio-x-generic"),
    (".mp4|.mkv|.avi|.mov|.webm|.wmv|.m4v|.ts", "video-x-generic"),
    (".zip|.tar|.gz|.xz|.bz2|.7z|.rar|.tgz", "package-x-generic"),
    (".pdf", "application-pdf"),
    (".doc|.docx|.txt|.md|.odt|.odp|.ods", "text-x-generic"),
    (".py|.js|.c|.cpp|.h|.sh|.json|.yml|.yaml|.html|.css", "text-x-generic"),
)


def shelf_color_icon_name(path):
    if os.path.isdir(path):
        return "folder"
    ext = os.path.splitext(path)[1].lower()
    for ext_list, icon in SHELF_COLOR_ICONS:
        if ext in ext_list.split("|"):
            return icon
    return "text-x-generic"


def first_icon(*names):
    theme = Gtk.IconTheme.get_default()
    for name in names:
        if name and theme.has_icon(name):
            return name
    return "text-x-generic-symbolic"


def find_battery():
    root = "/sys/class/power_supply"
    try:
        for name in sorted(os.listdir(root)):
            if name.startswith("BAT") and os.path.exists(os.path.join(root, name, "capacity")):
                return os.path.join(root, name)
    except OSError:
        pass
    return None


def read_battery(path):
    if not path:
        return None
    try:
        with open(os.path.join(path, "capacity")) as f:
            capacity = int(f.read().strip())
        with open(os.path.join(path, "status")) as f:
            status = f.read().strip()
        return capacity, status
    except (OSError, ValueError):
        return None


class Island(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Zenon")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_app_paintable(True)
        self.set_opacity(0.0)
        self.stick()

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.expanded = False
        self.current_w = COMPACT_W
        self.current_h = COMPACT_H
        self.anim_source = None
        self.anim_from = (COMPACT_W, COMPACT_H)
        self.anim_to = (COMPACT_W, COMPACT_H)
        self.anim_t = 0.0
        self.anim_dir = 0

        self.closing = False
        self.close_source = None
        self.close_phase = 0
        self.close_start = 0.0
        self.close_opacity = 1.0
        self.close_fade = 1.0
        self.close_target_xy = None
        self.close_wait_count = 0
        self.compact_fade_start = 0.0
        self.shape_active = False
        self.card_x = 0.0
        self.card_y = 0.0
        self.card_w = float(COMPACT_W)
        self.card_h = float(COMPACT_H)

        self.player_bus_name = None
        self.player_obj = None
        self.player_props = None
        self.player_iface = None
        self.player_status = "Stopped"
        self.player_identity = ""
        self.track_title = ""
        self.track_artist = ""
        self.track_length = 0
        self.identity_cache = {}
        self.refresh_pending = False
        self.batt_path = find_battery()
        self.tick_count = 0
        self.track_album = ""
        self.track_url = ""
        self.position_us = 0
        self.art_url = None
        self.art_tint = None
        self.art_cache = {}
        self.art_token = 0
        self.lyrics = []
        self.lyrics_cache = {}
        self.lyrics_missing = False
        self.lyrics_pending = False
        self.lyric_token = 0
        self.lyric_index = -1
        self.current_track_key = None
        self.lyrics_mode = False
        self.current_slide = "media"
        self.shelf_items = []
        self.press_pos = None
        self.drag_active = False
        self.drag_pill = False
        self._drag_reset_id = None
        self._chip_drag_path = None
        self._chip_drag_failed = False
        self._chip_drag_self_drop = False
        self.weather_data = None
        self.weather_config = None
        self.weather_fetching = False
        self.weather_next_try = 0.0
        self.timer_duration = 25 * 60
        self.timer_remaining = float(self.timer_duration)
        self.timer_running = False
        self.timer_end = None
        self.timer_mode = "focus"
        self.timer_icon_state = None
        self.last_pointer = None
        self.last_move = time.monotonic()

        self.build_ui()
        self.connect("draw", self.on_draw)
        self.connect("configure-event", self.on_configure)
        self.connect("map-event", self.on_map)
        self.connect("button-press-event", self.on_click)
        self.connect("destroy", lambda *_: Gtk.main_quit())

        try:
            self.bus = dbus.SessionBus()
        except dbus.DBusException:
            self.bus = None
        if self.bus:
            for rule in (
                dict(
                    signal_name="PropertiesChanged",
                    dbus_interface="org.freedesktop.DBus.Properties",
                    path="/org/mpris/MediaPlayer2",
                ),
                dict(
                    signal_name="NameOwnerChanged",
                    dbus_interface="org.freedesktop.DBus",
                    bus_name="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                ),
            ):
                try:
                    self.bus.add_signal_receiver(self.queue_refresh, **rule)
                except dbus.DBusException:
                    pass

        self.show_all()
        self.slides_wrap.hide()
        self.lyrics_view.hide()
        self.update_top_meta()
        self.update_timer_ui()
        self.apply_geometry(COMPACT_W, COMPACT_H)
        GLib.timeout_add(60, self.first_place)
        GLib.timeout_add(90, self.reveal_window)
        GLib.timeout_add(300, self.resync_shape)
        GLib.timeout_add(20, self.watch_pointer)
        GLib.timeout_add(40, self.animate_eyes)
        GLib.timeout_add(1000, self.tick)
        GLib.timeout_add(200, self.refresh_media)

    def build_ui(self):
        self.root = Gtk.EventBox()
        self.root.set_name("root")
        self.root.set_visible_window(False)
        self.add(self.root)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_valign(Gtk.Align.START)
        self.root.add(outer)

        self.compact = Gtk.Overlay()
        self.compact.set_halign(Gtk.Align.CENTER)
        compact_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        compact_row.set_margin_start(16)
        compact_row.set_margin_end(16)
        compact_row.set_valign(Gtk.Align.CENTER)

        self.clock = Gtk.Label(label="--:--")
        self.clock.get_style_context().add_class("clock")

        self.equalizer = Equalizer()
        self.equalizer.hide()

        self.date_label = Gtk.Label(label="")
        self.date_label.get_style_context().add_class("meta")
        self.date_label.hide()

        compact_spacer = Gtk.Box()
        compact_spacer.set_hexpand(True)

        self.source_label = Gtk.Label(label="")
        self.source_label.get_style_context().add_class("meta")
        self.source_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.source_label.hide()

        self.batt = Gtk.Label(label="")
        self.batt.get_style_context().add_class("batt")

        compact_row.pack_start(self.clock, False, False, 0)
        compact_row.pack_start(self.equalizer, False, False, 0)
        compact_row.pack_start(self.date_label, False, False, 0)
        compact_row.pack_start(compact_spacer, True, True, 0)
        compact_row.pack_start(self.source_label, False, False, 0)
        compact_row.pack_start(self.batt, False, False, 0)
        compact_inner = Gtk.Overlay()
        compact_inner.add(compact_row)
        self.compact_drop = Gtk.EventBox()
        self.compact_drop.set_visible_window(True)
        self.compact_drop.get_style_context().add_class("shelf-dest")
        self.compact_drop.add(compact_inner)
        self.compact.add(self.compact_drop)
        self.eyes = Eyes()
        compact_inner.add_overlay(self.eyes)
        outer.pack_start(self.compact, False, False, 0)

        compact_targets = [
            Gtk.TargetEntry.new("text/uri-list", 0, SHELF_TARGET_URI),
            Gtk.TargetEntry.new("text/plain", 0, SHELF_TARGET_TEXT),
        ]
        self.drag_dest_set(
            Gtk.DestDefaults.MOTION | Gtk.DestDefaults.DROP,
            compact_targets,
            Gdk.DragAction.COPY | Gdk.DragAction.MOVE,
        )
        self.connect("drag-motion", self.on_window_drag_motion)
        self.connect("drag-leave", self.on_window_drag_leave)
        self.connect("drag-data-received", self.on_shelf_drop)

        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.detail.set_margin_start(20)
        self.detail.set_margin_end(20)
        self.detail.set_margin_bottom(12)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        content.set_margin_top(4)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_size_request(230, -1)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.art_expanded = AlbumArt(64)
        top.pack_start(self.art_expanded, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_valign(Gtk.Align.CENTER)
        self.title_label = Gtk.Label(label="Tidak ada media")
        self.title_label.get_style_context().add_class("title")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(20)
        self.artist_label = Gtk.Label(label="Spotify, VLC, Rhythmbox")
        self.artist_label.get_style_context().add_class("artist")
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.set_max_width_chars(24)
        info.pack_start(self.title_label, False, False, 0)
        info.pack_start(self.artist_label, False, False, 0)
        top.pack_start(info, True, True, 0)

        self.info_event = Gtk.EventBox()
        self.info_event.set_visible_window(False)
        self.info_event.set_tooltip_text("Klik untuk mode lirik")
        self.info_event.connect("button-press-event", self.on_info_click)
        self.info_event.connect("realize", self.on_info_realize)
        self.info_event.add(top)
        left.pack_start(self.info_event, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        self.elapsed_label = Gtk.Label(label="")
        self.elapsed_label.get_style_context().add_class("time")
        self.elapsed_label.set_xalign(0)
        self.elapsed_label.set_width_chars(5)
        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("track")
        self.progress.set_hexpand(True)
        self.progress.set_valign(Gtk.Align.CENTER)
        self.remaining_label = Gtk.Label(label="")
        self.remaining_label.get_style_context().add_class("time")
        self.remaining_label.set_xalign(1)
        self.remaining_label.set_width_chars(6)
        row.pack_start(self.elapsed_label, False, False, 0)
        row.pack_start(self.progress, True, True, 0)
        row.pack_start(self.remaining_label, False, False, 0)
        left.pack_start(row, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_margin_top(2)
        self.lyrics_button = self.make_button("format-justify-left-symbolic")
        self.lyrics_button.set_tooltip_text("Mode lirik")
        self.prev_button = self.make_button("media-skip-backward-symbolic")
        self.play_button = self.make_button("media-playback-start-symbolic")
        self.next_button = self.make_button("media-skip-forward-symbolic")
        self.lyrics_button.connect("clicked", lambda *_: self.open_lyrics_mode())
        self.prev_button.connect("clicked", lambda *_: self.media_command("Previous"))
        self.play_button.connect("clicked", lambda *_: self.media_command("PlayPause"))
        self.next_button.connect("clicked", lambda *_: self.media_command("Next"))
        controls.pack_start(self.lyrics_button, False, False, 0)
        controls.pack_start(self.prev_button, False, False, 0)
        controls.pack_start(self.play_button, False, False, 0)
        controls.pack_start(self.next_button, False, False, 0)
        left.pack_start(controls, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_margin_top(6)
        right.set_halign(Gtk.Align.FILL)
        right.set_valign(Gtk.Align.START)
        self.preview_current = Gtk.Label(label="")
        self.preview_current.get_style_context().add_class("preview-current")
        self.preview_current.set_halign(Gtk.Align.FILL)
        self.preview_current.set_xalign(0)
        self.preview_current.set_justify(Gtk.Justification.LEFT)
        self.preview_current.set_line_wrap(True)
        self.preview_current.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.preview_current.set_max_width_chars(22)
        self.preview_current.set_lines(2)
        self.preview_next = Gtk.Label(label="")
        self.preview_next.get_style_context().add_class("preview-next")
        self.preview_next.set_halign(Gtk.Align.FILL)
        self.preview_next.set_xalign(0)
        self.preview_next.set_justify(Gtk.Justification.LEFT)
        self.preview_next.set_line_wrap(True)
        self.preview_next.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.preview_next.set_max_width_chars(24)
        self.preview_next.set_lines(2)
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        preview.set_halign(Gtk.Align.FILL)
        preview.set_hexpand(True)
        preview.pack_start(self.preview_current, False, False, 0)
        preview.pack_start(self.preview_next, False, False, 0)
        self.preview_event = Gtk.EventBox()
        self.preview_event.set_visible_window(False)
        self.preview_event.set_tooltip_text("Klik untuk mode lirik")
        self.preview_event.set_halign(Gtk.Align.FILL)
        self.preview_event.set_hexpand(True)
        self.preview_event.connect("button-press-event", self.on_info_click)
        self.preview_event.connect("realize", self.on_info_realize)
        self.preview_event.add(preview)
        right.pack_start(self.preview_event, True, True, 0)

        content.pack_start(left, False, False, 0)
        content.pack_start(right, True, True, 0)
        self.detail.pack_start(content, False, False, 0)

        self.timer_view = self.build_timer_view()
        self.shelf_view = self.build_shelf_view()
        self.weather_view = self.build_weather_view()
        self.slides = Gtk.Stack()
        self.slides.set_transition_duration(180)
        self.slides.add_named(self.detail, "media")
        self.slides.add_named(self.timer_view, "timer")
        self.slides.add_named(self.shelf_view, "shelf")
        self.slides.add_named(self.weather_view, "weather")
        self.slides.set_visible_child_name("media")
        self.slides_wrap = Gtk.Overlay()
        self.slides_wrap.set_halign(Gtk.Align.FILL)
        self.slides_wrap.set_hexpand(True)
        self.slides_wrap.add(self.slides)
        self.nav_prev = self.make_nav_box("go-previous-symbolic", "Slide sebelumnya", -1)
        self.nav_prev.set_halign(Gtk.Align.START)
        self.nav_prev.set_valign(Gtk.Align.CENTER)
        self.nav_prev.set_margin_start(2)
        self.slides_wrap.add_overlay(self.nav_prev)
        self.nav_next = self.make_nav_box("go-next-symbolic", "Slide berikutnya", 1)
        self.nav_next.set_halign(Gtk.Align.END)
        self.nav_next.set_valign(Gtk.Align.CENTER)
        self.nav_next.set_margin_end(2)
        self.slides_wrap.add_overlay(self.nav_next)
        self.slide_dots = PageDots(4)
        self.slide_dots.set_halign(Gtk.Align.CENTER)
        self.slide_dots.set_margin_bottom(2)
        self.slides_wrap.add_overlay(self.slide_dots)
        self.slide_gesture = Gtk.GestureSwipe.new(self.slides_wrap)
        self.slide_gesture.connect("swipe", self.on_slide_swipe)
        outer.pack_start(self.slides_wrap, False, True, 0)

        self.lyrics_view = self.build_lyrics_view()
        outer.pack_start(self.lyrics_view, False, False, 0)
        self.lyrics_view.hide()

        self.load_shelf()
        self.load_weather()

    def update_top_meta(self):
        self.date_label.set_visible(self.expanded)
        show_media = self.expanded and (
            self.current_slide == "media" or self.lyrics_mode
        )
        self.source_label.set_visible(show_media)

    def build_timer_view(self):
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        view.set_margin_start(20)
        view.set_margin_end(20)
        view.set_margin_top(4)
        view.set_margin_bottom(10)

        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        main.set_halign(Gtk.Align.CENTER)
        main.set_valign(Gtk.Align.CENTER)
        main.set_margin_top(1)
        self.timer_ring = TimerRing(66)
        main.pack_start(self.timer_ring, False, False, 0)

        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        clock_box.set_valign(Gtk.Align.CENTER)
        self.timer_clock = Gtk.Label(label="25:00")
        self.timer_clock.get_style_context().add_class("timer-clock")
        self.timer_clock.set_halign(Gtk.Align.START)
        self.timer_clock.set_width_chars(5)
        self.timer_label = Gtk.Label(label="Focus time")
        self.timer_label.get_style_context().add_class("timer-label")
        self.timer_label.set_halign(Gtk.Align.START)
        clock_box.pack_start(self.timer_clock, False, False, 0)
        clock_box.pack_start(self.timer_label, False, False, 0)
        main.pack_start(clock_box, False, False, 0)

        self.timer_reset = self.make_nav_button("view-refresh-symbolic")
        self.timer_reset.set_tooltip_text("Reset timer")
        self.timer_reset.set_valign(Gtk.Align.START)
        self.timer_reset.get_style_context().add_class("timer-reset")
        self.timer_reset.connect("clicked", lambda *_: self.reset_timer())
        main.pack_start(self.timer_reset, False, False, 0)
        view.pack_start(main, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_margin_top(2)
        self.timer_break = self.make_timer_chip(
            "Short Break", "weather-clear-night-symbolic"
        )
        self.timer_focus = self.make_timer_chip("Focus Time", "alarm-symbolic")
        self.timer_break.connect(
            "clicked", lambda *_: self.set_timer_mode("break")
        )
        self.timer_focus.connect(
            "clicked", lambda *_: self.set_timer_mode("focus")
        )
        self.timer_play = Gtk.Button()
        self.timer_play.set_relief(Gtk.ReliefStyle.NONE)
        self.timer_play.set_can_focus(False)
        self.timer_play.get_style_context().add_class("timer-play")
        self.timer_play.set_image(
            Gtk.Image.new_from_icon_name(
                "media-playback-start-symbolic", Gtk.IconSize.BUTTON
            )
        )
        self.timer_play.set_tooltip_text("Mulai timer")
        self.timer_play.connect("clicked", lambda *_: self.toggle_timer())
        controls.pack_start(self.timer_break, False, False, 0)
        controls.pack_start(self.timer_play, False, False, 0)
        controls.pack_start(self.timer_focus, False, False, 0)
        view.pack_start(controls, False, False, 0)

        wrapper = Gtk.Overlay()
        wrapper.add(view)
        self.timer_heading = Gtk.Label(label="Pomodoro")
        self.timer_heading.get_style_context().add_class("timer-heading")
        self.timer_heading.set_halign(Gtk.Align.START)
        self.timer_heading.set_valign(Gtk.Align.START)
        self.timer_heading.set_margin_start(20)
        self.timer_heading.set_margin_top(4)
        wrapper.add_overlay(self.timer_heading)
        return wrapper

    def build_lyrics_view(self):
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        view.set_margin_start(20)
        view.set_margin_end(20)
        view.set_margin_top(2)
        view.set_margin_bottom(12)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.art_lyrics = AlbumArt(44)
        self.art_lyrics.set_valign(Gtk.Align.CENTER)
        header.pack_start(self.art_lyrics, False, False, 0)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.lyric_title = Gtk.Label(label="")
        self.lyric_title.get_style_context().add_class("lyric-title")
        self.lyric_title.set_halign(Gtk.Align.START)
        self.lyric_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.lyric_title.set_max_width_chars(30)
        self.lyric_artist = Gtk.Label(label="")
        self.lyric_artist.get_style_context().add_class("lyric-sub")
        self.lyric_artist.set_halign(Gtk.Align.START)
        self.lyric_artist.set_ellipsize(Pango.EllipsizeMode.END)
        self.lyric_artist.set_max_width_chars(30)
        text_box.pack_start(self.lyric_title, False, False, 0)
        text_box.pack_start(self.lyric_artist, False, False, 0)
        header.pack_start(text_box, True, True, 0)
        close_button = Gtk.Button()
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_can_focus(False)
        close_button.set_image(
            Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        )
        close_button.set_tooltip_text("Tutup mode lirik")
        close_button.connect("clicked", lambda *_: self.close_lyrics_mode())
        header.pack_start(close_button, False, False, 0)
        view.pack_start(header, False, False, 0)

        self.lyrics_lines = []
        lines_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lines_box.set_size_request(-1, 214)
        for _ in range(9):
            label = Gtk.Label(label="")
            label.get_style_context().add_class("lyrics-line")
            label.set_halign(Gtk.Align.CENTER)
            label.set_justify(Gtk.Justification.CENTER)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(56)
            label.set_size_request(-1, 23)
            lines_box.pack_start(label, False, False, 0)
            self.lyrics_lines.append(label)
        self.lyrics_box = Gtk.EventBox()
        self.lyrics_box.set_visible_window(False)
        self.lyrics_box.connect("button-press-event", lambda *_: True)
        self.lyrics_box.add(lines_box)
        view.pack_start(self.lyrics_box, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        self.lyrics_progress = Gtk.ProgressBar()
        self.lyrics_progress.get_style_context().add_class("track")
        self.lyrics_progress.set_hexpand(True)
        self.lyrics_progress.set_valign(Gtk.Align.CENTER)
        self.lyrics_time = Gtk.Label(label="")
        self.lyrics_time.get_style_context().add_class("meta")
        row.pack_start(self.lyrics_progress, True, True, 0)
        row.pack_start(self.lyrics_time, False, False, 0)
        view.pack_start(row, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_margin_top(3)
        self.lyrics_prev = self.make_button("media-skip-backward-symbolic")
        self.lyrics_play = self.make_button("media-playback-start-symbolic")
        self.lyrics_next = self.make_button("media-skip-forward-symbolic")
        self.lyrics_prev.connect("clicked", lambda *_: self.media_command("Previous"))
        self.lyrics_play.connect("clicked", lambda *_: self.media_command("PlayPause"))
        self.lyrics_next.connect("clicked", lambda *_: self.media_command("Next"))
        controls.pack_start(self.lyrics_prev, False, False, 0)
        controls.pack_start(self.lyrics_play, False, False, 0)
        controls.pack_start(self.lyrics_next, False, False, 0)
        view.pack_start(controls, False, False, 0)
        return view

    def build_shelf_view(self):
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        view.set_margin_start(20)
        view.set_margin_end(20)
        view.set_margin_top(4)
        view.set_margin_bottom(10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        heading = Gtk.Label(label="Shelf")
        heading.get_style_context().add_class("shelf-heading")
        heading.set_halign(Gtk.Align.START)
        header.pack_start(heading, False, False, 0)
        stretch = Gtk.Box()
        stretch.set_hexpand(True)
        header.pack_start(stretch, True, True, 0)
        self.shelf_clear = Gtk.Button()
        self.shelf_clear.set_relief(Gtk.ReliefStyle.NONE)
        self.shelf_clear.set_can_focus(False)
        self.shelf_clear.get_style_context().add_class("shelf-clear")
        self.shelf_clear.set_tooltip_text("Kosongkan shelf")
        self.shelf_clear.set_image(
            Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
        )
        self.shelf_clear.connect("clicked", lambda *_: self.clear_shelf())
        header.pack_start(self.shelf_clear, False, False, 0)
        view.pack_start(header, False, False, 0)

        self.shelf_zone = ShelfZone()
        overlay = Gtk.Overlay()
        overlay.add(self.shelf_zone)

        self.shelf_empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.shelf_empty.set_halign(Gtk.Align.CENTER)
        self.shelf_empty.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(
            first_icon(
                "folder-download-symbolic",
                "document-save-symbolic",
                "go-down-symbolic",
            ),
            Gtk.IconSize.LARGE_TOOLBAR,
        )
        hint = Gtk.Label(label="Drop files di sini")
        hint.get_style_context().add_class("shelf-hint")
        self.shelf_empty.pack_start(icon, False, False, 0)
        self.shelf_empty.pack_start(hint, False, False, 0)
        overlay.add_overlay(self.shelf_empty)

        self.shelf_files = Gtk.ScrolledWindow()
        self.shelf_files.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        self.shelf_files.set_margin_start(10)
        self.shelf_files.set_margin_end(10)
        self.shelf_files.set_margin_top(6)
        self.shelf_files.set_margin_bottom(6)
        self.shelf_files.set_halign(Gtk.Align.FILL)
        self.shelf_files.set_valign(Gtk.Align.FILL)
        self.shelf_flow = Gtk.FlowBox()
        self.shelf_flow.set_max_children_per_line(3)
        self.shelf_flow.set_min_children_per_line(1)
        self.shelf_flow.set_homogeneous(True)
        self.shelf_flow.set_row_spacing(8)
        self.shelf_flow.set_column_spacing(12)
        self.shelf_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.shelf_flow.set_halign(Gtk.Align.CENTER)
        self.shelf_flow.set_valign(Gtk.Align.CENTER)
        self.shelf_files.add(self.shelf_flow)
        overlay.add_overlay(self.shelf_files)

        self.shelf_dest = Gtk.EventBox()
        self.shelf_dest.set_visible_window(True)
        self.shelf_dest.get_style_context().add_class("shelf-dest")
        self.shelf_dest.add(overlay)

        view.pack_start(self.shelf_dest, False, False, 0)
        return view

    def build_weather_view(self):
        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        view.set_margin_start(20)
        view.set_margin_end(20)
        view.set_margin_top(4)
        view.set_margin_bottom(10)

        heading = Gtk.Label(label="Cuaca")
        heading.get_style_context().add_class("weather-heading")
        heading.set_halign(Gtk.Align.START)
        view.pack_start(heading, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        body.set_valign(Gtk.Align.CENTER)
        body.set_margin_top(2)

        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left.set_valign(Gtk.Align.CENTER)
        left.set_margin_start(14)
        self.weather_icon = Gtk.Image()
        self.weather_icon.set_from_icon_name(
            "weather-clear-symbolic", Gtk.IconSize.DIALOG
        )
        self.weather_icon.set_pixel_size(56)
        left.pack_start(self.weather_icon, False, False, 0)

        temp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        temp_box.set_valign(Gtk.Align.CENTER)
        self.weather_temp = Gtk.Label(label="--°")
        self.weather_temp.get_style_context().add_class("weather-temp")
        self.weather_temp.set_halign(Gtk.Align.START)
        self.weather_cond = Gtk.Label(label="Buka slide untuk memuat")
        self.weather_cond.get_style_context().add_class("weather-cond")
        self.weather_cond.set_halign(Gtk.Align.START)
        temp_box.pack_start(self.weather_temp, False, False, 0)
        temp_box.pack_start(self.weather_cond, False, False, 0)
        left.pack_start(temp_box, False, False, 0)
        body.pack_start(left, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        body.pack_start(spacer, True, True, 0)

        self.weather_forecast = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=14
        )
        self.weather_forecast.set_valign(Gtk.Align.CENTER)
        self.weather_forecast.set_margin_end(16)
        body.pack_start(self.weather_forecast, False, False, 0)
        view.pack_start(body, False, False, 0)

        self.weather_detail = Gtk.Label(label="")
        self.weather_detail.get_style_context().add_class("weather-detail")
        self.weather_detail.set_halign(Gtk.Align.START)
        self.weather_detail.set_ellipsize(Pango.EllipsizeMode.END)
        view.pack_start(self.weather_detail, False, False, 0)
        return view

    def make_button(self, icon):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_can_focus(False)
        button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))
        button.set_sensitive(False)
        return button

    def make_nav_button(self, icon):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_can_focus(False)
        button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU))
        button.get_style_context().add_class("nav")
        return button

    def make_nav_box(self, icon, tooltip, direction):
        box = Gtk.EventBox()
        box.set_visible_window(True)
        box.set_above_child(True)
        button = self.make_nav_button(icon)
        button.set_tooltip_text(tooltip)
        box.add(button)
        box.get_style_context().add_class("navbox")
        box.set_size_request(26, 26)
        box.connect("button-press-event", self.on_nav_press, direction)
        box.connect(
            "enter-notify-event",
            lambda w, e: (
                button.set_state_flags(Gtk.StateFlags.PRELIGHT, True),
                False,
            )[1],
        )
        box.connect(
            "leave-notify-event",
            lambda w, e: (
                button.unset_state_flags(Gtk.StateFlags.PRELIGHT),
                False,
            )[1],
        )
        box.connect("realize", self.on_nav_realize)
        return box

    def on_nav_press(self, widget, event, direction):
        if event.button == 1:
            self.switch_slide(direction)
            return True
        return False

    def on_nav_realize(self, widget):
        window = widget.get_window()
        if window is not None:
            window.set_cursor(
                Gdk.Cursor.new_from_name(widget.get_display(), "pointer")
            )

    def make_timer_chip(self, text, icon):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_can_focus(False)
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        content.pack_start(
            Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0
        )
        label = Gtk.Label(label=text)
        content.pack_start(label, False, False, 0)
        button.add(content)
        button.get_style_context().add_class("timer-chip")
        return button

    def build_shelf_card(self, path):
        missing = not os.path.exists(path)
        base = Gtk.EventBox()
        base.set_visible_window(True)
        base.get_style_context().add_class("shelf-card")
        base.set_tooltip_text(path)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.set_margin_start(4)
        box.set_margin_end(4)
        box.set_margin_top(2)
        box.set_margin_bottom(2)
        thumb = Thumb(path, 64, 46)
        thumb.set_halign(Gtk.Align.CENTER)
        box.pack_start(thumb, False, False, 0)
        name_label = Gtk.Label(label=os.path.basename(path) or path)
        if missing:
            name_label.set_text(os.path.basename(path) + " (hilang)")
            name_label.get_style_context().add_class("missing")
        name_label.get_style_context().add_class("shelf-card-name")
        name_label.set_halign(Gtk.Align.CENTER)
        name_label.set_xalign(0.5)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_width_chars(9)
        name_label.set_max_width_chars(10)
        size_label = Gtk.Label(label=self.shelf_size_text(path))
        size_label.get_style_context().add_class("shelf-card-size")
        size_label.set_halign(Gtk.Align.CENTER)
        size_label.set_xalign(0.5)
        box.pack_start(name_label, False, False, 0)
        box.pack_start(size_label, False, False, 0)
        base.add(box)
        card = Gtk.Overlay()
        card.add(base)
        card.set_size_request(80, -1)
        remove = Gtk.Button(label="×")
        remove.set_relief(Gtk.ReliefStyle.NONE)
        remove.set_can_focus(False)
        remove.get_style_context().add_class("shelf-remove")
        remove.set_tooltip_text("Buang dari shelf")
        remove.set_halign(Gtk.Align.END)
        remove.set_valign(Gtk.Align.START)
        remove.set_margin_top(2)
        remove.set_margin_end(2)
        remove.set_no_show_all(True)
        remove.connect("clicked", lambda *_: self.remove_shelf_item(path))
        card.add_overlay(remove)
        base.connect("enter-notify-event", self.on_card_enter, remove)
        base.connect("leave-notify-event", self.on_card_leave, remove)
        base.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [
                Gtk.TargetEntry.new("text/uri-list", 0, SHELF_TARGET_URI),
                Gtk.TargetEntry.new("text/plain", 0, SHELF_TARGET_TEXT),
            ],
            Gdk.DragAction.COPY | Gdk.DragAction.MOVE,
        )
        base.connect("drag-data-get", self.on_shelf_drag_get, path)
        base.connect("drag-begin", self.on_chip_drag_begin, path)
        base.connect("drag-end", self.on_chip_drag_end, path)
        base.connect("drag-failed", self.on_chip_drag_failed, path)
        base.connect("button-press-event", self.on_chip_press, path)
        base.connect("button-release-event", self.on_chip_release, path)
        return card

    def shelf_size_text(self, path):
        if not os.path.exists(path):
            return "Hilang"
        if os.path.isdir(path):
            return "Folder"
        try:
            return fmt_size(os.path.getsize(path))
        except OSError:
            return ""

    def on_chip_press(self, widget, event, path):
        if event.button == 3:
            self.press_pos = None
            menu = Gtk.Menu()
            open_item = Gtk.MenuItem(label="Buka")
            open_item.connect(
                "activate", lambda *_: self.open_path(path)
            )
            show_item = Gtk.MenuItem(label="Tampilkan di folder")
            show_item.connect(
                "activate", lambda *_: self.open_path(os.path.dirname(path) or "/")
            )
            remove_item = Gtk.MenuItem(label="Buang dari shelf")
            remove_item.connect(
                "activate", lambda *_: self.remove_shelf_item(path)
            )
            for item in (open_item, show_item, remove_item):
                menu.append(item)
            menu.show_all()
            self._shelf_menu = menu
            menu.popup_at_pointer(event)
            return True
        if event.button == 1:
            self.press_pos = (event.x_root, event.y_root)
        return False

    def on_chip_release(self, widget, event, path):
        if event.button != 1 or self.press_pos is None:
            return False
        dist = math.hypot(
            event.x_root - self.press_pos[0], event.y_root - self.press_pos[1]
        )
        self.press_pos = None
        if dist < 6:
            self.open_path(path)
        return False

    def on_card_enter(self, widget, event, remove):
        widget.set_state_flags(Gtk.StateFlags.PRELIGHT, True)
        remove.show()
        return False

    def on_card_leave(self, widget, event, remove):
        widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        remove.hide()
        return False

    def on_chip_drag_begin(self, widget, context, path):
        self.drag_active = True
        self._chip_drag_path = path
        self._chip_drag_failed = False
        self._chip_drag_self_drop = False

    def on_chip_drag_end(self, widget, context, path):
        self.drag_active = False
        failed = self._chip_drag_failed
        self_drop = self._chip_drag_self_drop
        action = context.get_selected_action()
        self._chip_drag_path = None
        self._chip_drag_failed = False
        self._chip_drag_self_drop = False
        if not failed and not self_drop and int(action) != 0:
            self.remove_shelf_item(path)

    def on_chip_drag_failed(self, widget, context, result, path):
        self._chip_drag_failed = True
        self.drag_active = False
        return False

    def on_shelf_drag_get(self, widget, context, data, info, time, path):
        if info == SHELF_TARGET_URI:
            data.set_uris([path_to_uri(path)])
        else:
            data.set_text(path, -1)

    def note_drag_activity(self):
        self.drag_active = True
        if self._drag_reset_id is not None:
            GLib.source_remove(self._drag_reset_id)
        self._drag_reset_id = GLib.timeout_add(1500, self.clear_drag_activity)

    def clear_drag_activity(self):
        self._drag_reset_id = None
        self.drag_active = False
        if self.drag_pill:
            self.drag_pill = False
            self.compact_drop.get_style_context().remove_class("drag-hover")
        return False

    def on_window_drag_motion(self, widget, context, x, y, time):
        self.note_drag_activity()
        if not self.expanded:
            self.expand()
            self.show_slide("shelf", 1)
            self.update_shelf_hover(x, y)
            return True
        if self.current_slide != "shelf":
            self.show_slide("shelf", 1)
        self.update_shelf_hover(x, y)
        return True

    def update_shelf_hover(self, x, y):
        hover = False
        if self.expanded and self.current_slide == "shelf":
            zx, zy = self.shelf_zone.translate_coordinates(self, 0, 0)
            alloc = self.shelf_zone.get_allocation()
            hover = zx <= x < zx + alloc.width and zy <= y < zy + alloc.height
        if self.shelf_zone.hover != hover:
            self.shelf_zone.hover = hover
            self.shelf_zone.queue_draw()

    def on_window_drag_leave(self, widget, context, time):
        self.drag_pill = False
        self.compact_drop.get_style_context().remove_class("drag-hover")
        if self.shelf_zone.hover:
            self.shelf_zone.hover = False
            self.shelf_zone.queue_draw()

    def on_shelf_drop(self, widget, context, x, y, data, info, time):
        self.drag_pill = False
        self.compact_drop.get_style_context().remove_class("drag-hover")
        self.shelf_zone.hover = False
        self.shelf_zone.queue_draw()
        uris = list(data.get_uris() or [])
        if not uris:
            text = data.get_text()
            if text:
                uris = [line.strip() for line in text.splitlines() if line.strip()]
        paths = []
        for uri in uris:
            path = uri_to_path(uri)
            if not path or not os.path.exists(path) or path in paths:
                continue
            paths.append(path)
        if self._chip_drag_path is not None and self._chip_drag_path in paths:
            self._chip_drag_self_drop = True
        for path in paths:
            if path in self.shelf_items:
                self.shelf_items.remove(path)
            self.shelf_items.insert(0, path)
            if len(self.shelf_items) > SHELF_MAX:
                self.shelf_items.pop()
        self.rebuild_shelf()
        if paths:
            self.save_shelf()
        context.finish(bool(paths), False, time)
        if paths and not self.expanded:
            GLib.timeout_add(120, self.expand_after_drop)

    def expand_after_drop(self):
        if not self.expanded and not self.closing:
            self.expand()
            self.show_slide("shelf", 1)
        return False

    def rebuild_shelf(self):
        for child in list(self.shelf_flow.get_children()):
            self.shelf_flow.remove(child)
        for path in self.shelf_items:
            self.shelf_flow.add(self.build_shelf_card(path))
        self.shelf_flow.show_all()
        count = len(self.shelf_items)
        self.shelf_files.set_visible(count > 0)
        self.shelf_empty.set_visible(count == 0)
        self.shelf_clear.set_sensitive(count > 0)
        self.shelf_zone.show_border = count == 0
        self.shelf_zone.set_opacity(0.0 if count else 1.0)
        self.shelf_zone.queue_draw()

    def remove_shelf_item(self, path):
        if path in self.shelf_items:
            self.shelf_items.remove(path)
            self.rebuild_shelf()
            self.save_shelf()

    def clear_shelf(self):
        self.shelf_items = []
        self.rebuild_shelf()
        self.save_shelf()

    def open_path(self, path):
        if not os.path.exists(path):
            return
        try:
            subprocess.Popen(
                ["xdg-open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def shelf_cache_path(self):
        return os.path.join(GLib.get_user_cache_dir(), "dynamic-island-shelf.json")

    def save_shelf(self):
        try:
            with open(self.shelf_cache_path(), "w") as handle:
                json.dump({"items": self.shelf_items}, handle)
        except OSError:
            pass

    def load_shelf(self):
        try:
            with open(self.shelf_cache_path()) as handle:
                items = json.load(handle).get("items", [])
        except (OSError, ValueError):
            items = []
        self.shelf_items = []
        for item in items:
            if (
                isinstance(item, str)
                and os.path.exists(item)
                and item not in self.shelf_items
            ):
                self.shelf_items.append(item)
        self.shelf_items = self.shelf_items[:SHELF_MAX]
        self.rebuild_shelf()

    def weather_config_path(self):
        return os.path.join(
            GLib.get_user_config_dir(), "dynamic-island", "weather.json"
        )

    def weather_cache_path(self):
        return os.path.join(
            GLib.get_user_cache_dir(), "dynamic-island-weather.json"
        )

    def load_weather(self):
        self.weather_config = None
        try:
            with open(self.weather_config_path()) as handle:
                cfg = json.load(handle)
            self.weather_config = {
                "city": cfg.get("city", ""),
                "lat": float(cfg["lat"]),
                "lon": float(cfg["lon"]),
            }
        except (OSError, ValueError, KeyError, TypeError):
            self.weather_config = None
        try:
            with open(self.weather_cache_path()) as handle:
                cache = json.load(handle)
            if cache.get("current") and cache.get("daily"):
                self.weather_data = cache
                self.apply_weather(cache)
        except (OSError, ValueError):
            pass
        if self.weather_data is None:
            if self.weather_config is None:
                self.weather_cond.set_text("Lokasi belum diatur")
                self.weather_detail.set_text(self.weather_config_path())
            else:
                self.weather_cond.set_text("Buka slide untuk memuat")

    def maybe_refresh_weather(self):
        if self.weather_config is None or self.weather_fetching:
            return
        if time.time() < self.weather_next_try:
            return
        fetched = (self.weather_data or {}).get("fetched_at", 0)
        if time.time() - fetched < WEATHER_TTL:
            return
        self.weather_fetching = True
        if self.weather_data is None:
            self.weather_cond.set_text("Memuat...")
            self.weather_detail.set_text("")
        threading.Thread(target=self.fetch_weather, daemon=True).start()

    def fetch_weather(self):
        cfg = self.weather_config
        data = None
        if cfg is not None:
            params = urllib.parse.urlencode(
                {
                    "latitude": cfg["lat"],
                    "longitude": cfg["lon"],
                    "current": (
                        "temperature_2m,apparent_temperature,"
                        "relative_humidity_2m,weather_code,wind_speed_10m"
                    ),
                    "daily": (
                        "weather_code,temperature_2m_max,"
                        "temperature_2m_min"
                    ),
                    "timezone": "auto",
                    "forecast_days": 3,
                }
            )
            request = urllib.request.Request(
                "https://api.open-meteo.com/v1/forecast?" + params,
                headers={"User-Agent": "Zenon/1.0"},
            )
            try:
                with urllib.request.urlopen(request, timeout=6) as response:
                    payload = json.loads(response.read(65536).decode("utf-8"))
                if payload.get("current") and payload.get("daily"):
                    data = {
                        "fetched_at": time.time(),
                        "current": payload["current"],
                        "daily": payload["daily"],
                    }
            except Exception:
                data = None
        GLib.idle_add(self.finish_weather, data)

    def finish_weather(self, data):
        self.weather_fetching = False
        if data is None:
            self.weather_next_try = time.time() + 120
            if self.weather_data is not None:
                self.apply_weather(self.weather_data, offline=True)
            else:
                self.weather_temp.set_text("--°")
                self.weather_cond.set_text("Cuaca tidak tersedia")
                self.weather_detail.set_text(
                    "Cek koneksi lalu buka slide ini lagi"
                )
            return False
        self.weather_next_try = 0.0
        self.weather_data = data
        self.save_weather_cache()
        self.apply_weather(data)
        return False

    def save_weather_cache(self):
        try:
            with open(self.weather_cache_path(), "w") as handle:
                json.dump(self.weather_data, handle)
        except OSError:
            pass

    def apply_weather(self, data, offline=False):
        current = data.get("current") or {}
        daily = data.get("daily") or {}
        code = int(current.get("weather_code") or 0)
        temp = current.get("temperature_2m")
        if temp is None:
            self.weather_temp.set_text("--°")
        else:
            self.weather_temp.set_text("%d°" % round(temp))
        self.weather_cond.set_text(WMO_LABELS.get(code, "Cuaca"))
        icon_name = WMO_ICONS.get(code, "weather-clear-symbolic")
        icon_name = first_icon(
            icon_name, "weather-overcast-symbolic", "weather-clear-symbolic"
        )
        self.weather_icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.weather_icon.set_pixel_size(56)

        details = []
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        if feels is not None:
            details.append("Terasa %d°" % round(feels))
        if humidity is not None:
            details.append("Kelembapan %d%%" % round(humidity))
        if wind is not None:
            details.append("Angin %d km/j" % round(wind))
        if offline:
            details.append("offline")
        self.weather_detail.set_text(" · ".join(details))

        for child in list(self.weather_forecast.get_children()):
            self.weather_forecast.remove(child)
        times = daily.get("time") or []
        codes = daily.get("weather_code") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        count = min(3, len(times), len(codes), len(highs), len(lows))
        for index in range(count):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            column.set_valign(Gtk.Align.CENTER)
            if index == 0:
                day_text = "Hari ini"
            elif index == 1:
                day_text = "Besok"
            else:
                try:
                    day_text = DAYS[
                        datetime.date.fromisoformat(times[index]).weekday()
                    ]
                except (ValueError, TypeError):
                    day_text = "-"
            day_label = Gtk.Label(label=day_text)
            day_label.get_style_context().add_class("weather-day")
            day_label.set_halign(Gtk.Align.CENTER)
            fcode = int(codes[index] or 0)
            ficon = WMO_ICONS.get(fcode, "weather-clear-symbolic")
            ficon = first_icon(
                ficon, "weather-overcast-symbolic", "weather-clear-symbolic"
            )
            icon = Gtk.Image()
            icon.set_from_icon_name(ficon, Gtk.IconSize.MENU)
            icon.set_pixel_size(22)
            icon.set_halign(Gtk.Align.CENTER)
            high = highs[index]
            low = lows[index]
            if high is None or low is None:
                range_text = "--"
            else:
                range_text = "%d° / %d°" % (round(high), round(low))
            range_label = Gtk.Label(label=range_text)
            range_label.get_style_context().add_class("weather-range")
            range_label.set_halign(Gtk.Align.CENTER)
            column.pack_start(day_label, False, False, 0)
            column.pack_start(icon, False, False, 0)
            column.pack_start(range_label, False, False, 0)
            self.weather_forecast.pack_start(column, False, False, 0)
        self.weather_forecast.show_all()

    def switch_slide(self, direction):
        index = SLIDE_ORDER.index(self.current_slide)
        target = SLIDE_ORDER[(index + direction) % len(SLIDE_ORDER)]
        self.show_slide(target, direction)

    def show_slide(self, name, direction=1):
        if name == self.current_slide:
            return
        if name == self.current_slide:
            return
        transition = (
            Gtk.StackTransitionType.SLIDE_LEFT
            if direction > 0
            else Gtk.StackTransitionType.SLIDE_RIGHT
        )
        self.slides.set_visible_child_full(name, transition)
        self.current_slide = name
        self.slide_dots.set_index(SLIDE_ORDER.index(name))
        self.update_top_meta()
        if name == "timer":
            self.update_timer_ui()
        if name == "weather":
            self.maybe_refresh_weather()
        self.queue_draw()

    def on_slide_swipe(self, gesture, vx, vy):
        if abs(vx) < 100 or abs(vx) <= abs(vy):
            return
        self.switch_slide(-1 if vx > 0 else 1)

    def set_timer_mode(self, mode):
        if mode == self.timer_mode or mode not in ("focus", "break"):
            return
        self.timer_mode = mode
        self.timer_duration = 5 * 60 if mode == "break" else 25 * 60
        self.timer_remaining = float(self.timer_duration)
        self.timer_running = False
        self.timer_end = None
        self.update_timer_ui()

    def toggle_timer(self):
        if self.timer_running:
            if self.timer_end is not None:
                self.timer_remaining = max(0.0, self.timer_end - time.monotonic())
            self.timer_running = False
            self.timer_end = None
        else:
            if self.timer_remaining <= 0:
                self.timer_remaining = float(self.timer_duration)
            self.timer_running = True
            self.timer_end = time.monotonic() + self.timer_remaining
        self.update_timer_ui()

    def reset_timer(self):
        self.timer_running = False
        self.timer_end = None
        self.timer_remaining = float(self.timer_duration)
        self.update_timer_ui()

    def update_timer_ui(self):
        secs = int(math.ceil(max(0.0, self.timer_remaining)))
        clock = "%02d:%02d" % (secs // 60, secs % 60)
        if self.timer_clock.get_text() != clock:
            self.timer_clock.set_text(clock)
        label = "Short break" if self.timer_mode == "break" else "Focus time"
        if self.timer_label.get_text() != label:
            self.timer_label.set_text(label)
        progress = 0.0
        if self.timer_duration > 0:
            progress = self.timer_remaining / self.timer_duration
        self.timer_ring.set_progress(progress)
        self.timer_ring.set_running(self.timer_running)
        if self.timer_icon_state != self.timer_running:
            icon = (
                "media-playback-pause-symbolic"
                if self.timer_running
                else "media-playback-start-symbolic"
            )
            self.timer_play.set_image(
                Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            )
            self.timer_play.set_tooltip_text(
                "Jeda timer" if self.timer_running else "Mulai timer"
            )
            self.timer_icon_state = self.timer_running
        for button, mode in (
            (self.timer_break, "break"),
            (self.timer_focus, "focus"),
        ):
            context = button.get_style_context()
            if mode == self.timer_mode:
                context.add_class("active")
            else:
                context.remove_class("active")

    def first_place(self):
        if not self.expanded:
            self.apply_geometry(COMPACT_W, COMPACT_H)
        return False

    def reveal_window(self):
        self.apply_window_shape()
        self.set_opacity(1.0)
        return False

    def on_map(self, widget, event):
        self.apply_window_shape()
        return False

    def resync_shape(self):
        self.apply_window_shape()
        return False

    def screen_geometry(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_workarea()

    def apply_geometry(self, w, h):
        w = max(COMPACT_W, int(w))
        h = max(COMPACT_H, int(h))
        geom = self.screen_geometry()
        if self.anim_dir == 2:
            self.current_w = w
            self.current_h = h
            self.root.set_size_request(w, h)
            x = geom.x + (geom.width - w) // 2
            self.move(x, geom.y + TOP_MARGIN)
            self.card_x = 0.0
            self.card_y = 0.0
            self.card_w = float(w)
            self.card_h = float(h)
        else:
            self.current_w = EXPANDED_W
            self.current_h = EXPANDED_H
            self.root.set_size_request(EXPANDED_W, EXPANDED_H)
            x = geom.x + (geom.width - EXPANDED_W) // 2
            self.move(x, geom.y + TOP_MARGIN)
            self.card_x = (EXPANDED_W - w) / 2.0
            self.card_y = 0.0
            self.card_w = float(w)
            self.card_h = float(h)
        self.compact.set_size_request(int(round(self.card_w)), COMPACT_H)
        self.apply_window_shape()
        self.queue_draw()

    def compact_target_xy(self):
        geom = self.screen_geometry()
        return (
            geom.x + (geom.width - COMPACT_W) // 2,
            geom.y + TOP_MARGIN,
        )

    def apply_window_shape(self):
        window = self.get_window()
        if window is None:
            return
        x = int(round(self.card_x))
        y = int(round(self.card_y))
        w = max(1, int(round(self.card_w)))
        h = max(1, int(round(self.card_h)))
        region = cairo.Region(cairo.RectangleInt(x, y, w, h))
        window.shape_combine_region(region, 0, 0)
        window.input_shape_combine_region(region, 0, 0)
        self.shape_active = True

    def clear_window_shape(self):
        window = self.get_window()
        if window is not None:
            window.shape_combine_region(None, 0, 0)
            window.input_shape_combine_region(None, 0, 0)
        self.shape_active = False

    def start_close_move(self):
        self.close_phase = 1
        self.close_wait_count = 0
        self.close_target_xy = self.compact_target_xy()
        self.move(*self.close_target_xy)
        GLib.timeout_add(5, self.close_move_wait)

    def close_move_wait(self):
        if not self.closing or self.close_phase != 1:
            return False
        tx, ty = self.close_target_xy
        wx, wy = self.get_position()
        self.card_x = float(tx - wx)
        self.card_y = float(ty - wy)
        self.card_w = float(COMPACT_W)
        self.card_h = float(COMPACT_H)
        self.apply_window_shape()
        self.queue_draw()
        if (wx, wy) == (tx, ty):
            self.start_close_resize()
            return False
        self.close_wait_count += 1
        if self.close_wait_count > 40:
            self.start_close_resize()
            return False
        return True

    def start_close_resize(self):
        self.close_phase = 2
        self.close_wait_count = 0
        self.current_w = COMPACT_W
        self.current_h = COMPACT_H
        self.root.set_size_request(COMPACT_W, COMPACT_H)
        self.resize(COMPACT_W, COMPACT_H)
        GLib.timeout_add(5, self.close_resize_wait)

    def close_resize_wait(self):
        if not self.closing or self.close_phase != 2:
            return False
        w, h = self.get_size()
        if (w, h) == (COMPACT_W, COMPACT_H):
            self.finish_close()
            return False
        tx, ty = self.close_target_xy
        wx, wy = self.get_position()
        self.card_x = float(tx - wx)
        self.card_y = float(ty - wy)
        self.card_w = float(COMPACT_W)
        self.card_h = float(COMPACT_H)
        self.apply_window_shape()
        self.queue_draw()
        self.close_wait_count += 1
        if self.close_wait_count > 40:
            self.finish_close()
            return False
        return True

    def finish_close(self):
        self.card_x = float((self.current_w - COMPACT_W) // 2)
        self.card_y = 0.0
        self.card_w = float(COMPACT_W)
        self.card_h = float(COMPACT_H)
        self.compact.set_size_request(COMPACT_W, COMPACT_H)
        self.apply_window_shape()
        self.close_phase = 0
        self.set_opacity(0.0)
        self.compact.set_opacity(1.0)
        self.batt.show()
        self.eyes.show()
        self.queue_draw()
        self.compact_fade_start = time.monotonic()
        GLib.timeout_add(ANIM_MS, self.compact_fade_in)

    def compact_fade_in(self):
        if not self.closing:
            self.set_opacity(1.0)
            return False
        progress = min(
            1.0, (time.monotonic() - self.compact_fade_start) / COMPACT_FADE_SECONDS
        )
        eased = progress * progress * (3 - 2 * progress)
        self.set_opacity(eased)
        if progress >= 1.0:
            self.set_opacity(1.0)
            self.closing = False
            self.close_phase = 0
            return False
        return True

    def on_configure(self, widget, event):
        if not self.closing or self.close_phase < 1 or self.close_target_xy is None:
            return False
        tx, ty = self.close_target_xy
        wx, wy = self.get_position()
        w, h = self.get_size()
        self.card_x = float(tx - wx)
        self.card_y = float(ty - wy)
        self.card_w = float(COMPACT_W)
        self.card_h = float(COMPACT_H)
        self.apply_window_shape()
        self.queue_draw()
        if self.close_phase == 1 and (wx, wy) == (tx, ty):
            self.start_close_resize()
        elif self.close_phase == 2 and (w, h) == (COMPACT_W, COMPACT_H):
            self.finish_close()
        return False

    def animate_size(self, target_w, target_h, direction):
        self.anim_from = (self.card_w, self.card_h)
        self.anim_to = (target_w, target_h)
        self.anim_t = 0.0
        self.anim_dir = direction
        if self.anim_source is None:
            self.anim_source = GLib.timeout_add(ANIM_MS, self.anim_step)

    def animate_panel(self, target_w, target_h):
        self.anim_from = (self.current_w, self.current_h)
        self.anim_to = (target_w, target_h)
        self.anim_t = 0.0
        self.anim_dir = 2
        if self.anim_source is None:
            self.anim_source = GLib.timeout_add(ANIM_MS, self.anim_step)

    def anim_step(self):
        self.anim_t = min(1.0, self.anim_t + 0.13)
        eased = 1 - (1 - self.anim_t) ** 3
        w = self.anim_from[0] + (self.anim_to[0] - self.anim_from[0]) * eased
        h = self.anim_from[1] + (self.anim_to[1] - self.anim_from[1]) * eased
        self.apply_geometry(w, h)
        if self.anim_dir == 1:
            self.slides_wrap.set_opacity(eased)
        if self.anim_t >= 1.0:
            self.anim_source = None
            self.anim_dir = 0
            return False
        return True

    def expand(self):
        if self.expanded or self.closing:
            return
        self.expanded = True
        self.lyrics_mode = False
        self.lyrics_view.hide()
        self.slides_wrap.show_all()
        self.slides.set_visible_child_name(self.current_slide)
        self.shelf_empty.set_visible(not self.shelf_items)
        self.shelf_files.set_visible(bool(self.shelf_items))
        self.update_top_meta()
        self.eyes.hide()
        self.slides_wrap.set_opacity(0.0)
        self.slide_dots.set_index(SLIDE_ORDER.index(self.current_slide))
        self.queue_draw()
        self.update_timer_ui()
        self.animate_size(EXPANDED_W, EXPANDED_H, 1)
        self.refresh_media()
        self.update_position()
        self.update_lyrics()
        if self.current_slide == "weather":
            self.maybe_refresh_weather()

    def collapse(self):
        if not self.expanded or self.closing:
            return
        self.expanded = False
        self.lyrics_mode = False
        self.lyrics_view.hide()
        self.update_top_meta()
        if self.anim_source is not None:
            GLib.source_remove(self.anim_source)
            self.anim_source = None
        self.anim_dir = 0
        self.anim_t = 0.0
        self.closing = True
        self.close_phase = 0
        self.close_start = time.monotonic()
        self.close_opacity = self.slides_wrap.get_opacity()
        self.close_fade = 1.0
        self.close_target_xy = self.compact_target_xy()
        self.card_x = 0.0
        self.card_y = 0.0
        self.card_w = float(self.current_w)
        self.card_h = float(self.current_h)
        self.compact.set_opacity(0.0)
        self.eyes.hide()
        self.apply_window_shape()
        if self.close_source is None:
            self.close_source = GLib.timeout_add(ANIM_MS, self.close_step)

    def close_step(self):
        if not self.closing:
            self.close_source = None
            return False
        progress = min(1.0, (time.monotonic() - self.close_start) / CLOSE_SECONDS)
        eased = 1 - (1 - progress) ** 3
        self.card_w = self.current_w + (COMPACT_W - self.current_w) * eased
        self.card_h = self.current_h + (COMPACT_H - self.current_h) * eased
        self.card_x = (self.current_w - self.card_w) / 2
        self.card_y = 0.0
        fade = max(0.0, 1.0 - progress / CLOSE_FADE)
        self.close_fade = max(0.0, 1.0 - progress)
        self.slides_wrap.set_opacity(self.close_opacity * fade * fade)
        out = max(0.0, min(1.0, (progress - 0.6) / 0.4))
        self.set_opacity(1.0 - out * out * (3 - 2 * out))
        self.compact.set_size_request(int(round(self.card_w)), COMPACT_H)
        self.apply_window_shape()
        self.queue_draw()
        if progress >= 1.0:
            self.set_opacity(0.0)
            self.slides_wrap.hide()
            self.close_source = None
            self.finish_close()
            return False
        return True

    def pointer_inside(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        if pointer is None:
            return False
        _, x, y = pointer.get_position()
        wx, wy = self.get_position()
        x0 = wx + self.card_x
        y0 = wy + self.card_y
        return x0 <= x < x0 + self.card_w and y0 <= y < y0 + self.card_h

    def watch_pointer(self):
        inside = self.pointer_inside()
        if inside:
            if not self.expanded and not self.drag_active and not x_button1_pressed():
                self.expand()
        elif (
            self.expanded
            and not self.lyrics_mode
            and not self.drag_active
            and self.anim_source is None
        ):
            self.collapse()
        return True

    def animate_eyes(self):
        if self.expanded or not self.eyes.get_visible():
            return True
        display = Gdk.Display.get_default()
        if display is None:
            return True
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat is not None else None
        if pointer is not None:
            now = time.monotonic()
            _, px, py = pointer.get_position()
            if (
                self.last_pointer is None
                or abs(px - self.last_pointer[0]) + abs(py - self.last_pointer[1]) > 1
            ):
                self.last_pointer = (px, py)
                self.last_move = now
            self.eyes.set_sleeping(now - self.last_move >= SLEEP_AFTER)
            coords = self.eyes.translate_coordinates(self, 0, 0)
            if coords:
                if len(coords) == 2:
                    ok, ex, ey = True, coords[0], coords[1]
                else:
                    ok, ex, ey = coords[0], coords[1], coords[2]
                if ok:
                    wx, wy = self.get_position()
                    alloc = self.eyes.get_allocation()
                    self.eyes.look_at(
                        px - (wx + ex + alloc.width / 2),
                        py - (wy + ey + alloc.height / 2),
                    )
        self.eyes.step()
        return True

    def on_info_click(self, widget, event):
        if event.button == 1:
            self.open_lyrics_mode()
            return True
        return False

    def on_info_realize(self, widget):
        window = widget.get_window()
        if window is not None:
            window.set_cursor(Gdk.Cursor.new_from_name(widget.get_display(), "pointer"))

    def open_lyrics_mode(self):
        if self.lyrics_mode:
            return
        if not self.player_iface or not self.track_title:
            return
        if not self.expanded:
            self.expand()
        self.lyrics_mode = True
        self.slides_wrap.hide()
        self.update_top_meta()
        self.lyrics_view.show_all()
        self.update_media_ui()
        self.update_lyrics_view(self.current_lyric_index())
        self.animate_panel(LYRICS_W, LYRICS_H)

    def close_lyrics_mode(self):
        if not self.lyrics_mode:
            return
        self.lyrics_mode = False
        self.lyrics_view.hide()
        self.slides_wrap.show_all()
        self.slides.set_visible_child_name(self.current_slide)
        self.update_top_meta()
        self.slides_wrap.set_opacity(1.0)
        self.animate_panel(EXPANDED_W, EXPANDED_H)

    def on_click(self, widget, event):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        if self.lyrics_mode:
            self.close_lyrics_mode()
            return True
        if not self.expanded:
            if event.button == 1:
                self.expand()
            return True
        return False

    def on_draw(self, widget, cr):
        x, y = self.card_x, self.card_y
        cw, ch = self.card_w, self.card_h
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        radius = min(ch / 2, 24)
        gradient = cairo.LinearGradient(0, y, 0, y + ch)
        gradient.add_color_stop_rgba(0.0, 0.09, 0.09, 0.10, 0.985)
        gradient.add_color_stop_rgba(1.0, 0.02, 0.02, 0.03, 0.985)
        rounded_path(cr, x + 0.5, y + 0.5, cw - 1, ch - 1, radius)
        cr.set_source(gradient)
        cr.fill()
        glow_tint = self.art_tint
        if self.current_slide == "timer" and (self.expanded or self.closing):
            glow_tint = (1.0, 0.28, 0.38)
        elif self.current_slide == "shelf" and (self.expanded or self.closing):
            glow_tint = (0.42, 0.66, 1.0)
        if glow_tint and (self.expanded or self.closing):
            tr, tg, tb = glow_tint
            glow_alpha = self.close_fade if self.closing else 1.0
            gx = x + cw * 0.18
            gy = y + ch * 1.05
            glow = cairo.RadialGradient(
                gx, gy, 8, gx, gy, max(cw, ch) * 0.9
            )
            glow.add_color_stop_rgba(0.0, tr, tg, tb, 0.42 * glow_alpha)
            glow.add_color_stop_rgba(0.5, tr, tg, tb, 0.14 * glow_alpha)
            glow.add_color_stop_rgba(1.0, tr, tg, tb, 0.0)
            cr.save()
            rounded_path(cr, x + 0.5, y + 0.5, cw - 1, ch - 1, radius)
            cr.clip()
            cr.set_source(glow)
            cr.paint()
            cr.restore()
        rounded_path(cr, x + 0.5, y + 0.5, cw - 1, ch - 1, radius)
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.set_line_width(1)
        cr.stroke()
        dots = getattr(self, "slide_dots", None)
        if dots is not None and self.expanded and not self.lyrics_mode:
            cx = x + cw / 2
            cy = y + ch - 6
            for i in range(dots.count):
                cr.set_source_rgba(1, 1, 1, 0.92 if i == dots.index else 0.26)
                cr.arc(cx + (i - (dots.count - 1) / 2) * 9, cy, 1.8, 0, 2 * math.pi)
                cr.fill()
        return False

    def queue_refresh(self, *args):
        if self.refresh_pending:
            return
        self.refresh_pending = True
        GLib.timeout_add(120, self.do_refresh)

    def do_refresh(self):
        self.refresh_pending = False
        self.refresh_media()
        self.update_position()
        return False

    def find_player(self):
        if not self.bus:
            return None
        try:
            names = [n for n in self.bus.list_names() if n.startswith("org.mpris.MediaPlayer2.")]
        except dbus.DBusException:
            return None
        candidates = []
        for name in names:
            try:
                obj = self.bus.get_object(name, "/org/mpris/MediaPlayer2")
                props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                status = str(props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
            except dbus.DBusException:
                continue
            candidates.append((name, obj, props, status))
        if not candidates:
            return None
        for candidate in candidates:
            if candidate[3] == "Playing":
                return candidate
        return candidates[0]

    def refresh_media(self):
        found = self.find_player()
        if not found:
            self.player_bus_name = None
            self.player_obj = None
            self.player_props = None
            self.player_iface = None
            self.player_status = "Stopped"
            self.player_identity = ""
            self.track_title = ""
            self.track_artist = ""
            self.track_album = ""
            self.track_url = ""
            self.track_length = 0
            self.position_us = 0
            if self.lyrics_mode:
                self.close_lyrics_mode()
            self.update_album_art("")
            self.update_media_ui()
            self.maybe_load_lyrics()
            return
        name, obj, props, status = found
        self.player_bus_name = name
        self.player_obj = obj
        self.player_props = props
        self.player_iface = dbus.Interface(obj, "org.mpris.MediaPlayer2.Player")
        self.player_status = status
        try:
            metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
        except dbus.DBusException:
            metadata = {}
        self.track_title = str(metadata.get("xesam:title", "") or "")
        artists = metadata.get("xesam:artist", [])
        if isinstance(artists, str):
            self.track_artist = artists
        else:
            self.track_artist = ", ".join(str(a) for a in artists)
        self.track_album = str(metadata.get("xesam:album", "") or "")
        self.track_url = str(metadata.get("xesam:url", "") or "")
        art_url = str(metadata.get("mpris:artUrl", "") or "")
        try:
            self.track_length = int(metadata.get("mpris:length", 0) or 0)
        except (TypeError, ValueError):
            self.track_length = 0
        if self.needs_display_cleanup():
            query_title, query_artist = self.lyrics_query()
            if query_title:
                self.track_title = query_title
            if query_artist:
                self.track_artist = query_artist
        if name not in self.identity_cache:
            try:
                identity = props.Get("org.mpris.MediaPlayer2", "Identity")
                self.identity_cache[name] = str(identity)
            except dbus.DBusException:
                self.identity_cache[name] = name.split(".", 3)[-1].capitalize()
        self.player_identity = self.identity_cache[name]
        self.update_album_art(art_url)
        self.update_media_ui()
        self.maybe_load_lyrics()

    def update_album_art(self, url):
        if url == self.art_url:
            return
        self.art_url = url
        self.art_token += 1
        token = self.art_token
        if not url:
            self.apply_album_art(None)
            return
        if url in self.art_cache:
            self.apply_album_art(self.art_cache[url])
            return
        threading.Thread(
            target=self.load_album_art, args=(token, url), daemon=True
        ).start()

    def load_album_art(self, token, url):
        data = None
        try:
            if url.startswith("data:"):
                header, _, payload = url.partition(",")
                if ";base64" in header:
                    data = base64.b64decode(payload)
                else:
                    data = urllib.parse.unquote_to_bytes(payload)
            elif url.startswith("http://") or url.startswith("https://"):
                request = urllib.request.Request(
                    url, headers={"User-Agent": "Zenon/1.0"}
                )
                with urllib.request.urlopen(request, timeout=6) as response:
                    data = response.read(8 * 1024 * 1024)
            else:
                if url.startswith("file://"):
                    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
                else:
                    path = url
                with open(path, "rb") as handle:
                    data = handle.read()
        except Exception:
            data = None
        GLib.idle_add(self.finish_album_art, token, url, data)

    def finish_album_art(self, token, url, data):
        if token != self.art_token:
            return False
        pixbuf = None
        if data:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            except Exception:
                pixbuf = None
        if len(self.art_cache) >= 8:
            self.art_cache.clear()
        self.art_cache[url] = pixbuf
        self.apply_album_art(pixbuf)
        return False

    def apply_album_art(self, pixbuf):
        self.art_expanded.set_pixbuf(pixbuf)
        self.art_lyrics.set_pixbuf(pixbuf)
        tint = None
        if pixbuf is not None:
            try:
                small = pixbuf.scale_simple(1, 1, GdkPixbuf.InterpType.BILINEAR)
                pixels = small.get_pixels()
                if len(pixels) >= 3:
                    red = pixels[0] / 255.0
                    green = pixels[1] / 255.0
                    blue = pixels[2] / 255.0
                    peak = max(red, green, blue, 0.001)
                    tint = (red / peak, green / peak, blue / peak)
            except Exception:
                tint = None
        self.art_tint = tint
        self.queue_draw()

    def update_media_ui(self):
        has_player = self.player_iface is not None
        playing = self.player_status == "Playing"
        if has_player:
            title = self.track_title or "Tanpa judul"
            artist = self.track_artist or self.player_identity
        else:
            title = "Tidak ada media"
            artist = "Spotify, VLC, Rhythmbox"
        self.title_label.set_text(title)
        self.title_label.set_tooltip_text(title if has_player else None)
        self.artist_label.set_text(artist)
        self.artist_label.set_tooltip_text(artist if has_player else None)
        self.lyric_title.set_text(title)
        self.lyric_artist.set_text(artist)
        self.source_label.set_text(self.player_identity if has_player else "")
        show_equalizer = has_player and playing
        self.equalizer.set_active(show_equalizer)
        self.equalizer.set_visible(show_equalizer)
        self.clock.set_visible(not show_equalizer)
        icon = "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
        for button in (self.play_button, self.lyrics_play):
            button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))
        for button in (
            self.lyrics_button,
            self.prev_button,
            self.play_button,
            self.next_button,
            self.lyrics_prev,
            self.lyrics_play,
            self.lyrics_next,
        ):
            button.set_sensitive(has_player)
        if not has_player:
            for bar in (self.progress, self.lyrics_progress):
                bar.set_fraction(0.0)
            self.elapsed_label.set_text("")
            self.remaining_label.set_text("")
            self.lyrics_time.set_text("")
            self.preview_current.set_text("")
            self.preview_next.set_text("")

    def update_position(self):
        if not self.expanded or self.player_props is None:
            return
        try:
            position = int(
                self.player_props.Get("org.mpris.MediaPlayer2.Player", "Position")
            )
        except dbus.DBusException:
            position = 0
        self.position_us = position
        if self.track_length > 0:
            fraction = max(0.0, min(1.0, position / self.track_length))
            for bar in (self.progress, self.lyrics_progress):
                bar.set_fraction(fraction)
            remaining = max(0, self.track_length - position)
            self.elapsed_label.set_text(fmt_clock(position))
            self.remaining_label.set_text("-" + fmt_clock(remaining))
            text = "%s / %s" % (fmt_us(position), fmt_us(self.track_length))
            self.lyrics_time.set_text(text)
        else:
            for bar in (self.progress, self.lyrics_progress):
                bar.set_fraction(0.0)
            text = fmt_us(position) if position else ""
            self.elapsed_label.set_text(fmt_clock(position) if position else "")
            self.remaining_label.set_text("")
            self.lyrics_time.set_text(text)

    def needs_display_cleanup(self):
        artist = self.track_artist.strip().lower()
        return (
            artist in ("", "unknown", "unknown artist", "various artists")
            or strip_audio_ext(self.track_title).lower() != self.track_title.lower()
            or bool(NOISE_RE.search(self.track_title))
        )

    def lyrics_query(self):
        title = self.track_title.strip()
        artist = self.track_artist.strip()
        if artist.lower() in ("unknown", "unknown artist", "various artists"):
            artist = ""
        hint = filename_from_url(self.track_url)
        if not hint and strip_audio_ext(title).lower() != title.lower():
            hint = title
        hint_title, hint_artist = split_artist_title(hint) if hint else ("", "")
        use_hint = bool(hint_title) and (
            not artist
            or NOISE_RE.search(title)
            or strip_audio_ext(title).lower() != title.lower()
        )
        if use_hint:
            title = hint_title
            artist = hint_artist or artist
        if not artist and " - " in title:
            split_title, split_artist = split_artist_title(title)
            if split_artist:
                title, artist = split_title, split_artist
        return clean_track_text(title), clean_track_text(artist)

    def maybe_load_lyrics(self):
        title, artist = self.lyrics_query()
        key = (title.lower(), artist.lower(), int(self.track_length // 1000000))
        if key == self.current_track_key:
            return
        self.current_track_key = key
        self.lyrics = []
        self.lyrics_missing = False
        self.lyric_index = -1
        self.lyrics_pending = False
        self.lyric_token += 1
        if not self.player_iface or not title:
            self.preview_current.set_text("")
            self.preview_next.set_text("")
            return
        if key in self.lyrics_cache:
            self.set_lyrics(self.lyrics_cache[key])
            return
        self.lyrics_pending = True
        self.update_lyrics_preview(-1)
        if self.lyrics_mode:
            self.update_lyrics_view(-1)
        threading.Thread(
            target=self.fetch_lyrics,
            args=(self.lyric_token, key, title, artist, self.track_length),
            daemon=True,
        ).start()

    def fetch_lyrics(self, token, key, title, artist, length):
        seconds = length / 1000000.0
        attempts = []
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        attempts.append(params)
        if artist:
            attempts.append({"track_name": title})
        lines = []
        for params in attempts:
            results = self.search_lrclib(params)
            if not isinstance(results, list):
                results = []
            best = None
            best_score = None
            for item in results:
                synced = item.get("syncedLyrics")
                if not synced:
                    continue
                score = abs((item.get("duration") or 0) - seconds) if seconds else 0
                if str(item.get("trackName", "")).strip().lower() == title.lower():
                    score -= 2
                if artist and str(item.get("artistName", "")).strip().lower() == artist.lower():
                    score -= 2
                if best_score is None or score < best_score:
                    best_score = score
                    best = synced
            if best:
                parsed = parse_lrc(best)
                if any(text for _, text in parsed):
                    lines = parsed
                    break
        GLib.idle_add(self.finish_lyrics, token, key, lines)

    @staticmethod
    def search_lrclib(params):
        try:
            url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(
                url, headers={"User-Agent": "Zenon/1.0"}
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

    def finish_lyrics(self, token, key, lines):
        if token != self.lyric_token:
            return False
        self.lyrics_pending = False
        self.lyrics_cache[key] = lines
        self.set_lyrics(lines)
        return False

    def set_lyrics(self, lines):
        self.lyrics = lines
        self.lyrics_missing = not lines
        self.lyric_index = -1
        self.update_lyrics_preview(self.current_lyric_index())
        if self.lyrics_mode:
            self.update_lyrics_view(self.current_lyric_index())

    def current_lyric_index(self):
        if not self.lyrics:
            return -1
        position = self.position_us / 1000000.0
        index = -1
        for i, (stamp, text) in enumerate(self.lyrics):
            if stamp <= position + 0.2:
                index = i
            else:
                break
        return index

    def update_lyrics(self):
        index = self.current_lyric_index()
        self.lyric_index = index
        self.update_lyrics_preview(index)
        if self.lyrics_mode:
            self.update_lyrics_view(index)

    def update_lyrics_preview(self, index):
        if self.lyrics_pending:
            self.preview_current.set_text("Mencari lirik...")
            self.preview_next.set_text("")
            return
        if not self.lyrics:
            if self.player_iface and self.track_title:
                self.preview_current.set_text(
                    "Lirik tidak tersedia" if self.lyrics_missing else ""
                )
            else:
                self.preview_current.set_text("")
            self.preview_next.set_text("")
            return
        if index < 0:
            index = 0
        if index >= len(self.lyrics):
            index = len(self.lyrics) - 1
        current = self.lyrics[index][1] or "\u266a"
        following = self.lyrics[index + 1][1] if index + 1 < len(self.lyrics) else ""
        self.preview_current.set_text(current)
        self.preview_next.set_text(following)

    def update_lyrics_view(self, index):
        if not self.lyrics_mode:
            return
        if self.lyrics_pending:
            self.show_lyrics_message("Mencari lirik...")
            return
        if not self.lyrics:
            self.show_lyrics_message("Lirik tidak tersedia")
            return
        start = index - 4 if index >= 0 else 0
        for slot, label in enumerate(self.lyrics_lines):
            line_index = start + slot
            if 0 <= line_index < len(self.lyrics):
                text = self.lyrics[line_index][1] or " "
            else:
                text = ""
            label.set_text(text)
            context = label.get_style_context()
            if line_index == index:
                context.add_class("active")
                context.remove_class("edge")
            else:
                context.remove_class("active")
                if slot in (0, 8):
                    context.add_class("edge")
                else:
                    context.remove_class("edge")

    def show_lyrics_message(self, text):
        for slot, label in enumerate(self.lyrics_lines):
            label.set_text(text if slot == 4 else "")
            context = label.get_style_context()
            context.remove_class("active")
            context.remove_class("edge")

    def media_command(self, method):
        if self.player_iface is None:
            return
        try:
            getattr(self.player_iface, method)()
        except dbus.DBusException:
            pass
        GLib.timeout_add(200, self.do_refresh)

    def update_battery(self):
        info = read_battery(self.batt_path)
        if not info:
            self.batt.set_text("")
            return
        capacity, status = info
        charging = status in ("Charging", "Full")
        self.batt.set_text("%d%%" % capacity)
        ctx = self.batt.get_style_context()
        if charging:
            ctx.add_class("charging")
            ctx.remove_class("low")
        else:
            ctx.remove_class("charging")
            if capacity <= 20:
                ctx.add_class("low")
            else:
                ctx.remove_class("low")

    def tick(self):
        now = datetime.datetime.now()
        self.clock.set_text(now.strftime("%H:%M"))
        self.date_label.set_text("%s, %d %s" % (DAYS[now.weekday()], now.day, MONTHS[now.month - 1]))
        if self.timer_running and self.timer_end is not None:
            remaining = self.timer_end - time.monotonic()
            if remaining <= 0:
                self.timer_remaining = 0.0
                self.timer_running = False
                self.timer_end = None
            else:
                self.timer_remaining = remaining
            self.update_timer_ui()
        self.tick_count += 1
        if self.tick_count % 15 == 0 or self.tick_count == 1:
            self.update_battery()
        if self.expanded:
            self.update_position()
            self.update_lyrics()
            if self.tick_count % 10 == 0:
                self.refresh_media()
            if self.current_slide == "weather" and self.tick_count % 60 == 0:
                self.maybe_refresh_weather()
        return True


def main():
    GLib.set_prgname("zenon")
    GLib.set_application_name("Zenon")
    if not os.environ.get("DISPLAY"):
        print("DISPLAY tidak tersedia")
        return 1
    lock_path = os.path.join(GLib.get_user_cache_dir(), "dynamic-island.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    Island()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
