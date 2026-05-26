"""Share card generation — pump.fun style PNG cards for benchmark results."""
from __future__ import annotations

import io
import json
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter(prefix="/share", tags=["share"])

RUNS_DIR = Path("~/.bench-loop/runs").expanduser()


def _score_color(score: float) -> tuple[int, int, int]:
    """Return RGB color based on score (red → yellow → green)."""
    if score >= 85:
        return (34, 197, 94)  # green
    elif score >= 70:
        return (234, 179, 8)  # yellow
    elif score >= 50:
        return (249, 115, 22)  # orange
    else:
        return (239, 68, 68)  # red


def _draw_score_bar(draw, x: int, y: int, width: int, height: int, score: float, label: str):
    """Draw a labeled score bar."""
    from PIL import ImageDraw, ImageFont

    # Background bar
    draw.rounded_rectangle([x, y, x + width, y + height], radius=4, fill=(30, 30, 35))

    # Filled bar
    fill_width = max(0, int(width * min(score, 100) / 100))
    color = _score_color(score)
    if fill_width > 0:
        draw.rounded_rectangle([x, y, x + fill_width, y + height], radius=4, fill=color)

    # Label + score text
    try:
        font_small = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 11)
    except Exception:
        font_small = ImageFont.load_default()

    draw.text((x + 4, y + 2), label, fill=(180, 180, 190), font=font_small)
    draw.text((x + width - 35, y + 2), f"{score:.1f}", fill=(255, 255, 255), font=font_small)


