(() => {
  const MAX_TOTAL_POSTS = 40;
  const MAX_TOTAL_NEWS = 30;
  const MAX_POSTS_PER_BAND = 8;
  const MAX_NEWS_PER_BAND = 10;
  const MAX_POST_TEXT = 900;
  const MAX_CONTENT_URLS = 6;
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const isHttpUrl = (url) => url.protocol === "https:" || url.protocol === "http:";
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
      if (!isHttpUrl(url)) return "";
      return `${url.origin}${url.pathname}`;
    } catch {
      return "";
    }
  };
  const failure = (error) => JSON.stringify({
    schemaVersion: 1,
    payloadType: "linkedin_digest_band",
    ok: false,
    error,
    capturedAt: new Date().toISOString(),
    title: document.title || "",
    url: safePageUrl(),
    posts: [],
    news: []
  });
  let pageUrl;
  try {
    pageUrl = new URL(location.href);
  } catch {
    return failure("invalid_page_url");
  }
  if (!isHttpUrl(pageUrl) || !isLinkedInHost(pageUrl.hostname)) {
    return failure("linkedin_page_required");
  }
  if (/^\/(login|checkpoint|authwall)(?:\/|$)/.test(pageUrl.pathname)) {
    return failure("linkedin_authentication_required");
  }
  if (!(pageUrl.pathname === "/" || /^\/feed(?:\/|$)/.test(pageUrl.pathname))) {
    return failure("linkedin_feed_page_required");
  }
  if (!document.querySelector('[data-testid="mainFeed"], main')) {
    return failure("linkedin_feed_not_ready");
  }
  const session = window.__agentLinkedInDigestSession ||= {
    postUrls: Object.create(null),
    newsUrls: Object.create(null),
    emittedPosts: 0,
    emittedNews: 0,
    bandsInspected: 0
  };
  session.bandsInspected += 1;
  const decodeLinkedInSafetyUrl = (href) => {
    try {
      const parsed = new URL(href, location.href);
      if (!isHttpUrl(parsed) || !isLinkedInHost(parsed.hostname)) return "";
      if (!/^\/safety\/go\/?/.test(parsed.pathname)) return "";
      const target = new URL(parsed.searchParams.get("url") || "");
      if (!isHttpUrl(target)) return "";
      return target.href;
    } catch {
      return "";
    }
  };
  const isRealContentUrl = (href) => {
    let url;
    try {
      url = new URL(href, location.href);
    } catch {
      return "";
    }
    if (!isHttpUrl(url)) return "";
    const host = normalizedHost(url.hostname);
    if (isLinkedInHost(host)) {
      url.hash = "";
      const full = `${url.origin}${url.pathname}`;
      if (/\/news\/story\//.test(url.pathname)) return full;
      if (/\/pulse\//.test(url.pathname)) return full;
      if (/\/learning\//.test(url.pathname)) return full;
      if (/\/events\//.test(url.pathname)) return full;
      if (/\/feed\/update\/urn:li:(activity|share):\d+/.test(url.pathname)) return full;
      if (/\/posts\//.test(url.pathname)) return full;
      if (/\/messaging\/thread\//.test(url.pathname)) return full;
      if (/\/safety\/go\//.test(url.pathname)) {
        const target = decodeLinkedInSafetyUrl(url.href);
        if (!target) return "";
        let targetUrl;
        try {
          targetUrl = new URL(target);
        } catch {
          return "";
        }
        if (!isHttpUrl(targetUrl)) return "";
        const targetHost = normalizedHost(targetUrl.hostname);
        if (["b.tech", "m.tech"].includes(targetHost)) return "";
        if (targetHost.includes(".")) return targetUrl.href;
      }
      return "";
    }
    if (host.includes(".")) return url.href;
    return "";
  };
  const authorFromText = (text) => {
    const match = text.match(/^Feed post\s+(Suggested\s+)?(.+?)\s+\u2022/);
    return clean(match ? match[2] : "");
  };
  const skipText = (text) => {
    const lower = text.toLowerCase();
    const skipPatterns = [
      "promoted", "#opentowork", "open to work", "#hiring", "we're hiring",
      "we are hiring", "started a new position", "starting a new position",
      "new role", "work anniversary", "celebrating", "congratulates",
      "congratulations", "appointed as", "chapter is coming to a close",
      "my time at", "came to an end", "premium members"
    ];
    return skipPatterns.some((pattern) => lower.includes(pattern));
  };
  const hasKnowledgeSignal = (text) => {
    const lower = text.toLowerCase();
    return [
      "agent", "agents", "ai ", "genai", "llm", "mcp", "rag", "governance",
      "security", "platform", "architecture", "cloud", "data", "research",
      "report", "whitepaper", "quantum", "chip", "market", "enterprise"
    ].some((term) => lower.includes(term));
  };
  const visiblePosts = Array.from(document.querySelectorAll('[data-testid="mainFeed"] [role="listitem"], article, .feed-shared-update-v2'));
  const posts = [];
  for (const node of visiblePosts) {
    if (session.emittedPosts >= MAX_TOTAL_POSTS || posts.length >= MAX_POSTS_PER_BAND) break;
    const rect = node.getBoundingClientRect();
    const text = clean(node.innerText || node.textContent || "");
    if (!text.startsWith("Feed post") || text.length < 120) continue;
    if (skipText(text) || !hasKnowledgeSignal(text)) continue;
    const links = Array.from(node.querySelectorAll("a[href]"))
      .map((a) => ({
        text: clean(a.innerText || a.getAttribute("aria-label") || ""),
        href: a.href,
        contentUrl: isRealContentUrl(a.href)
      }))
      .filter((link) => link.contentUrl);
    const contentUrls = Array.from(new Set(links.map((link) => link.contentUrl))).slice(0, MAX_CONTENT_URLS);
    if (!contentUrls.length) continue;
    const freshUrls = contentUrls.filter((url) => !session.postUrls[url]);
    if (!freshUrls.length) continue;
    for (const url of contentUrls) session.postUrls[url] = true;
    posts.push({
      author: authorFromText(text),
      contentUrls,
      text: text.slice(0, MAX_POST_TEXT),
      engagement: clean((text.match(/([0-9,]+ reactions?.*?)(?:Like Comment|$)/) || [])[1] || ""),
      top: Math.round(rect.top),
      height: Math.round(rect.height)
    });
    session.emittedPosts += 1;
  }
  const news = Array.from(document.querySelectorAll('a[href*="/news/story/"]'))
    .map((a) => ({
      text: clean(a.innerText || a.getAttribute("aria-label") || ""),
      href: isRealContentUrl(a.href)
    }))
    .filter((item) => item.text && item.href && !session.newsUrls[item.href])
    .slice(0, Math.min(MAX_NEWS_PER_BAND, MAX_TOTAL_NEWS - session.emittedNews));
  for (const item of news) session.newsUrls[item.href] = true;
  session.emittedNews += news.length;
  return JSON.stringify({
    schemaVersion: 1,
    payloadType: "linkedin_digest_band",
    ok: true,
    capturedAt: new Date().toISOString(),
    title: document.title,
    url: safePageUrl(),
    workspaceScrollTop: document.getElementById("workspace")?.scrollTop || 0,
    posts,
    news,
    sessionTotals: { posts: session.emittedPosts, news: session.emittedNews },
    completionMetadata: {
      feedBandsInspected: session.bandsInspected,
      pageValidated: true
    },
    capped: {
      posts: session.emittedPosts >= MAX_TOTAL_POSTS,
      news: session.emittedNews >= MAX_TOTAL_NEWS
    }
  });
})();
