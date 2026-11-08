"""냄쿵타자기와 다른 글꼴의 글자 모양을 비교해 닮음 정도를 숫자로 남긴다.

글자마다 두 글꼴을 같은 크기로 그린 뒤 잉크 영역을 64×64 칸에 맞춰 겹쳐 보고,
겹친 칸 수를 합친 칸 수로 나눈 값(IoU, 0~1)을 잰다. 같은 윤곽을 옮겨 쓰면
값이 1 에 가깝게 나온다. 비교 기준선으로 냄쿵타자기 세 판끼리도 같은 방법으로 잰다.

사용 예:
    python compare_fonts.py --ours build/NaemkungTypewriter-Regular.ttf \
        --calib build/NaemkungTypewriter-Clean.ttf \
        --refs /tmp/cmpfonts/*.ttf --out provenance
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

RENDER_PX = 96
GRID = 64
TOP_PAIRS = 12


def sample_chars() -> list[str]:
    """KS X 1001 한글 2,350자와 영문·숫자 62자."""
    hangul = []
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                hangul.append(bytes([lead, trail]).decode("euc-kr"))
            except UnicodeDecodeError:
                continue
    ascii_chars = [chr(c) for c in range(0x30, 0x3A)]
    ascii_chars += [chr(c) for c in range(0x41, 0x5B)]
    ascii_chars += [chr(c) for c in range(0x61, 0x7B)]
    return hangul + ascii_chars


def load_font(path: Path) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), RENDER_PX, index=0)


def _cmap_has(font: ImageFont.FreeTypeFont, ch: str) -> bool:
    cmap = getattr(font, "_nk_cmap", None)
    if cmap is None:
        from fontTools.ttLib import TTFont

        tt = TTFont(font.path, fontNumber=0, lazy=True)
        cmap = set(tt.getBestCmap())
        font._nk_cmap = cmap
    return ord(ch) in cmap


def bitmap(font: ImageFont.FreeTypeFont, ch: str) -> np.ndarray | None:
    """글자 잉크 영역을 잘라 가로세로 비율을 지킨 채 GRID×GRID 가운데에 맞춘다."""
    size = RENDER_PX * 2
    img = Image.new("L", (size, size), 0)
    ImageDraw.Draw(img).text((RENDER_PX // 2, RENDER_PX // 4), ch, font=font, fill=255)
    box = img.getbbox()
    if box is None:
        return None
    crop = img.crop(box)
    w, h = crop.size
    scale = (GRID - 2) / max(w, h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    crop = crop.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("L", (GRID, GRID), 0)
    canvas.paste(crop, ((GRID - nw) // 2, (GRID - nh) // 2))
    return np.asarray(canvas) > 127


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def font_label(path: Path) -> str:
    return path.stem


def compare(ours: Path, other: Path, chars: list[str]) -> list[tuple[str, float]]:
    fa, fb = load_font(ours), load_font(other)
    scores = []
    for ch in chars:
        if not (_cmap_has(fa, ch) and _cmap_has(fb, ch)):
            continue
        a, b = bitmap(fa, ch), bitmap(fb, ch)
        if a is None or b is None:
            continue
        scores.append((ch, iou(a, b)))
    return scores


def is_hangul(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def summarize(scores: list[tuple[str, float]]) -> dict:
    vals = np.array([s for _, s in scores])
    top = sorted(scores, key=lambda x: -x[1])[:TOP_PAIRS]
    hangul = [s for ch, s in scores if is_hangul(ch)]
    return {
        "hangul_mean": round(float(np.mean(hangul)), 3),
        "hangul_max": round(float(np.max(hangul)), 3),
        "glyphs": int(vals.size),
        "mean": round(float(vals.mean()), 3),
        "p99": round(float(np.percentile(vals, 99)), 3),
        "max": round(float(vals.max()), 3),
        "over_0_8": int((vals >= 0.8).sum()),
        "top": [[ch, round(s, 3)] for ch, s in top],
    }


def fitted(font: ImageFont.FreeTypeFont, ch: str, side: int) -> Image.Image:
    """글자 잉크 영역만 잘라 side×side 칸 가운데에 맞춘 그림(비교에 쓴 것과 같은 정렬)."""
    size = RENDER_PX * 2
    img = Image.new("L", (size, size), 0)
    ImageDraw.Draw(img).text((RENDER_PX // 2, RENDER_PX // 4), ch, font=font, fill=255)
    crop = img.crop(img.getbbox())
    scale = side / max(crop.size)
    crop = crop.resize(
        (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("L", (side, side), 0)
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    return canvas


def pair_sheet(
    ours: Path, rows: list[tuple[Path, str, float]], out: Path, label_path: Path
) -> None:
    """가장 닮게 나온 글자 쌍을 나란히 그려 눈으로 확인할 수 있게 한다."""
    cell = 110
    label_w = 330
    img = Image.new("RGB", (label_w + cell * 2, cell * len(rows)), "white")
    d = ImageDraw.Draw(img)
    label_font = ImageFont.truetype(str(label_path), 20)
    fo = load_font(ours)
    for i, (other, ch, score) in enumerate(rows):
        y = i * cell
        d.text((10, y + 30), f"{font_label(other)}", font=label_font, fill="black")
        d.text(
            (10, y + 60),
            f"\u201c{ch}\u201d  IoU {score:.3f}",
            font=label_font,
            fill="#555",
        )
        for col, (font, color) in enumerate(
            [(fo, (0, 0, 0)), (load_font(other), (138, 28, 28))]
        ):
            glyph = fitted(font, ch, cell - 14)
            ink = Image.new("RGB", glyph.size, color)
            img.paste(ink, (label_w + col * cell + 7, y + 7), glyph)
        d.line([(0, y + cell - 1), (img.width, y + cell - 1)], fill="#ddd")
    img.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", type=Path, required=True)
    ap.add_argument("--calib", type=Path, nargs="*", default=[])
    ap.add_argument("--refs", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--label-font",
        type=Path,
        default=Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    )
    args = ap.parse_args()

    chars = sample_chars()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "ours": font_label(args.ours),
        "method": {
            "render_px": RENDER_PX,
            "grid": GRID,
            "chars": len(chars),
            "metric": "IoU of ink bitmaps after bbox fit",
        },
        "calibration": {},
        "references": {},
    }

    for path in args.calib:
        report["calibration"][font_label(path)] = summarize(
            compare(args.ours, path, chars)
        )
    best: list[tuple[Path, str, float]] = []
    best_hangul: list[tuple[Path, str, float]] = []
    for path in args.refs:
        if font_label(path) in report["references"]:
            continue
        scores = compare(args.ours, path, chars)
        if not scores:
            continue
        report["references"][font_label(path)] = summarize(scores)
        best.append((path, *max(scores, key=lambda x: x[1])))
        hangul = [x for x in scores if is_hangul(x[0])]
        best_hangul.append((path, *max(hangul, key=lambda x: x[1])))

    (args.out / "similarity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    best.sort(key=lambda x: -x[2])
    best_hangul.sort(key=lambda x: -x[2])
    pair_sheet(args.ours, best, args.out / "most_similar_pairs.png", args.label_font)
    pair_sheet(
        args.ours, best_hangul, args.out / "most_similar_hangul.png", args.label_font
    )
    for name, r in {**report["calibration"], **report["references"]}.items():
        print(
            f"{name:40s} n={r['glyphs']:5d} mean={r['mean']:.3f} "
            f"p99={r['p99']:.3f} max={r['max']:.3f} >=0.8:{r['over_0_8']} "
            f"hangul_mean={r['hangul_mean']:.3f} hangul_max={r['hangul_max']:.3f}"
        )


if __name__ == "__main__":
    main()
