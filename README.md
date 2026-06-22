# kasa-hwpx

우주항공청(KASA) 표준보고서를 한글 **HWPX(.hwpx)**로 생성·편집·검증하는 Claude/Cowork **Skill**입니다.
표준양식(표지·MI 로고·편집용지)을 그대로 보존하고 본문만 채워, 규정에 맞는 보고서를 외부 패키지 없이
파이썬 표준 라이브러리만으로 만듭니다.

> 🔰 컴퓨터가 익숙하지 않으세요? 명령어 없이 **말로 시켜서** 보고서를 만드는 방법은
> **[쉬운 사용설명서](사용설명서.md)**에 단계별로 정리해 두었습니다.

## 저장소 구조

```
.
├── README.md
├── 사용설명서.md             # 컴퓨터가 낯선 분을 위한 쉬운 안내서
├── .gitignore
├── build_skill.py            # kasa-hwpx/ → kasa-hwpx.skill 패키징
└── kasa-hwpx/                # 스킬 본체(.skill 내부 구조와 동일)
    ├── SKILL.md              # 스킬 설명·규칙(트리거/Critical Rules)
    ├── assets/               # 기준 양식(SSOT) 및 참고 양식
    │   ├── kasa-standard-report.hwpx
    │   ├── reference-form-spacing.hwpx
    │   └── sample-report.hwpx
    ├── references/           # 스타일/구조 레퍼런스 문서
    └── scripts/              # 빌드·검증 엔진(파이썬 표준 라이브러리)
        ├── build_report.py   # JSON 사양 → 보고서 HWPX
        ├── validate.py       # 구조·KASA 규정·회귀 점검
        ├── extract_text.py   # 본문 텍스트 추출(검수용)
        ├── redraft.py        # 재기안: 기존 HWPX 서식 보존 본문 치환
        ├── kasa_lib.py       # 핵심 엔진
        └── office/           # HWPX(zip) 패킹/언패킹 보조
```

## 사용법

보고서 생성(JSON 사양 → HWPX):

```bash
python3 kasa-hwpx/scripts/build_report.py \
  --spec spec.json \
  --output 보고서.hwpx
```

생성물 검증(구조·KASA 규정·줄겹침/자동번호 회귀 점검):

```bash
python3 kasa-hwpx/scripts/validate.py 보고서.hwpx --kasa
```

재기안(기존 HWPX의 서식을 보존한 채 본문만 치환):

```bash
# repl.json 예: {"2025년": "2026년", "(부서명)": "우주수송정책과"}
python3 kasa-hwpx/scripts/redraft.py --input 원본.hwpx --map repl.json --output 결과.hwpx
```

## 스킬 패키징

```bash
python3 build_skill.py        # → dist/kasa-hwpx.skill 생성
```

생성된 `kasa-hwpx.skill`을 스킬 디렉터리에 풀어 넣거나 앱의 스킬 가져오기로 등록합니다.

## 핵심 설계 메모

- 본문 흐름 문단에는 줄 위치 캐시(`linesegarray`)를 넣지 않아 한글이 열 때 재계산 → 줄 겹침 방지.
- 본문 위계는 **선행 공백(항목 시작) + 내어쓰기(2줄 이상, 첫 글자 정렬)**. 첫 줄 시작은 항상 0.
- 좌여백 paraPr이 모두 OUTLINE(자동번호)이라, 무번호·무내어쓰기 paraPr을 빌드 시 헤더에 주입.
- 항목 앞 간격은 빈 문단(스페이서)으로 부여(□ 15pt, ㅇ 10pt, - 5pt, ※/* 3pt).
- 표 내부는 내어쓰기를 적용하지 않음. 긴 제목은 2줄 자동 줄바꿈.
- 자세한 규칙은 `kasa-hwpx/SKILL.md` 참고.

## 버전 히스토리

커밋은 [Conventional Commits](https://www.conventionalcommits.org), 태그는 [SemVer](https://semver.org)를 따릅니다.

- `v0.1.0` feat: 초기 버전 — 생성 엔진·검증기·기준 양식
- `v0.1.1` fix: 줄겹침(linesegarray) 해결 + 참고 머리 3칸 표 디자인
- `v0.2.0` feat: 선행 공백 + 내어쓰기 기반 본문 위계
- `v0.3.0` feat: 항목 간격·긴 제목 2줄·표 내어쓰기 제외·참고 서식 통일
- `v0.4.0` feat: 재기안(`redraft.py`) — 기존 HWPX 서식 보존 본문 치환 / docs: 쉬운 사용설명서 추가

### 커밋 규약

```
<type>(<scope>): <subject>

<body>
```

- type: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `chore` 등
- scope(예): `skill`, `layout`, `table`, `appendix`, `validate`, `build`
- 예: `fix(layout): linesegarray 캐시 제거로 본문 줄 겹침 해결`

## 라이선스

이 저장소의 코드(빌드·검증 엔진, 스크립트, 문서)는 **[MIT License](LICENSE)**를 따릅니다.
[hwpx-rekian](https://github.com/ai-public-peasant/hwpx-rekian) 등 원작 스킬이 MIT License를 적용하고 있으므로,
**각 하위 디렉터리에 별도 LICENSE 파일이 있는 경우 해당 파일의 라이선스를 우선 확인하세요.**

다만 `kasa-hwpx/assets/`에 포함된 우주항공청(KASA) 표준양식·로고 등 자산의 권리는 아래 우주항공청 저작권 정책을 따릅니다.

이 저작물은 대한민국의 국가기관 또는 지방자치단체가 업무상 작성하여 공표하였거나 계약에 따라 저작재산권의 전부를 보유하고 있습니다. [대한민국 저작권법](https://law.go.kr/%EB%B2%95%EB%A0%B9/%EC%A0%80%EC%9E%91%EA%B6%8C%EB%B2%95) 제24조의2에 따라, 이러한 저작물은 저작권자에게 별도의 허락을 받을 필요 없이 복제·변경·재배포·2차적저작물의 작성 및 이용 등의 자유로운 이용이 영리적 목적을 포함하여 허용됩니다.

출처: [우주항공청 저작권 정책](https://www.kasa.go.kr/prog/bbsArticle/BBSMSTR_000000000190/view.do?bbsId=BBSMSTR_000000000190&nttId=B000000001923Bi6xJ7) · [공공누리 유형 안내](https://www.kogl.or.kr/info/licenseType2.do)

## 기여자 (Contributors)

| 기여자                                                                   | 역할 |
|-----------------------------------------------------------------------| --- |
| [Engineering-Excellence](https://github.com/Engineering-Excellence) (Kyle) | 메인테이너 · KASA 표준보고서 엔진 |
| [Canine89 / 박현규](https://github.com/Canine89/hwpxskill)               | 원본 `hwpx` 스킬 제작자 — XML 직접 제어 방식의 기반 |
| [ai-public-peasant](https://github.com/ai-public-peasant)             | [hwpx-rekian](https://github.com/ai-public-peasant/hwpx-rekian) 제작자 — 재기안(re-draft) 기능 설계 참고 |
| [jkf87](https://github.com/jkf87)                                     | hwpx-skill 접근법 참고 — 네임스페이스 후처리·secPr 보존·mimetype STORED·워크플로우 트리 |
| [Claude](https://github.com/claude) (Anthropic)                       | AI 페어 — 엔진·문서 작성 보조 |
