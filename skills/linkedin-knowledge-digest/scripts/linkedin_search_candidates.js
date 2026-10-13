(() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const page = new URL(location.href);
  const query = page.searchParams.get("keywords") || "";
  const networkMode = page.origin === "https://www.linkedin.com" && page.pathname === "/feed/";
  const failure = (error) => JSON.stringify({
    payloadType: "linkedin_search_band", ok: false, error, posts: [], news: []
  });
  if (!networkMode && !/^https:\/\/(?:www\.)?linkedin\.com\/search\/results\/content\//.test(page.href)) {
    return failure("linkedin_search_page_required");
  }
  const main = document.querySelector("main");
  if (!main) return failure("linkedin_search_not_ready");
  if (/security verification|verify your identity|unusual activity|search limit/i.test(main.innerText || "")) {
    return failure("linkedin_access_boundary");
  }
  const contentUrl = (href) => {
    try {
      let url = new URL(href, page.href);
      if (/^(?:www\.)?linkedin\.com$/.test(url.hostname) && url.pathname === "/safety/go") {
        url = new URL(url.searchParams.get("url"));
      } else if (/^(?:www\.)?linkedin\.com$/.test(url.hostname) && url.pathname === "/safety/go/") {
        url = new URL(url.searchParams.get("url"));
      }
      if (!/^https?:$/.test(url.protocol) || url.username || url.password) return "";
      if (/(^|\.)linkedin\.com$/.test(url.hostname)) {
        if (!/^\/(pulse\/|posts\/|feed\/update\/urn:li:(activity|share):\d+)/.test(url.pathname)) return "";
        url.search = "";
      } else if (url.pathname === "/" && url.hostname !== "lnkd.in") return "";
      url.hash = "";
      return url.href.length <= 400 ? url.href : "";
    } catch { return ""; }
  };
  const selector = '.reusable-search__result-container, .feed-shared-update-v2, article, [data-testid="search-result"], [role="listitem"]';
  const nodes = Array.from(main.querySelectorAll(selector));
  const empty = /no results found|no matching results|we couldn't find any results/i.test(main.innerText || "");
  if (!nodes.length && !empty) return failure("linkedin_search_layout_unrecognized");
  const session = window.__agentLinkedInSearchSession ||= { query, band: 0, urls: Object.create(null) };
  if (session.query !== query) {
    session.query = query;
    session.band = 0;
    session.urls = Object.create(null);
  }
  session.band += 1;
  const posts = [];
  for (const node of nodes) {
    if (posts.length >= 3) break;
    const text = clean(node.innerText || node.textContent);
    if (text.length < 80 || /\b(promoted|promotion|hiring|congratulations|anniversary|open to work|book a demo|new (?:job|role|position)|company outing|team outing|offsite|team retreat|thrilled|honored|humbled|proud to announce)\b/i.test(text)) continue;
    const actor = node.querySelector('.update-components-actor__meta, .feed-shared-actor, .entity-result__title-text');
    const header = text.match(/^Feed post\s+(?:Suggested\s+)?(.+?)\s+\u2022\s+(1st|2nd|3rd\+)(?:\s|$)/);
    const firstDegree = header?.[2] === "1st" || /\b1st\b|first.degree/i.test(clean(actor?.innerText || actor?.textContent))
      || Boolean(node.querySelector('[aria-label*="1st degree connection"]'));
    if (networkMode && !firstDegree) continue;
    const links = Array.from(node.querySelectorAll("a[href]"));
    const urls = [...new Set(links.map((a) => contentUrl(a.href)).filter(Boolean))];
    const urn = node.getAttribute("data-urn") || node.getAttribute("data-id") || "";
    if (/^urn:li:(activity|share):\d+$/.test(urn)) urls.push(`https://www.linkedin.com/feed/update/${urn}/`);
    const contentUrls = [...new Set(urls)].slice(0, 6);
    if (!contentUrls.length || contentUrls.every((url) => session.urls[url])) continue;
    const authorNode = node.querySelector('.update-components-actor__name, .feed-shared-actor__name, .entity-result__title-text');
    const author = clean(authorNode?.innerText || header?.[1] || links.find((a) => /\/in\/|\/company\//.test(a.href))?.innerText).slice(0, 140);
    const labels = Array.from(node.querySelectorAll("[aria-label], [title]")).map((el) => `${el.getAttribute("aria-label") || ""} ${el.getAttribute("title") || ""}`).join(" ");
    const publicAudience = /visible to anyone|public post/i.test(`${text} ${labels}`);
    const timedHeader = text.match(/^(.{1,400}?)\s+\d+(?:m|h|d|w|mo|yr)(?:\s|$)/)?.[1];
    const item = {
      author, text: text.slice(0, 900), contentUrls,
      engagement: clean((text.match(/[\d,]+ (?:reactions?|comments?)/i) || [""])[0]),
      publicAudience,
      ...(networkMode ? { connectionDegree: 1, affiliationContext: clean(actor?.innerText || timedHeader || "") } : {})
    };
    // Twelve search/network bands stay below 60 KB; at most 36 posts per run.
    if (new TextEncoder().encode(JSON.stringify([...posts, item])).length > 4000) break;
    posts.push(item);
    for (const url of contentUrls) session.urls[url] = true;
  }
  return JSON.stringify({
    schemaVersion: 1, payloadType: networkMode ? "linkedin_network_band" : "linkedin_search_band", ok: true,
    query, searchUrl: page.href, capturedAt: new Date().toISOString(), posts, news: [],
    completionMetadata: { pageValidated: true, searchBandsInspected: session.band, resultNodes: nodes.length, empty }
  });
})();
