const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const contentPath = path.join(__dirname, "..", "extension", "content.js");
const sidepanelPath = path.join(__dirname, "..", "extension", "sidepanel.js");
const contentSource = fs.readFileSync(contentPath, "utf8");
const sidepanelSource = fs.readFileSync(sidepanelPath, "utf8");

test("side panel exposes a user-confirmed next page action", () => {
  assert.match(sidepanelSource, /data-next-page/);
  assert.match(sidepanelSource, /survey-copilot:next/);
  assert.match(sidepanelSource, /isUrlAllowed\(activeTabUrl, settings\)/);
});

test("content script clicks only visible next-style controls on request", () => {
  assert.match(contentSource, /survey-copilot:next/);
  assert.match(contentSource, /NEXT_LABELS/);
  assert.match(contentSource, /No visible Next, Continue, Submit, Done, or Finish button found/);
  assert.match(contentSource, /usableNavigationControl/);
});
