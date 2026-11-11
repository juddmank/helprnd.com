# -*- coding: utf-8 -*-
"""
기업마당(bizinfo.go.kr) 지원사업 공고 아침 브리핑 PPT 만들기 (Kay 전용)

사용법:  python bizinfo_briefing.py [--out 저장폴더] [--days 1]
- 지난번 실행 뒤 새로 올라온 공고를 모은다 (처음 실행이면 최근 --days 일).
- 관심 지역(HOMES: 부산, 울산, 경남) 공고와 전국(중앙부처) 공고를 따로 정리하고, 다른 지역 공고는 개수만 센다.
- 결과: <저장폴더>/YYYY-MM-DD_지원사업공고.pptx
"""
import argparse, datetime as dt, html, json, re, sys, time, urllib.request
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

BASE = "https://www.bizinfo.go.kr"
LIST = BASE + "/sii/siia/selectSIIA200View.do?rows=15&cpage={page}"
DETAIL = BASE + "/sii/siia/selectSIIA200Detail.do?pblancId={id}"
HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"

HOMES = ["부산", "울산", "경남"]  # 자세히 정리할 지역 (순서대로 장이 만들어진다)
HOME_LABEL = "·".join(HOMES)
REGIONS = ["서울", "부산", "대구", "인천", "전남", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "경북", "경남", "제주"]  # '[전남광주] 목포시'처럼 붙은 태그는 전남으로
REGION_ORG = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
              "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
              "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
              "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
              "경상남도": "경남", "제주특별자치도": "제주"}
FIELD_ORDER = ["경영", "금융", "창업", "인력", "기술", "수출", "내수", "기타"]

NAVY = RGBColor(0x14, 0x24, 0x3D)
ORANGE = RGBColor(0xF2, 0x8C, 0x28)
INK = RGBColor(0x22, 0x2B, 0x3A)
MUTED = RGBColor(0x6B, 0x75, 0x87)
LINE = RGBColor(0xE3, 0xE7, 0xEE)
ZEBRA = RGBColor(0xF6, 0xF8, 0xFB)
RED = RGBColor(0xD6, 0x45, 0x45)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "맑은 고딕"


# ---------------- 수집 ----------------
def _ssl_context():
    """기본 인증서 + 일부 기관 사이트가 빠뜨린 중간 인증서(certs/extra_intermediates.pem)로 검증한다."""
    import ssl
    ctx = ssl.create_default_context()
    extra = HERE / "certs" / "extra_intermediates.pem"
    if extra.exists():
        ctx.load_verify_locations(str(extra))
    return ctx


SSL_CTX = None


def fetch(url, tries=3):
    global SSL_CTX
    if SSL_CTX is None:
        SSL_CTX = _ssl_context()
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (bizinfo-briefing)"})
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 + i * 2)


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_list(page_html):
    body = re.search(r"<tbody>(.*?)</tbody>", page_html, re.S)
    if not body:
        return []
    items = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body.group(1), re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        m = re.search(r"pblancId=(PBLN_\d+)", tr)
        if len(tds) < 8 or not m:
            continue
        items.append({
            "no": clean(tds[0]), "field": clean(tds[1]), "title": clean(tds[2]),
            "period": clean(tds[3]), "org": clean(tds[4]), "agency": clean(tds[5]),
            "date": clean(tds[6]), "views": clean(tds[7]),
            "id": m.group(1), "num": int(m.group(1).split("_")[1]),
        })
    return items


def collect(since_num, since_date, max_pages=40):
    out = []
    for page in range(1, max_pages + 1):
        rows = parse_list(fetch(LIST.format(page=page)))
        if not rows:
            break
        new = [r for r in rows if (r["num"] > since_num if since_num else r["date"] >= since_date)]
        out += new
        if len(new) < len(rows):  # 목록은 등록일 최신순: 오래된 공고가 섞이기 시작하면 끝
            break
        time.sleep(0.5)
    return out


def parse_detail(page_html):
    """상세 페이지 '사업개요'에서 신청요건(지원대상)과 지원내용을 뽑는다.
    기업마당 사업개요는 보통 [소개문] / ☞ 지원대상 / ☞ 지원내용 순서로 쓰여 있다."""
    m = re.search(r'<span class="s_title">사업개요</span>\s*<div class="txt">(.*?)</div>\s*</li>', page_html, re.S)
    if not m:
        return {"intro": "", "target": "", "support": ""}
    raw = re.sub(r"<br\s*/?>", "\n", m.group(1))
    raw = re.sub(r"</(p|div|li)>", "\n", raw)
    lines = [clean(l) for l in raw.split("\n")]
    lines = [l for l in lines if l]
    blocks, cur = [], None
    intro = []
    for l in lines:
        if l.startswith("☞"):
            cur = [l.lstrip("☞").strip()]
            blocks.append(cur)
        elif cur is not None:
            cur.append(l)
        else:
            intro.append(l)
    fmt = lambda blk: "\n".join(blk) if blk else ""
    return {"intro": " ".join(intro), "target": fmt(blocks[0] if blocks else []),
            "support": fmt(blocks[1] if len(blocks) > 1 else [])}


def add_details(items):
    for it in items:
        if "target" in it:  # 이미 가져온 공고 (부산테크노파크 등)
            continue
        try:
            it.update(parse_detail(fetch(DETAIL.format(id=it["id"]))))
        except Exception:
            it.update({"intro": "", "target": "", "support": ""})
        time.sleep(0.3)


def link_of(it):
    return it.get("url") or DETAIL.format(id=it["id"])


