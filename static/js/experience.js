(() => {
  'use strict';

  const maps = document.querySelectorAll('[data-roamory-map]');
  if (!maps.length || !window.L) return;

  maps.forEach((container) => {
    let points = [];
    try {
      points = JSON.parse(container.dataset.points || '[]');
    } catch (_error) {
      points = [];
    }
    if (!Array.isArray(points) || !points.length) return;

    const map = L.map(container, {
      scrollWheelZoom: false,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    const latLngs = [];
    points.forEach((point, index) => {
      const lat = Number(point.latitude);
      const lon = Number(point.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

      const marker = L.marker([lat, lon]).addTo(map);
      const number = index + 1;
      const title = String(point.name || 'Stop');
      const time = String(point.time || '');
      const location = String(point.location || '');
      marker.bindPopup(
        `<div style="min-width:170px"><strong>${number}. ${escapeHtml(title)}</strong>${time ? `<br><small>${escapeHtml(time)}</small>` : ''}${location ? `<br><span>${escapeHtml(location)}</span>` : ''}</div>`
      );
      latLngs.push([lat, lon]);
    });

    if (!latLngs.length) return;
    if (latLngs.length === 1) {
      map.setView(latLngs[0], 13);
    } else {
      map.fitBounds(latLngs, {padding: [28, 28], maxZoom: 14});
      L.polyline(latLngs, {
        color: '#1769B0',
        weight: 3,
        opacity: .75,
        dashArray: '8 8',
      }).addTo(map);
    }

    window.setTimeout(() => map.invalidateSize(), 100);
  });

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }
})();
