"""냄쿵타자기(Naemkung Typewriter) 서체를 처음부터 만든다.

다른 글꼴 파일·윤곽을 읽지 않는다. 모든 글자는 이 파일에 적은 획 중심선
(좌표 목록)을 일정한 굵기로 두껍게 만들어 윤곽을 얻는다.

- 한글 11,172자: 초성·중성·종성 부품을 배치 틀마다 그리고, 음절은 부품을
  참조하는 합성 글리프로 만든다(파일 크기를 줄이고 획 굵기를 일정하게 유지).
- 영문·숫자·기호(ASCII 95자)와 한글 호환 자모(ㄱ~ㅣ 51자)를 함께 넣는다.
- 타자기 느낌: 뭉툭한 획 끝, 부품·글자마다 굵기와 위치를 조금씩 다르게 둔다.

실행: python3 build_font.py [--clean | --bold]
      (--clean 이면 위치·굵기 흔들림 없음, --bold 면 세게 친 굵은 판)
"""

from __future__ import annotations

import argparse
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

UPM = 1000
HANGUL_ADVANCE = 880
LATIN_ADVANCE = 500
ASCENT = 880
DESCENT = -120

HANGUL_WEIGHT = 70
LATIN_WEIGHT = 58
# Bold 는 활자를 세게 쳐서 잉크가 넓게 묻은 판이다. 획만 굵히고 배치는 그대로 둔다.
BOLD_SCALE = 1.4
BOLD_JONG_SCALE = 1.15
BOLD_DOUBLE_SCALE = 1.0

OUT_DIR = Path(__file__).resolve().parent / "build"
# 같은 코드로 같은 파일이 나오도록 글꼴 안의 만든 시각을 고정한다(재현 빌드).
# 2026-11-08 00:00 UTC, 1904-01-01 기준 초.
BUILD_TIMESTAMP = 3876940800


# ---------------------------------------------------------------------------
# 획 → 윤곽
# ---------------------------------------------------------------------------


@dataclass
class Stroke:
    """획 하나. pts 는 중심선 좌표, closed 면 고리(ㅇ·o 등)."""

    pts: list[tuple[float, float]]
    closed: bool = False