# ---------------- 부산테크노파크(BTP) 사업공고 ----------------
BTP_BASE = "https://www.btp.or.kr/kor/CMS/Board/Board.do"
BTP_LIST = BTP_BASE + "?mCode=MN013&page={page}"
BTP_VIEW = BTP_BASE + "?mCode=MN013&mode=view&mgr_seq=16&board_seq={seq}"
BTP_FIELD = {"창업": "창업", "입주": "창업", "수출": "수출", "해외": "수출", "R&D": "기술", "기술": "기술",
             "인증": "기술", "인력": "인력", "채용": "인력", "교육": "인력", "자금": "금융", "금융": "금융",
             "판로": "내수", "전시회": "내수", "마케팅": "내수", "컨설팅": "경영", "경영": "경영"}


def _strip_label(t):
    """'모 집 대 상 예비창업자…' 처럼 한 글자씩 띄운 소제목을 떼어낸다."""
    return re.sub(r"^(?:\S ){2,}\S\s+", "", t).strip()


def btp_parse_list(page_html):
    body = re.search(r"<tbody>(.*?)</tbody>", page_html, re.S)
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1) if body else "", re.S):
        m = re.search(r"board_seq=(\d+)", tr)
        title = re.search(r'class="titleHover">(.*?)</span>', tr, re.S)
        if not m or not title:
            continue
        cell = lambda c: clean((re.search(rf'<td class="{c}">(.*?)</td>', tr, re.S) or [None, ""])[1])
        period = re.sub(r"접수기간 :|D-\d+|D-DAY", "", cell("period"))
        period = " ~ ".join(d.replace(".", "-") for d in re.findall(r"\d{4}\.\d{2}\.\d{2}", period)) or clean(period)
        out.append({"seq": int(m.group(1)), "id": f"BTP_{m.group(1)}", "num": int(m.group(1)),
                    "title": clean(title.group(1)), "period": period, "state": cell("state"),
                    "date": cell("date").replace(".", "-"), "views": re.sub(r"\D", "", cell("cnt")) or "0",
                    "org": "부산테크노파크", "agency": "", "field": "기타",
                    "url": BTP_VIEW.format(seq=m.group(1)), "source": "btp"})
    return out


def btp_parse_detail(page_html):
    info = {}
    for li in re.findall(r"<li[^>]*>\s*<span class=\"tit[^\"]*\">(.*?)</span>(.*?)</li>", page_html, re.S):
        key = re.sub(r"\s+", "", clean(li[0]))
        val = re.sub(r"<br\s*/?>", "\n", li[1])
        lines = [_strip_label(clean(x)) for x in val.split("\n")]
        info[key] = "\n".join(l for l in lines if l)
    field = re.search(r'지원분야 : </span>(.*?)</li>', page_html)
    intro = re.search(r'<div class="txt-box">(.*?)</div>', page_html, re.S)
    f = clean(field.group(1)) if field else ""
    return {"target": info.get("지원대상", ""), "support": info.get("지원내용", ""),
            "intro": clean(intro.group(1)) if intro else "",
            "field": f}


def btp_collect(since_seq, since_date, max_pages=5):
    out = []
    for page in range(1, max_pages + 1):
        rows = btp_parse_list(fetch(BTP_LIST.format(page=page)))
        if not rows:
            break
        new = [r for r in rows if (r["seq"] > since_seq if since_seq else r["date"] >= since_date)]
        out += new
        if len(new) < len(rows):
            break
        time.sleep(0.5)
    for it in out:
        try:
            it.update(btp_parse_detail(fetch(it["url"])))
        except Exception:
            it.update({"target": "", "support": "", "intro": "", "field": ""})
        # 지원분야가 '기타'면 공고 제목으로 분야를 짐작한다
        it["field"] = next((v for k, v in BTP_FIELD.items() if k in it.get("field", "")), None)             or next((v for k, v in BTP_FIELD.items() if k in it["title"]), "기타")
        time.sleep(0.3)
    return out


def _with_tp(items, key, org, region):
    for it in items:
        it.update({"source": key, "org": org, "tp_region": region})
    return items


# ---------------- 공고 본문에서 '지원대상'·'지원내용' 줄 골라내기 (울산·경남TP 공통) ----------------
TARGET_KEYS = ("지원대상", "모집대상", "신청대상", "신청자격", "지원자격", "참가자격", "참여대상", "참가대상", "대상기업")
SUPPORT_KEYS = ("지원내용", "지원규모", "지원사항", "지원금액", "지원분야", "모집규모", "모집내용", "지원혜택", "임대내용")


def extract_sections(text):
    lines = [l.strip() for l in re.split(r"[\r\n]+", text or "") if l.strip()]
    found = {"target": [], "support": []}
    cur = None
    for l in lines:
        bare = re.sub(r"\s+", "", l)
        head = re.match(r"^[□■○●◦ㅇ\-\*·•▶▷※\d\.\)]*\s*", l)
        label_zone = re.sub(r"\s+", "", l[head.end():][:14]) if head else bare[:14]
        hit = None
        if any(label_zone.startswith(k) for k in TARGET_KEYS):
            hit = "target"
        elif any(label_zone.startswith(k) for k in SUPPORT_KEYS):
            hit = "support"
        if hit:
            cur = hit
            val = re.split(r"[:：]", l, 1)
            val = val[1].strip() if len(val) > 1 else ""
            if val:
                found[hit].append(val)
            continue
        if cur and re.match(r"^[\-◦ㆍ·•\*※]|^\(|^[가-하]\.", l):
            found[cur].append(l)
            continue
        if cur and re.match(r"^[□■○●ㅇ]", l):
            cur = None
    return {k: "\n".join(v[:6]) for k, v in found.items()}


# ---------------- 울산테크노파크 (utp.or.kr, JSON) ----------------
UTP_API = "https://www.utp.or.kr/proc/re_ancmt/list.php"
UTP_VIEW = "https://www.utp.or.kr/include/contents.php?mnuno=M0000018&menu_group=1&sno=0102&task=view&seq={seq}"


