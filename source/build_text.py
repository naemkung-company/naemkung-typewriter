"""냄쿵타자기의 본문(Text) 판을 만든다. 책 본문처럼 긴 글을 읽기 위한 판이다(0.35 에서 추가).

Regular·Bold·Clean 생성기 build_font.py 의 글자 모양은 0.34 에서 동결했다(0.35 는 판 번호만 올림).
획 그리기·자음 모양·영문은 그대로 가져다 쓰고, 이 파일은 책 본문용 배치만 새로 정한다.

본편과 다른 점(2026-11-10 견본 A~E 비교 결과):
- 반네모: 받침 유무에 따라 초성·모음 자리를 바꿔 음절 아랫선 차이를 390 → 약 150 으로 줄인다.
  본편은 가로 모음 받침이 영문 꼬리 높이(-190)까지 내려가 아랫첨자처럼 읽혔다.
- 칸 폭 880 → 800, 초성을 키우고 모음을 초성 쪽으로 당긴다. 글자 사이가 낱말 사이처럼 보였다.
- 매끈한 윤곽(흔들림·거칠기 없음), 획 대비를 40% 로 줄이고 굵기 64.
- 책에 자주 나오는 “ ” ‘ ’ … — 「 」 『 』 를 더하고, 마침표·쉼표 칸을 좁힌다.

실행: python3 build_text.py   # build/NaemkungTypewriter-Text.ttf
"""

from __future__ import annotations

import sys
from pathlib import Path

# 공개 저장소에서는 build_font.py 와 같은 폴더, 작업 저장소에서는 한 단계 위 폴더에 있다
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent.parent)]

import build_font as bf
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

line, path, Stroke = bf.line, bf.path, bf.Stroke

VERSION = "Version 0.350"
OUT_DIR = Path(__file__).resolve().parent / "build"
ADVANCE = 800
WEIGHT = 64
CONTRAST = 0.4
DY = -60
NARROW = {".": 300, ",": 300}  # 마침표 뒤 틈이 낱말 사이보다 넓어 보여 칸을 좁힌다
WIDE = {"…": ADVANCE, "—": ADVANCE}

# (모음 갈래, 받침 여부) 마다 초성 상자·받침 상자·세로 기둥 아래 끝·가로 모음 (가로획 y, 기둥 끝 y)
LAYOUT = {
    ("V", False): {"cho": (80, 380, 480, 800), "stem": 150},
    ("V", True): {
        "cho": (80, 470, 480, 800),
        "stem": 310,
        "jong": (90, 40, 470, 270),
        "jong2": (60, 40, 560, 270),
    },
    ("H", False): {"cho": (80, 400, 480, 800), "h": {"ㅗ": (215, 385), "ㅜ": (340, 170), "ㅡ": (320, None)}},
    ("H", True): {
        "cho": (80, 480, 480, 800),
        "h": {"ㅗ": (385, 480), "ㅜ": (440, 335), "ㅡ": (410, None)},
        "jong": (100, 30, 520, 260),
        "jong2": (60, 30, 600, 260),
    },
    ("M", False): {
        "cho": (80, 400, 480, 800),
        "stem": 150,
        "h": {"ㅗ": (215, 385), "ㅜ": (340, 170), "ㅡ": (320, None)},
    },
    ("M", True): {
        "cho": (80, 480, 480, 800),
        "stem": 300,
        "h": {"ㅗ": (385, 480), "ㅜ": (440, 335), "ㅡ": (410, None)},
        "jong": (100, 30, 500, 260),
        "jong2": (60, 30, 560, 260),
    },
}
CLASS_DX = {"V": 0, "H": 100, "M": 0}
SHIFT = 70  # 세로 모음을 초성 쪽으로 당기는 양

# 세로 모음: (기둥 x 목록, 짧은 가로획 (x0, x1)) — 본편 값에서 SHIFT 만큼 당긴다
V_SHAPES = {
    k: ([x - SHIFT for x in xs], (b[0] - SHIFT, b[1] - SHIFT) if b else None) for k, (xs, b) in bf._V_SHAPES.items()
}
# 섞인 모음: (가로 부분, 가로획 끝 x, 기둥 x 목록, 짧은 가로획)
# ㅝ·ㅞ 는 짧은 가로획이 초성에 닿지 않도록 본편보다 짧게 둔다(E 견본 「뭘」 겹침).
M_SHAPES = {
    "ㅘ": ("ㅗ", 520, [610], (610, 740)),
    "ㅙ": ("ㅗ", 490, [575, 730], (575, 730)),
    "ㅚ": ("ㅗ", 540, [630], None),
    "ㅝ": ("ㅜ", 520, [745], (640, 745)),
    "ㅞ": ("ㅜ", 490, [640, 770], (570, 640)),
    "ㅟ": ("ㅜ", 540, [640], None),
    "ㅢ": ("ㅡ", 540, [640], None),
}


