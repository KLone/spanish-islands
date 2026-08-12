const CACHE = 'island-player-v4';

// On install: cache all files listed in playlist.json
self.addEventListener('install', event => {
  event.waitUntil(
    fetch('playlist.json')
      .then(r => r.json())
      .then(playlist => {
        const audioFiles = new Set();
        playlist.forEach(card => {
          card.segments.forEach(seg => audioFiles.add(seg.audio));
        });

        const filesToCache = [
          'player.html',
          'playlist.json',
          'manifest.json',
          'icon.svg',
          ...audioFiles,
        ];

        return caches.open(CACHE).then(cache => {
          console.log('[SW] Caching', filesToCache.length, 'files');
          // Cache in small batches to avoid overwhelming the browser
          const batchSize = 5;
          const batches = [];
          for (let i = 0; i < filesToCache.length; i += batchSize) {
            batches.push(filesToCache.slice(i, i + batchSize));
          }
          return batches.reduce((chain, batch) => {
            return chain.then(() => cache.addAll(batch));
          }, Promise.resolve());
        });
      })
  );
  self.skipWaiting();
});

// On activate: delete old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// On fetch: serve from cache, fall back to network
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});
