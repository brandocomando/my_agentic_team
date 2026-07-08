#!/usr/bin/env node

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const normalize = require("../extension/shared/normalize");
const memoryApi = require("../extension/shared/memory");

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;
const BASE_JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type"
};
const SYSTEM_PROMPT = [
  "You are the suggestion engine for Survey Copilot Agent.",
  "You help a human answer visible survey questions from their saved local memory.",
  "Use confirmed answers and profile facts as evidence, but do not guess beyond them.",
  "For recent, time-sensitive, preference, opinion, or unknown questions, return answer null.",
  "For choice questions, choose only one of the provided visible options.",
  "Return strict JSON only."
].join(" ");

function loadDotEnv() {
  const candidates = [
    path.join(process.cwd(), ".env"),
    path.join(__dirname, "..", ".env")
  ];
  const env = {};
  const envPath = candidates.find((candidate) => fs.existsSync(candidate));

  if (!envPath) {
    return env;
  }

  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      return;
    }

    const index = trimmed.indexOf("=");
    const key = trimmed.slice(0, index).trim();
    const value = trimmed.slice(index + 1).trim().replace(/^["']|["']$/g, "");

    if (key && !(key in process.env)) {
      env[key] = value;
    }
  });

  return env;
}

function loadConfig(env = { ...loadDotEnv(), ...process.env }) {
  return {
    host: env.LLM_HELPER_HOST || DEFAULT_HOST,
    port: Number(env.LLM_HELPER_PORT || DEFAULT_PORT),
    provider: (env.LLM_PROVIDER || "ollama").toLowerCase(),
    ollamaBaseUrl: env.OLLAMA_BASE_URL || "http://localhost:11434",
    ollamaModel: env.OLLAMA_MODEL || "llama3.1:8b",
    openaiApiKey: env.OPENAI_API_KEY || "",
    openaiBaseUrl: env.OPENAI_BASE_URL || "https://api.openai.com/v1",
    openaiModel: env.OPENAI_MODEL || "gpt-4.1-mini"
  };
}

function jsonHeadersForRequest(request) {
  const origin = request && request.headers ? request.headers.origin : "";
  const headers = { ...BASE_JSON_HEADERS };

  if (origin && origin.startsWith("chrome-extension://")) {
    headers["access-control-allow-origin"] = origin;
  }

  return headers;
}

function sendJson(response, statusCode, payload, request) {
  response.writeHead(statusCode, jsonHeadersForRequest(request));
  response.end(JSON.stringify(payload));
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";

    request.on("data", (chunk) => {
      body += chunk;

      if (body.length > 1_000_000) {
        request.destroy();
        reject(new Error("Request body is too large."));
      }
    });

    request.on("end", () => {
      if (!body) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(new Error("Request body must be valid JSON."));
      }
    });

    request.on("error", reject);
  });
}

function compactMemory(memory) {
  const safeMemory = memoryApi.ensureMemory(memory);
  const now = new Date();

  return {
    confirmedAnswers: safeMemory.answers
      .filter((answer) => !memoryApi.isExpired(answer.expiresAt, now))
      .slice(0, 40)
      .map((answer) => ({
        source: "confirmed-answer",
        questionText: answer.questionText,
        questionKey: answer.questionKey || "",
        answer: answer.answer,
        updatedAt: answer.updatedAt || answer.createdAt || null,
        expiresAt: answer.expiresAt || null
      })),
    profileFacts: safeMemory.profileFacts
      .filter((fact) => !memoryApi.isExpired(fact.expiresAt, now))
      .slice(0, 80)
      .map((fact) => ({
        source: "profile-fact",
        label: fact.label,
        questionPattern: fact.questionPattern,
        answer: fact.answer,
        updatedAt: fact.updatedAt || fact.createdAt || null,
        expiresAt: fact.expiresAt || null
      }))
  };
}

function compactQuestions(questions) {
  return (Array.isArray(questions) ? questions : []).slice(0, 60).map((question) => ({
    id: String(question.id || ""),
    text: String(question.text || ""),
    kind: String(question.kind || "unknown"),
    options: (Array.isArray(question.options) ? question.options : []).map((option) => ({
      label: String(option.label || ""),
      value: String(option.value || option.label || "")
    }))
  }));
}

