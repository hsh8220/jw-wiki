"""jwscripture — 전사본/본문에서 성경 인용을 추출하고 한국어 정경 이름으로 정규화한다.

한국어 자막과 (폴백된) 영어 자막을 모두 다루므로, 영어 책 이름도 한국어로 매핑한다.
정밀도를 우선한다(모호한 단독 "요한"/"마태" 등은 잡지 않는다).
"""
from __future__ import annotations

import re

# 정경 한국어 이름 → 표면형(별칭) 목록. 표면형은 정규식 후보로 쓰인다.
KO_BOOKS = {
    "창세기": ["창세기"], "출애굽기": ["출애굽기", "탈출기"], "레위기": ["레위기"],
    "민수기": ["민수기"], "신명기": ["신명기"], "여호수아": ["여호수아"],
    "판관기": ["판관기", "사사기"], "룻기": ["룻기"],
    "사무엘상": ["사무엘 상", "사무엘상", "사무엘 첫째"],
    "사무엘하": ["사무엘 하", "사무엘하", "사무엘 둘째"],
    "열왕기상": ["열왕기 상", "열왕기상", "열왕기 첫째"],
    "열왕기하": ["열왕기 하", "열왕기하", "열왕기 둘째"],
    "역대상": ["역대 상", "역대상", "역대기 상", "역대기 첫째"],
    "역대하": ["역대 하", "역대하", "역대기 하", "역대기 둘째"],
    "에스라": ["에스라"], "느헤미야": ["느헤미야"], "에스더": ["에스더"],
    "욥기": ["욥기"], "시편": ["시편"], "잠언": ["잠언"], "전도서": ["전도서"],
    "솔로몬의 노래": ["솔로몬의 노래", "아가"], "이사야": ["이사야"],
    "예레미야": ["예레미야"], "예레미야애가": ["예레미야애가", "애가"],
    "에스겔": ["에스겔"], "다니엘": ["다니엘"], "호세아": ["호세아"],
    "요엘": ["요엘"], "아모스": ["아모스"], "오바댜": ["오바댜"], "요나": ["요나"],
    "미가": ["미가"], "나훔": ["나훔"], "하박국": ["하박국"], "스바냐": ["스바냐"],
    "학개": ["학개"], "스가랴": ["스가랴"], "말라기": ["말라기"],
    "마태복음": ["마태복음"], "마가복음": ["마가복음", "마르코복음"],
    "누가복음": ["누가복음"], "요한복음": ["요한복음"], "사도행전": ["사도행전"],
    "로마서": ["로마서"],
    "고린도전서": ["고린도 전서", "고린도전서", "고린도 첫째"],
    "고린도후서": ["고린도 후서", "고린도후서", "고린도 둘째"],
    "갈라디아서": ["갈라디아서"], "에베소서": ["에베소서", "에페소서"],
    "빌립보서": ["빌립보서", "필리피서"], "골로새서": ["골로새서", "골로사이서"],
    "데살로니가전서": ["데살로니가 전서", "데살로니가전서"],
    "데살로니가후서": ["데살로니가 후서", "데살로니가후서"],
    "디모데전서": ["디모데 전서", "디모데전서"],
    "디모데후서": ["디모데 후서", "디모데후서"],
    "디도서": ["디도서"], "빌레몬서": ["빌레몬서"], "히브리서": ["히브리서"],
    "야고보서": ["야고보서"],
    "베드로전서": ["베드로 전서", "베드로전서", "베드로 첫째"],
    "베드로후서": ["베드로 후서", "베드로후서", "베드로 둘째"],
    "요한일서": ["요한 1서", "요한1서", "요한일서", "요한 첫째"],
    "요한이서": ["요한 2서", "요한2서", "요한이서", "요한 둘째"],
    "요한삼서": ["요한 3서", "요한3서", "요한삼서", "요한 셋째"],
    "유다서": ["유다서"], "요한계시록": ["요한계시록", "요한 계시록", "계시록"],
}