def h_vowel(v: str, x0: float, x1: float, shapes: dict) -> list:
    base = {"ㅛ": "ㅗ", "ㅠ": "ㅜ"}.get(v, v)
    bar_y, stem_end = shapes[base]
    strokes = [line((x0, bar_y), (x1, bar_y))]
    if stem_end is not None:
        mid, w = (x0 + x1) / 2, x1 - x0
        xs = [mid - w * 0.2, mid + w * 0.2] if v in "ㅛㅠ" else [mid - w * 0.05]
        strokes += [line((x, bar_y), (x, stem_end)) for x in xs]
    return strokes


def jung(v: str, final: bool) -> list:
    cls = bf.vowel_class(v)
    lay = LAYOUT[(cls, final)]
    if cls == "V":
        stems, bar = V_SHAPES[v]
        strokes = [line((x, bf.STEM_TOP), (x, lay["stem"])) for x in stems]
        if bar:
            strokes += bf._bars(*bar, v in bf._DOUBLE_BAR)
        return strokes
    if cls == "H":
        return h_vowel(v, 50, 530, lay["h"])
    hv, hx1, stems, bar = M_SHAPES[v]
    strokes = h_vowel(hv, 50, hx1, lay["h"])
    strokes += [line((x, bf.STEM_TOP), (x, lay["stem"])) for x in stems]
    if bar:
        strokes += bf._bars(*bar, False)
    return strokes


def extra_strokes() -> dict[str, list]:
    """본편에 없는 책 문장부호. 좌표는 폭 500 칸 기준(…·— 는 ADVANCE)."""

    def open_q(x: float) -> list:
        return [path((x, 520), (x, 560), (x + 45, 660))]

    def close_q(x: float) -> list:
        return [path((x, 660), (x, 620), (x - 45, 520))]

    g = {
        "“": open_q(165) + open_q(300),
        "”": close_q(200) + close_q(335),
        "‘": open_q(230),
        "’": close_q(270),
        "…": [line((x, 22), (x, 62)) for x in (160, 400, 640)],
        "—": [line((40, 330), (ADVANCE - 40, 330))],
        "「": [path((440, 740), (230, 740), (230, 380))],
        "」": [path((270, 280), (270, -80), (60, -80))],
        "『": [path((450, 740), (190, 740), (190, 360)), path((450, 660), (270, 660), (270, 360))],
        "』": [path((310, 300), (310, -80), (50, -80)), path((230, 300), (230, 0), (50, 0))],
    }
    return g