function buildPrompt(payload) {
  const questions = compactQuestions(payload.questions);
  const memory = compactMemory(payload.memory);

  return [
    "Return JSON in this shape:",
    '{"suggestions":[{"questionId":"...","answer":{"label":"...","value":"...","text":"..."},"confidence":"low|medium|high","reason":"...","source":"llm"}]}',
    "Use answer null when memory does not support a safe suggestion.",
    "Confirmed answers are prior user-approved answers for specific question text and option sets.",
    "Profile facts are reusable user profile facts; use them only when the question asks for the same fact.",
    "Prefer exact confirmed-answer support over broader profile facts.",
    "Mention the supporting memory source briefly in each reason.",
    "Visible questions:",
    JSON.stringify(questions, null, 2),
    "Saved memory:",
    JSON.stringify(memory, null, 2)
  ].join("\n");
}

function parseJsonFromModel(content) {
  const text = String(content || "").trim();

  if (!text) {
    throw new Error("LLM returned an empty response.");
  }

  try {
    return JSON.parse(text);
  } catch (_error) {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");

    if (start >= 0 && end > start) {
      return JSON.parse(text.slice(start, end + 1));
    }

    throw new Error("LLM response was not valid JSON.");
  }
}

function optionMatchesAnswer(option, answer) {
  const optionLabel = normalize.normalizeText(option && option.label);
  const optionValue = normalize.normalizeText(option && option.value);
  const answerLabel = normalize.normalizeText(answer && answer.label);
  const answerValue = normalize.normalizeText(answer && answer.value);
  const answerText = normalize.normalizeText(answer && answer.text);
  const candidates = [answerLabel, answerValue, answerText].filter(Boolean);

  return candidates.some((candidate) => {
    return (
      candidate === optionLabel ||
      candidate === optionValue ||
      (optionLabel && optionLabel.includes(candidate)) ||
      (candidate && candidate.includes(optionLabel))
    );
  });
}

function answerMatchesAnswer(left, right) {
  const leftAnswer = memoryApi.normalizeAnswer(left);
  const rightAnswer = memoryApi.normalizeAnswer(right);
  const leftCandidates = [leftAnswer.label, leftAnswer.value, leftAnswer.text]
    .map(normalize.normalizeText)
    .filter(Boolean);
  const rightCandidates = [rightAnswer.label, rightAnswer.value, rightAnswer.text]
    .map(normalize.normalizeText)
    .filter(Boolean);

  return leftCandidates.some((leftCandidate) => {
    return rightCandidates.some((rightCandidate) => {
      return leftCandidate === rightCandidate;
    });
  });
}

function answerIsSupportedByMemory(question, answer, memory) {
  const safeMemory = memoryApi.ensureMemory(memory);
  const questionText = question && question.text ? question.text : "";
  const questionKey =
    (question && question.questionKey) ||
    normalize.makeQuestionKey(questionText, question && question.options);
  const now = new Date();
  const confirmedAnswer = safeMemory.answers.find((record) => {
    if (record.questionKey !== questionKey || memoryApi.isExpired(record.expiresAt, now)) {
      return false;
    }

    const supportedAnswer = memoryApi.findMatchingOption(question, record.answer);
    return supportedAnswer && answerMatchesAnswer(supportedAnswer, answer);
  });

  if (confirmedAnswer) {
    return true;
  }

  return safeMemory.profileFacts.some((fact) => {
    if (
      memoryApi.isExpired(fact.expiresAt, now) ||
      !memoryApi.patternMatchesQuestion(fact.questionPattern, questionText)
    ) {
      return false;
    }

    const supportedAnswer = memoryApi.findMatchingOption(question, fact.answer);
    return supportedAnswer && answerMatchesAnswer(supportedAnswer, answer);
  });
}

function unsupportedMemorySuggestion(questionId) {
  return {
    questionId,
    answer: null,
    confidence: "low",
    reason: "LLM suggested an answer that was not supported by saved memory.",
    source: "llm"
  };
}

function normalizeLlmSuggestion(rawSuggestion, questionsById, memory) {
  const questionId = String(rawSuggestion && rawSuggestion.questionId ? rawSuggestion.questionId : "");
  const question = questionsById.get(questionId);

  if (!question) {
    return null;
  }

  const reason = String(rawSuggestion.reason || "Suggested by local LLM helper.").slice(0, 300);
  const confidence = ["low", "medium", "high"].includes(rawSuggestion.confidence)
    ? rawSuggestion.confidence
    : "low";

  if (!rawSuggestion.answer) {
    return {
      questionId,
      answer: null,
      confidence,
      reason,
      source: "llm"
    };
  }

  const answer = memoryApi.normalizeAnswer(rawSuggestion.answer);

  if (question.options.length > 0) {
    const option = question.options.find((candidate) => optionMatchesAnswer(candidate, answer));

    if (!option) {
      return {
        questionId,
        answer: null,
        confidence: "low",
        reason: "LLM suggested an answer that was not one of the visible options.",
        source: "llm"
      };
    }

    const selectedAnswer = {
      label: option.label,
      value: option.value,
      text: option.label
    };

    if (!answerIsSupportedByMemory(question, selectedAnswer, memory)) {
      return unsupportedMemorySuggestion(questionId);
    }

    return {
      questionId,
      answer: selectedAnswer,
      confidence,
      reason,
      source: "llm"
    };
  }

  if (!(answer.label || answer.value || answer.text)) {
    return {
      questionId,
      answer: null,
      confidence: "low",
      reason,
      source: "llm"
    };
  }

  const selectedAnswer = {
    label: answer.label || answer.text || answer.value,
    value: answer.value || answer.label || answer.text,
    text: answer.text || answer.label || answer.value
  };

  if (!answerIsSupportedByMemory(question, selectedAnswer, memory)) {
    return unsupportedMemorySuggestion(questionId);
  }

  return {
    questionId,
    answer: selectedAnswer,
    confidence,
    reason,
    source: "llm"
  };
}

