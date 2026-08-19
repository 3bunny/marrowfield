#!/usr/bin/env python3
"""
Marrowfield — the daily job.

Steps the world one day, renders the day's scenes, composes a Short, uploads it,
and commits the new world state. The world state file IS the canon; it is the
only thing here that must never be lost.

Design rules enforced in code:
  * A day already present in the chronicle is never re-simulated. The world
    advances exactly once per day, or not at all.
  * The episode is written from the state diff by simulate.py. This file only
    renders what it is given.
  * If image generation fails partway, nothing is committed — the world does not
    half-advance.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
CHRONICLE = ROOT / "chronicle"
BUILD = ROOT / "build"
WORLD = ROOT / "world.json"
LOG = ROOT / "log.jsonl"


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def day_number(cfg: dict, today: dt.date) -> int:
    start = dt.date.fromisoformat(cfg["start_date"])
    return (today - start).days + 1


# ----------------------------------------------------------------------------
# generation
# ----------------------------------------------------------------------------

def generate_image(prompt: str, cfg: dict, out_path: Path) -> None:
    import requests

    account = os.environ["CF_ACCOUNT_ID"]
    token = os.environ["CF_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{cfg['image_model']}"

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt, **cfg.get("image_params", {})},
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Cloudflare returned {resp.status_code}: {resp.text[:600]}")

    if "application/json" in resp.headers.get("content-type", ""):
        payload = resp.json()
        if not payload.get("success", True):
            raise RuntimeError(f"Cloudflare error: {payload.get('errors')}")
        b64 = (payload.get("result") or {}).get("image")
        if not b64:
            raise RuntimeError(f"No image in response: {str(payload)[:400]}")
        out_path.write_bytes(base64.b64decode(b64))
        return

    out_path.write_bytes(resp.content)


# ----------------------------------------------------------------------------
# composition
# ----------------------------------------------------------------------------

def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    for n in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(n).exists():
            return ImageFont.truetype(n, size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _centre(draw, y: int, text: str, font, fill, W: int) -> int:
    w = draw.textlength(text, font=font)
    draw.text(((W - w) // 2, y), text, font=font, fill=fill)
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def compose_scene(cfg: dict, day: int, date_str: str, scene: dict,
                  idx: int, total: int, img_path: Path, out_path: Path) -> None:
    from PIL import Image, ImageDraw

    W, H = cfg["frame_width"], cfg["frame_height"]
    BG, INK, DIM, AC = (12, 12, 14), (233, 229, 220), (135, 130, 122), (196, 155, 104)

    frame = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(frame)

    _centre(draw, 92, "MARROWFIELD", _font(44, bold=True), AC, W)
    _centre(draw, 152, date_str, _font(26), DIM, W)

    img = Image.open(img_path).convert("RGB")
    iw = 1000
    img = img.resize((iw, max(1, round(img.size[1] * iw / img.size[0]))))
    top = 250
    frame.paste(img, ((W - iw) // 2, top))
    y = top + img.size[1] + 62

    body = _font(42)
    for line in scene["lines"]:
        for piece in _wrap(draw, line, body, W - 150):
            _centre(draw, y, piece, body, INK, W)
            y += 60
        y += 16

    dots = "   ".join("●" if i == idx else "○" for i in range(total))
    _centre(draw, H - 150, dots, _font(22), DIM, W)
    _centre(draw, H - 104, f"day {day} of {cfg['total_days']}", _font(20), DIM, W)

    frame.save(out_path)


def render_scene_clip(cfg: dict, frame_path: Path, out_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-loop", "1", "-i", str(frame_path),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", str(cfg["seconds_per_scene"]),
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-r", "30",
         "-c:a", "aac", "-b:a", "96k", "-shortest", str(out_path)],
        check=True,
    )


def concat_clips(clips: list[Path], out_path: Path) -> None:
    listing = BUILD / "concat.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listing.name, "-c", "copy", out_path.name],
        check=True, cwd=BUILD,
    )


# ----------------------------------------------------------------------------
# upload
# ----------------------------------------------------------------------------

def upload(cfg: dict, video: Path, entry: dict, world: dict) -> str | None:
    if os.environ.get("SKIP_UPLOAD") == "1":
        print("SKIP_UPLOAD=1 — not uploading.")
        return None

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    narration = "\n".join(l for s in entry["scenes"] for l in s["lines"])
    river = world["river"]
    description = (
        f"{entry['date']}\n\n{narration}\n\n"
        "— \n"
        "Marrowfield is a chalk valley with a river, three factions and a lie in the "
        "historical record. Every morning the world advances one day under its own rules, "
        "and the episode is written from what changed. Nothing is retconned. If someone "
        "dies they stay dead.\n\n"
        f"river level: {river['level']} / 100\n"
        f"flooded: {river['flooded']}\n"
        f"event: {entry['event']}\n"
        f"world day: {entry['day']} of {cfg['total_days']}\n\n"
        "The full world state and every episode are committed to a public git repository "
        "the morning they are made, so the chronicle is verifiable rather than claimed.\n\n"
        "#Shorts"
    )

    body = {
        "snippet": {
            "title": f"Marrowfield — Day {entry['day']:03d}",
            "description": description[:4900],
            "tags": ["marrowfield", "worldbuilding", "simulation", "chronicle", "shorts"],
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": os.environ.get("YT_PRIVACY", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }

    req = youtube.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True),
    )
    return req.execute().get("id")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main() -> None:
    cfg = load_config()
    tz = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(tz)
    day = day_number(cfg, now.date())

    if day < 1:
        sys.exit(f"Marrowfield has not begun (starts {cfg['start_date']}).")
    if day > cfg["total_days"]:
        print(f"Day {day} is past the end of the chronicle. The story is finished.")
        return

    CHRONICLE.mkdir(exist_ok=True)
    ARCHIVE.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)

    entry_path = CHRONICLE / f"day-{day:04d}.json"
    if entry_path.exists():
        print(f"Day {day} is already chronicled. The world does not advance twice.")
        return

    world = json.loads(WORLD.read_text(encoding="utf-8"))
    world.setdefault("projects", {})

    if world.get("day", 0) >= day:
        sys.exit(f"World is already at day {world['day']}; refusing to step backwards.")

    entry = simulate.step(world, day)
    print(f"Day {day} — {entry['event']} — {entry['date']}")

    scene_dir = ARCHIVE / f"day-{day:04d}"
    scene_dir.mkdir(exist_ok=True)

    # Generate every image before touching the world file. If any call fails the
    # run dies here and tomorrow retries cleanly.
    images = []
    for i, scene in enumerate(entry["scenes"], start=1):
        p = scene_dir / f"scene-{i}.png"
        if not p.exists():
            generate_image(scene["prompt"], cfg, p)
        images.append(p)

    clips = []
    for i, (scene, img) in enumerate(zip(entry["scenes"], images)):
        frame = BUILD / f"frame-{day:04d}-{i+1}.png"
        clip = BUILD / f"clip-{day:04d}-{i+1}.mp4"
        compose_scene(cfg, day, entry["date"], scene, i, len(entry["scenes"]), img, frame)
        render_scene_clip(cfg, frame, clip)
        clips.append(clip)

    video = BUILD / f"day-{day:04d}.mp4"
    concat_clips(clips, video)

    video_id = upload(cfg, video, entry, world)

    entry["video_id"] = video_id
    entry["privacy"] = os.environ.get("YT_PRIVACY", "private")
    entry_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    WORLD.write_text(json.dumps(world, indent=2, ensure_ascii=False), encoding="utf-8")

    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "day": day,
            "generated_at": now.isoformat(),
            "event": entry["event"],
            "recurring": entry["recurring"],
            "river_level": entry["river_level"],
            "tension": entry["tension_after"],
            "video_id": video_id,
        }) + "\n")

    print(f"done — {video.name}, video_id={video_id}")


if __name__ == "__main__":
    main()
