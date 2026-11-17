/* helprnd.com 상담 신청 팝업 (공용): <link rel=stylesheet href=consult.css> + <script src=consult.js data-auto-open="초"></script> */
(function(){
  if(!document.getElementById('consult')){
    document.body.insertAdjacentHTML('beforeend', '<div class="modal" id="consult" role="dialog" aria-modal="true" aria-labelledby="consult-title">\n  <div class="dialog">\n    <button class="x" type="button" data-close aria-label="닫기">×</button>\n    <form id="consult-form" novalidate>\n      <h3 id="consult-title">지원사업 무료 상담 신청</h3>\n      <p class="lead">우리 회사에 맞는 지원사업을 골라 연락드립니다.</p>\n      <label class="f"><span>회사명 <i>*</i></span><input name="company" maxlength="60" autocomplete="organization" required></label>\n      <label class="f"><span>담당자 이름 <i>*</i></span><input name="name" maxlength="30" autocomplete="name" required></label>\n      <label class="f"><span>전화번호 <i>*</i></span><input name="phone" maxlength="20" inputmode="tel" autocomplete="tel" placeholder="010-0000-0000" required></label>\n      <label class="f"><span>이메일 <i>*</i></span><input name="email" type="email" maxlength="80" autocomplete="email" placeholder="name@company.com" required></label>\n      <label class="f"><span>궁금한 점 (선택)</span><textarea name="message" maxlength="1000" placeholder="예: 업종, 지역, 관심 분야(수출·R&D·채용 등)"></textarea></label>\n      <label class="hp" aria-hidden="true">웹사이트<input name="website" tabindex="-1" autocomplete="off"></label>\n      <div class="consent">\n        <b style="color:var(--ink)">개인정보 수집·이용 안내</b>\n        <table>\n          <tr><th>목적</th><td>지원사업 상담 및 맞춤 공고 안내 연락</td></tr>\n          <tr><th>항목</th><td>회사명, 담당자 이름, 전화번호, 이메일, 문의내용(선택)</td></tr>\n          <tr><th>보유기간</th><td>상담 종료 후 1년 (삭제 요청 시 즉시 파기)</td></tr>\n        </table>\n        동의를 거부할 수 있으며, 거부하시면 상담 신청이 어렵습니다. 자세한 내용은 <a href="privacy.html" target="_blank">개인정보처리방침</a>을 확인하세요.\n      </div>\n      <label class="agree"><input type="checkbox" name="consent"> 개인정보 수집·이용에 동의합니다. (필수)</label>\n      <button class="cta" type="submit">상담 신청하기</button>\n      <p class="msg" id="consult-msg" role="status"></p>\n    </form>\n    <div class="done" id="consult-done" hidden>\n      <div class="big">✅</div>\n      <h3>신청이 접수되었습니다</h3>\n      <p class="lead">확인 후 남겨 주신 연락처로 연락드리겠습니다.</p>\n      <button class="cta" type="button" data-close>닫기</button>\n    </div>\n  </div>\n</div>');
  }
})();
/* 상담 신청 팝업: 입력 내용은 Supabase 함수(lead)를 거쳐 DB에 저장되고 Resend로 알림 메일이 간다 */
(function(){
  const LEAD_ENDPOINT = "https://lqcdnzrsviivkajntmqs.supabase.co/functions/v1/lead";  // 비우면 상담 버튼·팝업을 숨김
  const AUTO_OPEN_SEC = Number((document.currentScript && document.currentScript.dataset.autoOpen) || 0);            // 첫 방문 후 자동으로 띄우기까지 초
  const SNOOZE_DAYS = 7;               // 닫으면 며칠 동안 자동으로 다시 안 띄움
  if(!LEAD_ENDPOINT) return;

  const modal = document.getElementById("consult");
  const form = document.getElementById("consult-form");
  const msg = document.getElementById("consult-msg");
  const KEY = "helprnd_consult";
  const get = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e){ return {}; } };
  const set = v => { try { localStorage.setItem(KEY, JSON.stringify(Object.assign(get(), v))); } catch(e){} };
  let lastFocus = null;

  document.querySelectorAll("[data-consult],[data-consult-band]").forEach(el => el.hidden = false);
  document.querySelectorAll("[data-consult]").forEach(b => b.addEventListener("click", () => open("button")));
  modal.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", close));
  modal.addEventListener("click", e => { if(e.target === modal) close(); });
  document.addEventListener("keydown", e => { if(e.key === "Escape" && modal.classList.contains("open")) close(); });

  function open(){
    lastFocus = document.activeElement;
    modal.classList.add("open");
    document.body.style.overflow = "hidden";
    setTimeout(() => (form.hidden ? modal.querySelector(".done .cta") : form.company).focus(), 30);
  }
  function close(){
    modal.classList.remove("open");
    document.body.style.overflow = "";
    set({ snoozeUntil: Date.now() + SNOOZE_DAYS * 864e5 });
    if(lastFocus) lastFocus.focus();
  }

  // 자동으로 한 번 띄우기 (신청했거나 최근에 닫았으면 안 띄움)
  const st = get();
  if(AUTO_OPEN_SEC > 0 && !st.done && !(st.snoozeUntil > Date.now())){
    setTimeout(() => { if(!modal.classList.contains("open")) open("auto"); }, AUTO_OPEN_SEC * 1000);
  }

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form).entries());
    d.consent = form.consent.checked;
    d.page = location.href;
    const need = [["company","회사명을"],["name","담당자 이름을"],["phone","전화번호를"],["email","이메일을"]];
    const miss = need.find(([k]) => !String(d[k] || "").trim());
    if(miss){ return fail(miss[1] + " 입력해 주세요.", form[miss[0]]); }
    if(!/^[0-9\-+ ]{8,20}$/.test(d.phone.trim())) return fail("전화번호를 확인해 주세요.", form.phone);
    if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email.trim())) return fail("이메일 형식을 확인해 주세요.", form.email);
    if(!d.consent) return fail("개인정보 수집·이용에 동의해 주세요.", form.consent);

    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true; btn.textContent = "보내는 중…"; msg.textContent = ""; msg.className = "msg";
    try{
      const res = await fetch(LEAD_ENDPOINT, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(d) });
      const r = await res.json();
      if(!r.ok) throw new Error(r.message || "전송 실패");
      form.hidden = true; document.getElementById("consult-done").hidden = false;
      set({ done: true });
      modal.querySelector(".done .cta").focus();
    }catch(err){
      fail((err && err.message && !/fetch|network/i.test(err.message)) ? err.message : "전송하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }finally{
      btn.disabled = false; btn.textContent = "상담 신청하기";
    }
  });
  function fail(t, el){ msg.textContent = t; msg.className = "msg err"; if(el) el.focus(); }
})();