# 영어 책 이름 → 한국어 정경
EN_BOOKS = {
    "Genesis": "창세기", "Exodus": "출애굽기", "Leviticus": "레위기",
    "Numbers": "민수기", "Deuteronomy": "신명기", "Joshua": "여호수아",
    "Judges": "판관기", "Ruth": "룻기", "1 Samuel": "사무엘상",
    "2 Samuel": "사무엘하", "1 Kings": "열왕기상", "2 Kings": "열왕기하",
    "1 Chronicles": "역대상", "2 Chronicles": "역대하", "Ezra": "에스라",
    "Nehemiah": "느헤미야", "Esther": "에스더", "Job": "욥기",
    "Psalms": "시편", "Psalm": "시편", "Proverbs": "잠언",
    "Ecclesiastes": "전도서", "Song of Solomon": "솔로몬의 노래",
    "Song of Songs": "솔로몬의 노래", "Isaiah": "이사야", "Jeremiah": "예레미야",
    "Lamentations": "예레미야애가", "Ezekiel": "에스겔", "Daniel": "다니엘",
    "Hosea": "호세아", "Joel": "요엘", "Amos": "아모스", "Obadiah": "오바댜",
    "Jonah": "요나", "Micah": "미가", "Nahum": "나훔", "Habakkuk": "하박국",
    "Zephaniah": "스바냐", "Haggai": "학개", "Zechariah": "스가랴",
    "Malachi": "말라기", "Matthew": "마태복음", "Mark": "마가복음",
    "Luke": "누가복음", "John": "요한복음", "Acts": "사도행전",
    "Romans": "로마서", "1 Corinthians": "고린도전서", "2 Corinthians": "고린도후서",
    "Galatians": "갈라디아서", "Ephesians": "에베소서", "Philippians": "빌립보서",
    "Colossians": "골로새서", "1 Thessalonians": "데살로니가전서",
    "2 Thessalonians": "데살로니가후서", "1 Timothy": "디모데전서",
    "2 Timothy": "디모데후서", "Titus": "디도서", "Philemon": "빌레몬서",
    "Hebrews": "히브리서", "James": "야고보서", "1 Peter": "베드로전서",
    "2 Peter": "베드로후서", "1 John": "요한일서", "2 John": "요한이서",
    "3 John": "요한삼서", "Jude": "유다서", "Revelation": "요한계시록",
}

# 표면형 → 정경. 긴 표면형부터 매칭하도록 정렬.
_SURFACE = {}
for canon, surfs in KO_BOOKS.items():
    for s in surfs:
        _SURFACE[s] = canon
_KO_ALT = sorted(_SURFACE, key=len, reverse=True)
_KO_PAT = re.compile(
    r"(" + "|".join(re.escape(s) for s in _KO_ALT) + r")"
    r"\s*(\d+)\s*(?::\s*(\d+(?:\s*[,\-–]\s*\d+)*))?(장)?"
)

# 영어: 숫자 접두(1/2/3, First/Second/Third) + 책 이름 + 장:절
_EN_NUM = {"first": "1", "second": "2", "third": "3", "1": "1", "2": "2", "3": "3"}
_EN_BASE = sorted({re.sub(r"^[123]\s+", "", k) for k in EN_BOOKS}, key=len, reverse=True)
_EN_PAT = re.compile(
    r"\b(?:(First|Second|Third|[123])\s+)?"
    r"(" + "|".join(re.escape(b) for b in _EN_BASE) + r")"
    r"\s+(\d+)(?::(\d+(?:\s*[,\-–]\s*\d+)*))?",
    re.IGNORECASE,
)


def _norm_ref(book: str, chap: str, verses: str, is_chapter: bool) -> str:
    if verses:
        verses = re.sub(r"\s*([,\-–])\s*", r"\1", verses)
        return f"{book} {chap}:{verses}"
    if is_chapter:
        return f"{book} {chap}장"
    return f"{book} {chap}"


def extract(text: str, lang: str = "KO") -> list:
    """본문에서 성구 인용을 추출해 한국어 정경 표기로 정규화한 목록(순서/중복제거) 반환."""
    refs, seen = [], set()

    for m in _KO_PAT.finditer(text):
        surf, chap, verses, jang = m.group(1), m.group(2), m.group(3), m.group(4)
        ref = _norm_ref(_SURFACE[surf], chap, verses, bool(jang))
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)

    if lang and lang.upper() not in ("KO", "KOREAN"):
        for m in _EN_PAT.finditer(text):
            num, base, chap, verses = m.groups()
            name = base
            if num:
                name = f"{_EN_NUM.get(num.lower(), num)} {base}"
            # 정확한 키 매칭 (대소문자 보정)
            canon = None
            for k, v in EN_BOOKS.items():
                if k.lower() == name.lower():
                    canon = v
                    break
            if not canon:
                continue
            ref = _norm_ref(canon, chap, verses, False)
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)

    return refs