def _norm(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    return dx / length, dy / length


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 0.5:
            out.append(p)
    return out


def _offset_side(
    pts: list[tuple[float, float]], halves: list[float], side: float, closed: bool
) -> list[tuple[float, float]]:
    """중심선을 한쪽으로 점마다 halves[i] 만큼 민 선. 꺾인 곳은 뾰족 이음, 너무 뾰족하면 깎는다."""
    n = len(pts)
    out: list[tuple[float, float]] = []
    for i in range(n):
        p = pts[i]
        half = halves[i]
        if closed:
            a, b = pts[i - 1], pts[(i + 1) % n]
        else:
            a = pts[i - 1] if i > 0 else None
            b = pts[i + 1] if i < n - 1 else None
        d_in = _norm(p[0] - a[0], p[1] - a[1]) if a else None
        d_out = _norm(b[0] - p[0], b[1] - p[1]) if b else None
        if d_in is None:
            d_in = d_out
        if d_out is None:
            d_out = d_in
        n_in = (-d_in[1] * side, d_in[0] * side)
        n_out = (-d_out[1] * side, d_out[0] * side)
        mx, my = _norm(n_in[0] + n_out[0], n_in[1] + n_out[1])
        cos_half = mx * n_in[0] + my * n_in[1]
        if cos_half < 0.4:
            out.append((p[0] + n_in[0] * half, p[1] + n_in[1] * half))
            out.append((p[0] + n_out[0] * half, p[1] + n_out[1] * half))
        else:
            k = half / cos_half
            out.append((p[0] + mx * k, p[1] + my * k))
    return out


def _cap(
    p: tuple[float, float], d: tuple[float, float], half: float
) -> list[tuple[float, float]]:
    """획 끝. 활자 끝에 잉크가 번져 둥그스름해진 뭉툭한 끝."""
    nx, ny = -d[1], d[0]
    out = []
    for a in (55, 25, -25, -55):
        c, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
        out.append(
            (
                p[0] + (nx * s_ + d[0] * c * 0.7) * half,
                p[1] + (ny * s_ + d[1] * c * 0.7) * half,
            )
        )
    return out


def _area(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i - 1]
        x2, y2 = poly[i]
        s += x1 * y2 - x2 * y1
    return s / 2


def _orient(
    poly: list[tuple[float, float]], clockwise: bool
) -> list[tuple[float, float]]:
    if (_area(poly) < 0) != clockwise:
        poly = poly[::-1]
    return poly


def _dot(p: tuple[float, float], half: float) -> list[list[tuple[float, float]]]:
    r = half * 1.15
    poly = [
        (p[0] + r * math.cos(math.radians(a)), p[1] + r * math.sin(math.radians(a)))
        for a in range(0, 360, 45)
    ]
    return [_orient(poly, clockwise=True)]


def _halves(pts: list[tuple[float, float]], half: float, closed: bool) -> list[float]:
    """점마다 굵기. 활자 원도(붓글씨 바탕)를 따른다.

    - 가로획이 세로획보다 조금 굵다
    - 내려긋는 획으로 시작하면 머리가 굵다
    - 내려긋는 획으로 끝나도 뾰족하게 빼지 않는다. 끝에서 아주 조금만 가늘어지고
      둥근 잉크 끝으로 멈춘다(활자가 종이를 친 자국, 2026-11-08)
    - 가로획으로 끝나면 끝에서 붓을 멈춘 것처럼 살짝 불룩하다
    """
    n = len(pts)
    dirs = []
    for i in range(n):
        if closed:
            a, b = pts[i - 1], pts[(i + 1) % n]
        else:
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        dirs.append(_norm(b[0] - a[0], b[1] - a[1]))
    out = [half * (0.92 + 0.16 * d[0] * d[0]) for d in dirs]
    if closed or n < 2:
        return out
    cum = [0.0]
    for i in range(n - 1):
        cum.append(
            cum[-1] + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        )
    total = cum[-1] or 1.0

    def falling(i: int) -> bool:
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        return _norm(x1 - x0, y1 - y0)[1] < -0.5

    # 끝 꼬리: 마지막에 이어지는 내려긋는 구간
    tail = n - 1
    while tail > 0 and falling(tail - 1):
        tail -= 1
    if tail < n - 1:
        span = cum[-1] - cum[tail] or 1.0
        for i in range(tail, n):
            t = (cum[i] - cum[tail]) / span
            out[i] *= 1.02 - 0.10 * t**2
    elif abs(dirs[-1][0]) > 0.8:
        for i in range(n):
            t = (cum[i] / total - 0.86) / 0.14
            if t > 0:
                out[i] *= 1 + 0.12 * t
    # 머리: 내려긋는 획으로 시작
    if falling(0):
        for i in range(n):
            t = cum[i] / total
            if t < 0.2:
                out[i] *= 1.14 - 0.7 * t
    return out


def stroke_to_contours(
    stroke: Stroke, weight: float
) -> list[list[tuple[float, float]]]:
    half = weight / 2
    pts = _dedupe(stroke.pts)
    if stroke.closed and len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 2:
        return _dot(pts[0], half)
    hs = _halves(pts, half, stroke.closed)
    if stroke.closed:
        outer = _offset_side(pts, hs, -1.0, closed=True)
        inner = _offset_side(pts, hs, 1.0, closed=True)
        if abs(_area(outer)) < abs(_area(inner)):
            outer, inner = inner, outer
        return [_orient(outer, clockwise=True), _orient(inner, clockwise=False)]
    left = _offset_side(pts, hs, 1.0, closed=False)
    right = _offset_side(pts, hs, -1.0, closed=False)
    d_end = _norm(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
    d_start = _norm(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
    end_cap = _cap(pts[-1], d_end, hs[-1])
    start_cap = _cap(pts[0], d_start, hs[0])
    poly = left + end_cap + right[::-1] + start_cap
    return [_orient(poly, clockwise=True)]


def _round_corners(
    poly: list[tuple[float, float]], radius: float
) -> list[tuple[float, float]]:
    """꼭짓점 둘레 radius 안쪽만 둥글린다(잉크가 모서리를 메운 모양). 네모가 동그라미로 변하지 않게 한다."""
    n = len(poly)
    out: list[tuple[float, float]] = []
    for i in range(n):
        px, py = poly[i - 1]
        cx, cy = poly[i]
        nx_, ny_ = poly[(i + 1) % n]
        la, lb = math.hypot(px - cx, py - cy), math.hypot(nx_ - cx, ny_ - cy)
        r = min(radius, la * 0.45, lb * 0.45)
        if r < 1:
            out.append((cx, cy))
            continue
        ax, ay = cx + (px - cx) * r / la, cy + (py - cy) * r / la
        bx, by = cx + (nx_ - cx) * r / lb, cy + (ny_ - cy) * r / lb
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):  # 꼭짓점을 조절점으로 한 2차 곡선
            u = 1 - t
            out.append(
                (
                    u * u * ax + 2 * u * t * cx + t * t * bx,
                    u * u * ay + 2 * u * t * cy + t * t * by,
                )
            )
    return out


def _rough(
    poly: list[tuple[float, float]], seed: str, amp: float
) -> list[tuple[float, float]]:
    """가장자리를 잘게 나눠 법선 방향으로 흔든다(종이 섬유에 잉크가 먹은 거친 가장자리)."""
    step = 14.0
    dense: list[tuple[float, float]] = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        k = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        dense += [(x1 + (x2 - x1) * j / k, y1 + (y2 - y1) * j / k) for j in range(k)]
    m = len(dense)
    # 매끄러운 잡음: 몇 개의 사인파를 겹친다(위상은 seed 로 고정)
    ph = [_rand(f"{seed}.{j}", 0, 6.283) for j in range(4)]
    out = []
    for i in range(m):
        ax, ay = dense[i - 1]
        bx, by = dense[(i + 1) % m]
        nx, ny = _norm(by - ay, -(bx - ax))
        t = i / m * 6.283
        r = (
            math.sin(t * 7 + ph[0]) * 0.5
            + math.sin(t * 13 + ph[1]) * 0.3
            + math.sin(t * 29 + ph[2]) * 0.2
            + math.sin(t * 53 + ph[3]) * 0.15
        )
        out.append((dense[i][0] + nx * r * amp, dense[i][1] + ny * r * amp))
    return out


def draw_strokes(
    strokes: list[Stroke], weight: float, seed: str | None = None
) -> TTGlyphPen:
    """획을 윤곽으로 바꿔 펜에 담는다. seed 가 있으면 잉크 자국처럼 가장자리를 거칠게 한다."""
    pen = TTGlyphPen(None)
    for si, s in enumerate(strokes):
        for ci, contour in enumerate(stroke_to_contours(s, weight)):
            contour = _round_corners(contour, weight * (0.3 if seed else 0.18))
            if seed:
                contour = _rough(contour, f"{seed}.{si}.{ci}", weight * 0.04)
            ipts = []
            for x, y in contour:
                q = (round(x), round(y))
                if not ipts or q != ipts[-1]:
                    ipts.append(q)
            if len(ipts) > 1 and ipts[0] == ipts[-1]:
                ipts.pop()
            if len(ipts) < 3:
                continue
            pen.moveTo(ipts[0])
            for q in ipts[1:]:
                pen.lineTo(q)
            pen.closePath()
    return pen


# ---------------------------------------------------------------------------
# 도형 도우미
# ---------------------------------------------------------------------------


def arc(cx, cy, rx, ry, a0, a1, step=10.0) -> list[tuple[float, float]]:
    """타원 호 위의 점들. 각도는 도, a0 → a1 방향으로."""
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [
        (
            cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
            cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))),
        )
        for i in range(n)
    ]


