const assert = require("node:assert/strict");
const test = require("node:test");

const normalize = require("../extension/shared/normalize");
globalThis.SurveyCopilotNormalize = normalize;
const memoryApi = require("../extension/shared/memory");

const NOW = new Date("2026-07-05T12:00:00.000Z");

test("findSuggestion returns a previous confirmed answer", () => {
  const question = {
    text: "What is your age range?",
    questionKey: normalize.makeQuestionKey("What is your age range?"),
    options: [
      { label: "25-34", value: "25-34" },
      { label: "35-44", value: "35-44" }
    ]
  };
  const memory = memoryApi.upsertConfirmedAnswer(
    memoryApi.ensureMemory(),
    question,
    { label: "35-44", value: "35-44" },
    "",
    NOW
  );

  const suggestion = memoryApi.findSuggestion(question, memory, NOW);

  assert.equal(suggestion.kind, "saved-answer");
  assert.equal(suggestion.answer.label, "35-44");
  assert.equal(suggestion.confidence, "high");
});

test("findSuggestion skips expired answers", () => {
  const question = {
    text: "Have you bought groceries in the last 3 days?",
    questionKey: normalize.makeQuestionKey("Have you bought groceries in the last 3 days?"),
    options: [
      { label: "Yes", value: "yes" },
      { label: "No", value: "no" }
    ]
  };
  const memory = memoryApi.upsertConfirmedAnswer(
    memoryApi.ensureMemory(),
    question,
    { label: "Yes", value: "yes" },
    1,
    new Date("2026-07-01T12:00:00.000Z")
  );

  assert.equal(memoryApi.findSuggestion(question, memory, NOW), null);
});

test("findSuggestion uses profile facts when keywords match", () => {
  const question = {
    text: "Which household income range best describes you?",
    questionKey: normalize.makeQuestionKey("Which household income range best describes you?"),
    options: [
      { label: "$50k-$99k", value: "50-99" },
      { label: "$100k-$149k", value: "100-149" }
    ]
  };
  const memory = memoryApi.upsertProfileFact(
    memoryApi.ensureMemory(),
    {
      label: "Income range",
      questionPattern: "household income range",
      answer: "$100k-$149k"
    },
    NOW
  );

  const suggestion = memoryApi.findSuggestion(question, memory, NOW);

  assert.equal(suggestion.kind, "profile-fact");
  assert.equal(suggestion.answer.label, "$100k-$149k");
});

test("upsertConfirmedAnswer replaces previous answer for same question", () => {
  const question = {
    text: "What phone do you use?",
    questionKey: normalize.makeQuestionKey("What phone do you use?"),
    options: [
      { label: "Android", value: "android" },
      { label: "iPhone", value: "iphone" }
    ]
  };
  const first = memoryApi.upsertConfirmedAnswer(
    memoryApi.ensureMemory(),
    question,
    "Android",
    "",
    NOW
  );
  const second = memoryApi.upsertConfirmedAnswer(
    first,
    question,
    "iPhone",
    "",
    new Date("2026-07-05T12:05:00.000Z")
  );

  assert.equal(second.answers.length, 1);
  assert.equal(second.answers[0].answer.label, "iPhone");
});

test("confirmed answer keys include the visible option set", () => {
  const firstQuestion = {
    text: "Which of these is part of your job?",
    options: [
      { label: "Software engineering", value: "software" },
      { label: "Sales", value: "sales" }
    ]
  };
  const secondQuestion = {
    text: "Which of these is part of your job?",
    options: [
      { label: "Accounting", value: "accounting" },
      { label: "Customer support", value: "support" }
    ]
  };
  const firstMemory = memoryApi.upsertConfirmedAnswer(
    memoryApi.ensureMemory(),
    firstQuestion,
    "Software engineering",
    "",
    NOW
  );
  const secondMemory = memoryApi.upsertConfirmedAnswer(
    firstMemory,
    secondQuestion,
    "Accounting",
    "",
    new Date("2026-07-05T12:05:00.000Z")
  );

  assert.equal(secondMemory.answers.length, 2);
  assert.equal(
    memoryApi.findSuggestion(firstQuestion, secondMemory, NOW).answer.label,
    "Software engineering"
  );
  assert.equal(memoryApi.findSuggestion(secondQuestion, secondMemory, NOW).answer.label, "Accounting");
});
