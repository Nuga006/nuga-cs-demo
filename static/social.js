// Nuga CS Demo — профиль, подписки, лента, уведомления и «Наш Телеграм».
// Подключается перед основным скриптом страницы и пользуется его функциями (esc, showView, openClip, USER, MATCH_LIST…)
// только в момент вызова, когда они уже существуют.
const Social = (() => {
  const el = (id) => document.getElementById(id);

  async function api(url, method = "GET", body) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Ошибка сервера (${res.status})`);
    return data;
  }

  let ready = false;          // уже знаем, вошёл человек или нет
  let wantOwn = false;        // открыт «мой профиль», но вход ещё проверяется
  let P = null;               // открытый профиль
  let tab = "public";         // вкладка своего профиля: public / private
  let feedScope = "all";
  let hideTimer = null;

  // ---------- Мелочи ----------
  function note(html, isError = false) {
    let t = el("sToast");
    if (!t) { t = document.createElement("div"); t.id = "sToast"; document.body.appendChild(t); }
    t.className = "toast" + (isError ? " err" : "");
    t.innerHTML = html;
    t.style.display = "flex";
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => (t.style.display = "none"), 5000);
    t.querySelector("[data-go-profile]")?.addEventListener("click", (e) => { e.preventDefault(); t.style.display = "none"; showView("profile"); });
  }

  function modal(title, body, wide = false) {
    let m = el("sModal");
    if (!m) {
      m = document.createElement("div");
      m.id = "sModal";
      m.className = "modal smodal";
      document.body.appendChild(m);
      m.addEventListener("click", (e) => { if (e.target === m) closeModal(); });
    }
    m.innerHTML = `<div class="mbox${wide ? " wide" : ""}"><h3><span>${title}</span><button id="sModalClose" title="Закрыть">×</button></h3>` +
      `<div id="sModalBody">${body}</div></div>`;
    m.classList.add("on");
    el("sModalClose").addEventListener("click", closeModal);
    return el("sModalBody");
  }
  function closeModal() {
    const m = el("sModal");
    if (!m) return;
    m.classList.remove("on");
    m.innerHTML = "";                               // заодно останавливает видео
    if (m.onclose) { const f = m.onclose; m.onclose = null; f(); }
  }

  const avatar = (src, cls = "") => (src ? `<img class="${cls}" src="${esc(src)}" alt="">` : `<span class="noav ${cls}"></span>`);
  const badge = (t) => (t === "ACE" ? "ace" : t === "4K" ? "k4" : t === "3K" ? "k3" : "cl");
  const day = (ts) => new Date(ts * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  const sameClip = (c, m, h) => c.match_id === m.id && c.round === h.r && c.tick === h.k && c.type === h.t;

  function ago(ts) {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 90) return "только что";
    if (s < 3600) return `${Math.round(s / 60)} мин назад`;
    if (s < 86400) return `${Math.round(s / 3600)} ч назад`;
    if (s < 86400 * 7) return `${Math.round(s / 86400)} дн назад`;
    return day(ts);
  }

  // Карточка клипа — такая же, как в разделе «Клипы»
  function card(c, i, extra = "") {
    const map = encodeURIComponent(c.map);
    const sub = [mapTitle(c.map), c.round >= 0 ? `раунд ${c.round + 1}` : "", day(c.published || c.created)].filter(Boolean).join(" · ");
    const author = c.author !== undefined
      ? `<span class="auth" data-u="${esc(c.steam_id)}">${avatar(c.author_avatar)}${esc(c.author || "Игрок")}</span>` : "";
    return `<div class="pclip"><button class="clipc" data-i="${i}" style="--mc:${mapColor(c.map)}">` +
      `<div class="thumb"><span class="rad" style="background-image:url('/static/maps/${map}.png')"></span>` +
      `<img class="lg" src="/static/maps/icons/${map}.png" alt="" loading="lazy" onerror="this.remove()">` +
      `<span class="bd ${badge(c.type)}">${esc(c.type)}</span>${c.video && c.type !== "3D" ? `<span class="vid">3D</span>` : ""}<span class="play">▶</span></div>` +
      `<div class="info"><div class="who">${esc(c.title || c.player || (c.type === "3D" ? "3D-клип" : "Клип"))}</div>` +
      `<div class="det">${esc(sub)}</div>${author}</div></button>${extra}</div>`;
  }

  // Открыть клип: есть видео — показываем его, иначе запускаем 2D-реплей момента в матче
  function play(c) {
    const moment = { m: { id: c.match_id }, h: { r: c.round, k: c.tick, t: c.type } };
    if (!c.video) return openClip(moment);
    const body = modal(esc(c.title || [c.type === "3D" ? "3D-клип" : c.type, c.player].filter(Boolean).join(" · ")),
      `<video class="svideo" src="${esc(c.video)}" controls autoplay playsinline></video>` +
      `<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">` +
      (c.round >= 0 ? `<button class="pbtn small" id="svMatch">Открыть момент в матче</button>` : `<button class="pbtn small" id="svMatch">Открыть матч</button>`) +
      `<a class="pbtn small" href="${esc(c.video)}" download>⬇ Скачать видео</a></div>`, true);
    body.querySelector("#svMatch").addEventListener("click", () => { closeModal(); c.round >= 0 ? openClip(moment) : openMatch(c.match_id, true); });
  }

  // ---------- Сохранить момент в профиль ----------
  async function saveClip(payload, publish = false) {
    if (!USER) { note("Войдите через Steam, чтобы сохранять клипы в профиль", true); return null; }
    try {
      let clip = await api("/api/clips", "POST", payload);
      if (publish && !clip.public) clip = await api(`/api/clips/${clip.id}/publish`, "POST", { public: true });
      note((publish ? "✅ Клип опубликован в профиле." : "✅ Клип сохранён в «Личные».") +
        ` <a href="/app/profile" data-go-profile>Открыть профиль</a>`);
      return clip;
    } catch (e) {
      note(esc(e.message), true);
      return null;
    }
  }

  // ---------- Профиль ----------
  async function renderProfile(id) {
    const box = el("profileBox");
    wantOwn = false;
    if (!id) {
      if (!ready) { wantOwn = true; box.innerHTML = `<div class="note">Загружаем...</div>`; return; }
      if (!USER) {
        box.innerHTML = `<div class="phead"><div><h1>Профиль</h1></div></div><div class="gate"><p>Войдите через Steam — у вас появится профиль с клипами, подписчиками и подписками.</p>` +
          `<a class="steambtn" href="/auth/steam">Войти через Steam</a></div>`;
        return;
      }
      id = USER.steam_id;
    }
    if (!P || P.steam_id !== id) box.innerHTML = `<div class="note">Загружаем...</div>`;
    try {
      P = await api(`/api/profile/${id}`);
    } catch (e) {
      P = null;
      box.innerHTML = `<div class="pfempty">${esc(e.message)}</div>`;
      return;
    }
    if (!P.is_me) tab = "public";
    drawProfile();
    // Ссылка вида /u/<id>?clip=12 — сразу открываем этот клип
    const want = Number(new URLSearchParams(location.search).get("clip"));
    if (want) {
      history.replaceState({}, "", location.pathname);
      const c = [...P.clips, ...(P.private || [])].find((x) => x.id === want);
      if (c) play(c);
    }
  }

  function drawProfile() {
    const p = P, box = el("profileBox");
    document.title = `${p.name} — Nuga CS Demo`;
    const share = `<button class="pbtn small" id="pfShare">↗ Поделиться профилем</button>`;
    const buttons = p.is_me
      ? `<button class="pbtn small primary" id="pfAdd">＋ Опубликовать клип</button>${share}`
      : `<button class="pbtn small${p.is_following ? "" : " primary"}" id="pfFollow">${p.is_following ? "✓ Вы подписаны" : "Подписаться"}</button>${share}`;
    let tg = "";
    if (p.is_me && p.telegram?.available) {
      tg = p.telegram.linked
        ? `<div class="pftg"><span>✅ Уведомления приходят в Telegram</span><button class="pbtn" id="pfTgOff">Отключить</button></div>`
        : `<div class="pftg"><button class="pbtn" id="pfTg">✈ Уведомления в Telegram</button><span>новые подписчики и клипы — сообщением от бота</span></div>`;
    }
    const list = tab === "private" ? p.private || [] : p.clips;
    const acts = (c) => !p.is_me ? "" : c.public
      ? `<div class="pacts"><button data-act="hide" data-id="${c.id}">В личные</button>` +
        `<button class="ic" data-act="title" data-id="${c.id}" title="Изменить подпись">✎</button>` +
        `<button class="ic del" data-act="del" data-id="${c.id}" title="Удалить клип">🗑</button></div>`
      : `<div class="pacts"><button class="go" data-act="publish" data-id="${c.id}">Опубликовать</button>` +
        `<button class="ic del" data-act="del" data-id="${c.id}" title="Удалить клип">🗑</button></div>`;
    const empty = p.is_me
      ? (tab === "private"
          ? `<div class="pfempty">Здесь лежат клипы, которые видите только вы.<br>Сохраняйте моменты кнопкой ＋ в «Клипах» и на вкладке «Хайлайты» матча.</div>`
          : `<div class="pfempty">Вы ещё ничего не опубликовали.<br><button class="pbtn primary" id="pfAdd2">＋ Опубликовать клип</button></div>`)
      : `<div class="pfempty">Игрок пока не опубликовал клипы.</div>`;

    box.innerHTML =
      `<div class="pfhead">${avatar(p.avatar, "pfav")}<div class="pfmain">` +
      `<div class="pftop"><span class="pfname">${esc(p.name)}</span>${buttons}</div>` +
      `<div class="pfsub">${p.faceit ? `FACEIT: ${esc(p.faceit)}` : ""}</div>` +
      `<div class="pfstats"><button class="pfst" disabled><b>${p.posts}</b><span>публикации</span></button>` +
      `<button class="pfst" data-list="followers"><b>${p.followers}</b><span>подписчики</span></button>` +
      `<button class="pfst" data-list="following"><b>${p.following}</b><span>подписки</span></button></div>${tg}</div></div>` +
      (p.is_me
        ? `<div class="segtabs" id="pfTabs"><button data-t="public" class="${tab === "public" ? "on" : ""}">Опубликованные <span class="cnt">${p.clips.length}</span></button>` +
          `<button data-t="private" class="${tab === "private" ? "on" : ""}">Личные <span class="cnt">${(p.private || []).length}</span></button></div>`
        : `<h2 class="first">Клипы</h2>`) +
      (list.length ? `<div class="cgal">${list.map((c, i) => card(c, i, acts(c))).join("")}</div>` : empty);

    box.querySelectorAll(".clipc").forEach((b) => b.addEventListener("click", () => play(list[+b.dataset.i])));
    box.querySelectorAll("#pfTabs button").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.t; drawProfile(); }));
    box.querySelectorAll(".pfst[data-list]").forEach((b) => b.addEventListener("click", () => showPeople(b.dataset.list)));
    box.querySelectorAll(".pacts button").forEach((b) => b.addEventListener("click", () => clipAction(b.dataset.act, +b.dataset.id)));
    el("pfShare").addEventListener("click", shareProfile);
    el("pfAdd")?.addEventListener("click", pickClips);
    el("pfAdd2")?.addEventListener("click", pickClips);
    el("pfFollow")?.addEventListener("click", toggleFollow);
    el("pfTg")?.addEventListener("click", linkTelegram);
    el("pfTgOff")?.addEventListener("click", async () => { await api("/api/telegram/link", "DELETE").catch(() => {}); renderProfile(P.steam_id); });
  }

  async function shareProfile() {
    const url = `${location.origin}/u/${P.steam_id}`;
    try {
      if (navigator.share && matchMedia("(max-width: 760px)").matches) await navigator.share({ title: `${P.name} — Nuga CS Demo`, url });
      else { await navigator.clipboard.writeText(url); el("pfShare").textContent = "✅ Ссылка скопирована"; }
    } catch (e) {
      if (e?.name !== "AbortError") prompt("Скопируйте ссылку:", url);
    }
  }

  async function toggleFollow() {
    if (!P.logged_in) { note(`Войдите через Steam, чтобы подписываться. <a href="/auth/steam">Войти</a>`); return; }
    el("pfFollow").disabled = true;
    try {
      await api(`/api/profile/${P.steam_id}/follow`, P.is_following ? "DELETE" : "POST");
    } catch (e) { note(esc(e.message), true); }
    renderProfile(P.steam_id);
  }

  async function showPeople(kind) {
    const body = modal(kind === "followers" ? "Подписчики" : "Подписки", `<div class="note">Загружаем...</div>`);
    let list;
    try { list = await api(`/api/profile/${P.steam_id}/follows?kind=${kind}`); } catch (e) { body.innerHTML = `<div class="status err">${esc(e.message)}</div>`; return; }
    body.innerHTML = list.length
      ? list.map((u) => `<button class="urow" data-u="${esc(u.steam_id)}">${avatar(u.avatar)}<span><b>${esc(u.name)}</b>` +
          `<small>${u.faceit ? `FACEIT: ${esc(u.faceit)}` : ""}</small></span></button>`).join("")
      : `<div class="note">${kind === "followers" ? "Пока нет подписчиков." : "Пока нет подписок."}</div>`;
    body.querySelectorAll(".urow").forEach((b) => b.addEventListener("click", () => { closeModal(); go(b.dataset.u); }));
  }

  async function clipAction(act, id) {
    const c = [...P.clips, ...(P.private || [])].find((x) => x.id === id);
    if (!c) return;
    try {
      if (act === "del") {
        if (!confirm("Удалить этот клип из профиля?")) return;
        await api(`/api/clips/${id}`, "DELETE");
      } else if (act === "hide") {
        await api(`/api/clips/${id}/publish`, "POST", { public: false });
      } else {
        const title = prompt("Подпись к клипу (можно оставить пустой):", c.title || "");
        if (title === null) return;
        await api(`/api/clips/${id}/publish`, "POST", { public: true, title });
        if (act === "publish") { tab = "public"; note("✅ Клип опубликован — его видят все, у кого есть ссылка на профиль."); }
      }
    } catch (e) { note(esc(e.message), true); }
    renderProfile(P.steam_id);
  }

  // «Опубликовать клип»: выбираем из своих моментов в разобранных матчах
  function pickClips() {
    const have = [...P.clips, ...(P.private || [])];
    let all = [];
    for (const m of MATCH_LIST) for (const h of m.hl || []) all.push({ m, h });
    const mine = all.filter((c) => isMe(c.h.p));
    const list = (mine.length ? mine : all).filter((c) => !have.some((x) => sameClip(x, c.m, c.h))).slice(0, 80);
    const waiting = have.filter((c) => !c.public).length;
    const body = modal("Опубликовать клип",
      (waiting ? `<div class="note" style="margin:8px 0 4px">В «Личных» уже лежит клипов: ${waiting} — их можно опубликовать на вкладке «Личные».</div>` : "") +
      (list.length
        ? `<div class="note" style="margin:8px 0">Моменты из ваших разобранных матчей</div>` + list.map((c, i) =>
            `<div class="pickc"><span class="bd">${esc(c.h.t)}</span><span class="tx"><b>${esc(c.h.p)}</b>` +
            `<small>${esc([mapTitle(c.m.map), `раунд ${c.h.r + 1}`, day(c.m.created)].join(" · "))}</small></span>` +
            `<button data-i="${i}" data-pub="0">В личные</button><button class="go" data-i="${i}" data-pub="1">Опубликовать</button></div>`).join("")
        : `<div class="pfempty" style="margin-top:12px">Новых моментов нет. Разберите матч — эйсы, 4K, 3K и клатчи появятся здесь сами.<br>` +
          `<button class="pbtn primary" id="pkUpload">⇪ Загрузить демо</button></div>`), true);
    body.querySelector("#pkUpload")?.addEventListener("click", () => { closeModal(); showView("upload"); });
    body.querySelectorAll(".pickc button").forEach((b) => b.addEventListener("click", async () => {
      const c = list[+b.dataset.i], row = b.parentElement;
      row.querySelectorAll("button").forEach((x) => (x.disabled = true));
      const saved = await saveClip({ match_id: c.m.id, round: c.h.r, tick: c.h.k, type: c.h.t }, b.dataset.pub === "1");
      if (saved) b.textContent = "✓ Готово";
      else row.querySelectorAll("button").forEach((x) => (x.disabled = false));
    }));
    el("sModal").onclose = () => renderProfile(P.steam_id);
  }

  async function linkTelegram() {
    try {
      const { url } = await api("/api/telegram/link", "POST");
      const body = modal("Уведомления в Telegram",
        `<p style="color:var(--muted)">Откройте бота и нажмите «Запустить» (Start) — после этого новые подписчики и клипы будут приходить вам в Telegram.</p>` +
        `<a class="pbtn primary" href="${esc(url)}" target="_blank" rel="noopener">✈ Открыть бота</a>`);
      body.querySelector("a").addEventListener("click", () => setTimeout(closeModal, 300));
      el("sModal").onclose = () => renderProfile(P.steam_id);
    } catch (e) { note(esc(e.message), true); }
  }

  // Открыть чужой профиль и поменять адрес на /u/<id>
  function go(id, clip) {
    history.pushState({}, "", `/u/${id}` + (clip ? `?clip=${clip}` : ""));
    showView("profile", false, id);
  }

  // ---------- Лента ----------
  async function renderFeed() {
    const box = el("feedGrid");
    el("feedScope").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.s === feedScope));
    box.innerHTML = `<div class="note">Загружаем...</div>`;
    let list;
    try { list = await api(`/api/feed?scope=${feedScope}`); } catch (e) { box.innerHTML = `<div class="status err">${esc(e.message)}</div>`; return; }
    if (!list.length) {
      box.innerHTML = `<div class="pfempty" style="grid-column:1/-1">${feedScope === "following"
        ? (ready && !USER ? "Войдите через Steam и подпишитесь на игроков — их клипы появятся здесь." : "Здесь появятся клипы игроков, на которых вы подписаны.")
        : "Пока никто не опубликовал клипы. Будьте первым — откройте свой профиль и нажмите «Опубликовать клип»."}</div>`;
      return;
    }
    box.innerHTML = list.map((c, i) => card(c, i)).join("");
    box.querySelectorAll(".clipc").forEach((b) => b.addEventListener("click", (e) => {
      const a = e.target.closest(".auth");
      if (a) go(a.dataset.u); else play(list[+b.dataset.i]);
    }));
  }

  // ---------- Уведомления ----------
  async function poll() {
    if (!USER || document.hidden) return;
    try {
      const n = await api("/api/notifications");
      const c = el("bellCount");
      if (c) { c.hidden = !n.unread; c.textContent = n.unread > 99 ? "99+" : n.unread; }
      return n;
    } catch { return null; }
  }

  async function openBell() {
    const panel = el("bellPanel");
    if (panel.classList.toggle("on") === false) return;
    panel.innerHTML = `<h3>Уведомления</h3><div class="nempty">Загружаем...</div>`;
    const n = await poll();
    if (!n) { panel.innerHTML = `<h3>Уведомления</h3><div class="nempty">Не удалось загрузить уведомления</div>`; return; }
    const text = (x) => x.kind === "follow" ? " подписался на вас" : x.kind === "clip" ? " опубликовал клип" : "";
    panel.innerHTML = `<h3>Уведомления</h3>` + (n.items.length
      ? n.items.map((x, i) => `<button class="nitem${x.read ? "" : " new"}" data-i="${i}">${avatar(x.actor_avatar)}` +
          `<span><b>${esc(x.actor_name)}</b><span>${text(x)}</span>${x.clip ? `<span>: ${esc(x.clip)}</span>` : ""}<small>${ago(x.ts)}</small></span></button>`).join("")
      : `<div class="nempty">Пока пусто. Здесь появятся новые подписчики и клипы тех, на кого вы подписаны.</div>`);
    panel.querySelectorAll(".nitem").forEach((b) => b.addEventListener("click", () => {
      const x = n.items[+b.dataset.i];
      panel.classList.remove("on");
      if (x.actor) go(x.actor, x.kind === "clip" ? x.clip_id : null);
    }));
    if (n.unread) {
      api("/api/notifications/read", "POST").catch(() => {});
      el("bellCount").hidden = true;
    }
  }

  // Вызывается основным скриптом, когда стало известно, вошёл человек или нет
  function onUser() {
    ready = true;
    if (USER && !el("bellBtn")) {
      const bar = el("userBar");
      const bell = document.createElement("button");
      bell.className = "bellbtn";
      bell.id = "bellBtn";
      bell.title = "Уведомления";
      bell.innerHTML = `🔔<span class="bdg" id="bellCount" hidden></span>`;
      bar.insertBefore(bell, el("coinBtn"));
      const panel = document.createElement("div");
      panel.className = "bellpanel";
      panel.id = "bellPanel";
      document.body.appendChild(panel);
      bell.addEventListener("click", (e) => { e.stopPropagation(); openBell(); });
      document.addEventListener("click", (e) => { if (!e.target.closest("#bellPanel")) panel.classList.remove("on"); });
      bar.querySelector("img").title = "Мой профиль";
      bar.querySelectorAll("img, .ut").forEach((x) => x.addEventListener("click", () => showView("profile")));
      poll();
      setInterval(poll, 60000);
      document.addEventListener("visibilitychange", poll);
    }
    if (wantOwn) renderProfile();
  }

  // «Наш Телеграм»: ссылка появляется, когда канал указан в настройках сервера
  api("/api/config").then((cfg) => {
    const a = el("tgNav");
    if (a && cfg.telegram) { a.href = cfg.telegram; a.hidden = false; }
  }).catch(() => {});

  document.addEventListener("DOMContentLoaded", () => {
    el("feedScope")?.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { feedScope = b.dataset.s; renderFeed(); }));
  });

  return { renderProfile, renderFeed, saveClip, onUser, go, note };
})();
