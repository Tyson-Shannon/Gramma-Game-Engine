"""Text tracker score -> portable gr_note events + PSGlib-format stream.

The score language is deliberately small: directives declare tempo, timing,
channel count and patterns; each pattern row is one 16th-note tick with one cell
per channel. It is compiled ahead of time on the host, like images and WAVs.
The emitted C exports ``const gr_song <name>`` so C and Grain code can use the
asset exactly like a hand-written song.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .project import MusicAsset


MAX_BPM = 65535
MAX_FPS = 255
MAX_VOLUME = 15
PSG_DIVISOR = 111860  # SN76489 tone divisor for the NTSC SMS/GG master clock
WAVES = {
    "square": "GR_WAVE_SQUARE",
    "triangle": "GR_WAVE_TRIANGLE",
    "saw": "GR_WAVE_SAW",
    "noise": "GR_WAVE_NOISE",
}
DIRECTIVES = {"bpm", "fps", "loop", "channels", "wave", "pattern", "order"}
SEMITONES = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
NOTE_RE = re.compile(r"^([A-Ga-g])([#b-]?)([0-8])$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class MusicError(ValueError):
    """A score could not be parsed or compiled."""


@dataclass(frozen=True)
class Cell:
    """A triggered note; ``midi is None`` is an explicit note-off/rest."""

    midi: int | None
    volume: int


@dataclass
class Pattern:
    name: str
    rows: list[list[Cell | None]] = field(default_factory=list)


@dataclass
class Score:
    bpm: int
    fps: int
    loop: bool
    channels: int
    wave: str
    patterns: dict[str, Pattern] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    @property
    def rows(self) -> list[list[Cell | None]]:
        rows: list[list[Cell | None]] = []
        for name in self.order:
            rows.extend(self.patterns[name].rows)
        return rows

    @property
    def frames_per_row(self) -> int:
        # One 16th note lasts 60/BPM/4 = 15/BPM seconds.
        return max(1, math.floor(self.fps * 15 / self.bpm + 0.5))


@dataclass
class MusicResult:
    name: str
    note_count: int
    psg_bytes: int
    frames: int
    duration_ms: int
    source: str
    rom_bytes: int
    source_text: str


def _fail(filename: str, line: int, message: str) -> MusicError:
    return MusicError(f"{filename}:{line}: {message}")


def _note_frequency(midi: int) -> int:
    """Scientific pitch notation to rounded Hz (A4 = 440 Hz)."""

    return max(1, min(65535, round(440.0 * 2.0 ** ((midi - 69) / 12.0))))


def _parse_cell(text: str, filename: str, line: int) -> Cell | None:
    if text == "-":
        return None  # hold: no new event on this channel
    if text.lower() == "off":
        return Cell(None, 0)
    match = re.fullmatch(r"(.+):([0-9]+)", text)
    if match is None:
        raise _fail(filename, line, f"invalid cell {text!r} (expected - or NOTE:VOL)")
    name, volume_text = match.groups()
    note = NOTE_RE.fullmatch(name)
    if note is None:
        raise _fail(filename, line, f"invalid note {name!r}")
    letter, accidental, octave = note.groups()
    semitone = SEMITONES[letter.lower()]
    if accidental == "#":
        semitone += 1
    elif accidental == "b":
        semitone -= 1
    midi = (int(octave) + 1) * 12 + semitone
    if not 0 <= midi <= 127:
        raise _fail(filename, line, f"note {name!r} is outside MIDI range")
    volume = int(volume_text)
    if volume > MAX_VOLUME:
        raise _fail(filename, line, f"volume {volume} exceeds {MAX_VOLUME}")
    return Cell(midi, volume)


def _parse_int(parts: list[str], filename: str, line: int, low: int,
               high: int) -> int:
    try:
        value = int(parts[1])
    except (IndexError, ValueError):
        raise _fail(filename, line, f"expected an integer, got {' '.join(parts)!r}")
    if not low <= value <= high:
        raise _fail(filename, line, f"value {value} is outside {low}..{high}")
    return value


def parse_score(text: str, filename: str = "score.tick") -> Score:
    """Parse a tracker score. Errors include the source file and line number."""

    score = Score(bpm=120, fps=50, loop=True, channels=1, wave="square")
    current: Pattern | None = None
    saw_pattern = False

    for line_number, raw in enumerate(text.splitlines(), 1):
        # ';' always starts a comment; '#' does so only at the start of a token
        # so sharps in note names (C#4) survive.
        line = raw.split(";", 1)[0]
        line = re.split(r"(?<!\S)#", line, maxsplit=1)[0].strip()
        if not line:
            continue
        parts = line.split()
        keyword = parts[0].lower()

        if keyword not in DIRECTIVES:
            if current is None:
                raise _fail(filename, line_number,
                            "row outside a pattern (add 'pattern <name>' first)")
            if len(parts) != score.channels:
                raise _fail(filename, line_number,
                            f"row has {len(parts)} cell(s), "
                            f"expected {score.channels}")
            current.rows.append([_parse_cell(cell, filename, line_number)
                                 for cell in parts])
            continue

        current = None
        if keyword == "bpm":
            score.bpm = _parse_int(parts, filename, line_number, 1, MAX_BPM)
        elif keyword == "fps":
            score.fps = _parse_int(parts, filename, line_number, 1, MAX_FPS)
        elif keyword == "channels":
            if saw_pattern:
                raise _fail(filename, line_number,
                            "channels must be declared before any pattern")
            score.channels = _parse_int(parts, filename, line_number, 1, 4)
        elif keyword == "wave":
            if len(parts) != 2 or parts[1].lower() not in WAVES:
                raise _fail(filename, line_number,
                            "wave must be one of " + ", ".join(WAVES))
            score.wave = parts[1].lower()
        elif keyword == "loop":
            if len(parts) > 2:
                raise _fail(filename, line_number, "loop takes on or off")
            setting = parts[1].lower() if len(parts) == 2 else "on"
            if setting not in ("on", "off", "true", "false", "1", "0"):
                raise _fail(filename, line_number, "loop takes on or off")
            score.loop = setting in ("on", "true", "1")
        elif keyword == "pattern":
            if len(parts) != 2 or not NAME_RE.fullmatch(parts[1]):
                raise _fail(filename, line_number,
                            "pattern needs one identifier name")
            name = parts[1]
            if name in score.patterns:
                raise _fail(filename, line_number,
                            f"duplicate pattern {name!r}")
            current = Pattern(name)
            score.patterns[name] = current
            saw_pattern = True
        elif keyword == "order":
            if score.order:
                raise _fail(filename, line_number, "duplicate order directive")
            if len(parts) < 2:
                raise _fail(filename, line_number,
                            "order needs at least one pattern name")
            score.order = parts[1:]

    if not score.order:
        raise MusicError(f"{filename}: missing order directive")
    for name in score.order:
        if name not in score.patterns:
            raise MusicError(f"{filename}: order references undefined pattern {name!r}")
    for pattern in score.patterns.values():
        if not pattern.rows:
            raise MusicError(f"{filename}: pattern {pattern.name!r} has no rows")
    return score


def _portable_notes(score: Score) -> list[tuple[int, int, int, str]]:
    """Flatten the lead channel into (freq, ticks, volume, wave) events.

    The portable players share one time cursor and mostly play a single voice,
    so v1 emits channel 0 here. Full multi-channel playback ships in the SMS/GG
    PSG stream; other targets keep the existing one-note-at-a-time sequencer.
    """

    triggers = [i for i, row in enumerate(score.rows)
                if row[0] is not None]
    if not triggers:
        return [(0, len(score.rows), 0, score.wave)]
    notes: list[tuple[int, int, int, str]] = []
    for position, start in enumerate(triggers):
        end = (triggers[position + 1] if position + 1 < len(triggers)
               else len(score.rows))
        cell = score.rows[start][0]
        assert cell is not None
        freq = 0 if cell.midi is None else _note_frequency(cell.midi)
        volume = cell.volume if cell.midi is not None else 0
        notes.append((freq, end - start, volume, score.wave))
    return notes


def _psg_writes(channel: int, cell: Cell) -> list[int]:
    """SN76489 register writes in PSGlib format (latch, then |0x40 data)."""

    psg_channel = 3 if channel == 3 else channel
    shift = psg_channel << 5
    if cell.midi is None or cell.volume == 0:
        return [0x80 | shift | 0x10, 0x40 | 0x0f]
    freq = _note_frequency(cell.midi)
    if channel == 3:
        # The noise channel has no 10-bit period; use the note's pitch class.
        period = 1 + cell.midi % 15
    else:
        period = max(1, min(1023, PSG_DIVISOR // freq))
    attenuation = MAX_VOLUME - cell.volume
    return [
        0x80 | shift | (period & 0x0f), 0x40 | (period >> 4),
        0x80 | shift | 0x10, 0x40 | attenuation,
    ]


def _psg_stream(score: Score) -> list[int]:
    """Uncompressed PSGlib byte stream: writes, frame waits, loop and end."""

    stream: list[int] = [0x01] if score.loop else []
    frames_per_row = score.frames_per_row
    for row in score.rows:
        for channel, cell in enumerate(row):
            if cell is not None:
                stream.extend(_psg_writes(channel, cell))
        remaining = frames_per_row
        while remaining > 0:
            wait = min(remaining, 8)
            stream.append(0x38 | (wait - 1))
            remaining -= wait
    stream.append(0x00)
    return stream


def _c_rows(values: list[int], per_row: int = 16) -> str:
    rows = []
    for start in range(0, len(values), per_row):
        rows.append("    " + ", ".join(f"0x{value:02x}"
                                       for value in values[start:start + per_row]))
    return ",\n".join(rows)


def compile_score(score: Score, name: str, source: str, psg: bool = False) \
        -> MusicResult:
    """Compile a parsed score into C source exporting ``const gr_song name``."""

    ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
    notes = _portable_notes(score)
    if len(notes) > 65535:
        raise MusicError(f"{source}: score has {len(notes)} notes; "
                         "gr_song.note_count is 16-bit")
    note_lines = [
        "    { %d, %d, %d, 0, %s }" % (freq, ticks, volume, WAVES[wave])
        for freq, ticks, volume, wave in notes
    ]
    lines = [
        "/* Generated by the Gramma asset pipeline. DO NOT EDIT. */",
        f"/* From {source}: {score.bpm} BPM, {score.fps} fps, "
        f"{score.channels} channel(s), "
        f"{'loop' if score.loop else 'one shot'}. */",
        "#include <gramma/gramma.h>",
        "",
        f"static const gr_note {ident}_notes[] = {{",
        ",\n".join(note_lines),
        "};",
        "",
    ]
    stream = _psg_stream(score) if psg else []
    if psg:
        lines += [
            f"/* Uncompressed PSGlib stream: {len(stream)} bytes. */",
            f"static const uint8_t {ident}_psg[] = {{",
            _c_rows(stream),
            "};",
            "",
        ]
    psg_expr = f"{ident}_psg" if psg else "NULL"
    lines += [
        f"const gr_song {ident} = {{",
        f"    {score.bpm}, sizeof({ident}_notes) / sizeof({ident}_notes[0]),",
        f"    {ident}_notes, {'true' if score.loop else 'false'}, {psg_expr}",
        "};",
        "",
    ]
    frames = len(score.rows) * score.frames_per_row
    return MusicResult(
        name=name,
        note_count=len(notes),
        psg_bytes=len(stream),
        frames=frames,
        duration_ms=round(frames * 1000 / score.fps),
        source=source,
        # Approximate target-side ROM use: 8 bytes per packed gr_note plus PSG.
        rom_bytes=len(notes) * 8 + len(stream),
        source_text="\n".join(lines),
    )


def process_music(asset: MusicAsset, psg: bool = False) -> MusicResult:
    """Read a score file and compile it; *psg* chooses the SMS/GG byte stream."""

    if not asset.file.is_file():
        raise FileNotFoundError(f"missing music score: {asset.file}")
    text = asset.file.read_text(encoding="utf-8")
    score = parse_score(text, asset.file.name)
    return compile_score(score, asset.name, asset.file.name, psg=psg)
