const assert = require("node:assert/strict");
const test = require("node:test");

const llmClient = require("../extension/shared/llmClient");

test("ensureSettings defaults to disabled local helper", () => {
  assert.deepEqual(llmClient.ensureSettings(), {
    allowedHosts: ["file:", "localhost", "127.0.0.1"],
    llmEnabled: false,
    helperUrl: "http://127.0.0.1:8765"
  });
});

test("ensureSettings trims trailing slash and normalizes enabled flag", () => {
  assert.deepEqual(
    llmClient.ensureSettings({
      llmEnabled: 1,
      helperUrl: "http://localhost:8765/"
    }),
    {
      allowedHosts: ["file:", "localhost", "127.0.0.1"],
      llmEnabled: true,
      helperUrl: "http://localhost:8765"
    }
  );
});

test("parseAllowedHosts accepts newlines, commas, URLs, and wildcards", () => {
  assert.deepEqual(
    llmClient.parseAllowedHosts("https://app.example.com/path\n*.survey.test, file://"),
    ["app.example.com", "*.survey.test", "file:"]
  );
});

test("isUrlAllowed requires an explicit host match", () => {
  const settings = llmClient.ensureSettings({
    allowedHosts: "app.example.com\n*.survey.test\nfile:"
  });

  assert.equal(llmClient.isUrlAllowed("https://app.example.com/form", settings), true);
  assert.equal(llmClient.isUrlAllowed("https://foo.survey.test/form", settings), true);
  assert.equal(llmClient.isUrlAllowed("file:///tmp/sample.html", settings), true);
  assert.equal(llmClient.isUrlAllowed("https://other.example.com/form", settings), false);
  assert.equal(llmClient.isUrlAllowed("chrome://extensions", settings), false);
});

test("isUrlAllowed denies all web pages when allowlist is empty", () => {
  const settings = llmClient.ensureSettings({
    allowedHosts: []
  });

  assert.equal(llmClient.isUrlAllowed("https://app.example.com/form", settings), false);
});
