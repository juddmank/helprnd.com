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

    const ins = await db("leads", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ company, name, phone, email, region, industry, message: message || null, consent: true, page, ip_hash: ipHash }),
    });
    if (!ins.ok) {
      console.error("insert error", ins.status, await ins.text());
      return reply(origin, false, "저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", 500);
    }

    const when = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
    const rows = [["회사명", company], ["지역", region], ["업종", industry], ["담당자", name], ["전화번호", phone], ["이메일", email], ["문의내용", message || "(없음)"], ["접수시각", when]]
      .map(([k, v]) => `<tr><th align="left" style="padding:4px 12px 4px 0;color:#667085">${k}</th><td style="padding:4px 0">${esc(v).replace(/\n/g, "<br>")}</td></tr>`)
      .join("");
    const notify = env("NOTIFY_EMAIL");
    if (notify) {
      await sendMail(notify, `[helprnd.com] 새 상담 신청 - ${company} ${name}`,
        `<div style="font-family:sans-serif;font-size:15px"><h2 style="margin:0 0 10px">새 상담 신청</h2><table>${rows}</table>
         <p style="color:#667085;font-size:13px">Supabase → Table Editor → leads 에서 전체 목록을 볼 수 있습니다.</p></div>`, email);
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
