// Service Worker — 缓存 + 后台通知检查
const CACHE_NAME = 'ai-assistant-v3';
// HTML 页面不缓存，避免旧代码卡住；只缓存图标等静态资源
const STATIC_ASSETS = ['/static/icon.svg'];

// 安装：预缓存静态资源
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 拦截请求：HTML 页面和 API 始终走网络，只有图标走缓存
self.addEventListener('fetch', e => {
  const url = e.request.url;
  // API 请求和 HTML 页面不缓存，直接走网络
  if (url.includes('/api/') || e.request.mode === 'navigate') return;
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

// 接收主线程消息（用于显示通知）
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'SHOW_NOTIFICATION') {
    self.registration.showNotification(e.data.title, {
      body: e.data.body,
      icon: '/static/icon.svg',
      badge: '/static/icon.svg',
      tag: 'github-daily',
      renotify: true,
      data: { url: e.data.url || '/' },
    });
  }
});

// 点击通知：打开 App
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(wins => {
      if (wins.length > 0) {
        wins[0].focus();
        wins[0].navigate(e.notification.data.url || '/');
      } else {
        clients.openWindow(e.notification.data.url || '/');
      }
    })
  );
});
