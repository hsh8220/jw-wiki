# JW Wiki

여호와의 증인 온라인 출판물(**jw.org**, **wol.jw.org**)의 내용을 수집·지식화하는 개인 위키.
[llm-wiki.md](llm-wiki.md)의 "LLM이 유지보수하는 위키" 패턴을 이 도메인에 구체화한 것이다.

LLM 에이전트(Claude Code 등)가 위키를 작성·유지하는 운영 규칙은 [CLAUDE.md](CLAUDE.md)에 있다.

## 빠른 시작

```bash
# 1) 의존성 설치 (최초 1회) — 가상환경 .venv 는 이미 만들어져 있다
.venv/bin/pip install -r requirements.txt

# 2) URL을 raw 소스로 수집 (동영상/기사 자동 판별)
.venv/bin/python tools/jwfetch.py "<jw.org 또는 wol.jw.org URL>"

#   동영상 예
.venv/bin/python tools/jwfetch.py "https://www.jw.org/ko/라이브러리/동영상/#ko/mediaitems/StudioFeatured/pub-jwb-138_1_VIDEO"
#   기사 예
.venv/bin/python tools/jwfetch.py "https://wol.jw.org/ko/wol/d/r8/lp-ko/502300131"

# 3) 이후 LLM 에이전트에게 "방금 수집한 소스를 위키에 정리해줘" 라고 하면
#    CLAUDE.md의 수집 워크플로에 따라 위키 페이지를 만들고 갱신한다.

# 위키 검색
.venv/bin/python tools/wikisearch.py "평화"
```

## 파이프라인

```
URL ──jwfetch.py──▶ raw/(불변 원본)  ──LLM(에이전트)──▶ wiki/(지식 베이스)
       ├ 동영상 → mediator API로 메타 + .vtt 자막 → 전사본
       └ 기사   → <article> HTML → 마크다운 + 성구 추출
```

- **도구(`tools/`)** 는 깨끗한 *원본*을 만드는 것까지만 담당한다.
- **지식화**(요약·교차참조·성구 그래프·모순 표기)는 LLM이 [CLAUDE.md](CLAUDE.md)의 규칙대로 수행한다.

## 구조

- `raw/` — 수집한 원본(기사/동영상). 불변.
- `wiki/` — LLM이 만드는 마크다운 지식 베이스(sources / concepts / entities / scriptures).
- `index.md` — 전체 카탈로그. `log.md` — 시간순 작업 기록.
- `tools/jwfetch.py` — 수집 CLI, `tools/jwlib.py` — 공용 로직, `tools/wikisearch.py` — 검색.

Obsidian으로 `jw_wiki/` 폴더를 열면 위키링크/그래프뷰로 탐색할 수 있다.