function validateSuggestions(payload, modelResponse) {
  const questions = compactQuestions(payload.questions);
  const questionsById = new Map(questions.map((question) => [question.id, question]));
  const suggestions = Array.isArray(modelResponse && modelResponse.suggestions)
    ? modelResponse.suggestions
    : [];

  return suggestions
    .map((suggestion) => normalizeLlmSuggestion(suggestion, questionsById, payload.memory))
    .filter(Boolean);
}

async function callOllama(config, prompt) {
  const response = await fetch(`${config.ollamaBaseUrl.replace(/\/$/, "")}/api/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      model: config.ollamaModel,
      stream: false,
      format: "json",
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: prompt }
      ],
      options: {
        temperature: 0.1
      }
    })
  });

  if (!response.ok) {
    throw new Error(`Ollama request failed with HTTP ${response.status}.`);
  }

  const body = await response.json();
  return parseJsonFromModel(body.message && body.message.content);
}

async function callOpenAi(config, prompt) {
  if (!config.openaiApiKey) {
    throw new Error("OPENAI_API_KEY is required when LLM_PROVIDER=openai.");
  }

  const response = await fetch(`${config.openaiBaseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${config.openaiApiKey}`,
      "content-type": "application/json"
    },
    body: JSON.stringify({
      model: config.openaiModel,
      temperature: 0.1,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: prompt }
      ]
    })
  });

  if (!response.ok) {
    throw new Error(`OpenAI request failed with HTTP ${response.status}.`);
  }

  const body = await response.json();
  const content =
    body.choices &&
    body.choices[0] &&
    body.choices[0].message &&
    body.choices[0].message.content;
  return parseJsonFromModel(content);
}

async function runLlm(config, payload) {
  const prompt = buildPrompt(payload);

  if (config.provider === "ollama") {
    return callOllama(config, prompt);
  }

  if (config.provider === "openai") {
    return callOpenAi(config, prompt);
  }

  throw new Error(`Unsupported LLM_PROVIDER: ${config.provider}`);
}

async function handleSuggest(config, request, response) {
  const payload = await readJson(request);
  const modelResponse = await runLlm(config, payload);
  const suggestions = validateSuggestions(payload, modelResponse);

  sendJson(response, 200, {
    ok: true,
    provider: config.provider,
    suggestions
  }, request);
}

function createServer(config = loadConfig()) {
  return http.createServer(async (request, response) => {
    try {
      if (request.method === "OPTIONS") {
        sendJson(response, 204, {}, request);
        return;
      }

      if (request.method === "GET" && request.url === "/health") {
        sendJson(response, 200, {
          ok: true,
          provider: config.provider,
          model: config.provider === "openai" ? config.openaiModel : config.ollamaModel
        }, request);
        return;
      }

      if (request.method === "POST" && request.url === "/suggest") {
        await handleSuggest(config, request, response);
        return;
      }

      sendJson(response, 404, {
        ok: false,
        error: "Not found"
      }, request);
    } catch (error) {
      sendJson(response, 500, {
        ok: false,
        error: error.message
      }, request);
    }
  });
}

function start() {
  const config = loadConfig();
  const server = createServer(config);

  server.listen(config.port, config.host, () => {
    const model = config.provider === "openai" ? config.openaiModel : config.ollamaModel;
    console.log(
      `Survey Copilot LLM helper listening on http://${config.host}:${config.port} (${config.provider}:${model})`
    );
  });
}

if (require.main === module) {
  start();
}

module.exports = {
  buildPrompt,
  compactMemory,
  compactQuestions,
  createServer,
  loadDotEnv,
  loadConfig,
  normalizeLlmSuggestion,
  parseJsonFromModel,
  validateSuggestions
};
