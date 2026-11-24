// @ts-nocheck  (아래 매칭 규칙은 site/match.js 와 같은 JS 코드라 타입 검사를 끔)
// helprnd.com 상담 신청 받기 (Supabase Edge Function: lead)
// 1) 입력 확인 → 2) leads 테이블에 저장 → 3) Resend로 운영자에게 알림 메일 (+ 선택: 신청자 자동 답장)
//
// 필요한 Secrets (Supabase 대시보드 → Edge Functions → Secrets):
//   RESEND_API_KEY   Resend에서 만든 API 키 (re_로 시작)
//   NOTIFY_EMAIL     알림 받을 메일 (예: juddmank@gmail.com)
//   FROM_EMAIL       보내는 사람. 도메인 인증 전: "HelpR&D <onboarding@resend.dev>"
//                    helprnd.com 인증 후: "HelpR&D <noreply@helprnd.com>"
//   AUTOREPLY        "on"이면 신청자에게 접수 확인 메일 발송 (helprnd.com 도메인 인증 후에만 켜기)
// SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 는 Supabase가 자동으로 넣어 줍니다.

const ALLOWED_ORIGINS = ["https://helprnd.com", "https://www.helprnd.com", "http://localhost:8765"];
const REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
  "충북", "충남", "전북", "전남", "경북", "경남", "제주", "해외·기타"];
const PER_IP_PER_HOUR = 5;
const TOTAL_PER_HOUR = 60;

// ===== 매칭 규칙 (site/match.js 복사본 — 고치면 둘 다 고치기) =====
/* helprnd.com 맞춤 지원사업 매칭 (상담 신청 업체 ↔ 공고)
 * 관리자 페이지(admin.html)와 접수 함수(supabase/functions/lead)가 같은 규칙을 씁니다.
 * ※ 규칙을 고치면 supabase/functions/lead/index.ts 안의 같은 부분도 함께 고치세요.
 * 로컬 PPT 도구(지원사업_매칭/make_match.py)와 같은 생각으로 만든 간단판입니다. */
