// Lightweight OpenStreetMap/Leaflet site picker for the assessment intake.
// Geocoding is opt-in via the Find address button; map clicks never call a
// remote service and simply write the selected coordinates into the form.
(() => {
  const DEFAULT_CENTER = [39.8283, -98.5795];

  function formatCoordinate(value) {
    return Number(value).toFixed(6);
  }

  function initSiteMap() {
    const element = document.getElementById("site-map");
    if (!element || element.dataset.initialized || !window.L) return;
    element.dataset.initialized = "true";

    const address = document.getElementById("address");
    const latitude = document.getElementById("latitude");
    const longitude = document.getElementById("longitude");
    const search = document.getElementById("find-address");
    const status = document.getElementById("site-map-status");
    const existingLat = Number.parseFloat(element.dataset.latitude);
    const existingLon = Number.parseFloat(element.dataset.longitude);
    const hasExisting = Number.isFinite(existingLat) && Number.isFinite(existingLon);
    const map = window.L.map(element).setView(hasExisting ? [existingLat, existingLon] : DEFAULT_CENTER, hasExisting ? 15 : 4);

    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    let marker = hasExisting ? window.L.marker([existingLat, existingLon]).addTo(map) : null;

    function setLocation(lat, lon, message) {
      latitude.value = formatCoordinate(lat);
      longitude.value = formatCoordinate(lon);
      if (!marker) marker = window.L.marker([lat, lon]).addTo(map);
      else marker.setLatLng([lat, lon]);
      map.setView([lat, lon], Math.max(map.getZoom(), 15));
      status.textContent = message || `Pinned at ${latitude.value}, ${longitude.value}.`;
    }

    map.on("click", (event) => setLocation(event.latlng.lat, event.latlng.lng, "Map pin set. Review the coordinates before saving."));

    search.addEventListener("click", async () => {
      const query = address.value.trim();
      if (!query) {
        status.textContent = "Enter an address before searching.";
        address.focus();
        return;
      }
      search.disabled = true;
      status.textContent = "Searching OpenStreetMap...";
      try {
        const url = new URL("https://nominatim.openstreetmap.org/search");
        url.searchParams.set("format", "jsonv2");
        url.searchParams.set("limit", "1");
        url.searchParams.set("q", query);
        const response = await fetch(url, { headers: { "Accept-Language": "en" } });
        if (!response.ok) throw new Error("The address service returned an error.");
        const results = await response.json();
        if (!results.length) {
          status.textContent = "No matching address found. Try a more complete address or click the map.";
          return;
        }
        const result = results[0];
        setLocation(Number(result.lat), Number(result.lon), `Found: ${result.display_name}`);
      } catch (error) {
        status.textContent = "Address search failed. Click the map to place the site pin instead.";
      } finally {
        search.disabled = false;
      }
    });

    window.setTimeout(() => map.invalidateSize(), 0);
  }

  document.addEventListener("DOMContentLoaded", initSiteMap);
  document.addEventListener("htmx:afterSwap", initSiteMap);
})();
