# Log — JW Wiki 작업 기록

append-only. 각 항목은 `## [YYYY-MM-DD] <op> | <제목>` 형식. (`grep "^## \[" log.md | tail -5`)

## [2026-06-06] setup | 위키 구조·파이프라인 구축
- llm-wiki.md 패턴을 JW 도메인에 맞게 구체화. 3계층(raw/wiki/스키마) 구성.
- tools/jwfetch.py + jwlib.py: URL → raw 수집 파이프라인. 동영상(mediator API + .vtt 자막)과 기사(<article> HTML → 마크다운 + 성구 추출) 자동 판별.
- tools/wikisearch.py: 위키 전문 검색. CLAUDE.md(스키마), README, index, overview 작성.

## [2026-06-06] ingest | 요한복음 14:27—“나는 평화를 너희에게 남겨 준다”
- 소스: wol.jw.org 기사(doc 502300131, pub ijwbv). 성구 25개 추출.
- 생성/갱신: sources, concepts/평화, scriptures/요한복음 14_27, entities/예수 그리스도, index.

## [2026-06-06] ingest | JW 방송—2026년 6월: 제159기 길르앗 졸업식
- 소스: jw.org 동영상(pub-jwb-138_1_VIDEO, 1:32:23). KO 자막 전사본 추출(약 32k자).
- 주제 "평화를 이루십시오"가 요한복음 14:27 기사와 연결됨 → concepts/평화에서 두 측면으로 통합.
- 생성/갱신: sources, concepts/평화, scriptures/마태복음 5_23-24·창세기 13_8-9, entities/아브라함·길르앗 학교·예수 그리스도, index.

## [2026-06-06] setup | 카테고리 일괄 수집 기능 추가
- jwlib.fetch_category + parse_url 카테고리 판별 + jwfetch 카테고리 처리(세션 재사용, 중복 건너뛰기, --limit/--force).

## [2026-06-06] ingest | 카테고리 'StudioTalks'(연설) 동영상 102개 — raw 수집
- 102개 전부 raw/videos/ 에 메타데이터 캡처.
- 자막 있음 66개(KO .vtt 전사본 추출), 자막 없음 37개.
- 자막 없는 37개는 모두 구작(2014~2020, pub-jwban_2014~2016 / jwb_2017~2018 / mwbv_202005):
  jw.org에 KO .vtt 자막 자체가 미발행. mediator·GETPUBMEDIALINKS 모두 KO 자막 없음(영어 자막은 존재).
  → 전사본은 ASR 없이는 불가. 현재는 메타데이터만 보유(frontmatter의 subtitle_url 비어 있음).
- 아직 위키 지식화(wiki 페이지 생성) 전 단계. raw frontmatter ingested:false 유지.

## [2026-06-06] setup | 자막 영어 폴백 + 소스 페이지 생성기 추가
- jwlib.fetch_video: 한국어 자막 없으면 영어(E) 자막 폴백, transcript_lang 기록. 자막없던 37개 재수집 → 25개 영어 전사본 확보(12개는 전 언어 미발행, 메타데이터만).
- tools/jwscripture.py: 전사본 성구 추출 + 한국어 정경 정규화(영어 책이름→한국어 매핑).
- tools/gen_talk_pages.py: raw 동영상 → 소스·연사·성경책 페이지·index 일괄 생성.

## [2026-06-06] ingest | StudioTalks 연설 102편 — 위키 지식화
- 소스 페이지 102개(전사본 90 + 메타데이터 12) 생성. 연사 페이지 35명, 성경책 페이지 54권.
- 성구 그래프: 638개 구절 인용이 연설들과 교차연결. index.md 자동 재생성.
- 요약은 추출형(주제+도입부). 개별 연설 심층요약은 질의/요청 시 전사본 정독해 보강 예정.
- raw 동영상 source_url을 카테고리 URL → 개별 mediaitems URL로 보정.

## [2026-06-06] setup | 제목 핵심 성구(약어) 추출 추가
- jwscripture.parse_title_scripture: 제목 괄호의 핵심 성구를 약어(시·마태·누가·디모데 후서 등)까지 인식해 한국어 정경으로 정규화. gen_talk_pages가 key_scripture로 기록·표시하고 성구 목록 맨 앞에 추가.
- gen_talk_pages: category 필드를 raw에서 그대로 사용(하드코딩 제거), "접두어—연사" 형태 연사명 정리.

