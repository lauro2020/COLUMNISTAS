#!/usr/bin/env python3
"""Genera los íconos PNG de la PWA sin dependencias externas.

Uso:  python3 tools/make_icons.py

Dibuja un cuadrado redondeado oscuro con tres líneas de texto y un
triángulo de reproducción: leer + escuchar, que es de lo que va la app.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (17, 18, 20)
FG = (238, 236, 231)
ACCENT = (217, 164, 65)

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public"


class Canvas:
    def __init__(self, size: int, background: tuple[int, int, int] | None = None):
        self.size = size
        self.px = [[background or (0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
        if background:
            self.px = [[(*background, 255) for _ in range(size)] for _ in range(size)]

    def set(self, x: int, y: int, color: tuple[int, int, int], alpha: int = 255) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            self.px[y][x] = (*color, alpha)

    def rect(self, x0: float, y0: float, x1: float, y1: float, color) -> None:
        for y in range(int(y0), int(y1)):
            for x in range(int(x0), int(x1)):
                self.set(x, y, color)

    def rounded_rect(self, x0, y0, x1, y1, radius, color) -> None:
        for y in range(int(y0), int(y1)):
            for x in range(int(x0), int(x1)):
                cx = min(max(x, x0 + radius), x1 - radius)
                cy = min(max(y, y0 + radius), y1 - radius)
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius**2:
                    self.set(x, y, color)

    def triangle(self, ax, ay, bx, by, cx, cy, color) -> None:
        def sign(px, py, qx, qy, rx, ry):
            return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)

        min_x, max_x = int(min(ax, bx, cx)), int(max(ax, bx, cx)) + 1
        min_y, max_y = int(min(ay, by, cy)), int(max(ay, by, cy)) + 1
        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                d1 = sign(x, y, ax, ay, bx, by)
                d2 = sign(x, y, bx, by, cx, cy)
                d3 = sign(x, y, cx, cy, ax, ay)
                neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
                pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
                if not (neg and pos):
                    self.set(x, y, color)

    def to_png(self, path: Path) -> None:
        raw = b""
        for row in self.px:
            raw += b"\x00" + b"".join(bytes(p) for p in row)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.size, self.size, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(raw, 9))
        png += chunk(b"IEND", b"")
        path.write_bytes(png)


def draw_icon(size: int, maskable: bool = False) -> Canvas:
    canvas = Canvas(size)
    u = size / 100  # unidad relativa, para que escale a cualquier tamaño

    if maskable:
        # Zona segura: el fondo ocupa todo el lienzo
        canvas.rect(0, 0, size, size, BG)
        pad = 20 * u
    else:
        canvas.rounded_rect(0, 0, size, size, 22 * u, BG)
        pad = 22 * u

    # Tres líneas de texto
    line_h = max(1, int(5 * u))
    gap = 12 * u
    top = pad - 2 * u
    widths = (56, 56, 34)
    for index, width in enumerate(widths):
        y = top + index * gap
        canvas.rounded_rect(pad, y, pad + width * u, y + line_h, line_h / 2, FG)

    # Triángulo de reproducción
    cx, cy = size * 0.66, size * 0.735
    r = 15 * u
    canvas.triangle(cx - r * 0.55, cy - r, cx - r * 0.55, cy + r, cx + r * 0.85, cy, ACCENT)

    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        draw_icon(size).to_png(OUT / f"icon-{size}.png")
        print(f"✓ icon-{size}.png")
    draw_icon(512, maskable=True).to_png(OUT / "icon-maskable-512.png")
    print("✓ icon-maskable-512.png")


if __name__ == "__main__":
    main()