def _generate_card(run_data: dict) -> bytes:
    """Generate a share card PNG from run data."""
    from PIL import Image, ImageDraw, ImageFont

    # Card dimensions (Twitter-friendly 1200x630)
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (13, 13, 16))
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/SFNSDisplay.ttf", 36)
        font_large = ImageFont.truetype("/System/Library/Fonts/SFNSDisplay.ttf", 64)
        font_body = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 16)
        font_small = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 13)
        font_badge = ImageFont.truetype("/System/Library/Fonts/SFNSDisplay.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font_large = font_title
        font_body = font_title
        font_small = font_title
        font_badge = font_title

    # Header bar
    draw.rectangle([0, 0, W, 4], fill=(34, 197, 94))

    # Brand
    draw.text((40, 24), "⚡ BENCHLOOP", fill=(34, 197, 94), font=font_badge)
    draw.text((40, 44), "local-first LLM benchmarking", fill=(120, 120, 130), font=font_small)

    # Model name
    model_id = run_data.get("model", {}).get("model_id", "Unknown Model")
    if len(model_id) > 45:
        model_id = model_id[:42] + "..."
    draw.text((40, 80), model_id, fill=(255, 255, 255), font=font_title)

    # Overall score (big)
    overall = run_data.get("overall_score", 0)
    color = _score_color(overall)
    draw.text((40, 135), f"{overall:.1f}", fill=color, font=font_large)
    draw.text((260, 175), "/ 100 overall", fill=(120, 120, 130), font=font_body)

    # Score bars
    bar_x, bar_w, bar_h = 40, 350, 28
    bar_y = 230

    quality = run_data.get("quality_score", 0)
    speed = run_data.get("speed_score", 0)
    reliability = run_data.get("reliability_score", 0)

    _draw_score_bar(draw, bar_x, bar_y, bar_w, bar_h, quality, "QUALITY")
    _draw_score_bar(draw, bar_x, bar_y + 40, bar_w, bar_h, speed, "SPEED")
    _draw_score_bar(draw, bar_x, bar_y + 80, bar_w, bar_h, reliability, "RELIABILITY")

    # Suite scores on the right
    suites = run_data.get("suites", {})
    suite_x = 440
    suite_y = 230
    for i, (name, data) in enumerate(suites.items()):
        score = data.get("score", 0)
        pass_c = data.get("pass_count", 0)
        total_c = data.get("task_count", 0)
        s_color = _score_color(score)
        draw.text((suite_x, suite_y + i * 28), name, fill=(180, 180, 190), font=font_small)
        draw.text((suite_x + 140, suite_y + i * 28), f"{score:.0f}", fill=s_color, font=font_body)
        draw.text((suite_x + 190, suite_y + i * 28), f"({pass_c}/{total_c})", fill=(100, 100, 110), font=font_small)

    # Hardware info
    machine = run_data.get("machine", {})
    gpu = machine.get("gpu", "Unknown GPU")
    gpu_mem = machine.get("gpu_memory_gb", "?")
    hw_y = 440

    # GPU badge
    badge_text = f"🖥 {gpu} {gpu_mem}GB"
    draw.rounded_rectangle([40, hw_y, 40 + len(badge_text) * 9 + 16, hw_y + 30], radius=6, fill=(30, 30, 35))
    draw.text((48, hw_y + 6), badge_text, fill=(200, 200, 210), font=font_badge)

    # Speed metrics
    speed_metrics = run_data.get("speed_metrics", {})
    tok_s = speed_metrics.get("generation_tok_per_sec", 0)
    ttft = speed_metrics.get("ttft_ms", 0)
    runtime = run_data.get("total_runtime_sec", 0)

    metrics_y = hw_y + 45
    draw.text((40, metrics_y), f"{tok_s:.1f} tok/s", fill=(34, 197, 94), font=font_body)
    draw.text((200, metrics_y), f"{ttft:.0f}ms TTFT", fill=(234, 179, 8), font=font_body)
    draw.text((360, metrics_y), f"{runtime:.0f}s runtime", fill=(180, 180, 190), font=font_body)

    # Cloud/Local badge
    is_remote = run_data.get("is_remote", False)
    scope = "☁ Cloud" if is_remote else "🏠 Local"
    draw.rounded_rectangle([W - 140, 24, W - 30, 50], radius=6, fill=(30, 30, 35))
    draw.text((W - 132, 28), scope, fill=(200, 200, 210), font=font_badge)

    # Profile info (bottom)
    profile = run_data.get("profile", {}) or {}
    profile_name = profile.get("name", "")
    if profile_name:
        draw.text((40, H - 50), f"by {profile_name}", fill=(140, 140, 150), font=font_small)

    # Footer
    draw.text((W - 250, H - 50), "bench-loop.com/leaderboard", fill=(80, 80, 90), font=font_small)

    # Border
    draw.rectangle([0, 0, W - 1, H - 1], outline=(40, 40, 45), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@router.get("/card/{run_id}")
async def get_share_card(run_id: str):
    """Generate a share card PNG for a benchmark run."""
    run_dir = RUNS_DIR / run_id
    run_file = run_dir / "run.json"
    if not run_file.exists():
        # Try matching by prefix
        for d in RUNS_DIR.iterdir():
            if d.name.startswith(run_id):
                run_file = d / "run.json"
                break
        if not run_file.exists():
            raise HTTPException(status_code=404, detail="Run not found")

    run_data = json.loads(run_file.read_text())
    png_bytes = _generate_card(run_data)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f'inline; filename="benchloop-{run_id}.png"',
        },
    )


@router.get("/tweet/{run_id}")
async def get_tweet_text(run_id: str):
    """Generate pre-filled tweet text for a benchmark run."""
    run_dir = RUNS_DIR / run_id
    run_file = run_dir / "run.json"
    if not run_file.exists():
        for d in RUNS_DIR.iterdir():
            if d.name.startswith(run_id):
                run_file = d / "run.json"
                break
        if not run_file.exists():
            raise HTTPException(status_code=404, detail="Run not found")

    run_data = json.loads(run_file.read_text())
    model = run_data.get("model", {}).get("model_id", "Unknown")
    overall = run_data.get("overall_score", 0)
    quality = run_data.get("quality_score", 0)
    speed_metrics = run_data.get("speed_metrics", {})
    tok_s = speed_metrics.get("generation_tok_per_sec", 0)
    machine = run_data.get("machine", {})
    gpu = machine.get("gpu", "Unknown GPU")

    tweet = (
        f"⚡ Benchmarked {model}\n\n"
        f"Overall: {overall:.1f}/100\n"
        f"Quality: {quality:.1f}\n"
        f"Speed: {tok_s:.1f} tok/s\n"
        f"GPU: {gpu}\n\n"
        f"#BenchLoop #LLM #LocalAI"
    )

    return {
        "text": tweet,
        "url": f"https://bench-loop.com/share/{run_id}",
        "card_url": f"/api/share/card/{run_id}",
    }