def ellipse(cx, cy, rx, ry) -> Stroke:
    return Stroke(arc(cx, cy, rx, ry, 90, 450, step=10)[:-1], closed=True)


def line(*pts) -> Stroke:
    return Stroke(list(pts))


def path(*parts) -> Stroke:
    pts: list[tuple[float, float]] = []
    for part in parts:
        if isinstance(part, tuple):
            pts.append(part)
        else:
            pts.extend(part)
    return Stroke(pts)


def hserif(x0, x1, y) -> Stroke:
    return line((x0, y), (x1, y))


def map_box(strokes: list[Stroke], box, weight: float) -> list[Stroke]:
    """단위 상자(0~1)에 그린 획을 잉크 상자 box 안으로 옮긴다(굵기만큼 안쪽으로)."""
    x0, y0, x1, y1 = box
    half = weight / 2
    ix0, iy0, ix1, iy1 = x0 + half, y0 + half, x1 - half, y1 - half
    return [
        Stroke(
            [(ix0 + x * (ix1 - ix0), iy0 + y * (iy1 - iy0)) for x, y in s.pts], s.closed
        )
        for s in strokes
    ]


def sub(strokes: list[Stroke], box) -> list[Stroke]:
    """단위 상자 안의 부분 상자로 줄여 넣는다(겹자음 등)."""
    x0, y0, x1, y1 = box
    return [
        Stroke([(x0 + x * (x1 - x0), y0 + y * (y1 - y0)) for x, y in s.pts], s.closed)
        for s in strokes
    ]


# ---------------------------------------------------------------------------
# 한글 자음 (단위 상자 0~1, 획 중심선)
# ---------------------------------------------------------------------------


def _curve(p0, p1, p2, n: int = 9) -> list[tuple[float, float]]:
    """p1 을 조절점으로 한 2차 곡선(붓으로 삐친 획)."""
    out = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        out.append(
            (
                u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
            )
        )
    return out


def _single_consonant(ch: str) -> list[Stroke]:
    if ch == "ㄱ":
        return [path((0, 1), _curve((1, 1), (0.98, 0.45), (0.72, 0)))]
    if ch == "ㄴ":
        return [line((0, 1), (0, 0), (1, 0))]
    if ch == "ㄷ":
        return [line((0, 1), (1, 1)), line((0, 1), (0, 0), (1, 0))]
    if ch == "ㄹ":
        return [line((0, 1), (1, 1), (1, 0.5), (0, 0.5), (0, 0), (1, 0))]
    if ch == "ㅁ":
        return [Stroke([(0, 0), (0, 1), (1, 1), (1, 0)], closed=True)]
    if ch == "ㅂ":
        return [
            line((0, 1), (0, 0), (1, 0), (1, 1)),
            line((0, 0.52), (1, 0.52)),
        ]
    if ch == "ㅅ":
        return [
            Stroke(_curve((0.52, 1), (0.42, 0.35), (0, 0))),
            line((0.47, 0.62), (1, 0)),
        ]
    if ch == "ㅇ":
        return [ellipse(0.5, 0.5, 0.5, 0.5)]
    if ch == "ㅈ":
        return [
            line((0, 1), (0.96, 1)),
            Stroke(_curve((0.56, 1), (0.44, 0.35), (0.02, 0))),
            line((0.5, 0.6), (1, 0)),
        ]
    if ch == "ㅊ":
        return [
            line((0.3, 1), (0.7, 1)),
            line((0, 0.72), (1, 0.72)),
            Stroke(_curve((0.56, 0.72), (0.44, 0.25), (0.04, 0))),
            line((0.5, 0.42), (1, 0)),
        ]
    if ch == "ㅋ":
        return [
            path((0, 1), _curve((1, 1), (0.98, 0.45), (0.72, 0))),
            line((0.02, 0.52), (0.94, 0.52)),
        ]
    if ch == "ㅌ":
        return [
            line((0, 1), (1, 1)),
            line((0, 1), (0, 0), (1, 0)),
            line((0, 0.5), (0.9, 0.5)),
        ]
    if ch == "ㅍ":
        return [
            line((0, 1), (1, 1)),
            line((0, 0), (1, 0)),
            line((0.3, 1), (0.3, 0)),
            line((0.7, 1), (0.7, 0)),
        ]
    if ch == "ㅎ":
        return [
            line((0.3, 1), (0.7, 1)),
            line((0, 0.73), (1, 0.73)),
            ellipse(0.5, 0.25, 0.36, 0.25),
        ]
    raise KeyError(ch)


_DOUBLE = {
    "ㄲ": "ㄱㄱ",
    "ㄸ": "ㄷㄷ",
    "ㅃ": "ㅂㅂ",
    "ㅆ": "ㅅㅅ",
    "ㅉ": "ㅈㅈ",
    "ㄳ": "ㄱㅅ",
    "ㄵ": "ㄴㅈ",
    "ㄶ": "ㄴㅎ",
    "ㄺ": "ㄹㄱ",
    "ㄻ": "ㄹㅁ",
    "ㄼ": "ㄹㅂ",
    "ㄽ": "ㄹㅅ",
    "ㄾ": "ㄹㅌ",
    "ㄿ": "ㄹㅍ",
    "ㅀ": "ㄹㅎ",
    "ㅄ": "ㅂㅅ",
}


def consonant(ch: str, box, weight: float) -> list[Stroke]:
    """자음 ch 를 잉크 상자 box 에 그린다. 겹자음은 좌우 두 칸으로 나눈다."""
    if ch in _DOUBLE:
        a, b = _DOUBLE[ch]
        x0, y0, x1, y1 = box
        gap = max(weight * 0.7, (x1 - x0) * 0.08)
        mid = (x0 + x1) / 2
        return consonant(a, (x0, y0, mid - gap / 2, y1), weight) + consonant(
            b, (mid + gap / 2, y0, x1, y1), weight
        )
    return map_box(_single_consonant(ch), box, weight)


