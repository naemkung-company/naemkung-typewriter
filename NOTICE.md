# 권리 고지 (NOTICE)

## 저작권자

냄쿵타자기(Naemkung Typewriter)의 글꼴 파일과 생성기 코드는 냄쿵콤파니(Naemkung Company)가 만들었다. 저작권은 냄쿵콤파니에 있고, [SIL Open Font License 1.1](OFL.txt)로 공개한다.

```
Copyright 2026 냄쿵콤파니
Copyright 2026 Naemkung Company
```

## 만든 방법

○ 다른 글꼴의 데이터를 쓰지 않았다

다른 글꼴 파일, 글리프 윤곽, 좌표, 비트맵을 가져오거나 변환하지 않았다. 글자마다 획이 지나가는 중심선 좌표를 `source/build_font.py` 에 직접 적고, 그 선에 굵기를 입혀 윤곽을 만든다. 생성기는 실행 중에 다른 글꼴 파일을 읽지 않는다. 누구나 `source/` 의 코드로 같은 글꼴을 다시 만들어 확인할 수 있다.

○ 참고한 것은 옛 타자기의 배치 원리다

1950~70년대 세벌식(공병우식) 수동 타자기 출력물에서 윗선을 맞추고 아랫선을 들쭉날쭉하게 두는 배치 원리(탈네모꼴)를 참고했다. 이 원리는 특정 글꼴의 것이 아니다. 지금 판매·배포 중인 탈네모꼴 글꼴은 보고 따라 그리지 않았다. 참고한 사진은 저장소와 배포 파일에 넣지 않았다.

○ 증거는 공개한다

코드로 배포 파일과 같은 파일을 다시 만드는 재현 빌드, 기존 한글 글꼴 16종과의 모양 비교, 0.1 부터 0.35 까지의 판별 기록을 [PROVENANCE.md](PROVENANCE.md) 에 모았다.

## 이름

- 「공병우식」은 세벌식 타자기의 방식을 가리키는 설명이다. 냄쿵타자기는 공병우 박사, 그 유족, 관련 단체와 관계가 없고 그들의 후원이나 승인을 받지 않았다.
- 공병우 박사가 만든 글꼴(공한체 등)과 다른 별개의 글꼴이다.
- 공병우 박사에 대한 존경을 담아 소개 페이지에 [위키백과 공병우](https://ko.wikipedia.org/wiki/%EA%B3%B5%EB%B3%91%EC%9A%B0) 등 공개 자료 링크를 걸었다. 링크는 소개이며 관계나 승인을 뜻하지 않는다.
- 「냄쿵타자기」, 「Naemkung Typewriter」, 「냄쿵콤파니」는 이 글꼴을 만든 쪽이 쓰는 이름이다.

## 구성 요소

| 구성 요소 | 쓰임 | 라이선스 | 배포 파일에 포함 |
|---|---|---|---|
| fontTools | 글꼴 파일 생성 | MIT | 포함 안 함 |
| Pillow, numpy | 견본 그림 생성 | MIT-CMU, BSD | 포함 안 함 |

`images/` 의 견본 그림은 이 글꼴로 직접 그린 것이다.

## 보증 없음

이 글꼴은 있는 그대로 제공한다. 어떤 보증도 하지 않으며, 사용해서 생긴 손해에 책임지지 않는다. 자세한 조건은 [OFL.txt](OFL.txt) 원문을 따른다.

## 권리 침해 신고

이 글꼴이 다른 사람의 권리를 침해한다고 판단되면 [GitHub Issues](https://github.com/naemkung-company/naemkung-typewriter/issues) 에 알려 주기 바란다. 공개하기 어려운 내용은 메일 [jaykafka12@gmail.com](mailto:jaykafka12@gmail.com) 로 보내도 된다. 신고를 받으면 확인하는 동안 해당 판의 배포를 멈추고, 침해가 확인되면 해당 글자를 고치거나 배포를 중단한다.

---

## Notice (English)

Naemkung Typewriter is Copyright 2026 Naemkung Company and licensed under the SIL Open Font License 1.1.

No third-party font files, glyph outlines, coordinates or bitmaps were used. All glyphs are generated from stroke centerlines written in `source/build_font.py`, which reads no other font files. Reproducible-build, shape-comparison and development-history evidence is published in `PROVENANCE.md`. The design follows the layout principle of 1950s–70s Sebeolsik (Kong Byung-woo style) manual typewriter output. The project is not affiliated with, sponsored or endorsed by Dr. Kong Byung-woo's family or any related organization, and is unrelated to his own typefaces.

The font is provided "as is", without warranty of any kind. To report a rights concern, please open a GitHub issue or email jaykafka12@gmail.com; distribution of the affected version will be paused while it is reviewed.