def build() -> Path:
    old_halves = bf._halves
    bf._halves = lambda p, h, c: [h + (x - h) * CONTRAST for x in old_halves(p, h, c)]
    glyphs: dict[str, object] = {}
    advances: dict[str, int] = {}
    cmap: dict[int, str] = {}

    def add(name: str, strokes: list, weight: float, adv: int) -> None:
        glyphs[name] = bf.draw_strokes(strokes, weight, None).glyph()
        advances[name] = adv

    add(".notdef", [Stroke([(60, 0), (60, 700), (440, 700), (440, 0)], closed=True)], 40, bf.LATIN_ADVANCE)
    for name, code, adv in (
        ("space", 0x20, bf.LATIN_ADVANCE),
        ("nbsp", 0xA0, bf.LATIN_ADVANCE),
        ("ideospace", 0x3000, ADVANCE),
    ):
        glyphs[name] = TTGlyphPen(None).glyph()
        advances[name] = adv
        cmap[code] = name

    latin = bf.latin_strokes()
    latin.update(extra_strokes())
    for ch, strokes in latin.items():
        name = f"uni{ord(ch):04X}"
        adv = NARROW.get(ch) or WIDE.get(ch) or bf.LATIN_ADVANCE
        if ch in NARROW:
            # 점을 칸 왼쪽으로 붙여 좁힌 칸에 맞춘다
            strokes = bf._shift(strokes, 90 - 250, 0)
        add(name, strokes, bf.LATIN_WEIGHT, adv)
        cmap[ord(ch)] = name

    parts: dict[tuple, str] = {}

    def part(key: tuple, fn) -> str:
        if key not in parts:
            name = f"p{len(parts):04d}"
            add(name, fn(), WEIGHT, ADVANCE)
            parts[key] = name
        return parts[key]

    for ci, c in enumerate(bf.CHO):
        for vi, v in enumerate(bf.JUNG):
            cls = bf.vowel_class(v)
            for ti, t in enumerate(bf.JONG):
                final = t != " "
                lay = LAYOUT[(cls, final)]
                box = lay["cho"]
                if c in "ㄲㄸㅃㅆㅉ":
                    box = (box[0] - 30, box[1], box[2] + 50, box[3])
                comps = [
                    part(("c", c, box), lambda c=c, b=box: bf.consonant(c, b, WEIGHT)),
                    part(("v", v, final), lambda v=v, f=final: jung(v, f)),
                ]
                if final:
                    tbox = lay["jong2"] if t in bf._DOUBLE else lay["jong"]
                    comps.append(part(("t", t, tbox), lambda t=t, b=tbox: bf.consonant(t, b, WEIGHT)))
                code = 0xAC00 + (ci * 21 + vi) * 28 + ti
                name = f"uni{code:04X}"
                pen = TTGlyphPen(glyphs)
                for comp in comps:
                    pen.addComponent(comp, (1, 0, 0, 1, CLASS_DX[cls], DY))
                glyphs[name] = pen.glyph()
                advances[name] = ADVANCE
                cmap[code] = name

    for ch in "ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ":
        add(f"uni{ord(ch):04X}", bf.consonant(ch, (160, 90, 640, 700), WEIGHT), WEIGHT, ADVANCE)
        cmap[ord(ch)] = f"uni{ord(ch):04X}"
    for v in bf.JUNG:
        strokes = jung(v, False)
        xs = [x for s in strokes for x, _ in s.pts]
        name = f"uni{ord(v):04X}"
        add(name, bf._shift(strokes, ADVANCE / 2 - (min(xs) + max(xs)) / 2, 0), WEIGHT, ADVANCE)
        cmap[ord(v)] = name

    bf._halves = old_halves
    return save(glyphs, advances, cmap)


def save(glyphs: dict, advances: dict, cmap: dict) -> Path:
    order = [".notdef"] + sorted(n for n in glyphs if n != ".notdef")
    fb = FontBuilder(bf.UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    glyf = fb.font["glyf"]
    metrics = {}
    for n in order:
        glyf[n].recalcBounds(glyf)
        metrics[n] = (advances[n], getattr(glyf[n], "xMin", 0))
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=bf.ASCENT, descent=bf.DESCENT, lineGap=0)
    family = {"en": "Naemkung Typewriter", "ko": "냄쿵타자기"}
    style = {"en": "Text", "ko": "본문"}
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": style,
            "uniqueFontIdentifier": "NaemkungTypewriter-Text;2026",
            "fullName": {lang: f"{name} {style[lang]}" for lang, name in family.items()},
            "psName": "NaemkungTypewriter-Text",
            "version": VERSION,
            "copyright": {"en": "Copyright 2026 Naemkung Company", "ko": "Copyright 2026 냄쿵콤파니"},
            "manufacturer": {"en": "Naemkung Company", "ko": "냄쿵콤파니"},
            "designer": {"en": "Naemkung Company", "ko": "냄쿵콤파니"},
            "vendorURL": "https://naemkung-company.github.io/naemkung-typewriter/",
            "licenseDescription": (
                "This Font Software is licensed under the SIL Open Font License, "
                "Version 1.1. This license is available with a FAQ at: https://openfontlicense.org"
            ),
            "licenseInfoURL": "https://openfontlicense.org",
        }
    )
    fb.setupOS2(
        sTypoAscender=bf.ASCENT,
        sTypoDescender=bf.DESCENT,
        sTypoLineGap=0,
        usWinAscent=bf.ASCENT + 40,
        usWinDescent=-bf.DESCENT + 120,
        sxHeight=bf.XH,
        sCapHeight=bf.CAP,
        achVendID="NONE",
        usWeightClass=400,
        fsSelection=0x40,
        fsType=0,
        ulUnicodeRange1=0b11,
        ulUnicodeRange2=(1 << 20) | (1 << 24),
        ulCodePageRange1=(1 << 19),
    )
    fb.setupPost(keepGlyphNames=False, isFixedPitch=0)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "NaemkungTypewriter-Text.ttf"
    fb.font["head"].created = bf.BUILD_TIMESTAMP
    fb.font["head"].modified = bf.BUILD_TIMESTAMP
    fb.font.recalcTimestamp = False
    fb.save(out)
    return out


if __name__ == "__main__":
    result = build()
    print(result, result.stat().st_size)
