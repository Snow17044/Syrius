"""Génère les icônes PNG de l'app (sans dépendance externe)."""
import math
import struct
import sys
import zlib
from pathlib import Path


def png(size: int) -> bytes:
    rows = []
    c = size / 2
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            d = math.hypot(x + .5 - c, y + .5 - c) / (size / 2)
            ang = math.atan2(y - c, x - c)
            r, g, b = 5, 8, 15
            if d < 0.75:
                t = d / 0.75
                if t < 0.3:
                    r, g, b = 232, 251, 255
                else:
                    k = (t - 0.3) / 0.7
                    r = int(56 * (1 - k) + 11 * k); g = int(217 * (1 - k) + 79 * k); b = int(255 * (1 - k) + 115 * k)
            if 0.56 < d < 0.62 and (math.degrees(ang) % 90) < 62:
                r, g, b = 191, 244, 255
            row += bytes((r, g, b))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "web/icons")
    for s in (192, 512):
        (out / f"icon-{s}.png").write_bytes(png(s))
    print("ok")
