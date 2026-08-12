(() => {
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const spam = /(real estate|mortgage|loan|wealth management|financial advisor|insurance|crypto|forex|lead generation|seo services|outsourcing|staff augmentation)/i;
  const links = Array.from(document.querySelectorAll('a[href*="/messaging/thread/"]'));
  const threads = [];
  const seen = new Set();
  for (const a of links) {
    const href = new URL(a.getAttribute("href"), location.href).href.split("?")[0];
    if (seen.has(href)) continue;
    seen.add(href);
    const node = a.closest("li, div[role='listitem'], div") || a;
    const text = clean(node.innerText || a.innerText || a.getAttribute("aria-label") || "");
    if (!text || spam.test(text)) continue;
    if (text.length < 20) continue;
    threads.push({ href, text: text.slice(0, 400) });
  }
  return JSON.stringify({
    schemaVersion: 1,
    payloadType: "linkedin_messages_candidates",
    ok: true,
    capturedAt: new Date().toISOString(),
    title: document.title,
    url: location.href,
    threads: threads.slice(0, 10)
  });
})();
