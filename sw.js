// Island Player service worker
//  - App files (player.html, playlist.json, manifest, icon): network-first,
//    so a git push shows up on the next open; cached copy is the offline fallback.
//  - Audio: cache-first in a long-lived cache that survives app updates.
//    One failed download never blocks an update; missing files are fetched
//    (and cached) when played, and retried on the next update.

const SHELL_CACHE = 'island-shell-v10';
const AUDIO_CACHE = 'island-audio';
const SHELL_FILES = ['player.html', 'playlist.json', 'manifest.json', 'icon.svg'];

async function precacheAudio() {
  const res = await fetch('playlist.json', { cache: 'no-store' });
  const playlist = await res.json();
  const files = new Set();
  playlist.forEach(entry =>
    (entry.segments || []).forEach(seg => { if (seg.audio) files.add(seg.audio); })
  );
  const cache = await caches.open(AUDIO_CACHE);
  const list = [...files];
  for (let i = 0; i < list.length; i += 6) {
    await Promise.all(list.slice(i, i + 6).map(async f => {
      try {
        if (await cache.match(f)) return;          // already have it
        const r = await fetch(f);
        if (r.ok && r.status === 200) await cache.put(f, r);
      } catch (e) { /* skip; will retry when played or on next update */ }
    }));
  }
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(c => c.addAll(SHELL_FILES.map(f => new Request(f, { cache: 'no-store' }))))
      .then(() => precacheAudio().catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== SHELL_CACHE && k !== AUDIO_CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

function isShell(url) {
  const path = url.pathname;
  return path.endsWith('/') || SHELL_FILES.some(f => path.endsWith('/' + f));
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate' || isShell(url)) {
    // Network first, fall back to cache when offline
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then(res => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(SHELL_CACHE).then(c => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req, { ignoreSearch: true })
          .then(r => r || caches.match('player.html')))
    );
    return;
  }

  // Audio and everything else: cache first, then network (and keep a copy)
  event.respondWith(
    caches.match(req, { ignoreSearch: true }).then(cached => {
      if (cached) return cached;
      return fetch(req).then(res => {
        if (res.ok && res.status === 200 && url.pathname.includes('/audio/')) {
          const copy = res.clone();
          caches.open(AUDIO_CACHE).then(c => c.put(req, copy));
        }
        return res;
      });
    })
  );
});
