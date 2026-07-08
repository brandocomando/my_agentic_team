const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const manifestPath = path.join(__dirname, "..", "extension", "manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

test("manifest uses Chrome Manifest V3 side panel", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.side_panel.default_path, "sidepanel.html");
  assert.equal(manifest.background.service_worker, "background.js");
});

test("manifest avoids automation and network interception permissions", () => {
  const permissions = new Set(manifest.permissions || []);

  assert.equal(permissions.has("cookies"), false);
  assert.equal(permissions.has("debugger"), false);
  assert.equal(permissions.has("declarativeNetRequest"), false);
  assert.equal(permissions.has("webRequest"), false);
  assert.equal(permissions.has("webRequestBlocking"), false);
});

test("manifest only grants local helper host permissions", () => {
  assert.deepEqual(manifest.host_permissions, [
    "http://127.0.0.1:8765/*",
    "http://localhost:8765/*"
  ]);
});

test("content script loads only first-party extension files", () => {
  assert.equal(manifest.content_scripts.length, 1);
  assert.deepEqual(manifest.content_scripts[0].js, [
    "shared/normalize.js",
    "content.js"
  ]);
});