def utp_collect(since_seq, since_date, max_pages=3):
    out = []
    for page in range(1, max_pages + 1):
        data = json.loads(fetch(f"{UTP_API}?task=list&page={page}")).get("data") or []
        if not data:
            break
        for d in data:
            seq = int(d["seq"])
            created = d["created_dt"][:10]
            new = seq > since_seq if since_seq else created >= since_date
            if not new or d.get("status") == "3":
                continue
            out.append({"seq": seq, "id": f"UTP_{seq}", "num": seq, "title": clean(d["title"]),
                        "period": f'{d["apply_start_dt"][:10]} ~ {d["apply_end_dt"][:10]}',
                        "state": {"1": "접수중", "2": "접수전"}.get(d.get("status"), ""), "date": created,
                        "views": str(d.get("hit_cnt", "0")), "agency": "", "field": "기타",
                        "url": UTP_VIEW.format(seq=seq)})
        if all(d.get("is_gonggi") != "Y" and d["created_dt"][:10] < since_date for d in data[-3:]) and not since_seq:
            break
        time.sleep(0.5)
    uniq = {it["seq"]: it for it in out}
    out = list(uniq.values())
    for it in out:
        try:
            v = json.loads(fetch(f"{UTP_API}?task=getItem&seq={it['seq']}"))["data"]
            sec = extract_sections((v.get("supported_target") or "") + "\n" + (v.get("outline") or ""))
            it.update({"target": sec["target"] or re.sub(r"^[□\s]*지원대상\s*", "", v.get("supported_target") or "").strip(),
                       "support": sec["support"], "intro": clean(v.get("content") or "")})
        except Exception:
            it.update({"target": "", "support": "", "intro": ""})
        time.sleep(0.3)
    return out


# ---------------- 경남테크노파크 (gntp.or.kr) ----------------
GNTP_LIST = "https://www.gntp.or.kr/biz/apply"
GNTP_VIEW = "https://www.gntp.or.kr/biz/applyInfo/{seq}"


def gntp_collect(since_seq, since_date):
    h = fetch(GNTP_LIST)
    body = h[h.find('id="gridData"'):]
    out = []
    for tr in re.findall(r'<tr class="table-contents">(.*?)</tr>', body, re.S):
        m = re.search(r"/biz/applyInfo/(\d+)", tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not m or len(tds) < 8:
            continue
        seq = int(m.group(1))
        start = (re.findall(r"\d{4}-\d{2}-\d{2}", tds[5]) or [""])[0]
        end = (re.findall(r"\d{4}-\d{2}-\d{2}", tds[6]) or [""])[0]
        state = clean(tds[7])
        new = seq > since_seq if since_seq else start >= since_date
        if not new or "마감" in state:
            continue
        out.append({"seq": seq, "id": f"GNTP_{seq}", "num": seq, "title": clean(tds[4]),
                    "period": f"{start} ~ {end}", "state": state, "date": start, "views": "0",
                    "agency": clean(tds[2]), "field": "기타", "url": GNTP_VIEW.format(seq=seq)})
    for it in out:
        try:
            v = fetch(it["url"])
            t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", v, flags=re.S)
            t = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</td>|</th>", "\n", t)
            t = html.unescape(re.sub(r"<[^>]+>", " ", t))
            t = "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n"))
            body_txt = t[t.find("공고 제"):] if "공고 제" in t else t
            sec = extract_sections(body_txt)
            intro = re.search(r"호\s*\n+[^\n]*\n+([^\n]{30,})", body_txt)
            it.update({"target": sec["target"], "support": sec["support"], "intro": intro.group(1).strip() if intro else ""})
        except Exception:
            it.update({"target": "", "support": "", "intro": ""})
        time.sleep(0.3)
    return out


def _norm_title(t):
    return re.sub(r"\[[^\]]*\]|[^가-힣A-Za-z0-9]", "", t)


def page_lines(page_html):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page_html, flags=re.S)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</td>|</th>|</dt>|</dd>|</h\d>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return [l for l in (re.sub(r"\s+", " ", x).strip() for x in t.split("\n")) if l]


STOP_LABELS = ("공고기간", "접수기간", "접수방법", "신청방법", "문의처", "관련문의", "기타", "사업명", "사업기간",
               "첨부파일", "담당자", "담당부서", "선정방법", "제출서류", "목록", "목록으로", "다음글", "이전글")


def extract_pairs(lines, limit=6):
    """'지원대상' 같은 제목 줄 다음 줄들에 값이 오는 표 모양 상세 페이지용 (대구·포항TP)."""
    out = {"target": [], "support": []}
    cur = None
    for l in lines:
        key = re.sub(r"[\s\.·:：]", "", l)
        if key in TARGET_KEYS:
            cur = "target"; continue
        if key in SUPPORT_KEYS:
            cur = "support"; continue
        if key in STOP_LABELS or (len(key) <= 8 and l.startswith(".")):
            cur = None; continue
        if cur and len(out[cur]) < limit:
            out[cur].append(l)
    return {k: "\n".join(v) for k, v in out.items()}


def _body_after(lines, marker_regex):
    for n, l in enumerate(lines):
        if re.search(marker_regex, l):
            return lines[n:]
    return lines


# ---------------- 대구테크노파크 (ttp.org) ----------------
TTP_LIST = "https://www.ttp.org/bbs/BoardControll.do?bbsId=BBSMSTR_000000000003&pageIndex={page}"
TTP_VIEW = "https://www.ttp.org/bbs/BoardControllView.do?nttId={seq}&bbsId=BBSMSTR_000000000003"


