"use strict";

const LinkedInScanOrchestrator = (() => {
  const PAYLOAD_TYPE = "linkedin_digest_scan_summary";
  const MAX_CANDIDATES = 24;
  const MAX_EXCERPT = 520;
  const TRACKING_PARAMS = /^(?:utm_.+|trk|trackingId|lipi|midToken|midSig|ref|source)$/i;
  const KNOWLEDGE_SIGNAL = /\b(?:ai|artificial intelligence|agentic|agents?|llm|mcp|rag|model|research|report|study|benchmark|governance|compliance|regulation|privacy|security|architecture|infrastructure|cloud|database|data platform|developer|open source|enterprise|semiconductor|chip|market|product strategy|technical|technology|software|cyber|quantum|robotics)\b/i;
  const LOW_VALUE_SIGNAL = /\b(?:congratulations|congrats|anniversary|new role|new job|joined|promotion|promoted|graduation|graduated|hiring|we(?:'| a)re hiring|i am thrilled|i'm thrilled|excited to announce|real estate|mortgage|financial advisor|lead generation|book a demo|apply now)\b/i;
  const AI_SIGNAL = /\b(?:ai|artificial intelligence|genai|generative ai|machine learning|deep learning|neural networks?|large language models?|llms?|agentic|rag|retrieval[- ]augmented|model evaluations?|model training|inference|fine[- ]tuning|transformers?|embeddings?|diffusion models?|reinforcement learning|computer vision|natural language processing)\b/i;
  const EVIDENCE_HINT = /\b(?:paper|research|report|study|benchmark|evaluation|experiment|ablation|methodology|dataset|reproducib\w*|source code|case study|limitations|trade[- ]offs?|failure modes?)\b/i;

  function compactWhitespace(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function utf8Bytes(value) {
    let bytes = 0;
    for (const char of String(value)) {
      const code = char.codePointAt(0);
      bytes += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    }
    return bytes;
  }

  function shellQuote(value) {
    return `'${String(value).replace(/'/g, `'\\''`)}'`;
  }

  function buildOsaScriptCommand(lines) {
    if (!Array.isArray(lines) || lines[0] !== 'tell application "Google Chrome"') {
      throw new Error("invalid_manifest_prefix");
    }
    return `osascript ${lines.map((line) => `-e ${shellQuote(line)}`).join(" ")}`;
  }

  function parseJson(value) {
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  }

  function parseMarkedTransport(raw, { discoveryMode = "feed", searchQueries = [], includeConnectionsUpdates = false } = {}) {
    const marker = /<<<LINKEDIN_(BAND|CONNECTIONS|MESSAGES|DONE)>>>/g;
    const sections = [];
    let match;
    while ((match = marker.exec(raw)) !== null) {
      if (sections.length) sections[sections.length - 1].end = match.index;
      sections.push({ type: match[1], start: marker.lastIndex, end: raw.length });
    }

    if (!sections.some((section) => section.type === "DONE")) {
      return { ok: false, code: "completion_marker_missing" };
    }

    const bandSections = sections.filter((section) => section.type === "BAND");
    const bands = [];
    for (const section of bandSections) {
      const value = parseJson(raw.slice(section.start, section.end).trim());
      if (
        !value
        || !(discoveryMode === "search" ? ["linkedin_search_band", ...(includeConnectionsUpdates ? ["linkedin_network_band"] : [])] : ["linkedin_digest_band"]).includes(value.payloadType)
        || value.ok !== true
        || value.completionMetadata?.pageValidated !== true
      ) {
        return { ok: false, code: "required_feed_payload_invalid" };
      }
      bands.push(value);
    }

    if (bands.length < 3) return { ok: false, code: "insufficient_feed_bands" };
    if (discoveryMode === "search") {
      const searchBands = bands.filter((band) => band.payloadType === "linkedin_search_band");
      const networkBands = bands.filter((band) => band.payloadType === "linkedin_network_band");
      if (includeConnectionsUpdates && (networkBands.length !== 3 || networkBands.some((band, i) => band.completionMetadata.searchBandsInspected !== i + 1))) {
        return { ok: false, code: "network_band_metadata_inconsistent" };
      }
      const queries = [...new Set(searchBands.map((band) => band.query))];
      if (!searchQueries.length || queries.length !== searchQueries.length || queries.some((q) => !searchQueries.includes(q))) {
        return { ok: false, code: "search_query_coverage_invalid" };
      }
      for (const query of queries) {
        const group = searchBands.filter((band) => band.query === query);
        if (group.length < 3 || group.some((band, i) => band.completionMetadata.searchBandsInspected !== i + 1)) {
          return { ok: false, code: "search_band_metadata_inconsistent" };
        }
      }
      return {
        ok: true, bands, searchBandsInspected: searchBands.length, networkBandsInspected: networkBands.length, searchQueriesInspected: queries,
        connections: { ok: false, items: [], error: "not_in_scope" },
        messages: { ok: false, threads: [], error: "not_in_scope" }
      };
    }
    const counts = bands.map((band) => Number(band.completionMetadata.feedBandsInspected));
    if (counts.some((count) => !Number.isInteger(count) || count < 1)) {
      return { ok: false, code: "feed_band_metadata_invalid" };
    }
    for (let index = 1; index < counts.length; index += 1) {
      if (counts[index] <= counts[index - 1]) {
        return { ok: false, code: "feed_band_metadata_inconsistent" };
      }
    }

    const optional = (type, emptyKey) => {
      const section = sections.find((entry) => entry.type === type);
      if (!section) return { ok: false, [emptyKey]: [], error: "source_missing" };
      const value = parseJson(raw.slice(section.start, section.end).trim());
      if (!value || typeof value !== "object") {
        return { ok: false, [emptyKey]: [], error: "source_invalid" };
      }
      return value;
    };

    return {
      ok: true,
      bands,
      connections: optional("CONNECTIONS", "items"),
      messages: optional("MESSAGES", "threads"),
      feedBandsInspected: counts[counts.length - 1]
    };
  }

  function normalizedHost(hostname) {
    return String(hostname || "").toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
  }

  function parseHttpUrl(raw) {
    const match = String(raw || "").trim().match(/^(https?):\/\/([^/?#]+)([^?#]*)(\?[^#]*)?(?:#.*)?$/i);
    if (!match) return null;
    const protocol = `${match[1].toLowerCase()}:`;
    const authority = match[2];
    if (authority.includes("@")) return null;
    const hostname = authority.replace(/:\d+$/, "");
    return {
      protocol,
      authority,
      hostname,
      pathname: match[3] || "/",
      query: match[4] || ""
    };
  }

  function urlHost(raw) {
    const parsed = parseHttpUrl(raw);
    return parsed ? normalizedHost(parsed.hostname) : "";
  }

  function normalizeContentUrl(raw) {
    const url = parseHttpUrl(raw);
    if (!url) return "";
    const query = url.query
      ? url.query.slice(1).split("&").filter((part) => {
        const key = part.split("=", 1)[0];
        try {
          return !TRACKING_PARAMS.test(decodeURIComponent(key.replace(/\+/g, " ")));
        } catch {
          return !TRACKING_PARAMS.test(key);
        }
      })
      : [];
    const host = normalizedHost(url.hostname);
    let authority = url.authority;
    if (host === "linkedin.com" || host.endsWith(".linkedin.com")) {
      authority = "www.linkedin.com";
      const path = url.pathname;
      if (!/^\/(?:feed\/update\/urn:li:(?:activity|share):\d+|posts\/|pulse\/|news\/story\/|learning\/|events\/)/.test(path)) {
        return "";
      }
      query.length = 0;
    }
    const normalized = `${url.protocol}//${authority}${url.pathname}${query.length ? `?${query.join("&")}` : ""}`;
    return normalized.replace(/\/$/, "");
  }

  function parseRelativeAgeMs(text) {
    const source = String(text || "");
    const match = source.match(/(?:^|[\s\u2022])(\d+)\s*(m|h|d|w|mo|yr)(?:[\s\u2022]|$)/i);
    if (!match) return null;
    const amount = Number(match[1]);
    const unit = match[2].toLowerCase();
    const units = {
      m: 60 * 1000,
      h: 60 * 60 * 1000,
      d: 24 * 60 * 60 * 1000,
      w: 7 * 24 * 60 * 60 * 1000,
      mo: 30 * 24 * 60 * 60 * 1000,
      yr: 365 * 24 * 60 * 60 * 1000
    };
    return amount * units[unit];
  }

  function candidateScore(item) {
    // Shortlist hints only: the digest author must still read and assess the source.
    let score = item.evidenceHint ? 12 : 0;
    if (item.contentUrls.some((url) => urlHost(url) !== "linkedin.com")) score += 4;
    if (item.priorityNetwork) score += 1;
    const engagement = Number((item.engagement.match(/[\d,]+/) || ["0"])[0].replace(/,/g, ""));
    score += Math.min(1, Math.log10(engagement + 1) / 5);
    if (item.relativeAgeHours !== null) score += Math.max(0, 2 - Math.floor(item.relativeAgeHours / 48));
    return score;
  }

  function buildCompactSummary({ transport, state, currentTimeIso, overlapHours = 4, priorityOrganizations = [], contentFocus = "ai", discoveryMode = "feed", maxSourceAgeDays = 7 }) {
    if (!["ai", "general"].includes(contentFocus)) throw new Error("invalid_content_focus");
    const nowMs = Date.parse(currentTimeIso);
    const lastSuccessMs = Date.parse(state.last_successful_run_at || "");
    if (!Number.isFinite(nowMs)) throw new Error("invalid_current_time");
    const cutoffMs = discoveryMode === "search" ? nowMs - maxSourceAgeDays * 86400000 : Number.isFinite(lastSuccessMs)
      ? lastSuccessMs - overlapHours * 60 * 60 * 1000
      : nowMs - 7 * 24 * 60 * 60 * 1000;
    const allowedAgeMs = Math.max(0, nowMs - cutoffMs);
    const seen = new Set((state.seen || []).map((entry) => normalizeContentUrl(entry.url)).filter(Boolean));
    const pending = state.pending_digest?.candidates || state.pending_digest?.items || [];
    for (const entry of pending) {
      const url = normalizeContentUrl(entry.url);
      if (url) seen.add(url);
    }

    const connectionText = (transport.connections?.items || [])
      .map((item) => compactWhitespace(item.text).toLowerCase())
      .join("\n");
    const priorityPattern = priorityOrganizations.length
      ? new RegExp(`\\b(?:${priorityOrganizations.map((value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`, "i")
      : null;
    const candidates = [];
    const emitted = new Set();

    const addCandidate = (candidate) => {
      const networkUpdate = candidate.networkUpdate === true;
      if (networkUpdate && candidate.connectionDegree !== 1) return;
      const aiRelevant = AI_SIGNAL.test(candidate.excerpt);
      if (contentFocus === "ai" && !aiRelevant && !networkUpdate) return;
      const urls = [...new Set((candidate.contentUrls || []).map(normalizeContentUrl).filter(Boolean))]
        .filter((url) => !seen.has(url) && !emitted.has(url))
        .sort((left, right) => Number(urlHost(left) === "linkedin.com") - Number(urlHost(right) === "linkedin.com"));
      if (!urls.length) return;
      const relativeAgeMs = parseRelativeAgeMs(candidate.excerpt);
      const networkAgeMs = Number.isFinite(lastSuccessMs) ? Math.max(0, nowMs - lastSuccessMs + overlapHours * 3600000) : allowedAgeMs;
      if (relativeAgeMs !== null && relativeAgeMs > (networkUpdate ? networkAgeMs : allowedAgeMs) + 60 * 60 * 1000) return;
      for (const url of urls) emitted.add(url);
      const source = compactWhitespace(candidate.source) || "LinkedIn";
      const excerpt = compactWhitespace(candidate.excerpt).slice(0, MAX_EXCERPT);
      const priorityNetwork = (networkUpdate || discoveryMode !== "search") && Boolean(
        (priorityPattern && priorityPattern.test(networkUpdate ? candidate.affiliationContext || "" : `${source} ${excerpt}`))
        || (source.length >= 4 && connectionText.includes(source.toLowerCase()))
      );
      const item = {
        kind: candidate.kind,
        source: source.slice(0, 140),
        excerpt,
        engagement: compactWhitespace(candidate.engagement).slice(0, 120),
        contentUrls: urls,
        ...(discoveryMode === "search" ? {
          discovery: networkUpdate ? "connections_updates" : "linkedin_search", searchQuery: candidate.searchQuery,
          ...(networkUpdate ? { connectionDegree: 1 } : {}),
          publicAudience: candidate.publicAudience === true,
          sourceVerificationRequired: true
        } : {}),
        priorityNetwork,
        aiRelevant,
        evidenceHint: EVIDENCE_HINT.test(candidate.excerpt),
        relativeAgeHours: relativeAgeMs === null ? null : Math.round(relativeAgeMs / 3600000)
      };
      item.score = candidateScore(item);
      candidates.push(item);
    };

    const orderedBands = [...transport.bands].sort((a, b) => Number(b.payloadType === "linkedin_network_band") - Number(a.payloadType === "linkedin_network_band"));
    for (const band of orderedBands) {
      for (const post of band.posts || []) {
        const excerpt = compactWhitespace(post.text);
        if ((!KNOWLEDGE_SIGNAL.test(excerpt) && !AI_SIGNAL.test(excerpt)) || LOW_VALUE_SIGNAL.test(excerpt)) continue;
        addCandidate({
          kind: band.payloadType === "linkedin_network_band" ? "connection_update" : "post",
          source: post.author,
          excerpt,
          engagement: post.engagement,
          contentUrls: post.contentUrls,
          searchQuery: band.query,
          publicAudience: post.publicAudience,
          networkUpdate: band.payloadType === "linkedin_network_band",
          connectionDegree: post.connectionDegree,
          affiliationContext: post.affiliationContext
        });
      }
      for (const news of band.news || []) {
        const excerpt = compactWhitespace(news.text);
        if ((!KNOWLEDGE_SIGNAL.test(excerpt) && !AI_SIGNAL.test(excerpt)) || LOW_VALUE_SIGNAL.test(excerpt)) continue;
        addCandidate({
          kind: "news",
          source: "LinkedIn News",
          excerpt,
          engagement: news.engagement,
          contentUrls: [news.href]
        });
      }
    }

    candidates.sort((left, right) => right.score - left.score);
    return {
      schemaVersion: 1,
      payloadType: PAYLOAD_TYPE,
      ok: true,
      contentFocus,
      discoveryMode,
      state: {
        lastSuccessfulRunAt: state.last_successful_run_at || null,
        cutoffAt: new Date(cutoffMs).toISOString(),
        seenCount: seen.size
      },
      scan: {
        ...(discoveryMode === "search" ? {
          searchBandsInspected: transport.searchBandsInspected,
          networkBandsInspected: transport.networkBandsInspected,
          searchQueriesInspected: transport.searchQueriesInspected,
          coverage: "Bounded LinkedIn search, not exhaustive platform coverage."
        } : {}),
        feedBandsInspected: transport.feedBandsInspected,
        feedBandPayloads: transport.bands.length,
        extractedPosts: transport.bands.reduce((sum, band) => sum + (band.posts || []).length, 0),
        extractedNews: transport.bands.reduce((sum, band) => sum + (band.news || []).length, 0)
      },
      optionalSources: {
        connectionsOk: transport.connections?.ok === true,
        messagesOk: transport.messages?.ok === true
      },
      inbox: {
        publicActionUrls: [],
        note: "Private inbox content omitted from cross-service output."
      },
      candidates: candidates.slice(0, MAX_CANDIDATES).map(({ score, ...item }) => item)
    };
  }

  async function readJsonFile(tools, path, workdir, code) {
    const result = await tools.exec_command({
      cmd: `cat ${shellQuote(path)}`,
      workdir,
      yield_time_ms: 10000,
      max_output_tokens: 30000
    });
    if (result.exit_code !== 0) return { ok: false, code };
    const value = parseJson(result.output);
    if (!value) return { ok: false, code: `${code}_invalid_json` };
    return { ok: true, value };
  }

  async function collectBrowserOutput(tools, command, workdir) {
    let result = await tools.exec_command({
      cmd: command,
      workdir,
      yield_time_ms: 1000,
      max_output_tokens: 30000
    });
    let raw = result.output || "";
    let polls = 0;
    while (result.session_id !== undefined && result.session_id !== null) {
      if (polls >= 12) {
        result = await tools.write_stdin({
          session_id: result.session_id,
          chars: "\u0003",
          yield_time_ms: 1000,
          max_output_tokens: 30000
        });
        raw += result.output || "";
        let cleanupPolls = 0;
        while (result.session_id !== undefined && result.session_id !== null && cleanupPolls < 4) {
          result = await tools.write_stdin({
            session_id: result.session_id,
            chars: "",
            yield_time_ms: 1000,
            max_output_tokens: 30000
          });
          raw += result.output || "";
          cleanupPolls += 1;
        }
        return { ok: false, code: "browser_scan_timeout", raw: "", byteCount: utf8Bytes(raw) };
      }
      result = await tools.write_stdin({
        session_id: result.session_id,
        chars: "",
        yield_time_ms: 30000,
        max_output_tokens: 30000
      });
      raw += result.output || "";
      polls += 1;
    }
    return {
      ok: result.exit_code === 0,
      code: result.exit_code === 0 ? null : "browser_exit_nonzero",
      exitCode: result.exit_code,
      raw,
      byteCount: utf8Bytes(raw)
    };
  }

  async function run({
    tools,
    manifestPath,
    statePath,
    workdir,
    currentTimeIso,
    overlapHours = 4,
    maxTransportBytes = 60000,
    priorityOrganizations = [],
    contentFocus = "ai",
    discoveryMode = "feed",
    searchQueries = [],
    maxSourceAgeDays = 7,
    includeConnectionsUpdates = false
  }) {
    try {
      if (!["ai", "general"].includes(contentFocus)) throw new Error("invalid_content_focus");
      if (!["feed", "search"].includes(discoveryMode)) throw new Error("invalid_linkedin_mode");
      if (!Number.isFinite(maxSourceAgeDays) || maxSourceAgeDays <= 0) throw new Error("invalid_source_age");
      const stateRead = await readJsonFile(tools, statePath, workdir, "state_read_failed");
      if (!stateRead.ok) return { schemaVersion: 1, payloadType: PAYLOAD_TYPE, ...stateRead };
      const state = stateRead.value;
      if (state.pending_digest) {
        return {
          schemaVersion: 1,
          payloadType: PAYLOAD_TYPE,
          ok: false,
          code: "pending_digest_unresolved"
        };
      }

      const manifestRead = await readJsonFile(tools, manifestPath, workdir, "manifest_read_failed");
      if (!manifestRead.ok) return { schemaVersion: 1, payloadType: PAYLOAD_TYPE, ...manifestRead };
      const isSearchManifest = manifestRead.value.some((line) => line.includes("linkedin_search_candidates.js"));
      if (isSearchManifest !== (discoveryMode === "search")) throw new Error("manifest_discovery_mode_mismatch");
      if (discoveryMode === "search" && manifestRead.value.includes("repeat with networkBandIndex from 1 to 3") !== includeConnectionsUpdates) throw new Error("manifest_network_scope_mismatch");
      if (discoveryMode === "search" && (!searchQueries.length || searchQueries.some((q) => !manifestRead.value.some((line) => line.includes(`keywords=${encodeURIComponent(q)}&`))))) {
        throw new Error("manifest_search_queries_mismatch");
      }
      const command = buildOsaScriptCommand(manifestRead.value);
      const browser = await collectBrowserOutput(tools, command, workdir);
      if (!browser.ok) {
        return {
          schemaVersion: 1,
          payloadType: PAYLOAD_TYPE,
          ok: false,
          code: browser.code,
          exitCode: browser.exitCode ?? null,
          byteCount: browser.byteCount
        };
      }
      if (browser.byteCount >= maxTransportBytes) {
        return {
          schemaVersion: 1,
          payloadType: PAYLOAD_TYPE,
          ok: false,
          code: "transport_oversized",
          exitCode: browser.exitCode,
          byteCount: browser.byteCount
        };
      }

      const transport = parseMarkedTransport(browser.raw, { discoveryMode, searchQueries, includeConnectionsUpdates });
      browser.raw = "";
      if (!transport.ok) {
        return {
          schemaVersion: 1,
          payloadType: PAYLOAD_TYPE,
          ok: false,
          code: transport.code,
          exitCode: browser.exitCode,
          byteCount: browser.byteCount
        };
      }

      const summary = buildCompactSummary({
        transport,
        state,
        currentTimeIso,
        overlapHours,
        priorityOrganizations,
        contentFocus,
        discoveryMode,
        maxSourceAgeDays
      });
      summary.transport = { exitCode: browser.exitCode, byteCount: browser.byteCount };
      return summary;
    } catch (error) {
      return {
        schemaVersion: 1,
        payloadType: PAYLOAD_TYPE,
        ok: false,
        code: compactWhitespace(error?.message || "orchestration_failure").slice(0, 120)
      };
    }
  }

  return {
    buildCompactSummary,
    buildOsaScriptCommand,
    collectBrowserOutput,
    normalizeContentUrl,
    parseMarkedTransport,
    run,
    shellQuote,
    utf8Bytes
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = LinkedInScanOrchestrator;
LinkedInScanOrchestrator;
