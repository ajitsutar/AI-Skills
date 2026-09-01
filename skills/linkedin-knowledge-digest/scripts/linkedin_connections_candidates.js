(() => {
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const seen = new Set();
  const items = [];

  for (const anchor of document.querySelectorAll('a[href*="/in/"]')) {
    let profile;
    try {
      profile = new URL(anchor.getAttribute("href"), location.href).href.split("?")[0];
    } catch {
      continue;
    }
    if (seen.has(profile)) continue;
    seen.add(profile);

    const container = anchor.closest("li, [role='listitem']") || anchor;
    const text = clean(
      container.innerText ||
      anchor.innerText ||
      anchor.getAttribute("aria-label") ||
      ""
    );
    if (text.length < 2) continue;

    items.push({ profile, text: text.slice(0, 220) });
    if (items.length >= 20) break;
  }

  return JSON.stringify({
    schemaVersion: 1,
    payloadType: "linkedin_connections_candidates",
    ok: true,
    capturedAt: new Date().toISOString(),
    items
  });
})();