# ---------------------------------------------------------------------------
# 한글 배치 틀
# ---------------------------------------------------------------------------

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

V_CLASS = set("ㅏㅐㅑㅒㅓㅔㅕㅖㅣ")
H_CLASS = set("ㅗㅛㅜㅠㅡ")
M_CLASS = set("ㅘㅙㅚㅝㅞㅟㅢ")

# 탈네모꼴(세벌식 타자기 방식) 배치.
# - 모든 음절이 같은 윗선(빨랫줄)에 매달린다. 아랫선은 모음·받침에 따라 들쭉날쭉하다.
# - 초성·중성·종성은 음절과 상관없이 자기 자리·크기가 고정이다(초성 1벌, 중성 1벌, 종성 1벌).
# - 좌표는 잉크 기준. 음절 전체를 HANGUL_DY 만큼 내려 영문과 윗선을 맞춘다.
HANGUL_DY = -60
CHO_BOX = (90, 455, 465, 790)
CHO_BOX_DOUBLE = (55, 455, 540, 790)
STEM_TOP, STEM_BOTTOM = 760, 190  # 세로 모음 기둥(중심선)
JONG_BOX = {
    ("V", False): (100, 20, 500, 300),
    ("V", True): (60, 20, 600, 300),
    # 가로·섞인 모음의 받침은 ㅜ·ㅠ 다리가 받침과 붙지 않도록 낮게 둔다(0.34).
    ("H", False): (100, -130, 540, 150),
    ("H", True): (60, -130, 640, 150),
    ("M", False): (100, -130, 540, 150),
    ("M", True): (60, -130, 600, 150),
}
# 가로 모음만 있는 음절은 폭이 좁아 가운데로 민다.
CLASS_DX = {"V": 0, "H": 110, "M": 0}


def vowel_class(v: str) -> str:
    if v in V_CLASS:
        return "V"
    if v in H_CLASS:
        return "H"
    return "M"


def cho_box(c: str) -> tuple:
    return CHO_BOX_DOUBLE if c in "ㄲㄸㅃㅆㅉ" else CHO_BOX


# 세로 모음: (기둥 x 목록, 짧은 가로획 (x0, x1))
_V_SHAPES = {
    "ㅏ": ([650], (650, 800)),
    "ㅑ": ([650], (650, 800)),
    "ㅓ": ([790], (640, 790)),
    "ㅕ": ([790], (640, 790)),
    "ㅣ": ([660], None),
    "ㅐ": ([610, 780], (610, 780)),
    "ㅒ": ([610, 780], (610, 780)),
    "ㅔ": ([670, 810], (560, 670)),
    "ㅖ": ([670, 810], (560, 670)),
}
_DOUBLE_BAR = set("ㅑㅕㅒㅖ")
BAR_Y, BAR_D = 590, 70


def _bars(x0: float, x1: float, double: bool) -> list[Stroke]:
    ys = [BAR_Y + BAR_D, BAR_Y - BAR_D] if double else [BAR_Y]
    return [line((x0, y), (x1, y)) for y in ys]


def _v_vowel(v: str) -> list[Stroke]:
    stems, bar = _V_SHAPES[v]
    strokes = [line((x, STEM_TOP), (x, STEM_BOTTOM)) for x in stems]
    if bar:
        strokes += _bars(*bar, v in _DOUBLE_BAR)
    return strokes


# 가로 모음: 가로획 y, 기둥 끝 y(초성 쪽 또는 아래쪽)
# ㅗ·ㅛ 기둥은 초성 아래로 잉크 100 이상 보여야 ㅛ 두 줄이 읽힌다(0.34, 묭이 몽으로 보임).
_H_SHAPES = {
    "ㅗ": (305, 440),
    "ㅛ": (305, 440),
    "ㅜ": (410, 290),
    "ㅠ": (410, 290),
    "ㅡ": (395, None),
}


def _h_vowel(v: str, x0: float, x1: float) -> list[Stroke]:
    bar_y, stem_end = _H_SHAPES[v]
    strokes = [line((x0, bar_y), (x1, bar_y))]
    if stem_end is not None:
        mid = (x0 + x1) / 2
        span = (x1 - x0) * 0.2
        xs = [mid - span, mid + span] if v in "ㅛㅠ" else [mid - (x1 - x0) * 0.05]
        strokes += [line((x, bar_y), (x, stem_end)) for x in xs]
    return strokes


# 섞인 모음: (가로 부분, 가로획 끝 x, 세로 기둥 x 목록, 짧은 가로획 (x0, x1))
_M_SHAPES = {
    "ㅘ": ("ㅗ", 560, [660], (660, 800)),
    "ㅙ": ("ㅗ", 530, [620, 780], (620, 780)),
    "ㅚ": ("ㅗ", 580, [670], None),
    "ㅝ": ("ㅜ", 580, [800], (660, 800)),
    "ㅞ": ("ㅜ", 540, [680, 820], (590, 680)),
    "ㅟ": ("ㅜ", 580, [680], None),
    "ㅢ": ("ㅡ", 580, [680], None),
}


def _m_vowel(v: str) -> list[Stroke]:
    hv, hx1, stems, bar = _M_SHAPES[v]
    strokes = _h_vowel(hv, 50, hx1)
    strokes += [line((x, STEM_TOP), (x, STEM_BOTTOM)) for x in stems]
    if bar:
        strokes += _bars(*bar, False)
    return strokes


def jung_strokes(v: str) -> list[Stroke]:
    """중성 획(절대 좌표). 받침 유무와 상관없이 같은 모양이다."""
    cls = vowel_class(v)
    if cls == "V":
        return _v_vowel(v)
    if cls == "H":
        return _h_vowel(v, 50, 530)
    return _m_vowel(v)


