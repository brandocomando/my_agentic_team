(function attachLlmClient(root, factory) {
  const api = factory();

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  root.SurveyCopilotLlmClient = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createLlmClient() {
  const DEFAULT_SETTINGS = Object.freeze({
    allowedHosts: ["file:", "localhost", "127.0.0.1"],
    llmEnabled: false,
    helperUrl: "http://127.0.0.1:8765"
  });

  function ensureSettings(settings = DEFAULT_SETTINGS) {
    const helperUrl = String(settings.helperUrl || DEFAULT_SETTINGS.helperUrl).replace(/\/$/, "");

    return {
      allowedHosts: parseAllowedHosts(settings.allowedHosts || DEFAULT_SETTINGS.allowedHosts),
      llmEnabled: Boolean(settings.llmEnabled),
      helperUrl
    };
  }

  function parseAllowedHosts(value) {
    if (Array.isArray(value)) {
      return value.map(normalizeAllowedHost).filter(Boolean);
    }

    return String(value || "")
      .split(/[\n,]+/)
      .map(normalizeAllowedHost)
      .filter(Boolean);
  }

  function normalizeAllowedHost(value) {
    const trimmed = String(value || "").trim().toLowerCase();

    if (!trimmed) {
      return "";
    }

    if (trimmed === "file:" || trimmed === "file://") {
      return "file:";
    }

    try {
      const parsed = new URL(trimmed.includes("://") ? trimmed : `https://${trimmed}`);

      if (parsed.protocol === "file:") {
        return "file:";
      }

      if (!parsed.hostname) {
        return "";
      }

      if (trimmed.startsWith("*.")) {
        return `*.${parsed.hostname.replace(/^\*\./, "")}`;
      }

      return parsed.hostname;
    } catch (_error) {
      return trimmed.replace(/:\d+$/, "");
    }
  }

  function hostMatchesPattern(host, pattern) {
    const normalizedHost = String(host || "").toLowerCase();
    const normalizedPattern = normalizeAllowedHost(pattern);

    if (!normalizedHost || !normalizedPattern) {
      return false;
    }

    if (normalizedPattern.startsWith("*.")) {
      const suffix = normalizedPattern.slice(2);
      return normalizedHost === suffix || normalizedHost.endsWith(`.${suffix}`);
    }

    return normalizedHost === normalizedPattern;
  }

  function isUrlAllowed(url, settings = DEFAULT_SETTINGS) {
    const safeSettings = ensureSettings(settings);

    if (safeSettings.allowedHosts.length === 0) {
      return false;
    }

    let parsed;

    try {
      parsed = new URL(url);
    } catch (_error) {
      return false;
    }

    if (parsed.protocol === "file:") {
      return safeSettings.allowedHosts.includes("file:");
    }

    if (!["http:", "https:"].includes(parsed.protocol)) {
      return false;
    }

    return safeSettings.allowedHosts.some((pattern) => {
      return hostMatchesPattern(parsed.hostname, pattern);
    });
  }

  async function helperHealth(settings) {
    const safeSettings = ensureSettings(settings);
    const response = await fetch(`${safeSettings.helperUrl}/health`, {
      method: "GET"
    });

    if (!response.ok) {
      throw new Error(`LLM helper health check failed with HTTP ${response.status}.`);
    }

    return response.json();
  }

  async function suggest(settings, questions, memory) {
    const safeSettings = ensureSettings(settings);

    if (!safeSettings.llmEnabled) {
      return {
        ok: false,
        suggestions: [],
        skipped: true
      };
    }

    const response = await fetch(`${safeSettings.helperUrl}/suggest`, {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        questions,
        memory
      })
    });

    if (!response.ok) {
      throw new Error(`LLM helper suggestion request failed with HTTP ${response.status}.`);
    }

    return response.json();
  }

  return {
    DEFAULT_SETTINGS,
    ensureSettings,
    helperHealth,
    hostMatchesPattern,
    isUrlAllowed,
    normalizeAllowedHost,
    parseAllowedHosts,
    suggest
  };
});
