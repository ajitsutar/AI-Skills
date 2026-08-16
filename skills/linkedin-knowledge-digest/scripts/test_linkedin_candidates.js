#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SCRIPT_DIR = __dirname;

function runHelper(filename, options = {}) {
  const url = options.url || "https://www.linkedin.com/feed/";
  const document = {
    title: options.title || "LinkedIn",
    querySelector: (selector) => {
      if (options.querySelector) return options.querySelector(selector);
      return {};
    },
    querySelectorAll: (selector) => (options.selectors || {})[selector] || [],
    getElementById: () => ({ scrollTop: 120 })
  };
  const context = vm.createContext({
    URL,
    document,
    location: { href: url },
    window: {}
  });
  const source = fs.readFileSync(path.join(SCRIPT_DIR, filename), "utf8");
  return JSON.parse(vm.runInContext(source, context, { filename }));
}

function anchor(href, text, containerText = text) {
  const container = { innerText: containerText };
  return {
    href,
    innerText: text,
    parentElement: container,
    getAttribute: (name) => (name === "href" ? href : ""),
    closest: () => container
  };
}

function testFeedExtractionAndAuthorEncoding() {
  const articleUrl = "https://example.com/research?utm_source=linkedin";
  const safetyUrl = `https://www.linkedin.com/safety/go/?url=${encodeURIComponent(articleUrl)}`;
  const postText = [
    "Feed post Suggested Ada Lovelace \u2022",
    "Research report about AI architecture, security, enterprise platforms, and useful data.",
    "This substantive analysis explains the findings and practical implications in detail."
  ].join(" ");
  const postLink = anchor(safetyUrl, "Read report");
  const post = {
    innerText: postText,
    getBoundingClientRect: () => ({ top: 10, height: 300 }),
    querySelectorAll: () => [postLink]
  };
  const result = runHelper("linkedin_digest_candidates.js", {
    selectors: {
      '[data-testid="mainFeed"] [role="listitem"], article, .feed-shared-update-v2': [post],
      'a[href*="/news/story/"]': []
    }
  });
  assert.equal(result.ok, true);
  assert.equal(result.posts.length, 1);
  assert.equal(result.posts[0].author, "Ada Lovelace");
  assert.deepEqual(result.posts[0].contentUrls, [articleUrl]);
  assert.equal(result.completionMetadata.feedBandsInspected, 1);
  assert.equal(result.completionMetadata.pageValidated, true);
}

function testFeedRejectsLookalikeAndAuthenticationPages() {
  const lookalike = runHelper("linkedin_digest_candidates.js", {
    url: "https://evil-linkedin.com/feed/"
  });
  assert.equal(lookalike.ok, false);
  assert.equal(lookalike.error, "linkedin_page_required");

  const login = runHelper("linkedin_digest_candidates.js", {
    url: "https://www.linkedin.com/login?session=do-not-export"
  });
  assert.equal(login.ok, false);
  assert.equal(login.error, "linkedin_authentication_required");
  assert.equal(login.url, "https://www.linkedin.com/login");
}

function testMessageExtractionSkipsMalformedAndOffsiteLinks() {
  const selector = 'a[href*="/messaging/thread/"]';
  const result = runHelper("linkedin_messages_candidates.js", {
    url: "https://www.linkedin.com/messaging/?session=do-not-export",
    selectors: {
      [selector]: [
        anchor("https://www.linkedin.com/messaging/thread/abc?trk=test", "Open", "Useful technical discussion that needs review"),
        anchor("https://evil-linkedin.com/messaging/thread/leak", "Offsite", "This must not be exported"),
        anchor("http://[/messaging/thread/bad", "Malformed", "This must not abort extraction")
      ]
    }
  });
  assert.equal(result.ok, true);
  assert.equal(result.pageValidated, true);
  assert.equal(result.url, "https://www.linkedin.com/messaging/");
  assert.deepEqual(result.threads, [{
    href: "https://www.linkedin.com/messaging/thread/abc",
    text: "Useful technical discussion that needs review"
  }]);
}

testFeedExtractionAndAuthorEncoding();
testFeedRejectsLookalikeAndAuthenticationPages();
testMessageExtractionSkipsMalformedAndOffsiteLinks();
console.log("LinkedIn extraction helper tests passed.");