def book_of(ref: str) -> str:
    """정규화된 성구 문자열에서 책 이름만 추출."""
    m = re.match(r"(.+?)\s+\d", ref)
    return m.group(1) if m else ref


# --------------------------------------------------------------------------- #
# 제목 괄호 안의 핵심 성구 (약어 포함). 예: "... (시 19:7)", "(디모데 후서 3:12)"
# 본문 추출보다 공격적으로(약어까지) 매칭한다 — 괄호 안은 인용이 거의 확실하므로.
# --------------------------------------------------------------------------- #
KO_ABBREV = {
    "창세": "창세기", "출애굽": "출애굽기", "레위": "레위기", "민수": "민수기",
    "신명": "신명기", "여호수아": "여호수아", "판관": "판관기", "룻": "룻기",
    "사무엘상": "사무엘상", "사무엘하": "사무엘하", "사무엘 상": "사무엘상",
    "사무엘 하": "사무엘하", "열왕기상": "열왕기상", "열왕기하": "열왕기하",
    "열왕기 상": "열왕기상", "열왕기 하": "열왕기하", "역대상": "역대상",
    "역대하": "역대하", "역대 상": "역대상", "역대 하": "역대하",
    "에스라": "에스라", "느헤미야": "느헤미야", "에스더": "에스더", "욥": "욥기",
    "시": "시편", "잠": "잠언", "전도": "전도서", "전": "전도서", "아가": "솔로몬의 노래",
    "이사야": "이사야", "예레미야": "예레미야", "애가": "예레미야애가",
    "에스겔": "에스겔", "다니엘": "다니엘", "호세아": "호세아", "요엘": "요엘",
    "아모스": "아모스", "오바댜": "오바댜", "요나": "요나", "미가": "미가",
    "나훔": "나훔", "하박국": "하박국", "스바냐": "스바냐", "학개": "학개",
    "스가랴": "스가랴", "말라기": "말라기",
    "마태": "마태복음", "마가": "마가복음", "누가": "누가복음", "요한": "요한복음",
    "사도": "사도행전", "로마": "로마서",
    "고린도 전서": "고린도전서", "고린도 후서": "고린도후서",
    "고전": "고린도전서", "고후": "고린도후서", "갈라디아": "갈라디아서",
    "에베소": "에베소서", "빌립보": "빌립보서", "골로새": "골로새서",
    "데살로니가 전서": "데살로니가전서", "데살로니가 후서": "데살로니가후서",
    "디모데 전서": "디모데전서", "디모데 후서": "디모데후서",
    "디도": "디도서", "빌레몬": "빌레몬서", "히브리": "히브리서", "야고보": "야고보서",
    "베드로 전서": "베드로전서", "베드로 후서": "베드로후서",
    "요한 1서": "요한일서", "요한 2서": "요한이서", "요한 3서": "요한삼서",
    "유다": "유다서", "계시록": "요한계시록", "요한계시록": "요한계시록",
}
_TITLE_SURFACE = dict(_SURFACE)
_TITLE_SURFACE.update(KO_ABBREV)
_TITLE_ALT = sorted(_TITLE_SURFACE, key=len, reverse=True)
_TITLE_PAT = re.compile(
    r"\(\s*(" + "|".join(re.escape(s) for s in _TITLE_ALT) + r")"
    r"\s*(\d+)\s*(?::\s*(\d+(?:\s*[,\-–]\s*\d+)*))?(장)?\s*\)"
)


def parse_title_scripture(title: str):
    """제목 끝의 괄호 안 핵심 성구를 한국어 정경 표기로 반환. 없으면 None."""
    matches = list(_TITLE_PAT.finditer(title))
    if not matches:
        return None
    m = matches[-1]      # 제목 맨 끝의 괄호를 핵심 성구로 본다
    surf, chap, verses, jang = m.group(1), m.group(2), m.group(3), m.group(4)
    return _norm_ref(_TITLE_SURFACE[surf], chap, verses, bool(jang))
