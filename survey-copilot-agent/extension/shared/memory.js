(function attachMemory(root, factory) {
  const normalize =
    root.SurveyCopilotNormalize ||
    (typeof require !== "undefined" ? require("./normalize") : undefined);
  const api = factory(normalize);

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  root.SurveyCopilotMemory = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createMemory(normalize) {
  const EMPTY_MEMORY = Object.freeze({
    answers: [],
    profileFacts: []
  });

  function ensureMemory(memory = EMPTY_MEMORY) {
    return {
      answers: Array.isArray(memory && memory.answers) ? memory.answers : [],
      profileFacts: Array.isArray(memory && memory.profileFacts)
        ? memory.profileFacts
        : []
    };
  }

  function isExpired(expiresAt, now = new Date()) {
    if (!expiresAt) {
      return false;
    }

    return new Date(expiresAt).getTime() <= now.getTime();
  }

  function computeExpiresAt(ttlDays, now = new Date()) {
    const days = Number(ttlDays);

    if (!Number.isFinite(days) || days <= 0) {
      return null;
    }

    const expiresAt = new Date(now.getTime());
    expiresAt.setDate(expiresAt.getDate() + days);
    return expiresAt.toISOString();
  }

  function normalizeAnswer(answer) {
    if (typeof answer === "string") {
      return {
        label: answer,
        value: answer,
        text: answer
      };
    }

    return {
      label: answer && answer.label ? String(answer.label) : "",
      value: answer && answer.value ? String(answer.value) : "",
      text: answer && answer.text ? String(answer.text) : ""
    };
  }

  function optionMatchesAnswer(option, answer) {
    const optionLabel = normalize.normalizeText(option && option.label);
    const optionValue = normalize.normalizeText(option && option.value);
    const answerLabel = normalize.normalizeText(answer && answer.label);
    const answerValue = normalize.normalizeText(answer && answer.value);
    const answerText = normalize.normalizeText(answer && answer.text);
    const answerCandidates = [answerLabel, answerValue, answerText].filter(Boolean);

    return answerCandidates.some((candidate) => {
      return (
        candidate === optionLabel ||
        candidate === optionValue ||
        (optionLabel && optionLabel.includes(candidate)) ||
        (candidate && candidate.includes(optionLabel))
      );
    });
  }

  function findMatchingOption(question, answer) {
    const options = Array.isArray(question && question.options) ? question.options : [];

    if (options.length === 0) {
      return normalizeAnswer(answer);
    }

    const normalizedAnswer = normalizeAnswer(answer);
    return options.find((option) => optionMatchesAnswer(option, normalizedAnswer)) || null;
  }

  function patternMatchesQuestion(pattern, questionText) {
    const patternWords = normalize.words(pattern);
    const questionWords = new Set(normalize.words(questionText));

    if (patternWords.length === 0) {
      return false;
    }

    return patternWords.every((word) => questionWords.has(word));
  }

  function sortNewestFirst(items) {
    return [...items].sort((left, right) => {
      const leftTime = new Date(left.updatedAt || left.createdAt || 0).getTime();
      const rightTime = new Date(right.updatedAt || right.createdAt || 0).getTime();
      return rightTime - leftTime;
    });
  }

  function buildSuggestion(kind, record, option, confidence, reason) {
    const answer = option || normalizeAnswer(record.answer || record.answerLabel || "");

    return {
      kind,
      confidence,
      reason,
      answer: {
        label: answer.label || answer.text || answer.value,
        value: answer.value || answer.label || answer.text,
        text: answer.text || answer.label || answer.value
      },
      memoryId: record.id || null
    };
  }

  function findSuggestion(question, memory = EMPTY_MEMORY, now = new Date()) {
    const safeMemory = ensureMemory(memory);
    const questionText = question && question.text ? question.text : "";
    const questionKey =
      (question && question.questionKey) ||
      normalize.makeQuestionKey(questionText, question && question.options);

    const savedAnswer = sortNewestFirst(safeMemory.answers).find((answer) => {
      return answer.questionKey === questionKey && !isExpired(answer.expiresAt, now);
    });

    if (savedAnswer) {
      const option = findMatchingOption(question, savedAnswer.answer || savedAnswer);

      if (option) {
        return buildSuggestion(
          "saved-answer",
          savedAnswer,
          option,
          "high",
          "Matched a previous confirmed answer."
        );
      }
    }

    const profileFact = sortNewestFirst(safeMemory.profileFacts).find((fact) => {
      return (
        !isExpired(fact.expiresAt, now) &&
        patternMatchesQuestion(fact.questionPattern, questionText)
      );
    });

    if (profileFact) {
      const option = findMatchingOption(question, profileFact.answer);

      if (option) {
        return buildSuggestion(
          "profile-fact",
          profileFact,
          option,
          "medium",
          "Matched reusable profile memory."
        );
      }
    }

    return null;
  }

  function upsertConfirmedAnswer(memory, question, answer, ttlDays, now = new Date()) {
    const safeMemory = ensureMemory(memory);
    const normalizedAnswer = normalizeAnswer(answer);
    const questionText = question && question.text ? question.text : "";
    const questionKey =
      (question && question.questionKey) ||
      normalize.makeQuestionKey(questionText, question && question.options);
    const nowIso = now.toISOString();
    const entry = {
      id: `answer-${questionKey}`,
      questionText,
      questionKey,
      answer: normalizedAnswer,
      expiresAt: computeExpiresAt(ttlDays, now),
      createdAt: nowIso,
      updatedAt: nowIso
    };
    const existing = safeMemory.answers.find((item) => item.questionKey === questionKey);

    if (existing && existing.createdAt) {
      entry.createdAt = existing.createdAt;
    }

    return {
      ...safeMemory,
      answers: [
        entry,
        ...safeMemory.answers.filter((item) => item.questionKey !== questionKey)
      ]
    };
  }

  function upsertProfileFact(memory, fact, now = new Date()) {
    const safeMemory = ensureMemory(memory);
    const nowIso = now.toISOString();
    const label = String((fact && fact.label) || "").trim();
    const questionPattern = String((fact && fact.questionPattern) || "").trim();
    const answer = normalizeAnswer((fact && fact.answer) || "");

    if (!label || !questionPattern || !(answer.label || answer.value || answer.text)) {
      throw new Error("Profile facts need a label, question pattern, and answer.");
    }

    const id =
      (fact && fact.id) ||
      `fact-${normalize.hashText(`${label} ${questionPattern} ${answer.label}`)}`;
    const entry = {
      id,
      label,
      questionPattern,
      answer,
      expiresAt: computeExpiresAt(fact && fact.ttlDays, now),
      createdAt: nowIso,
      updatedAt: nowIso
    };
    const existing = safeMemory.profileFacts.find((item) => item.id === id);

    if (existing && existing.createdAt) {
      entry.createdAt = existing.createdAt;
    }

    return {
      ...safeMemory,
      profileFacts: [
        entry,
        ...safeMemory.profileFacts.filter((item) => item.id !== id)
      ]
    };
  }

  function deleteMemoryItem(memory, collectionName, id) {
    const safeMemory = ensureMemory(memory);
    const collection = Array.isArray(safeMemory[collectionName])
      ? safeMemory[collectionName]
      : [];

    return {
      ...safeMemory,
      [collectionName]: collection.filter((item) => item.id !== id)
    };
  }

  return {
    computeExpiresAt,
    deleteMemoryItem,
    ensureMemory,
    findMatchingOption,
    findSuggestion,
    isExpired,
    normalizeAnswer,
    patternMatchesQuestion,
    upsertConfirmedAnswer,
    upsertProfileFact
  };
});