def ttp_collect(since_seq, since_date, max_pages=2):
    out = []
    for page in range(1, max_pages + 1):
        h = fetch(TTP_LIST.format(page=page))
        body = h[h.find("<tbody"):h.find("</tbody>")]
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        if not rows:
            break
        old = 0
        for r in rows:
            m = re.search(r"fn_egov_inqire_notice\('(\d+)'", r)
            tds = [clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if not m or len(tds) < 8:
                continue
            seq, date, state = int(m.group(1)), tds[7], tds[4]
            a = re.search(r'class="tooltiptext"><a[^>]*>([^<]+)', r) or re.search(r'<a href="#link"[^>]*>\s*([^<]+?)\s*</a>', r)
            title = clean(a.group(1)) if a else tds[2]
            new = seq > since_seq if since_seq else date >= since_date
            if not new:
                old += 1
                continue
            if "완료" in state or "마감" in state:
                continue
            ds = re.findall(r"\d{4}-\d{2}-\d{2}", tds[3])
            out.append({"seq": seq, "id": f"TTP_{seq}", "num": seq, "title": title,
                        "period": " ~ ".join(ds) if ds else state, "state": state, "date": date,
                        "views": re.sub(r"\D", "", tds[8]) if len(tds) > 8 else "0", "agency": tds[1],
                        "field": "기타", "url": TTP_VIEW.format(seq=seq)})
        if old >= len(rows) - 2:
            break
        time.sleep(0.5)
    for it in out:
        try:
            L = page_lines(fetch(it["url"]))
            body = _body_after(L, r"공고 제")
            pairs = extract_pairs(body)
            intro = next((l for l in body[2:8] if len(l) > 40), "")
            it.update({"target": pairs["target"], "support": pairs["support"], "intro": intro})
        except Exception:
            it.update({"target": "", "support": "", "intro": ""})
        time.sleep(0.3)
    return out


# ---------------- 경북테크노파크 (gbtp.or.kr) ----------------
GBTP_LIST = "https://www.gbtp.or.kr/user/board.do?bbsId=BBSMSTR_000000000021&pageIndex={page}"
GBTP_VIEW = "https://www.gbtp.or.kr/user/boardDetail.do?bbsId=BBSMSTR_000000000021&nttNo={seq}"


def gbtp_collect(since_seq, since_date, max_pages=2):
    out = []
    for page in range(1, max_pages + 1):
        h = fetch(GBTP_LIST.format(page=page))
        body = h[h.find("<tbody"):]
        body = body[:body.find("</tbody>")]
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        if not rows:
            break
        old = 0
        for r in rows:
            m = re.search(r"fn_detail\('(\d+)'", r)
            tds = [clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if not m or len(tds) < 4:
                continue
            seq = int(m.group(1))
            date = (re.findall(r"\d{4}-\d{2}-\d{2}", tds[2]) or [""])[0]
            ds = re.findall(r"\d{4}-\d{2}-\d{2}", tds[3])
            state = tds[4] if len(tds) > 4 else tds[-1]
            new = seq > since_seq if since_seq else date >= since_date
            if not new:
                old += 1
                continue
            if "마감" in state or "완료" in state:
                continue
            out.append({"seq": seq, "id": f"GBTP_{seq}", "num": seq, "title": tds[1],
                        "period": " ~ ".join(ds), "state": state, "date": date, "views": "0",
                        "agency": "", "field": "기타", "url": GBTP_VIEW.format(seq=seq)})
        if old >= len(rows) - 2:
            break
        time.sleep(0.5)
    for it in out:
        try:
            L = page_lines(fetch(it["url"]))
            dept = next((L[n + 1] for n, l in enumerate(L) if l == "담당부서" and n + 1 < len(L)), "")
            body = _body_after(L, r"^내용$")[1:]
            body = body[:next((n for n, l in enumerate(body) if l in ("다음글", "이전글")), len(body))]
            sec = extract_sections("\n".join(body))
            pairs = extract_pairs(body)
            intro = " ".join(body)[:300].strip('" ')
            it.update({"agency": dept, "target": sec["target"] or pairs["target"],
                       "support": sec["support"] or pairs["support"], "intro": intro})
        except Exception:
            it.update({"target": "", "support": "", "intro": ""})
        time.sleep(0.3)
    return out


# ---------------- 포항테크노파크 (ptp.or.kr) ----------------
PTP_LIST = "https://www.ptp.or.kr/main/board/index.do?menu_idx=116&manage_idx=15&pageIndex={page}"
PTP_VIEW = "https://www.ptp.or.kr/main/board/view.do?menu_idx=116&manage_idx=15&board_idx={seq}"


def ptp_collect(since_seq, since_date):
    h = fetch(PTP_LIST.format(page=1))
    body = h[h.find("<tbody"):]
    body = body[:body.find("</tbody>")]
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        m = re.search(r"viewBoard\((\d+)", r)
        if not m:
            continue
        seq = int(m.group(1))
        title = clean((re.search(r'<td class="subject">.*?<span>(.*?)</span>', r, re.S) or [None, ""])[1])
        dept = clean((re.search(r'<td class="point-blue">(.*?)</td>', r, re.S) or [None, ""])[1])
        state = clean((re.search(r'<span class="tag-d[^"]*">(.*?)</span>', r, re.S) or [None, ""])[1])
        ds = re.findall(r"\d{4}-\d{2}-\d{2}", r)
        posted = (re.findall(r"\d{4}\.\d{2}\.\d{2}", r) or [""])[0].replace(".", "-") or (ds[0] if ds else "")
        new = seq > since_seq if since_seq else posted >= since_date
        if not new or not title or "마감" in state or any(o["seq"] == seq for o in out):
            continue
        out.append({"seq": seq, "id": f"PTP_{seq}", "num": seq, "title": title,
                    "period": " ~ ".join(ds[:2]), "state": state, "date": posted, "views": "0",
                    "agency": dept, "field": "기타", "url": PTP_VIEW.format(seq=seq)})
    for it in out:
        try:
            L = page_lines(fetch(it["url"]))
            body = _body_after(L, r"^사업명$")
            pairs = extract_pairs(body)
            it.update({"target": pairs["target"], "support": pairs["support"], "intro": ""})
        except Exception:
            it.update({"target": "", "support": "", "intro": ""})
        time.sleep(0.3)
    return out


def drop_tp_duplicates(biz, tp):
    """같은 공고가 기업마당과 테크노파크 양쪽에 있으면 기업마당 쪽을 뺀다 (TP 원문이 더 자세함)."""
    keys = [_norm_title(t["title"]) for t in tp]
    def dup(x):
        nx = _norm_title(x["title"])
        return any(nx == k or (len(k) > 15 and (k in nx or nx in k)) for k in keys)
    return [x for x in biz if not dup(x)]


# 지역 테크노파크 목록 (키, 기관명, 지역, 수집함수) — 새 TP는 여기에 한 줄 추가
TP_SOURCES = [
    ("btp", "부산테크노파크", "부산", btp_collect),
    ("utp", "울산테크노파크", "울산", utp_collect),
    ("gntp", "경남테크노파크", "경남", gntp_collect),
    ("ttp", "대구테크노파크", "대구", ttp_collect),
    ("gbtp", "경북테크노파크", "경북", gbtp_collect),
    ("ptp", "포항테크노파크", "경북", ptp_collect),
]


def collect_technoparks(state, today, days=7):
    """모든 TP에서 새 공고를 모은다. 한 곳이 실패해도 나머지는 계속한다. state는 그 자리에서 갱신된다."""
    since_date = (today - dt.timedelta(days=days)).isoformat()
    allitems, report = [], {}
    for key, org, region, fn in TP_SOURCES:
        try:
            got = fn(state.get(f"{key}_last_seq", 0), since_date)
            got = [x for x in got if "마감" not in x.get("state", "")]
            for it in got:
                if it.get("field") in FIELD_ORDER and it["field"] != "기타":
                    continue
                it["field"] = next((v for k, v in BTP_FIELD.items() if k in it.get("field", "")), None) \
                    or next((v for k, v in BTP_FIELD.items() if k in it["title"]), "기타")
            _with_tp(got, key, org, region)
            if got:
                state[f"{key}_last_seq"] = max(state.get(f"{key}_last_seq", 0), max(x["seq"] for x in got))
            allitems += got
            report[org] = len(got)
        except Exception as e:
            print(f"[warn] {org} 수집 실패: {e}", file=sys.stderr)
            report[org] = "실패"
    return allitems, report


# ---------------- 분류 ----------------
def region_of(item):
    m = re.match(r"\s*\[([^\]]+)\]", item["title"])
    if m:
        tag = m.group(1)
        for r in REGIONS:
            if r in tag:
                return r
    return REGION_ORG.get(item["org"])


def end_date(period):
    m = re.findall(r"(\d{4}-\d{2}-\d{2})", period)
    if len(m) >= 2:
        return dt.date.fromisoformat(m[1])
    return None


def dday(period, today):
    e = end_date(period)
    if not e:
        return ("상시" if period else "-"), 999
    d = (e - today).days
    if d < 0:
        return "마감", d
    return ("D-DAY" if d == 0 else f"D-{d}"), d


# ---------------- PPT ----------------
def tb(slide, x, y, w, h, text, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
    r.font.color.rgb = color
    return box


def header(prs, slide, title, sub=None):
    bar = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(0.95))
    bar.fill.solid(); bar.fill.fore_color.rgb = NAVY; bar.line.fill.background()
    tb(slide, Inches(0.5), Inches(0.18), Inches(9), Inches(0.6), title, 24, True, WHITE, anchor=MSO_ANCHOR.MIDDLE)
    if sub:
        tb(slide, Inches(8.3), Inches(0.18), Inches(4.6), Inches(0.6), sub, 12, False, RGBColor(0xC9, 0xD3, 0xE3),
           PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE)
    acc = slide.shapes.add_shape(1, 0, Inches(0.95), Inches(1.2), Inches(0.06))
    acc.fill.solid(); acc.fill.fore_color.rgb = ORANGE; acc.line.fill.background()


def footer(prs, slide, text):
    tb(slide, Inches(0.5), prs.slide_height - Inches(0.45), Inches(12.3), Inches(0.3), text, 9, False, MUTED)


def set_cell(cell, text, size=11, bold=False, color=INK, fill=None, link=None, align=PP_ALIGN.LEFT):
    cell.text = ""
    tf = cell.text_frame
    tf.word_wrap = True
    cell.margin_left = cell.margin_right = Inches(0.08)
    cell.margin_top = cell.margin_bottom = Inches(0.04)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
    r.font.color.rgb = color
    if link:
        r.hyperlink.address = link
    if fill is not None:
        cell.fill.solid(); cell.fill.fore_color.rgb = fill


def table_slide(prs, title, sub, rows, today, foot):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    header(prs, s, title, sub)
    cols = [("분야", 0.8), ("지원사업명 (누르면 공고로 이동)", 6.4), ("신청기간", 2.2), ("소관 · 수행기관", 2.2), ("마감", 0.75)]
    shape = s.shapes.add_table(len(rows) + 1, len(cols), Inches(0.45), Inches(1.25),
                               Inches(sum(w for _, w in cols)), Inches(0.42 * (len(rows) + 1)))
    t = shape.table
    for j, (name, w) in enumerate(cols):
        t.columns[j].width = Inches(w)
        set_cell(t.cell(0, j), name, 11, True, WHITE, NAVY, align=PP_ALIGN.CENTER if j != 1 else PP_ALIGN.LEFT)
    for i, it in enumerate(rows, start=1):
        fill = ZEBRA if i % 2 == 0 else WHITE
        label, d = dday(it["period"], today)
        urgent = 0 <= d <= 7
        org = it["org"] if it["agency"] in ("", it["org"]) else f'{it["org"]} · {it["agency"]}'
        set_cell(t.cell(i, 0), it["field"], 10, True, ORANGE, fill, align=PP_ALIGN.CENTER)
        set_cell(t.cell(i, 1), it["title"], 11, False, INK, fill, link=link_of(it))
        set_cell(t.cell(i, 2), it["period"], 10, False, MUTED, fill, align=PP_ALIGN.CENTER)
        set_cell(t.cell(i, 3), org, 10, False, MUTED, fill)
        set_cell(t.cell(i, 4), label, 10, urgent, RED if urgent else MUTED, fill, align=PP_ALIGN.CENTER)
    footer(prs, s, foot)


def shorten(text, limit):
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def detail_slides(prs, title, rows, today, foot):
    """공고 2건씩 한 장: 신청요건 · 지원내용 카드"""
    for k in range(0, len(rows), 2):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        header(prs, s, title, f"{k // 2 + 1} / {(len(rows) + 1) // 2}")
        for j, it in enumerate(rows[k:k + 2]):
            y = Inches(1.25 + j * 2.95)
            card = s.shapes.add_shape(1, Inches(0.45), y, Inches(12.43), Inches(2.8))
            card.fill.solid(); card.fill.fore_color.rgb = WHITE; card.line.color.rgb = LINE
            label, d = dday(it["period"], today)
            urgent = 0 <= d <= 7
            org = it["org"] if it["agency"] in ("", it["org"]) else f'{it["org"]} · {it["agency"]}'
            # 제목줄
            t = tb(s, Inches(0.65), y + Inches(0.12), Inches(10.6), Inches(0.45), shorten(it["title"], 56), 15, True, NAVY)
            t.text_frame.paragraphs[0].runs[0].hyperlink.address = link_of(it)
            tb(s, Inches(11.2), y + Inches(0.12), Inches(1.5), Inches(0.45), label, 14, True,
               RED if urgent else ORANGE, PP_ALIGN.RIGHT)
            tb(s, Inches(0.65), y + Inches(0.55), Inches(12), Inches(0.3),
               f'{it["field"]} · {it["period"]} · {org}', 10, False, MUTED)
            # 신청요건 / 지원내용
            target = it.get("target") or "원문 공고에서 확인해 주세요."
            support = it.get("support") or "원문 공고에서 확인해 주세요."
            for c, (head, body) in enumerate([("신청요건", target), ("지원내용", support)]):
                x = Inches(0.65 + c * 6.15)
                tb(s, x, y + Inches(0.95), Inches(5.9), Inches(0.3), head, 11, True, ORANGE)
                tb(s, x, y + Inches(1.25), Inches(5.9), Inches(1.5), shorten(body, 260), 10.5, False, INK)
        footer(prs, s, foot)


def build(items, today, since_label, out_path, btp=None):
    btp = btp or []
    items = drop_tp_duplicates(items, btp)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    by_home = {r: [i for i in items if region_of(i) == r] for r in HOMES}
    home = [i for r in HOMES for i in by_home[r]]
    national = [i for i in items if region_of(i) is None]
    others = [i for i in items if region_of(i) not in [None] + HOMES]
    add_details(home + national)  # 관심 지역·전국 공고만 상세 페이지에서 신청요건·지원내용을 가져온다
    by_region = {}
    for i in others:
        by_region[region_of(i)] = by_region.get(region_of(i), 0) + 1
    def sort_key(i):
        return (dday(i["period"], today)[1] if dday(i["period"], today)[1] >= 0 else 998,)
    urgent = sorted([i for i in home + national + btp if 0 <= dday(i["period"], today)[1] <= 7], key=sort_key)
    stamp = today.strftime("%Y년 %m월 %d일") + " " + "월화수목금토일"[today.weekday()] + "요일"
    foot = f"출처: 기업마당(bizinfo.go.kr)" + (" · 지역 테크노파크" if btp else "") + f" · {since_label} 등록분 · 신청 전 원문 공고를 꼭 확인하세요"

    # 1. 표지
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    tb(s, Inches(0.8), Inches(1.2), Inches(11), Inches(0.5), stamp, 18, False, RGBColor(0xC9, 0xD3, 0xE3))
    tb(s, Inches(0.8), Inches(1.8), Inches(11.5), Inches(1.2), "오늘의 지원사업 공고 브리핑", 44, True, WHITE)
    acc = s.shapes.add_shape(1, Inches(0.8), Inches(3.15), Inches(1.6), Inches(0.08))
    acc.fill.solid(); acc.fill.fore_color.rgb = ORANGE; acc.line.fill.background()
    stats = ([("새 공고", len(items), WHITE)] + [(r, len(by_home[r]), ORANGE) for r in HOMES]
             + [("테크노파크", len(btp), ORANGE), ("전국", len(national), WHITE), ("7일 내 마감", len(urgent), WHITE)])
    step = 11.7 / len(stats)
    for k, (label, n, color) in enumerate(stats):
        x = Inches(0.8 + k * step)
        tb(s, x, Inches(3.8), Inches(step - 0.2), Inches(1.0), str(n), 48, True, color)
        tb(s, x, Inches(4.9), Inches(step - 0.2), Inches(0.4), label, 16, False, RGBColor(0xC9, 0xD3, 0xE3))
    tb(s, Inches(0.8), Inches(6.5), Inches(11.5), Inches(0.4), f"helprnd.com · {since_label} 기업마당·지역 테크노파크에 올라온 공고", 12, False,
       RGBColor(0x9F, 0xAE, 0xC6))

    if not items and not btp:
        s2 = prs.slides.add_slide(prs.slide_layouts[6])
        header(prs, s2, "새로 올라온 공고가 없어요", stamp)
        tb(s2, Inches(0.8), Inches(2.0), Inches(11), Inches(1), "지난 브리핑 이후 기업마당에 새 지원사업 공고가 없습니다.", 20)
        footer(prs, s2, foot)
        prs.save(out_path)
        return {"total": 0}

    # 2. 한눈에 보기: 분야별 차트 + 핵심
    s = prs.slides.add_slide(prs.slide_layouts[6])
    header(prs, s, "한눈에 보기", stamp)
    counts = {f: 0 for f in FIELD_ORDER}
    for i in home + national:
        counts[i["field"] if i["field"] in counts else "기타"] += 1
    cats = [f for f in FIELD_ORDER if counts[f]] or ["없음"]
    cd = CategoryChartData(); cd.categories = cats
    cd.add_series("공고 수", [counts.get(c, 0) for c in cats])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.4), Inches(6.3), Inches(5.3), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = f"{HOME_LABEL} + 전국 공고, 분야별"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.name = FONT
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    plot.data_labels.font.size = Pt(11)
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ser = plot.series[0]
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = NAVY
    ch.category_axis.tick_labels.font.size = Pt(12)
    ch.category_axis.tick_labels.font.name = FONT
    ch.category_axis.reverse_order = True
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False

    x = Inches(7.2)
    tb(s, x, Inches(1.4), Inches(5.7), Inches(0.4), "오늘 먼저 볼 것", 16, True, NAVY)
    lines = []
    for r in HOMES:
        if by_home[r]:
            lines.append(f"• {r} 공고 {len(by_home[r])}건: " + ", ".join(sorted({i['field'] for i in by_home[r]})) + " 분야")
        else:
            lines.append(f"• {r} 공고: 새로 올라온 것 없음")
    if urgent:
        lines.append(f"• 7일 안에 마감되는 공고 {len(urgent)}건 (다음 장)")
    if btp:
        tpc = {}
        for i in btp:
            tpc[i["org"].replace("테크노파크", "")] = tpc.get(i["org"].replace("테크노파크", ""), 0) + 1
        lines.append(f"• 테크노파크 새 공고 {len(btp)}건 (" + " · ".join(f"{k} {v}" for k, v in tpc.items()) + ")")
    by_org = {}
    for i in national:
        by_org[i["org"]] = by_org.get(i["org"], 0) + 1
    if by_org:
        lines.append("• 부처별: " + " · ".join(f"{o} {n}" for o, n in sorted(by_org.items(), key=lambda kv: -kv[1])[:4]))
    top = sorted(national, key=lambda i: -int(re.sub(r'\D', '', i['views']) or 0))[:2]
    for i in top:
        lines.append(f"• 조회 많은 전국 공고: {i['title'][:38]}{'…' if len(i['title']) > 38 else ''}")
    if others:
        lines.append(f"• 다른 지역 공고 {len(others)}건은 '다른 지역' 장에 개수만, 맨 끝 '전국 전체 공고 한눈에'에 목록으로 정리")
    box = s.shapes.add_textbox(x, Inches(1.9), Inches(5.7), Inches(4.8))
    tf = box.text_frame; tf.word_wrap = True
    for k, line in enumerate(lines):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        r = p.add_run(); r.text = line
        r.font.size, r.font.name = Pt(14), FONT
        r.font.color.rgb = INK
    footer(prs, s, foot)

    # 3. 마감 임박
    if urgent:
        for k in range(0, len(urgent), 10):
            part = urgent[k:k + 10]
            table_slide(prs, "7일 안에 마감", f"{len(urgent)}건" + (f" · {k // 10 + 1}쪽" if len(urgent) > 10 else ""),
                        part, today, foot)

    # 4. 관심 지역(부산, 경남 …) — 지역마다 목록 표 + 신청요건·지원내용
    for r in HOMES:
        rows = by_home[r]
        if not rows:
            continue
        rows_sorted = sorted(rows, key=lambda i: (FIELD_ORDER.index(i["field"]) if i["field"] in FIELD_ORDER else 9))
        for k in range(0, len(rows_sorted), 10):
            table_slide(prs, f"{r} 공고", f"{len(rows)}건" + (f" · {k // 10 + 1}쪽" if len(rows) > 10 else ""),
                        rows_sorted[k:k + 10], today, foot)
        detail_slides(prs, f"{r} 공고 · 신청요건과 지원내용", rows_sorted, today, foot)

    # 4-1. 지역 테크노파크 사업공고 (각 TP 사이트에서 직접 수집)
    if btp:
        btp_sorted = sorted(btp, key=sort_key)
        for k in range(0, len(btp_sorted), 10):
            table_slide(prs, "테크노파크 공고", f"{len(btp)}건" + (f" · {k // 10 + 1}쪽" if len(btp) > 10 else ""),
                        btp_sorted[k:k + 10], today, foot)
        detail_slides(prs, "테크노파크 공고 · 신청요건과 지원내용", btp_sorted, today, foot)

    # 5. 전국(중앙부처) — 분야별
    nat_sorted = sorted(national, key=lambda i: (FIELD_ORDER.index(i["field"]) if i["field"] in FIELD_ORDER else 9))
    for k in range(0, len(nat_sorted), 10):
        table_slide(prs, "전국 공고 (중앙부처)", f"{len(national)}건" + (f" · {k // 10 + 1}쪽" if len(national) > 10 else ""),
                    nat_sorted[k:k + 10], today, foot)
    if nat_sorted:
        detail_slides(prs, "전국 공고 · 신청요건과 지원내용", nat_sorted, today, foot)

    # 6. 다른 지역
    if others:
        s = prs.slides.add_slide(prs.slide_layouts[6])
        header(prs, s, "다른 지역 공고", f"{len(others)}건")
        tb(s, Inches(0.6), Inches(1.4), Inches(12), Inches(0.5),
           f"관심 지역({HOME_LABEL})이 아니라 개수만 정리했어요. 필요하면 기업마당에서 지역 필터로 보세요.", 14, False, MUTED)
        items_sorted = sorted(by_region.items(), key=lambda kv: -kv[1])
        for k, (reg, n) in enumerate(items_sorted):
            col, row = k % 6, k // 6
            x, y = Inches(0.6 + col * 2.05), Inches(2.3 + row * 1.5)
            card = s.shapes.add_shape(1, x, y, Inches(1.85), Inches(1.25))
            card.fill.solid(); card.fill.fore_color.rgb = ZEBRA; card.line.color.rgb = LINE
            tb(s, x, y + Inches(0.12), Inches(1.85), Inches(0.6), str(n), 28, True, NAVY, PP_ALIGN.CENTER)
            tb(s, x, y + Inches(0.75), Inches(1.85), Inches(0.4), reg, 13, False, MUTED, PP_ALIGN.CENTER)
        footer(prs, s, foot)

    # 7. 전국 전체 공고 한눈에 (지역 상관없이 모든 새 공고, 마감 빠른 순)
    all_sorted = sorted(items, key=lambda i: (sort_key(i), region_of(i) or ""))
    per = 14
    for k in range(0, len(all_sorted), per):
        part = all_sorted[k:k + per]
        s = prs.slides.add_slide(prs.slide_layouts[6])
        pages = (len(all_sorted) + per - 1) // per
        header(prs, s, "전국 전체 공고 한눈에", f"{len(all_sorted)}건 · 마감 빠른 순" + (f" · {k // per + 1}/{pages}" if pages > 1 else ""))
        cols = [("지역", 0.85), ("분야", 0.75), ("지원사업명 (누르면 공고로 이동)", 7.6), ("소관", 2.2), ("마감", 1.0)]
        shape = s.shapes.add_table(len(part) + 1, len(cols), Inches(0.45), Inches(1.2),
                                   Inches(sum(w for _, w in cols)), Inches(0.37 * (len(part) + 1)))
        t = shape.table
        for j, (name, w) in enumerate(cols):
            t.columns[j].width = Inches(w)
            set_cell(t.cell(0, j), name, 10, True, WHITE, NAVY, align=PP_ALIGN.LEFT if j == 2 else PP_ALIGN.CENTER)
        for i, it in enumerate(part, start=1):
            t.rows[i].height = Inches(0.37)
            fill = ZEBRA if i % 2 == 0 else WHITE
            reg = region_of(it) or "전국"
            mine = reg in HOMES
            label, d = dday(it["period"], today)
            hot = 0 <= d <= 7
            set_cell(t.cell(i, 0), reg, 9.5, mine, ORANGE if mine else INK, fill, align=PP_ALIGN.CENTER)
            set_cell(t.cell(i, 1), it["field"], 9.5, False, MUTED, fill, align=PP_ALIGN.CENTER)
            set_cell(t.cell(i, 2), shorten(it["title"], 62), 9.5, False, INK, fill, link=link_of(it))
            set_cell(t.cell(i, 3), shorten(it["org"], 14), 9.5, False, MUTED, fill)
            set_cell(t.cell(i, 4), label, 9.5, hot, RED if hot else MUTED, fill, align=PP_ALIGN.CENTER)
        footer(prs, s, foot)

    prs.save(out_path)
    summary = {"total": len(items)}
    summary.update({r: len(by_home[r]) for r in HOMES})
    tp_by = {}
    for i in btp:
        tp_by[i["org"]] = tp_by.get(i["org"], 0) + 1
    summary.update({"tp": len(btp), "tp_by_org": tp_by,
                    "tp_titles": [f'[{i["org"].replace("테크노파크", "TP")}] {i["title"]}' for i in sorted(btp, key=sort_key)][:5]})
    summary.update({"national": len(national), "others": len(others), "urgent": len(urgent),
                    "home_titles": {r: [i["title"] for i in by_home[r]][:3] for r in HOMES}})
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "브리핑"))
    ap.add_argument("--days", type=int, default=1, help="처음 실행할 때 며칠 전 등록분부터 모을지")
    ap.add_argument("--full", action="store_true", help="지난 실행 기록을 무시하고 --days 기준으로 모으기")
    args = ap.parse_args()

    today = dt.date.today()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    state = {}
    if STATE.exists() and not args.full:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    since_num = state.get("last_num", 0)
    since_date = (today - dt.timedelta(days=args.days)).isoformat()
    items = collect(since_num, since_date)
    if since_num:
        since_label = f"{state.get('last_run', '지난 브리핑')} 이후"
    else:
        since_label = f"{since_date} 이후"

    # 지역 테크노파크(부산·울산·경남 …): 처음이면 최근 7일, 그다음부터는 지난번 이후 새 글만
    btp, tp_report = collect_technoparks(state, today)

    out_path = out_dir / f"{today.isoformat()}_지원사업공고.pptx"
    summary = build(items, today, since_label, out_path, btp)
    summary["tp_report"] = tp_report
    if items:
        state["last_num"] = max(i["num"] for i in items)
    elif not since_num:
        pass
    state["last_run"] = today.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["file"] = str(out_path)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