(function (root) {
  const INTERESTS = {
    "수출": [["수출"], ["수출", "해외", "바이어", "무역", "글로벌", "박람회", "전시회"]],
    "R&D": [["기술"], ["R&D", "연구개발", "기술개발", "실증", "시제품", "특허"]],
    "기술": [["기술"], ["기술개발", "연구개발", "특허", "시제품"]],
    "인증": [["기술", "경영"], ["인증", "ISO", "벤처", "이노비즈", "메인비즈", "기업부설연구소"]],
    "채용": [["인력"], ["채용", "고용", "인건비", "일자리"]],
    "인력": [["인력"], ["채용", "고용", "인력", "교육", "훈련"]],
    "자금": [["금융"], ["융자", "보증", "자금", "이차보전", "대출", "투자"]],
    "판로": [["내수"], ["판로", "마케팅", "홍보", "온라인", "입점"]],
    "마케팅": [["내수"], ["마케팅", "홍보", "브랜드", "판로", "디자인"]],
    "창업": [["창업"], ["창업", "스타트업"]],
    "스마트공장": [["기술", "경영"], ["스마트공장", "스마트제조", "자동화", "공정"]],
    "디지털": [["기술", "경영"], ["디지털", "AI", "인공지능", "데이터", "플랫폼"]],
    "ESG": [["경영"], ["ESG", "탄소", "에너지", "친환경"]],
    "에너지": [["경영", "기술"], ["에너지", "탄소", "효율", "절감"]],
  };
  const SECTORS = ["음식점", "외식", "레스토랑", "식품", "푸드", "농업", "농산", "축산", "수산", "어업", "임업", "바이오", "의료기기",
    "의료", "제약", "헬스케어", "화장품", "뷰티", "패션", "섬유", "관광", "숙박", "게임", "콘텐츠", "웹툰", "영화", "방산", "방위",
    "조선", "해양", "항공", "우주", "반도체", "이차전지", "배터리", "수소", "자동차", "모빌리티", "물류", "건설", "건축", "공예",
    "출판", "어린이집", "전통시장", "상점가", "소상공인", "사회적경제", "비타", "펫", "반려", "수처리", "폐기물", "소각", "정보보호",
    "보안", "의류", "맛집", "서점", "선박", "GPU", "도서", "미용", "카페", "한복", "전통주", "원예", "포상", "유공자", "카드수수료", "동백전"];
  const AGENCY_CALL = ["운영기관", "수행기관", "전문기관", "주관기관", "위탁기관", "협력기관", "연구개발기관", "평가위원", "심사위원", "강사"];
  const TYPE_ONLY = ["장애인기업", "여성기업", "사회적기업", "마을기업", "협동조합", "자활기업", "청년기업"];
  const PEOPLE_ONLY = ["농업인", "농업경영체", "농업법인", "농가", "어업인", "어가", "예비창업자", "주민", "가구", "학생", "구직자"];

  const words = t => String(t || "").replace(/업(?=\s|,|$)/g, " ").split(/[\s,/·()\[\]]+/).filter(w => w.length >= 2);

  // lead: {region, industry, message}  items: announcements.json 의 items  today: "YYYY-MM-DD"
  function matchLead(lead, items, today, top) {
    const region = String(lead.region || "").trim();
    const industry = String(lead.industry || "");
    const msg = String(lead.message || "");
    const mine = (industry + " " + msg);
    const own = [...new Set(words(industry))];
    const fields = new Set(), keys = [];
    for (const [name, [fs, ks]] of Object.entries(INTERESTS)) {
      if (mine.includes(name) || ks.some(k => msg.includes(k))) { fs.forEach(f => fields.add(f)); keys.push(...ks); }
    }
    const out = [];
    for (const it of items) {
      const title = it.title || "", tgt = (it.target || "") + " " + title;
      const body = [title, it.target, it.support, it.intro].join(" ").toLowerCase();
      if (it.end && it.end <= today) continue;                         // 오늘 마감·지난 공고
      const ir = it.region || "전국";
      if (region && region !== "해외·기타" && ir !== "전국" && ir !== region) continue;
      if (SECTORS.some(w => title.includes(w) && !mine.includes(w))) continue;
      if (AGENCY_CALL.some(w => title.includes(w))) continue;
      if (TYPE_ONLY.some(w => title.includes(w) && !mine.includes(w))) continue;
      if (PEOPLE_ONLY.some(w => tgt.includes(w)) && !/기업|사업자/.test(tgt)) continue;
      let s = ir === region ? 30 : 12;
      const why = ir === region ? [region + " 기업 대상"] : [];
      if (fields.has(it.field)) { s += 25; why.push("관심 분야(" + it.field + ")"); }
      const hit = []; let ownHit = 0;
      for (const k of [...new Set([...own, ...keys])]) {
        const kl = k.toLowerCase();
        if (!body.includes(kl)) continue;
        hit.push(k);
        const isOwn = own.includes(k);
        s += (isOwn ? 10 : 5) * (title.toLowerCase().includes(kl) ? 2 : 1);
        if (isOwn) ownHit++;
      }
      if (hit.length) why.push("'" + hit.slice(0, 3).join("', '") + "' 포함");
      if (!ownHit) s -= 15;
      if (it.end) {
        const left = Math.round((Date.parse(it.end) - Date.parse(today)) / 864e5);
        if (left <= 2) { s -= 10; why.push("마감 임박"); } else if (left <= 14) s += 3;
      }
      if (s >= 30 && why.length) out.push({ title, url: it.url, field: it.field, region: ir, end: it.end || null, org: it.org, agency: it.agency,
        period: it.period, target: it.target, support: it.support, score: s, why });
    }
    out.sort((a, b) => b.score - a.score || String(a.end || "9999").localeCompare(String(b.end || "9999")));
    return out.slice(0, top || 10);
  }

  root.HelpMatch = { matchLead };
})(globalThis);
// ===== 매칭 규칙 끝 =====

const env = (k: string) => Deno.env.get(k) ?? "";

function cors(origin: string | null) {
  const allow = origin && ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type, authorization, apikey, x-client-info",
    "Vary": "Origin",
  };
}

function reply(origin: string | null, ok: boolean, message: string, status = 200) {
  return new Response(JSON.stringify({ ok, message }), {
    status,
    headers: { ...cors(origin), "Content-Type": "application/json; charset=utf-8" },
  });
}

const clip = (v: unknown, n: number) => String(v ?? "").trim().slice(0, n);
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));

async function sha256(text: string) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

async function db(path: string, init: RequestInit = {}) {
  const key = env("SUPABASE_SERVICE_ROLE_KEY");
  return fetch(`${env("SUPABASE_URL")}/rest/v1/${path}`, {
    ...init,
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", ...(init.headers || {}) },
  });
}

async function countSince(filter: string) {
  const since = new Date(Date.now() - 3600_000).toISOString();
  const r = await db(`leads?select=id&created_at=gte.${encodeURIComponent(since)}${filter}`, {
    method: "HEAD",
    headers: { Prefer: "count=exact" },
  });
  const range = r.headers.get("content-range") || "*/0";
  return Number(range.split("/")[1] || 0);
}

