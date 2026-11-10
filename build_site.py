# -*- coding: utf-8 -*-
"""
helprnd.com 데이터 만들기: 기업마당 새 지원사업 공고를 모아 site/data/announcements.json 을 갱신하고
그날 브리핑 PPT를 site/briefings/ 에 저장한다.

사용법:  python build_site.py [--days 7] [--today 2026-11-10]
- data/state.json 에 마지막으로 가져온 공고 번호를 기록해 다음 실행 때 새 공고만 모은다.
- 처음 실행이면 최근 --days 일 등록분을 모은다.
- 사이트에는 아직 마감되지 않았거나 최근 KEEP_DAYS 일 안에 올라온 공고만 남긴다.
"""
import argparse, datetime as dt, json, sys
from pathlib import Path

import bizinfo_briefing as b

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
DATA = SITE / "data"
BRIEF = SITE / "briefings"
STATE = ROOT / "data" / "state.json"
KEEP_DAYS = 30


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def to_record(it, added):
    end = b.end_date(it["period"])
    return {
        "id": it["id"], "num": it["num"], "title": it["title"], "field": it["field"],
        "region": b.region_of(it) or "전국", "period": it["period"], "end": end.isoformat() if end else None,
        "org": it["org"], "agency": it["agency"], "date": it["date"], "added": added,
        "intro": it.get("intro", ""), "target": it.get("target", ""), "support": it.get("support", ""),
        "url": b.DETAIL.format(id=it["id"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--today", help="YYYY-MM-DD (시험용)")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    for d in (DATA, BRIEF, STATE.parent):
        d.mkdir(parents=True, exist_ok=True)
    state = load(STATE, {})
    since_num = state.get("last_num", 0)
    since_date = (today - dt.timedelta(days=args.days)).isoformat()
    items = b.collect(since_num, since_date, max_pages=60)
    since_label = f"{state.get('last_run', '지난 브리핑')} 이후" if since_num else f"{since_date} 이후"
    print(f"새 공고 {len(items)}건", flush=True)

    # 모든 새 공고의 신청요건·지원내용을 가져온다 (사이트 방문자는 전국 사람들이라 지역 구분 없이)
    b.add_details(items)

    # 그날 브리핑 PPT (Kay님용 구성 그대로; build 안에서 관심 지역 상세는 이미 채워져 있으면 다시 받지 않음)
    ppt_name = f"{today.isoformat()}_지원사업공고.pptx"
    summary = b.build(items, today, since_label, BRIEF / ppt_name)

    # 공고 목록 갱신
    db = load(DATA / "announcements.json", {"items": []})
    known = {r["id"]: r for r in db["items"]}
    for it in items:
        known[it["id"]] = to_record(it, today.isoformat())
    cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    keep = [r for r in known.values()
            if (r["end"] is None and r["added"] >= cutoff) or (r["end"] and r["end"] >= today.isoformat())
            or r["added"] >= cutoff]
    keep.sort(key=lambda r: -r["num"])

    briefings = load(DATA / "briefings.json", [])
    briefings = [x for x in briefings if x["date"] != today.isoformat()]
    briefings.insert(0, {"date": today.isoformat(), "count": len(items), "since": since_label,
                         "ppt": f"briefings/{ppt_name}",
                         "regions": {r: summary.get(r, 0) for r in b.HOMES}, "national": summary.get("national", 0)})

    (DATA / "announcements.json").write_text(
        json.dumps({"updated": dt.datetime.now().isoformat(timespec="minutes"), "today": today.isoformat(),
                    "items": keep}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "briefings.json").write_text(json.dumps(briefings[:120], ensure_ascii=False, indent=1), encoding="utf-8")

    if items:
        state["last_num"] = max(i["num"] for i in items)
    state["last_run"] = today.isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"new": len(items), "kept": len(keep), "ppt": ppt_name}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
