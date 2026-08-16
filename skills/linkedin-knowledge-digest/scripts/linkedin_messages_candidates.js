(() => {
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const spam = /(real estate|mortgage|loan|wealth management|financial advisor|insurance|crypto|forex|lead generation|seo services|outsourcing|staff augmentation)/i;
  const normalizedHost = (hostname) => (hostname || "")
    .toLowerCase()
    .replace(/\.$/, "")
    .replace(/^www\./, "");
  const isLinkedInHost = (hostname) => {
    const host = normalizedHost(hostname);
    return host === "linkedin.com" || host.endsWith(".linkedin.com");
  };
  const safePageUrl = () => {
    try {
      const url = new URL(location.href);
      if (!["https:", "http:"].includes(url.protocol)) return "";
      return `${url.origin}${url.pathname}`;
    } catch {
      return "";
    }
  };
  const failure = (error) => JSON.stringify({
    schemaVersion: 1,
    payloadType: "linkedin_messages_candidates",
    ok: false,
    error,
    capturedAt: new Date().toISOString(),
    title: document.title || "",
    url: safePageUrl(),
    threads: []
  });
  let pageUrl;
  try {
    pageUrl = new URL(location.href);
  } catch {
    return failure("invalid_page_url");
  }
  if (
    !["https:", "http:"].includes(pageUrl.protocol)
    || !isLinkedInHost(pageUrl.hostname)
  ) {
    return failure("linkedin_page_required");
  }
  if (/^\/(login|checkpoint|authwall)(?:\/|$)/.test(pageUrl.pathname)) {
    return failure("linkedin_authentication_required");
  }
  if (!/^\/messaging(?:\/|$)/.test(pageUrl.pathname)) {
    return failure("linkedin_messaging_page_required");
  }
  const links = Array.from(document.querySelectorAll('a[href*="/messaging/thread/"]'));
  const threads = [];
  const seen = new Set();
  for (const a of links) {
    let url;
    try {
      url = new URL(a.getAttribute("href"), location.href);
    } catch {
      continue;
    }
    if (
      !["https:", "http:"].includes(url.protocol)
      || !isLinkedInHost(url.hostname)
      || !/^\/messaging\/thread\//.test(url.pathname)
    ) {
      continue;
    }
    const href = `${url.origin}${url.pathname}`;
    if (seen.has(href)) continue;
    seen.add(href);
    const node = a.closest(
      "li, [role='listitem'], .msg-conversation-listitem, .msg-conversations-container__convo-item"
    ) || a.parentElement || a;
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
    url: safePageUrl(),
    pageValidated: true,
    threads: threads.slice(0, 10)
  });
})();
