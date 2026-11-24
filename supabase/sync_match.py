# -*- coding: utf-8 -*-
"""site/match.js 의 매칭 규칙을 supabase/functions/lead/index.ts 안 복사본에 그대로 덮어쓴다.
match.js 를 고친 뒤 실행:  python supabase/sync_match.py
그다음 lead 함수를 Supabase에 다시 배포해야 메일·저장되는 추천에도 반영된다."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site" / "match.js"
DST = ROOT / "supabase" / "functions" / "lead" / "index.ts"
START = "// ===== 매칭 규칙 (site/match.js 복사본 — 고치면 둘 다 고치기) =====\n"
END = "// ===== 매칭 규칙 끝 =====\n"

block = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
block = block.replace('})(typeof window !== "undefined" ? window : globalThis);', "})(globalThis);")
s = DST.read_text(encoding="utf-8").replace("\r\n", "\n")
assert START in s and END in s, "index.ts 에 매칭 규칙 표시가 없습니다"
s = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: START + block + END, s, flags=re.S)
DST.write_text(s, encoding="utf-8", newline="\n")
print("동기화 완료:", len(s), "글자")
