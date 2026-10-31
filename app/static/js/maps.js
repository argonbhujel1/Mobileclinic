/* Mobile Clinic — Leaflet map helpers + OSRM directions */
(function () {
  "use strict";

  function bikeIcon() {
    return L.divIcon({
      className: "",
      html: '<div style="background:#0f4c81;color:#fff;width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:18px">🛵</div>',
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
  }

  function userIcon() {
    return L.divIcon({
      className: "",
      html: '<div style="background:#16a34a;color:#fff;width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:16px">📍</div>',
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
  }

  window.MCMaps = {
    createMap(containerId, options = {}) {
      const el = document.getElementById(containerId);
      if (!el || typeof L === "undefined") return null;
      const tileUrl =
        el.dataset.tileUrl || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
      const map = L.map(containerId, {
        center: options.center || [27.7172, 85.324],
        zoom: options.zoom || 13,
        ...options,
      });
      L.tileLayer(tileUrl, {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);
      return map;
    },

    bikeIcon,
    userIcon,

    async drawRoute(map, fromLat, fromLng, toLat, toLng, existingLayer) {
      if (!map || fromLat == null || toLat == null) return existingLayer || null;
      try {
        const url =
          "https://router.project-osrm.org/route/v1/driving/" +
          fromLng + "," + fromLat + ";" + toLng + "," + toLat +
          "?overview=full&geometries=geojson";
        const res = await fetch(url);
        const data = await res.json();
        if (!data.routes || !data.routes[0]) return existingLayer || null;
        const coords = data.routes[0].geometry.coordinates.map((c) => [c[1], c[0]]);
        if (existingLayer) map.removeLayer(existingLayer);
        const layer = L.polyline(coords, { color: "#0f4c81", weight: 5, opacity: 0.85 }).addTo(map);
        layer._routeMeta = {
          distance_m: data.routes[0].distance,
          duration_s: data.routes[0].duration,
        };
        return layer;
      } catch (e) {
        console.warn("Route failed", e);
        return existingLayer || null;
      }
    },

    googleMapsDirectionsUrl(fromLat, fromLng, toLat, toLng) {
      if (toLat == null || toLng == null) return "#";
      if (fromLat != null && fromLng != null) {
        return "https://www.google.com/maps/dir/?api=1&origin=" + fromLat + "," + fromLng +
          "&destination=" + toLat + "," + toLng + "&travelmode=driving";
      }
      return "https://www.google.com/maps/dir/?api=1&destination=" + toLat + "," + toLng + "&travelmode=driving";
    },

    initPickupPicker(containerId, latInput, lngInput, addressInput) {
      const map = this.createMap(containerId, { zoom: 14 });
      if (!map) return;
      let marker = null;
      const setMarker = (latlng) => {
        if (marker) marker.setLatLng(latlng);
        else marker = L.marker(latlng, { draggable: true, icon: userIcon() }).addTo(map);
        marker.on("dragend", (e) => {
          const p = e.target.getLatLng();
          if (latInput) latInput.value = p.lat.toFixed(6);
          if (lngInput) lngInput.value = p.lng.toFixed(6);
        });
        if (latInput) latInput.value = latlng.lat.toFixed(6);
        if (lngInput) lngInput.value = latlng.lng.toFixed(6);
        map.setView(latlng, 15);
      };
      map.on("click", (e) => setMarker(e.latlng));
      const geoBtn = document.getElementById("use-my-location");
      if (geoBtn) {
        geoBtn.addEventListener("click", () => {
          if (!navigator.geolocation) { alert("Geolocation is not supported."); return; }
          geoBtn.disabled = true;
          geoBtn.textContent = "Locating…";
          navigator.geolocation.getCurrentPosition(
            (pos) => {
              setMarker({ lat: pos.coords.latitude, lng: pos.coords.longitude });
              geoBtn.disabled = false;
              geoBtn.textContent = "Use My Location";
            },
            () => {
              alert("Unable to retrieve location.");
              geoBtn.disabled = false;
              geoBtn.textContent = "Use My Location";
            },
            { enableHighAccuracy: true, timeout: 10000 }
          );
        });
      }
      if (latInput && latInput.value && lngInput && lngInput.value) {
        setMarker({ lat: parseFloat(latInput.value), lng: parseFloat(lngInput.value) });
      }
    },

    initTrackingMap(containerId, staffLat, staffLng, destLat, destLng) {
      const map = this.createMap(containerId);
      if (!map) return map;
      const bounds = [];
      if (staffLat && staffLng) {
        L.marker([staffLat, staffLng], { icon: bikeIcon() }).addTo(map).bindPopup("Admin (on the way)");
        bounds.push([staffLat, staffLng]);
      }
      if (destLat && destLng) {
        L.marker([destLat, destLng], { icon: userIcon() }).addTo(map).bindPopup("Your pickup location");
        bounds.push([destLat, destLng]);
      }
      if (bounds.length) map.fitBounds(bounds, { padding: [40, 40] });
      if (staffLat && destLat) this.drawRoute(map, staffLat, staffLng, destLat, destLng);
      return map;
    },
  };
})();
