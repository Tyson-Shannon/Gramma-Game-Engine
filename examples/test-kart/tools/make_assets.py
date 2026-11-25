"""Regenerates the test-kart source assets (PNG sprite sheet, PNG map, WAV)."""

from pathlib import Path
import math
import struct
import wave

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def make_kart() -> None:
    sheet = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    body = (32, 96, 220, 255)
    glass = (150, 220, 250, 255)
    tyre = (24, 24, 28, 255)
    light = (255, 230, 90, 255)
    tail = (220, 50, 50, 255)

    # Up
    draw.rectangle((2, 4, 4, 11), fill=tyre)
    draw.rectangle((11, 4, 13, 11), fill=tyre)
    draw.rectangle((4, 2, 11, 13), fill=body)
    draw.rectangle((5, 4, 10, 6), fill=glass)
    draw.rectangle((5, 1, 6, 2), fill=light)
    draw.rectangle((9, 1, 10, 2), fill=light)
    # Right
    draw.rectangle((18, 2, 25, 4), fill=tyre)
    draw.rectangle((18, 11, 25, 13), fill=tyre)
    draw.rectangle((20, 4, 31, 11), fill=body)
    draw.rectangle((26, 5, 28, 10), fill=glass)
    draw.rectangle((30, 5, 31, 6), fill=light)
    draw.rectangle((30, 9, 31, 10), fill=light)
    # Down
    draw.rectangle((34, 4, 36, 11), fill=tyre)
    draw.rectangle((43, 4, 45, 11), fill=tyre)
    draw.rectangle((36, 2, 43, 13), fill=body)
    draw.rectangle((37, 9, 42, 11), fill=glass)
    draw.rectangle((37, 13, 38, 14), fill=tail)
    draw.rectangle((41, 13, 42, 14), fill=tail)
    # Left
    draw.rectangle((50, 2, 57, 4), fill=tyre)
    draw.rectangle((50, 11, 57, 13), fill=tyre)
    draw.rectangle((52, 4, 63, 11), fill=body)
    draw.rectangle((53, 5, 55, 10), fill=glass)
    draw.rectangle((52, 5, 53, 6), fill=light)
    draw.rectangle((52, 9, 53, 10), fill=light)
    sheet.save(ASSETS / "kart.png")


def make_altkart() -> None:
    """A distinct kart sheet stored in the second NES CHR bank."""
    sheet = Image.new("RGBA", (64, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    body = (224, 96, 32, 255)
    glass = (255, 220, 160, 255)
    tyre = (40, 30, 26, 255)
    light = (255, 245, 210, 255)
    tail = (180, 24, 24, 255)

    draw.rectangle((2, 4, 4, 11), fill=tyre)
    draw.rectangle((11, 4, 13, 11), fill=tyre)
    draw.rectangle((4, 2, 11, 13), fill=body)
    draw.rectangle((5, 4, 10, 6), fill=glass)
    draw.rectangle((5, 1, 6, 2), fill=light)
    draw.rectangle((9, 1, 10, 2), fill=light)

    draw.rectangle((18, 2, 25, 4), fill=tyre)
    draw.rectangle((18, 11, 25, 13), fill=tyre)
    draw.rectangle((20, 4, 31, 11), fill=body)
    draw.rectangle((26, 5, 28, 10), fill=glass)
    draw.rectangle((30, 5, 31, 6), fill=light)
    draw.rectangle((30, 9, 31, 10), fill=light)

    draw.rectangle((34, 4, 36, 11), fill=tyre)
    draw.rectangle((43, 4, 45, 11), fill=tyre)
    draw.rectangle((36, 2, 43, 13), fill=body)
    draw.rectangle((37, 9, 42, 11), fill=glass)
    draw.rectangle((37, 13, 38, 14), fill=tail)
    draw.rectangle((41, 13, 42, 14), fill=tail)

    draw.rectangle((50, 2, 57, 4), fill=tyre)
    draw.rectangle((50, 11, 57, 13), fill=tyre)
    draw.rectangle((52, 4, 63, 11), fill=body)
    draw.rectangle((53, 5, 55, 10), fill=glass)
    draw.rectangle((52, 5, 53, 6), fill=light)
    draw.rectangle((52, 9, 53, 10), fill=light)
    sheet.save(ASSETS / "altkart.png")


def make_track() -> None:
    image = Image.new("RGBA", (256, 224), (26, 96, 44, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, 224, 16):
        for x in range(0, 256, 16):
            if ((x // 16) + (y // 16)) % 2 == 0:
                draw.rectangle((x, y, x + 15, y + 15), fill=(32, 112, 50, 255))

    draw.rectangle((0, 64, 255, 159), fill=(70, 70, 76, 255))
    for x in range(0, 256, 16):
        color = (210, 60, 60, 255) if (x // 16) % 2 == 0 else (235, 235, 235, 255)
        draw.rectangle((x, 64, x + 15, 71), fill=color)
        draw.rectangle((x, 152, x + 15, 159), fill=color)
    for x in range(0, 256, 32):
        draw.rectangle((x, 108, x + 15, 115), fill=(225, 225, 225, 255))

    for y in range(64, 160, 8):
        for x in range(8, 24, 8):
            color = (245, 245, 245, 255) if ((x + y) // 8) % 2 == 0 else (20, 20, 20, 255)
            draw.rectangle((x, y, x + 7, y + 7), fill=color)
    image.save(ASSETS / "track.png")


def make_engine() -> None:
    rate, seconds = 22050, 0.10
    with wave.open(str(ASSETS / "engine.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = []
        for i in range(int(rate * seconds)):
            envelope = 1.0 - i / (rate * seconds)
            value = 9000 * envelope * math.sin(2 * math.pi * 190 * i / rate)
            value += 2000 * envelope * math.sin(2 * math.pi * 380 * i / rate)
            frames.append(struct.pack("<h", int(value)))
        output.writeframes(b"".join(frames))


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    make_kart()
    make_altkart()
    make_track()
    make_engine()
    print(f"assets written to {ASSETS}")