# ---------------------------------------------------------------------------
# 영문·숫자·기호 (폭 500, 대문자 660, 소문자 480, 내림 -190)
# ---------------------------------------------------------------------------

CAP, XH, ASC, DSC = 660, 480, 700, -190


def latin_strokes() -> dict[str, list[Stroke]]:
    g: dict[str, list[Stroke]] = {}
    s = hserif

    # 대문자
    g["A"] = [
        line((70, 0), (250, CAP), (430, 0)),
        line((128, 210), (372, 210)),
        s(20, 130, 0),
        s(370, 480, 0),
    ]
    g["B"] = [
        line((90, 0), (90, CAP)),
        path((40, CAP), arc(285, 503, 150, 157, 90, -90), (90, 346)),
        path((90, 346), arc(305, 173, 165, 173, 90, -90), (40, 0)),
    ]
    g["C"] = [path(arc(260, 330, 190, 340, 38, 322)), line((410, 540), (410, 655))]
    g["D"] = [
        line((90, 0), (90, CAP)),
        path((40, CAP), arc(225, 330, 205, 330, 90, -90), (40, 0)),
    ]
    g["E"] = [
        line((100, 0), (100, CAP)),
        path((40, CAP), (420, CAP), (420, 540)),
        line((100, 340), (330, 340)),
        line((330, 285), (330, 395)),
        path((40, 0), (430, 0), (430, 135)),
    ]
    g["F"] = [
        line((100, 0), (100, CAP)),
        path((40, CAP), (420, CAP), (420, 540)),
        line((100, 340), (330, 340)),
        line((330, 285), (330, 395)),
        s(30, 230, 0),
    ]
    g["G"] = [
        path(arc(260, 330, 190, 340, 38, 335)),
        line((430, 270), (430, 50)),
        line((290, 270), (470, 270)),
        line((410, 540), (410, 655)),
    ]
    g["H"] = [
        line((90, 0), (90, CAP)),
        line((410, 0), (410, CAP)),
        line((90, 340), (410, 340)),
        s(30, 150, 0),
        s(350, 470, 0),
        s(30, 150, CAP),
        s(350, 470, CAP),
    ]
    g["I"] = [line((250, 0), (250, CAP)), s(110, 390, 0), s(110, 390, CAP)]
    g["J"] = [
        path((390, CAP), (390, 210), arc(250, 210, 140, 210, 0, -180), (110, 260)),
        s(250, 470, CAP),
    ]
    g["K"] = [
        line((90, 0), (90, CAP)),
        line((90, 240), (410, CAP)),
        line((185, 365), (430, 0)),
        s(30, 160, 0),
        s(30, 160, CAP),
        s(330, 475, CAP),
        s(350, 480, 0),
    ]
    g["L"] = [
        line((110, 0), (110, CAP)),
        path((40, 0), (430, 0), (430, 150)),
        s(40, 220, CAP),
    ]
    g["M"] = [
        line((70, 0), (70, CAP), (250, 230), (430, CAP), (430, 0)),
        s(20, 130, 0),
        s(370, 480, 0),
        s(20, 70, CAP),
        s(430, 480, CAP),
    ]
    g["N"] = [
        line((80, 0), (80, CAP), (420, 0), (420, CAP)),
        s(20, 150, 0),
        s(20, 80, CAP),
        s(350, 480, CAP),
    ]
    g["O"] = [ellipse(250, 330, 185, 340)]
    g["P"] = [
        line((90, 0), (90, CAP)),
        path((40, CAP), arc(265, 483, 175, 177, 90, -90), (90, 306)),
        s(30, 230, 0),
    ]
    g["Q"] = [ellipse(250, 330, 185, 340), line((250, 40), (440, -110))]
    g["R"] = [
        line((90, 0), (90, CAP)),
        path((40, CAP), arc(265, 483, 175, 177, 90, -90), (90, 306)),
        line((230, 306), (430, 0)),
        s(30, 210, 0),
        s(370, 480, 0),
    ]
    g["S"] = [path(arc(250, 498, 160, 162, 25, 270), arc(250, 168, 172, 172, 90, -155))]
    g["T"] = [
        path((50, 535), (50, CAP), (450, CAP), (450, 535)),
        line((250, CAP), (250, 0)),
        s(140, 360, 0),
    ]
    g["U"] = [
        path((90, CAP), (90, 205), arc(250, 205, 160, 205, 180, 360), (410, CAP)),
        s(30, 150, CAP),
        s(350, 470, CAP),
    ]
    g["V"] = [line((60, CAP), (250, 0), (440, CAP)), s(10, 130, CAP), s(370, 490, CAP)]
    g["W"] = [
        line((40, CAP), (130, 0), (250, 440), (370, 0), (460, CAP)),
        s(10, 100, CAP),
        s(400, 490, CAP),
    ]
    g["X"] = [
        line((70, CAP), (430, 0)),
        line((430, CAP), (70, 0)),
        s(20, 150, 0),
        s(350, 480, 0),
        s(20, 150, CAP),
        s(350, 480, CAP),
    ]
    g["Y"] = [
        line((60, CAP), (250, 320), (440, CAP)),
        line((250, 320), (250, 0)),
        s(10, 130, CAP),
        s(370, 490, CAP),
        s(140, 360, 0),
    ]
    g["Z"] = [path((80, 545), (80, CAP), (420, CAP), (80, 0), (430, 0), (430, 135))]

    # 소문자
    g["a"] = [
        path(arc(245, 335, 148, 145, 155, 0), (393, 0), (465, 0)),
        ellipse(232, 145, 162, 148),
    ]
    g["b"] = [line((100, ASC), (100, 0)), s(40, 100, ASC), ellipse(272, 240, 170, 245)]
    g["c"] = [path(arc(262, 240, 180, 245, 40, 320))]
    g["d"] = [
        line((400, ASC), (400, 0)),
        s(340, 400, ASC),
        s(400, 465, 0),
        ellipse(228, 240, 170, 245),
    ]
    g["e"] = [path((85, 250), (425, 250), arc(255, 240, 170, 245, 0, 318))]
    g["f"] = [
        path(arc(335, 565, 120, 125, 25, 180), (215, 0)),
        line((90, XH), (390, XH)),
        s(100, 340, 0),
    ]
    g["g"] = [
        ellipse(230, 255, 165, 225),
        path((395, XH), (395, 10), arc(240, 10, 155, 175, 0, -165)),
        s(395, 465, XH),
    ]
    g["h"] = [
        line((100, ASC), (100, 0)),
        path(arc(250, 300, 150, 175, 170, 0), (400, 0)),
        s(40, 100, ASC),
        s(40, 170, 0),
        s(330, 465, 0),
    ]
    g["i"] = [
        line((250, XH), (250, 0)),
        line((250, 655), (250, 615)),
        s(150, 250, XH),
        s(120, 380, 0),
    ]
    g["j"] = [
        path((290, XH), (290, -40), arc(170, -40, 120, 140, 0, -160)),
        line((290, 655), (290, 615)),
        s(180, 290, XH),
    ]
    g["k"] = [
        line((100, ASC), (100, 0)),
        line((390, XH), (100, 165)),
        line((195, 250), (420, 0)),
        s(40, 100, ASC),
        s(40, 170, 0),
        s(325, 460, XH),
        s(355, 480, 0),
    ]
    g["l"] = [line((250, ASC), (250, 0)), s(140, 250, ASC), s(120, 380, 0)]
    g["m"] = [
        line((60, XH), (60, 0)),
        path(arc(155, 330, 95, 150, 180, 0), (250, 0)),
        path(arc(345, 330, 95, 150, 180, 0), (440, 0)),
        s(20, 60, XH),
        s(20, 110, 0),
        s(390, 480, 0),
    ]
    g["n"] = [
        line((100, XH), (100, 0)),
        path(arc(250, 300, 150, 180, 170, 0), (400, 0)),
        s(40, 100, XH),
        s(40, 170, 0),
        s(330, 465, 0),
    ]
    g["o"] = [ellipse(250, 240, 175, 245)]
    g["p"] = [
        line((100, XH), (100, DSC)),
        ellipse(272, 240, 170, 245),
        s(40, 100, XH),
        s(30, 210, DSC),
    ]
    g["q"] = [
        line((400, XH), (400, DSC)),
        ellipse(228, 240, 170, 245),
        s(400, 465, XH),
        s(290, 470, DSC),
    ]
    g["r"] = [
        line((140, XH), (140, 0)),
        path(arc(320, 285, 180, 190, 180, 55)),
        s(60, 140, XH),
        s(50, 330, 0),
    ]
    g["s"] = [path(arc(250, 362, 140, 118, 25, 270), arc(250, 122, 155, 122, 90, -155))]
    g["t"] = [
        path((200, 640), (200, 95), arc(315, 95, 115, 95, 180, 300)),
        line((80, XH), (400, XH)),
    ]
    g["u"] = [
        path((100, XH), (100, 185), arc(250, 185, 150, 185, 180, 360)),
        line((400, XH), (400, 0)),
        s(40, 100, XH),
        s(340, 400, XH),
        s(400, 465, 0),
    ]
    g["v"] = [line((60, XH), (250, 0), (440, XH)), s(10, 130, XH), s(370, 490, XH)]
    g["w"] = [
        line((40, XH), (140, 0), (250, 330), (360, 0), (460, XH)),
        s(10, 100, XH),
        s(400, 490, XH),
    ]
    g["x"] = [
        line((80, XH), (420, 0)),
        line((420, XH), (80, 0)),
        s(30, 150, XH),
        s(350, 470, XH),
        s(30, 150, 0),
        s(350, 470, 0),
    ]
    g["y"] = [
        line((70, XH), (260, 40)),
        line((430, XH), (170, DSC)),
        s(20, 140, XH),
        s(360, 480, XH),
        s(80, 270, DSC),
    ]
    g["z"] = [path((90, 385), (90, XH), (410, XH), (90, 0), (420, 0), (420, 100))]

    # 숫자 (0 은 가운데 점으로 O 와 구분)
    g["0"] = [ellipse(250, 330, 170, 340), line((250, 320), (250, 342))]
    g["1"] = [path((115, 555), (250, CAP), (250, 0)), s(110, 390, 0)]
    g["2"] = [path(arc(250, 478, 162, 182, 160, -30), (80, 0), (420, 0), (420, 120))]
    g["3"] = [
        path(arc(240, 502, 150, 158, 150, -90), arc(240, 172, 180, 172, 90, -150))
    ]
    g["4"] = [path((330, 0), (330, CAP), (50, 200), (455, 200)), s(220, 440, 0)]
    g["5"] = [
        path((405, CAP), (125, CAP), (108, 362), arc(245, 212, 180, 205, 130, -150))
    ]
    g["6"] = [ellipse(255, 210, 175, 210), path(arc(290, 300, 210, 360, 72, 188))]
    g["7"] = [path((80, 545), (80, CAP), (420, CAP), (195, 0))]
    g["8"] = [ellipse(250, 503, 142, 157), ellipse(250, 175, 175, 175)]
    g["9"] = [ellipse(245, 450, 175, 210), path(arc(210, 360, 210, 360, 8, -108))]

    # 기호
    g["!"] = [line((250, CAP), (250, 200)), line((250, 22), (250, 62))]
    g['"'] = [line((170, CAP), (170, 480)), line((330, CAP), (330, 480))]
    g["#"] = [
        line((195, 620), (150, 40)),
        line((355, 620), (310, 40)),
        line((70, 430), (440, 430)),
        line((60, 230), (430, 230)),
    ]
    g["$"] = [
        path(arc(250, 488, 150, 150, 25, 270), arc(250, 178, 162, 160, 90, -155)),
        line((250, 720), (250, -60)),
    ]
    g["%"] = [
        ellipse(130, 520, 80, 110),
        ellipse(370, 140, 80, 110),
        line((430, 640), (70, 20)),
    ]
    g["&"] = [
        path(
            (445, 0),
            (170, 400),
            arc(225, 525, 92, 125, 222, -40),
            (95, 205),
            arc(225, 170, 130, 170, 168, 300),
            (455, 300),
        )
    ]
    g["'"] = [line((250, CAP), (250, 480))]
    g["("] = [path(arc(450, 330, 230, 420, 125, 235))]
    g[")"] = [path(arc(50, 330, 230, 420, 55, -55))]
    g["*"] = [
        line((250, 640), (250, 340)),
        line((120, 565), (380, 415)),
        line((380, 565), (120, 415)),
    ]
    g["+"] = [line((250, 520), (250, 140)), line((80, 330), (420, 330))]
    g[","] = [path((265, 62), (265, 22), (195, -115))]
    g["-"] = [line((100, 330), (400, 330))]
    g["."] = [line((250, 22), (250, 62))]
    g["/"] = [line((420, 700), (80, -80))]
    g[":"] = [line((250, 432), (250, 472)), line((250, 22), (250, 62))]
    g[";"] = [line((265, 432), (265, 472)), path((265, 62), (265, 22), (195, -115))]
    g["<"] = [line((420, 560), (80, 330), (420, 100))]
    g["="] = [line((80, 420), (420, 420)), line((80, 240), (420, 240))]
    g[">"] = [line((80, 560), (420, 330), (80, 100))]
    g["?"] = [
        path(arc(250, 498, 152, 162, 160, -60), (250, 310), (250, 200)),
        line((250, 22), (250, 62)),
    ]
    g["@"] = [
        path(arc(250, 320, 212, 335, -15, 330)),
        ellipse(242, 300, 88, 120),
        path((332, 430), (332, 230), (370, 180), (420, 180)),
    ]
    g["["] = [path((335, 740), (180, 740), (180, -80), (335, -80))]
    g["\\"] = [line((80, 700), (420, -80))]
    g["]"] = [path((165, 740), (320, 740), (320, -80), (165, -80))]
    g["^"] = [line((100, 430), (250, CAP), (400, 430))]
    g["_"] = [line((20, -150), (480, -150))]
    g["`"] = [line((190, 700), (300, 585))]
    g["{"] = [
        path(
            (340, 740),
            (255, 700),
            (255, 385),
            (165, 330),
            (255, 275),
            (255, -40),
            (340, -80),
        )
    ]
    g["|"] = [line((250, 760), (250, -160))]
    g["}"] = [
        path(
            (160, 740),
            (245, 700),
            (245, 385),
            (335, 330),
            (245, 275),
            (245, -40),
            (160, -80),
        )
    ]
    g["~"] = [
        Stroke(
            [
                (70 + 360 * i / 20, 330 + 55 * math.sin(math.pi * 2 * i / 20))
                for i in range(21)
            ]
        )
    ]
    g["·"] = [line((250, 318), (250, 358))]
    return g


