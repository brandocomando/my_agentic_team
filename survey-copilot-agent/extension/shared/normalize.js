(function attachNormalize(root, factory) {
  const api = factory();

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  root.SurveyCopilotNormalize = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createNormalize() {
  function normalizeText(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function words(value) {
    const normalized = normalizeText(value);
    return normalized ? normalized.split(" ") : [];
  }

  function hashText(value) {
    const text = normalizeText(value);
    let hash = 0;

    for (let index = 0; index < text.length; index += 1) {
      hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
    }

    return hash.toString(36);
  }

  function optionSignature(options = []) {
    const optionTexts = (Array.isArray(options) ? options : [])
      .map((option) => {
        if (typeof option === "string") {
          return normalizeText(option);
        }

        return normalizeText(`${option && option.label ? option.label : ""} ${
          option && option.value ? option.value : ""
        }`);
      })
      .filter(Boolean)
      .sort();

    return optionTexts.join("|");
  }

  function makeQuestionKey(value, options = []) {
    const signature = optionSignature(options);
    return hashText(signature ? `${value} | options: ${signature}` : value);
  }

  return {
    hashText,
    makeQuestionKey,
    normalizeText,
    optionSignature,
    words
  };
});
