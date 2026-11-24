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
})(typeof window !== "undefined" ? window : globalThis);
