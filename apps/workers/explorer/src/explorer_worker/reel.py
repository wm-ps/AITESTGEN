"""Stage 7 — the shareable highlight video (PLAN.md Step 9).

Picks the best moments (missions that found bugs or new screens, proofs of
known bugs), cuts ~7 seconds from each, puts a title card before each clip
and an opening/closing card with the numbers, and joins it all into one MP4
with ffmpeg. Text goes through `textfile=` so titles never need escaping.
"""

import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from domain import Application
from explorer_core import (
    ExplorerMission,
    ExplorerRecording,
    ExplorerRun,
    ExplorerScreen,
    ExplorerTestCase,
)
from sqlmodel import Session, col, select

from explorer_worker.db import engine
from explorer_worker.journal import Journal

WIDTH, HEIGHT, FPS = 1280, 800, 30
CLIP_SECONDS = 7.0
CARD_SECONDS = 2.6
MAX_CLIPS = 6
_FONTS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font() -> str | None:
    return next((f for f in _FONTS if Path(f).exists()), None)


def _ffmpeg(args: list[str], cwd: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], cwd=cwd, check=True, timeout=300)


def _wrap(text: str, width: int = 46) -> str:
    """Wrap each paragraph to `width` characters, keeping intended breaks."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            if line and len(line) + len(word) + 1 > width:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
    return "\n".join(lines[:5])


def _card(cwd: str, name: str, title: str, subtitle: str, seconds: float) -> str:
    Path(cwd, f"{name}-t.txt").write_text(_wrap(title, 38), encoding="utf-8")
    Path(cwd, f"{name}-s.txt").write_text(_wrap(subtitle, 60), encoding="utf-8")
    out = f"{name}.mp4"
    _ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0D6B64:s={WIDTH}x{HEIGHT}:d={seconds}:r={FPS}",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-shortest",
            "-vf",
            f"drawtext=fontfile=font.ttf:textfile={name}-t.txt:fontcolor=white:fontsize=54:"
            f"x=(w-text_w)/2:y=(h/2)-text_h-10:line_spacing=6,"
            f"drawtext=fontfile=font.ttf:textfile={name}-s.txt:fontcolor=0xD9F2EF:fontsize=28:"
            f"x=(w-text_w)/2:y=(h/2)+30:line_spacing=6,"
            f"fade=t=in:st=0:d=0.35,fade=t=out:st={seconds - 0.35}:d=0.35",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            out,
        ],  # fmt: skip
        cwd,
    )
    return out


def _clip(cwd: str, name: str, webm: bytes, duration: float, caption: str) -> str:
    Path(cwd, f"{name}.webm").write_bytes(webm)
    Path(cwd, f"{name}-c.txt").write_text(_wrap(caption, 80), encoding="utf-8")
    start = max(0.0, duration * 0.35 - 1) if duration > CLIP_SECONDS + 2 else 0.0
    out = f"{name}.mp4"
    _ffmpeg(
        [
            "-ss",
            f"{start:.1f}",
            "-t",
            f"{CLIP_SECONDS}",
            "-i",
            f"{name}.webm",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-shortest",
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=white,fps={FPS},"
            f"drawbox=x=0:y=ih-70:w=iw:h=70:color=black@0.62:t=fill,"
            f"drawtext=fontfile=font.ttf:textfile={name}-c.txt:fontcolor=white:fontsize=24:"
            f"x=28:y=h-52,fade=t=in:st=0:d=0.3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            out,
        ],  # fmt: skip
        cwd,
    )
    return out


def make_reel(run_id: uuid.UUID) -> bool:
    """Build and store the highlight video. False when there's nothing to
    show or ffmpeg/a font isn't available on this machine."""
    journal = Journal(run_id)
    font = _font()
    if shutil.which("ffmpeg") is None or font is None:
        journal.event(
            "thought",
            "Skipped the highlight video",
            "ffmpeg or a font isn't available on this machine.",
        )
        return False
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            return False
        app = session.get(Application, run.application_id)
        app_name = (run.brief or {}).get("app_name") or (app.name if app else "The app")
        missions = {
            m.id: m
            for m in session.exec(
                select(ExplorerMission).where(ExplorerMission.run_id == run_id)
            ).all()
        }
        tests = {
            t.id: t
            for t in session.exec(
                select(ExplorerTestCase).where(ExplorerTestCase.run_id == run_id)
            ).all()
        }
        recordings = session.exec(
            select(ExplorerRecording).where(
                ExplorerRecording.run_id == run_id, col(ExplorerRecording.kind) != "reel"
            )
        ).all()
        screens = session.exec(select(ExplorerScreen).where(ExplorerScreen.run_id == run_id)).all()

    picks: list[tuple[int, ExplorerRecording, str, str]] = []
    for rec in recordings:
        if rec.mission_id and rec.mission_id in missions:
            m = missions[rec.mission_id]
            score = (
                (3 if m.matches_expected is False else 0)
                + min(m.new_screens, 3)
                + (1 if m.status == "done" else 0)
            )
            subtitle = (
                "Possible bug found" if m.matches_expected is False
                else f"{m.new_screens} new screen(s) found" if m.new_screens
                else "Mission completed"
            )  # fmt: skip
            picks.append((score, rec, m.title, f"{subtitle} — {(m.outcome or '')[:120]}"))
        elif rec.test_case_id and rec.test_case_id in tests:
            t = tests[rec.test_case_id]
            if t.status == "known_bug":
                picks.append((4, rec, f"Known bug: {t.title}", f"Should: {t.expected[:90]}"))
            elif t.status == "proven":
                picks.append(
                    (1, rec, f"Proven test: {t.title}", "Replayed 3 times; fails when broken")
                )
    picks = sorted(picks, key=lambda p: -p[0])[:MAX_CLIPS]
    if not picks:
        return False

    hidden = sum(1 for s in screens if s.condition)
    proven = sum(1 for t in tests.values() if t.status == "proven")
    bugs = sum(1 for t in tests.values() if t.status == "known_bug") + sum(
        1 for m in missions.values() if m.matches_expected is False
    )
    numbers = f"{len(screens)} screens understood · {hidden} hidden · {proven} proven tests · {bugs} possible bugs"
    journal.event("phase", "Making the highlight video", f"{len(picks)} best moments")
    with tempfile.TemporaryDirectory(prefix="explorer-reel-") as cwd:
        shutil.copy(font, Path(cwd, "font.ttf"))
        parts = [_card(cwd, "intro", app_name, f"Explored by Vantage Explorer\n{numbers}", 3.4)]
        for index, (_, rec, title, subtitle) in enumerate(picks):
            parts.append(_card(cwd, f"card{index}", title, subtitle, CARD_SECONDS))
            parts.append(_clip(cwd, f"clip{index}", rec.data, rec.duration_seconds, title))
        parts.append(_card(cwd, "outro", "Vantage Explorer", numbers, 3.0))
        Path(cwd, "list.txt").write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        _ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "list.txt",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                "reel.mp4",
            ],
            cwd,
        )
        data = Path(cwd, "reel.mp4").read_bytes()
    with Session(engine) as session:
        for old in session.exec(
            select(ExplorerRecording).where(
                ExplorerRecording.run_id == run_id, ExplorerRecording.kind == "reel"
            )
        ).all():
            session.delete(old)
        session.add(
            ExplorerRecording(
                run_id=run_id,
                kind="reel",
                data=data,
                started_at=datetime.now(UTC),
                duration_seconds=round(3.4 + 3.0 + len(picks) * (CARD_SECONDS + CLIP_SECONDS), 1),
            )
        )
        session.commit()
    journal.event("summary", "Highlight video ready", "Find it on the Report — ready to share.")
    return True
