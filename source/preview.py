"""만든 서체로 견본 그림을 찍는다. T·B·C 는 앱이 그릴 때 얹는 타자 출력 효과를 흉내 낸다.

T 는 새 리본, B 는 낡은 리본, C 는 Bold 서체를 세게 친 것이다.

실행: python3 preview.py build/NaemkungTypewriter-Regular.ttf out.png
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LINES = [
    "오늘도 나의 작은 방에 편지를 남긴다. 1984",
    "아이묭단 출격! 아이묭은 내한 한번 더 해달라.",
    "추천곡은 3636",
    "밑줄 친 문장 · 말랑이와 함께 읽는 밤",
    "The quick brown fox jumps over the lazy dog.",
    '0O 1Il 5S 8B (a+b)*2=? "quote" #@$%&',
]
PAPER = (246, 241, 228)
INK = (24, 22, 20)


def typed(
    font_path: str,
    lines: list[str],
    size: int,
    width: int,
    seed: int = 3,
    worn: bool = False,
) -> Image.Image:
    """글자마다 따로 쳐서 찍은 것처럼 그린다.

    글자마다 잉크 농도·타격 위치가 다르고, 리본 천의 결이 비치며, 가장자리가 종이에 번진다.
    worn 이면 낡은 리본이다. 잉크가 말라 옅고, 리본에서 닳은 띠가 지나간 높이가
    더 옅게 빠지며, 천 결 사이로 종이가 비친다.
    """
    rng = np.random.default_rng(seed)
    force_mean, force_sd = (0.86, 0.07) if worn else (0.93, 0.05)
    font = ImageFont.truetype(font_path, size)
    line_h = int(size * 1.6)
    h = line_h * len(lines) + size
    alpha = np.zeros((h, width), dtype=np.float32)
    for li, text in enumerate(lines):
        x = size * 0.5
        for ch in text:
            adv = font.getlength(ch)
            if ch != " ":
                g = Image.new("L", (int(adv) + size, size * 2), 0)
                ImageDraw.Draw(g).text((size // 2, size // 3), ch, font=font, fill=255)
                # 세게 친 글자는 굵고 번지고, 약하게 친 글자는 옅고 빠진다
                force = float(np.clip(rng.normal(force_mean, force_sd), 0.55, 1.0))
                g = g.filter(ImageFilter.GaussianBlur(0.9))
                m = np.asarray(g, dtype=np.float32) / 255
                # 세게 친 글자는 잉크가 바깥으로 조금 더 번진다(문턱값이 낮아짐)
                m = np.clip((m - (0.42 - 0.25 * force)) * 2.4, 0, 1) * force
                # 아래쪽이 약간 옅다(활자 면이 비스듬히 닿음)
                tilt = rng.uniform(-0.08, 0.08)
                m *= 1 + tilt * np.linspace(-1, 1, m.shape[0])[:, None]
                ox = int(x - size // 2 + rng.normal(0, 0.6))
                oy = int(size // 3 + li * line_h - size // 3 + rng.normal(0, 0.8))
                y0, x0 = max(oy, 0), max(ox, 0)
                y1, x1 = min(oy + m.shape[0], h), min(ox + m.shape[1], width)
                region = m[y0 - oy : y1 - oy, x0 - ox : x1 - ox]
                alpha[y0:y1, x0:x1] = 1 - (1 - alpha[y0:y1, x0:x1]) * (1 - region)
            x += adv
    # 리본 천의 날실·씨실 결 + 잉크 얼룩
    yy, xx = np.mgrid[0:h, 0:width]
    weave = 0.9 + 0.1 * np.sin(xx * 1.9) * np.sin(yy * 1.7)
    if worn:
        weave = 0.82 + 0.18 * np.abs(np.sin(xx * 1.9) * np.sin(yy * 1.7))
        # 닳은 띠: 리본이 같은 높이로 감겨 있어 줄마다 비슷한 높이가 옅게 빠진다
        band = np.ones(h, dtype=np.float32)
        for li in range(len(lines)):
            top = li * line_h
            mid = top + size * rng.uniform(0.45, 0.85)
            band *= 1 - 0.3 * np.exp(-(((np.arange(h) - mid) / (size * 0.16)) ** 2))
        weave = weave * band[:, None]
        # 천 사이로 종이가 비치는 작은 빠짐(블록이 아니라 점 크기)
        holes = Image.fromarray((rng.random((h, width)) * 255).astype(np.uint8))
        holes = np.asarray(holes.filter(ImageFilter.GaussianBlur(0.7)), np.float32)
        weave = weave * np.clip((holes / 255 - 0.3) * 5, 0.5, 1)
    coarse = rng.random((h // 5 + 1, width // 5 + 1))
    coarse = (
        np.asarray(
            Image.fromarray((coarse * 255).astype(np.uint8)).resize(
                (width, h), Image.BICUBIC
            ),
            dtype=np.float32,
        )
        / 255
    )
    fine = rng.random((h, width))
    a = alpha * weave * (0.86 + 0.14 * coarse) * (0.9 + 0.1 * fine)
    a = np.clip(a * (1.06 if worn else 1.12), 0, 1)
    paper = np.empty((h, width, 3), dtype=np.float32)
    paper[:] = PAPER
    paper += rng.normal(0, 3, (h, width, 1))
    ink = np.array(INK, dtype=np.float32)
    out = paper * (1 - a[..., None]) + ink * a[..., None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def label(img: Image.Image, text: str, font_path: str) -> Image.Image:
    bar = Image.new("RGB", (img.width, 54), (60, 60, 60))
    ImageDraw.Draw(bar).text(
        (20, 10), text, font=ImageFont.truetype(font_path, 30), fill=(255, 255, 255)
    )
    out = Image.new("RGB", (img.width, img.height + bar.height))
    out.paste(bar, (0, 0))
    out.paste(img, (0, bar.height))
    return out


def main() -> None:
    font_path, out_path = sys.argv[1], sys.argv[2]
    bold_path = font_path.replace("-Regular", "-Bold")
    panels = [
        label(
            typed(font_path, LINES, 56, 1500),
            "T  타자 출력 (새 리본, 화면 기본)",
            font_path,
        ),
        label(
            typed(font_path, LINES, 56, 1500, seed=5, worn=True),
            "B  낡은 리본 (옅은 잉크·닳은 띠·천 결)",
            font_path,
        ),
        label(
            typed(bold_path, LINES, 56, 1500, seed=9),
            "C  강한 타격 = Bold 서체",
            font_path,
        ),
    ]
    sheet = Image.new("RGB", (1500, sum(p.height for p in panels)), PAPER)
    y = 0
    for p in panels:
        sheet.paste(p, (0, y))
        y += p.height
    sheet.save(out_path)
    print(out_path)


if __name__ == "__main__":
    main()