## [2026-06-06] ingest | 아침 숭배(VODPgmEvtMorningWorship) 동영상 325편 — 수집·지식화
- 325편 전부 한국어 자막 보유. raw 수집 후 gen_talk_pages로 일괄 지식화.
- 전체 위키 규모: 연설 소스 427편 · 연사 53명 · 성경책 62권 · 성구 인용 1,868곳.
- 요약은 추출형(주제 + 핵심 성구 + 도입부). 심층 요약은 요청 시 보강.

## [2026-06-07] query | 파수대 「우리는 미움을 받을 때에도 행복합니다」 교차 참조
- 기사 수집(doc 2026324, pub w) + 성구 44곳 정규화. 위키 연설과 성구 겹침/주제어로 교차 검색.
- 생성: sources/우리는-미움을-받을-때에도-행복합니다, concepts/미움과 박해 속의 행복(연구 동반 페이지).
- 강한 연결: 디모데후서 3:12(연설 2편 핵심성구), 요한복음 15:20, 요한복음 14:27→[[concepts/평화]], 사도행전 9:15.
- concepts/평화에 역링크 추가. index 재생성.

## [2026-06-07] lint   | 전면 점검: 엔티티 중복 2건, 개념층 단절, 빈 전사본 12건
- 엔티티 중복: 마크 누매어(14)/누메어(1); 제프리 W.잭슨(23)/재프리 W.잭슨(1)/제프리 잭슨(1) — raw 연사명 표기 불일치 원인
- 개념층: 430 소스 중 개념 링크 3건뿐, 태그는 [연설/연사명]만 → 주제 색인 부재
- 데이터: 빈 전사본(<40단어) 12건(한·영 자막 미발행), 영어폴백 32건
- 무결성 양호: 깨진 위키링크 0, 고아 페이지 0, frontmatter 누락 0

## [2026-06-07] lint   | 보완 처리: 엔티티 병합 + 개념 4종 신설 + overview 갱신
- P1 엔티티 중복 병합: gen_talk_pages.py에 SPEAKER_ALIASES 추가(마크 누메어→누매어, 재프리/제프리 잭슨→제프리 W. 잭슨), 낡은 변형 페이지 3개 삭제 후 재생성. 연사 53→50명.
- P2 개념 페이지 4종 신설(겸손과 교만·물질주의·사랑·자녀와 청소년 교육), 소스 49편 연결. concepts 2→6.
- P3 빈 전사본 12건: 생성기가 이미 '전사본 없음(자막 미발행)' 표시·transcript_lang:none로 필터 가능. 오해 요약 0건 확인, 추가 조치 불필요.
- overview.md 수치 갱신(연사 50명, 잭슨 25편, 새 개념 링크). 깨진 링크 0 유지.
## [2026-06-08] lint   | 반복 주제 심층 개념 페이지 6종 추가
- 지식 컴파일 1차 배치: [[concepts/지혜와 분별력]] · [[concepts/기도]] · [[concepts/인내와 위로]] · [[concepts/믿음과 희망]] · [[concepts/대속과 용서]] · [[concepts/전파와 봉사]] 생성.
- 각 개념은 관련 소스 9~16편을 묶어 핵심 종합·하위 주제·반복 성구·대표 소스를 정리.
- 관련 source 페이지 82곳에 concept 역링크 추가. index.md와 overview.md 재생성/갱신.

## [2026-06-08] lint   | 전체 source 반복 주제 concept 연결 확장
- 전체 컴파일 배치: concept 페이지를 30개로 확장하고 source 430/430개에 최소 1개 이상의 concept 역링크를 부여.
- 신규/확장 주제: 충성·순종·충절, 진리와 거짓, 사탄과 영적 전쟁, 중립과 세상과 구별됨, 성령과 하느님의 인도, 여호와에 대한 신뢰와 가까움, 예수의 본과 제자도, 성경과 영적 양식, 가정과 결혼 등.
- 각 concept에 `전체 연결 소스` 섹션을 추가해 source_count와 실제 역링크 수를 맞춤. index.md와 overview.md 갱신.
