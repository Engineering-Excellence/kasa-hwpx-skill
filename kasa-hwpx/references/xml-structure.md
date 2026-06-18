# HWPX XML 구조 메모

HWPX = **ZIP 패키지 + OWPML(XML) 파트**. 핵심 파트:
- `mimetype` — 첫 ZIP 엔트리, **무압축(STORED)**. 위반 시 일부 뷰어에서 안 열림.
- `Contents/header.xml` — 글꼴·charPr·paraPr·borderFill·style 정의.
- `Contents/section0.xml` — 표지/본문 레이아웃, secPr, 표, 머리말(MI).
- `Contents/content.hpf` — 파트/이미지 매니페스트(`BinData/image1.png` 등록).
- `BinData/image1.png` — 우주항공청 MI 로고.

## 루트 네임스페이스(section0.xml)
루트는 `<hs:sec ...>` 이며 다음 접두사를 선언한다:
`ha, hp, hp10, hs, hc, hh, hhs, hm, hpf, dc, opf, ooxmlchart, hwpunitchar, epub, config`.
**접두사(hp/hs/hh/hc 등)는 반드시 보존**한다. 본 엔진은 원본 section0.xml의 루트 선언을
그대로 유지하므로 접두사가 깨지지 않는다(`fix_namespaces`가 안전망으로 점검).

## 첫 문단 = secPr 캐리어
`section0.xml`의 **첫 `<hp:p>`(id=0)** 첫 run에 `<hp:secPr>`+`<hp:colPr>`가 들어 있고,
머리말(`<hp:header>` 안의 MI `<hp:pic>`)과 편집용지(`<hp:pagePr>`/`<hp:margin>`)도 여기 붙는다.
→ 이 문단을 보존해야 문서가 정상적으로 열리고 MI·여백이 유지된다.

## 단위(HWPUNIT)
| 값 | HWPUNIT |
| --- | --- |
| 1pt | 100 |
| 1mm | ≈ 283.465 |
| A4 폭/높이 | 59528 / 84188 |
| 본문 가용폭(좌우 20mm 여백) | ≈ 48188 |

편집용지 여백(본 양식): `header=5669(20mm) footer=2834(10mm) left=right=5669(20mm) top=1417(5mm) bottom=4251(15mm)`.

## 본문 문단 패턴
```xml
<hp:p id="{고유}" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="{30|41|29}"><hp:t>{텍스트}</hp:t></hp:run>
  <hp:linesegarray><hp:lineseg .../></hp:linesegarray>
</hp:p>
```
`linesegarray`의 vertpos 등은 한글이 열 때 재계산하므로 시드 값이어도 무방하다.

## 표 패턴
표는 `<hp:p paraPrIDRef="12"><hp:run charPrIDRef="15"><hp:tbl ...>…</hp:tbl><hp:t/></hp:run>…</hp:p>` 로 감싼다.
`<hp:tbl>` 자식 순서: `sz → pos → outMargin → inMargin → tr…`.
`<hp:tc>` = `subList(>p>run>t) + cellAddr + cellSpan + cellSz + cellMargin`.
제목행은 `colSpan = 열수`로 병합, 머리행 borderFill=11, 데이터 borderFill=3.

## 표지 치환 원칙
표지는 **표 기반 레이아웃**(중첩 `<hp:p>`)이라 정규식 단순 분리가 위험하다.
본 엔진은 표지를 통째로 보존하고, **주석 앵커가 포함된 문단 범위에서 `<hp:t>` 텍스트만**
교체한다(주석런은 빈 텍스트로 제거). 본문 영역만 유일 앵커 `□ 제목1`부터 `</hs:sec>` 직전까지
삭제 후 재생성한다.

---
### 출처/크레딧
설계·규칙(네임스페이스 후처리, secPr 필수, mimetype STORED, 페이지 수 가드, 워크플로우 트리)은
공개 저장소 **jkf87/hwpx-skill**, **Canine89/hwpxskill**의 접근법을 참고하여
표준 라이브러리만으로 재구현했다.