# ---------------------------------------------------------------------------
# 흔들림 (타자기 느낌)
# ---------------------------------------------------------------------------


def _rand(key: str, lo: float, hi: float) -> float:
    h = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") / 0xFFFFFFFF
    return lo + (hi - lo) * h


class Jitter:
    def __init__(self, enabled: bool, scale: float = 1.0):
        self.enabled = enabled
        self.scale = scale

    def weight(self, base: float, key: str) -> float:
        base *= self.scale
        return base * (1 + _rand("w" + key, -0.1, 0.1)) if self.enabled else base

    def offset(self, key: str, amount: float = 7) -> tuple[int, int]:
        if not self.enabled:
            return 0, 0
        return round(_rand("x" + key, -amount * 0.6, amount * 0.6)), round(
            _rand("y" + key, -amount, amount)
        )


def _shift(strokes: list[Stroke], dx: float, dy: float) -> list[Stroke]:
    return [Stroke([(x + dx, y + dy) for x, y in s.pts], s.closed) for s in strokes]


# ---------------------------------------------------------------------------
# 글꼴 조립
# ---------------------------------------------------------------------------


def build(clean: bool, bold: bool = False) -> Path:
    jit = Jitter(not clean, BOLD_SCALE if bold else 1.0)
    glyphs: dict[str, object] = {}
    advances: dict[str, int] = {}
    cmap: dict[int, str] = {}

    def add_simple(name: str, strokes: list[Stroke], weight: float, adv: int) -> None:
        seed = None if clean else name
        glyphs[name] = draw_strokes(strokes, weight, seed).glyph()
        advances[name] = adv

    add_simple(
        ".notdef",
        [Stroke([(60, 0), (60, 700), (440, 700), (440, 0)], closed=True)],
        40 * jit.scale,
        LATIN_ADVANCE,
    )
    for name, code in (("space", 0x20), ("nbsp", 0xA0)):
        glyphs[name] = TTGlyphPen(None).glyph()
        advances[name] = LATIN_ADVANCE
        cmap[code] = name
    glyphs["ideospace"] = TTGlyphPen(None).glyph()
    advances["ideospace"] = HANGUL_ADVANCE
    cmap[0x3000] = "ideospace"

    for ch, strokes in latin_strokes().items():
        name = f"uni{ord(ch):04X}"
        dx, dy = jit.offset(ch, 6)
        add_simple(
            name, _shift(strokes, dx, dy), jit.weight(LATIN_WEIGHT, ch), LATIN_ADVANCE
        )
        cmap[ord(ch)] = name

    # 한글 부품: (자모, 상자) 가 같으면 한 번만 만든다.
    part_names: dict[tuple, str] = {}

    def part(kind: str, key: tuple, strokes_fn) -> str:
        if key in part_names:
            return part_names[key]
        name = f"{kind}{len(part_names):04d}"
        w = jit.weight(HANGUL_WEIGHT, name)
        if jit.scale > 1:
            # 받침 칸은 작고, 겹자음·겹받침은 한 칸에 두 자를 넣는다.
            # Bold 로 똑같이 굵히면 속이 메워져서 덜 굵힌다. 가로획이 셋인
            # ㄹ·ㅌ 받침과 겹자음은 Regular 굵기 그대로 둔다.
            if key[1] in _DOUBLE or (kind == "t" and key[1] in "ㄹㅌ"):
                w *= BOLD_DOUBLE_SCALE / jit.scale
            elif kind == "t":
                w *= BOLD_JONG_SCALE / jit.scale
        add_simple(name, strokes_fn(w), w, HANGUL_ADVANCE)
        part_names[key] = name
        return name

    for ci, c in enumerate(CHO):
        for vi, v in enumerate(JUNG):
            cls = vowel_class(v)
            for ti, t in enumerate(JONG):
                final = t != " "
                code = 0xAC00 + (ci * 21 + vi) * 28 + ti
                box = cho_box(c)
                comps = [
                    part("c", ("c", c, box), lambda w, c=c, b=box: consonant(c, b, w)),
                    part("v", ("v", v), lambda w, v=v: jung_strokes(v)),
                ]
                if final:
                    tbox = JONG_BOX[(cls, t in _DOUBLE)]
                    comps.append(
                        part(
                            "t",
                            ("t", t, tbox),
                            lambda w, t=t, b=tbox: consonant(t, b, w),
                        )
                    )
                name = f"uni{code:04X}"
                pen = TTGlyphPen(glyphs)
                # 자모마다 따로 내려친 것처럼 부품별로 조금씩 어긋나게 둔다.
                # 기울기는 주지 않는다(타자 글씨는 각도가 비뚤지 않다, 2026-11-08).
                for k, comp in enumerate(comps):
                    dx, dy = jit.offset(f"{name}.{k}", 10)
                    pen.addComponent(
                        comp, (1, 0, 0, 1, dx + CLASS_DX[cls], dy + HANGUL_DY)
                    )
                glyphs[name] = pen.glyph()
                advances[name] = HANGUL_ADVANCE
                cmap[code] = name

    # 호환 자모 ㄱ(3131) ~ ㅣ(3163)
    compat_cons = "ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    for ch in compat_cons:
        name = f"uni{ord(ch):04X}"
        w = jit.weight(HANGUL_WEIGHT, name)
        add_simple(name, consonant(ch, (200, 90, 800, 700), w), w, HANGUL_ADVANCE)
        cmap[ord(ch)] = name
    for v in JUNG:
        name = f"uni{ord(v):04X}"
        strokes = jung_strokes(v)
        xs = [x for s in strokes for x, _ in s.pts]
        dx = 500 - (min(xs) + max(xs)) / 2
        w = jit.weight(HANGUL_WEIGHT, name)
        add_simple(name, _shift(strokes, dx, 0), w, HANGUL_ADVANCE)
        cmap[ord(v)] = name

    order = [".notdef"] + sorted(n for n in glyphs if n != ".notdef")
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    metrics = {}
    glyf = fb.font["glyf"]
    for n in order:
        g = glyf[n]
        g.recalcBounds(glyf)
        metrics[n] = (advances[n], getattr(g, "xMin", 0))
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT, lineGap=0)
    style = "Bold" if bold else "Clean" if clean else "Regular"
    family = {"en": "Naemkung Typewriter", "ko": "냄쿵타자기"}
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": style,
            "uniqueFontIdentifier": f"NaemkungTypewriter-{style};2026",
            "fullName": {lang: f"{name} {style}" for lang, name in family.items()},
            "psName": f"NaemkungTypewriter-{style}",
            "version": "Version 0.340",
            "copyright": {
                "en": "Copyright 2026 Naemkung Company",
                "ko": "Copyright 2026 냄쿵콤파니",
            },
            "manufacturer": {"en": "Naemkung Company", "ko": "냄쿵콤파니"},
            "designer": {"en": "Naemkung Company", "ko": "냄쿵콤파니"},
            "vendorURL": "https://naemkung-company.github.io/naemkung-typewriter/",
            "licenseDescription": (
                "This Font Software is licensed under the SIL Open Font License, "
                "Version 1.1. This license is available with a FAQ at: "
                "https://openfontlicense.org"
            ),
            "licenseInfoURL": "https://openfontlicense.org",
        }
    )
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        sTypoLineGap=0,
        usWinAscent=ASCENT + 40,
        usWinDescent=-DESCENT + 120,
        sxHeight=XH,
        sCapHeight=CAP,
        achVendID="NONE",
        usWeightClass=700 if bold else 400,
        fsSelection=0x20 if bold else 0x40,
        fsType=0,
        ulUnicodeRange1=0b11,
        ulUnicodeRange2=(1 << 20) | (1 << 24),
        ulCodePageRange1=(1 << 19),
    )
    fb.setupPost(keepGlyphNames=False, isFixedPitch=0)
    if bold:
        fb.font["head"].macStyle = 1
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"NaemkungTypewriter-{style}.ttf"
    fb.font["head"].created = BUILD_TIMESTAMP
    fb.font["head"].modified = BUILD_TIMESTAMP
    fb.font.recalcTimestamp = False
    fb.save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    style = ap.add_mutually_exclusive_group()
    style.add_argument(
        "--clean", action="store_true", help="위치·굵기 흔들림 없이 만든다"
    )
    style.add_argument("--bold", action="store_true", help="세게 친 굵은 판을 만든다")
    args = ap.parse_args()
    out = build(args.clean, args.bold)
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
