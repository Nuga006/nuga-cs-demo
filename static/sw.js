// Nuga CS Demo — сервис-воркер: делает сайт «приложением» и показывает экран «Нет сети».
// Меняйте номер версии, когда меняются файлы ниже, — старый кэш удалится сам.
const VERSION = "nuga-v4";
const SHELL = ["/app", "/static/offline.html", "/static/coin.png", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // Чужие сайты, загрузку демок, API и вход не трогаем — только сеть
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/")) return;

  // Страницы: сначала сеть (чтобы всегда была свежая версия), без сети — копия или экран «Нет сети»
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put("/app", copy));
          return res;
        })
        .catch(async () => (await caches.match("/app")) || caches.match("/static/offline.html"))
    );
    return;
  }

  // Картинки и файлы /static: сначала кэш, потом сеть (радары и логотипы карт грузятся один раз)
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
        return res;
      }))
    );
  }
});