async function sendMail(to: string, subject: string, html: string, replyTo?: string) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env("FROM_EMAIL") || "HelpR&D <onboarding@resend.dev>", to: [to], subject, html, ...(replyTo ? { reply_to: replyTo } : {}) }),
  });
  if (!r.ok) console.error("resend error", r.status, await r.text());
  return r.ok;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return reply(origin, false, "허용되지 않은 요청입니다.", 405);
  if (origin && !ALLOWED_ORIGINS.includes(origin)) return reply(origin, false, "허용되지 않은 주소입니다.", 403);

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(await req.text());
  } catch {
    return reply(origin, false, "잘못된 요청입니다.", 400);
  }

  // 로봇 걸러내기: 사람에게 안 보이는 칸이 채워져 있으면 성공처럼 답하고 저장하지 않음
  if (body.website) return reply(origin, true, "신청이 접수되었습니다.");

  const company = clip(body.company, 60);
  const name = clip(body.name, 30);
  const phone = clip(body.phone, 20).replace(/[^0-9\-+ ]/g, "");
  const email = clip(body.email, 80);
  const message = clip(body.message, 1000);
  const page = clip(body.page, 200);
  const region = REGIONS.includes(clip(body.region, 10)) ? clip(body.region, 10) : "";
  const industry = clip(body.industry, 40);
  if (!company || !name || !phone || !email || !region || !industry) return reply(origin, false, "필수 항목을 모두 입력해 주세요.", 400);
  if (phone.replace(/\D/g, "").length < 8) return reply(origin, false, "전화번호를 확인해 주세요.", 400);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return reply(origin, false, "이메일 형식을 확인해 주세요.", 400);
  if (body.consent !== true) return reply(origin, false, "개인정보 수집·이용에 동의해 주세요.", 400);

  try {
    const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim();
    const ipHash = ip ? await sha256(ip + "|helprnd") : null;
    if (ipHash && (await countSince(`&ip_hash=eq.${ipHash}`)) >= PER_IP_PER_HOUR) {
      return reply(origin, false, "잠시 후 다시 시도해 주세요.", 429);
    }
    if ((await countSince("")) >= TOTAL_PER_HOUR) return reply(origin, false, "잠시 후 다시 시도해 주세요.", 429);

    // 맞춤 지원사업 매칭 (실패해도 신청 접수는 계속)
    let matches = null;
    try {
      const ctl = AbortSignal.timeout(6000);
      const data = await (await fetch("https://helprnd.com/data/announcements.json", { signal: ctl })).json();
      const today = new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);
      matches = globalThis.HelpMatch.matchLead({ region, industry, message }, data.items || [], today, 10)
        .map((m) => ({ title: m.title, url: m.url, field: m.field, end: m.end, score: m.score, why: m.why }));
    } catch (e) {
      console.error("match error", e);
    }

    const ins = await db("leads", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ company, name, phone, email, region, industry, message: message || null, consent: true, page, ip_hash: ipHash, matches }),
    });
    if (!ins.ok) {
      console.error("insert error", ins.status, await ins.text());
      return reply(origin, false, "저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", 500);
    }

    const when = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
    const rows = [["회사명", company], ["지역", region], ["업종", industry], ["담당자", name], ["전화번호", phone], ["이메일", email], ["문의내용", message || "(없음)"], ["접수시각", when]]
      .map(([k, v]) => `<tr><th align="left" style="padding:4px 12px 4px 0;color:#667085">${k}</th><td style="padding:4px 0">${esc(v).replace(/\n/g, "<br>")}</td></tr>`)
      .join("");
    const matchHtml = matches && matches.length
      ? `<h3 style="margin:18px 0 6px">추천 지원사업 ${matches.length}건 (자동 매칭)</h3><ol style="padding-left:18px;margin:0">` +
        matches.slice(0, 5).map((m) => `<li style="margin:4px 0"><a href="${esc(m.url || "")}">${esc(m.title)}</a><br><span style="color:#667085;font-size:13px">${esc(m.field || "")} · 마감 ${esc(m.end || "상시")} · ${esc(m.why.join(" · "))}</span></li>`).join("") +
        `</ol>`
      : `<p style="color:#667085;font-size:13px">자동 매칭된 공고가 없습니다. 통화로 관심 분야를 확인해 보세요.</p>`;
    const notify = env("NOTIFY_EMAIL");
    if (notify) {
      await sendMail(notify, `[helprnd.com] 새 상담 신청 - ${company} ${name}`,
        `<div style="font-family:sans-serif;font-size:15px"><h2 style="margin:0 0 10px">새 상담 신청</h2><table>${rows}</table>${matchHtml}
         <p style="color:#667085;font-size:13px"><a href="https://helprnd.com/admin.html">관리자 페이지</a>에서 전체 목록과 매칭 PPT를 받을 수 있습니다.</p></div>`, email);
    }
    if (env("AUTOREPLY") === "on") {
      await sendMail(email, "[HelpR&D] 상담 신청이 접수되었습니다",
        `<div style="font-family:sans-serif;font-size:15px;line-height:1.7"><p>${esc(name)}님, 안녕하세요.</p>
         <p><b>${esc(company)}</b>의 지원사업 상담 신청이 접수되었습니다.<br>확인 후 남겨 주신 연락처로 연락드리겠습니다.</p>
         <p style="color:#667085;font-size:13px">매일 새 지원사업 공고는 <a href="https://helprnd.com">helprnd.com</a>에서 확인하실 수 있습니다.<br>
         본 메일은 발신 전용입니다.</p></div>`);
    }
    return reply(origin, true, "신청이 접수되었습니다.");
  } catch (e) {
    console.error(e);
    return reply(origin, false, "오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", 500);
  }
});
