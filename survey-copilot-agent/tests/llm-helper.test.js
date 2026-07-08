const assert = require("node:assert/strict");
const test = require("node:test");

const helper = require("../server/llm-helper");

test("parseJsonFromModel extracts a JSON object from model text", () => {
  const parsed = helper.parseJsonFromModel(
    'Sure. {"suggestions":[{"questionId":"q1","answer":null}]}'
  );

  assert.equal(parsed.suggestions[0].questionId, "q1");
});

test("compactMemory exposes profile facts and confirmed answers to the LLM", () => {
  const memory = {
    answers: [
      {
        questionText: "What is your age range?",
        questionKey: "age-key",
        answer: { label: "35-44", value: "35-44", text: "35-44" },
        updatedAt: "2026-01-01T00:00:00.000Z",
        expiresAt: null
      },
      {
        questionText: "Which store did you visit recently?",
        questionKey: "expired-key",
        answer: { label: "Store A", value: "Store A", text: "Store A" },
        expiresAt: "2000-01-01T00:00:00.000Z"
      }
    ],
    profileFacts: [
      {
        label: "Household income",
        questionPattern: "household income",
        answer: { label: "$100k-$149k", value: "$100k-$149k", text: "$100k-$149k" },
        updatedAt: "2026-01-02T00:00:00.000Z",
        expiresAt: null
      }
    ]
  };

  const compacted = helper.compactMemory(memory);

  assert.equal(compacted.confirmedAnswers.length, 1);
  assert.equal(compacted.confirmedAnswers[0].source, "confirmed-answer");
  assert.equal(compacted.confirmedAnswers[0].questionText, "What is your age range?");
  assert.equal(compacted.profileFacts.length, 1);
  assert.equal(compacted.profileFacts[0].source, "profile-fact");
  assert.equal(compacted.profileFacts[0].label, "Household income");
});

test("buildPrompt tells the LLM how to use confirmed answers and profile facts", () => {
  const prompt = helper.buildPrompt({
    questions: [{ id: "q1", text: "What is your age range?", options: [] }],
    memory: {
      answers: [
        {
          questionText: "What is your age range?",
          answer: { label: "35-44", value: "35-44", text: "35-44" }
        }
      ],
      profileFacts: [
        {
          label: "Income",
          questionPattern: "income",
          answer: { label: "$100k-$149k", value: "$100k-$149k", text: "$100k-$149k" }
        }
      ]
    }
  });

  assert.match(prompt, /Confirmed answers are prior user-approved answers/);
  assert.match(prompt, /Profile facts are reusable user profile facts/);
  assert.match(prompt, /"confirmedAnswers"/);
  assert.match(prompt, /"profileFacts"/);
});

test("validateSuggestions keeps visible option answers supported by memory", () => {
  const payload = {
    questions: [
      {
        id: "q1",
        text: "What is your age range?",
        kind: "single_choice",
        options: [
          { label: "25-34", value: "25-34" },
          { label: "35-44", value: "35-44" }
        ]
      }
    ],
    memory: {
      profileFacts: [
        {
          label: "Age range",
          questionPattern: "age range",
          answer: { label: "35-44", value: "35-44", text: "35-44" }
        }
      ]
    }
  };

  const suggestions = helper.validateSuggestions(payload, {
    suggestions: [
      {
        questionId: "q1",
        answer: { label: "35-44", value: "35-44" },
        confidence: "high",
        reason: "Supported by memory."
      }
    ]
  });

  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0].answer.label, "35-44");
});

test("validateSuggestions nulls visible option answers that conflict with memory", () => {
  const payload = {
    questions: [
      {
        id: "q1",
        text: "What is your age range?",
        kind: "single_choice",
        options: [
          { label: "25-34", value: "25-34" },
          { label: "35-44", value: "35-44" }
        ]
      }
    ],
    memory: {
      profileFacts: [
        {
          label: "Age range",
          questionPattern: "age range",
          answer: { label: "35-44", value: "35-44", text: "35-44" }
        }
      ]
    }
  };

  const suggestions = helper.validateSuggestions(payload, {
    suggestions: [
      {
        questionId: "q1",
        answer: { label: "25-34", value: "25-34" },
        confidence: "high",
        reason: "Model picked the wrong age."
      }
    ]
  });

  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0].answer, null);
  assert.equal(suggestions[0].confidence, "low");
  assert.match(suggestions[0].reason, /not supported by saved memory/);
});

test("validateSuggestions nulls answers that are not visible options", () => {
  const payload = {
    questions: [
      {
        id: "q1",
        text: "What is your age range?",
        kind: "single_choice",
        options: [
          { label: "25-34", value: "25-34" },
          { label: "35-44", value: "35-44" }
        ]
      }
    ],
    memory: {}
  };

  const suggestions = helper.validateSuggestions(payload, {
    suggestions: [
      {
        questionId: "q1",
        answer: { label: "45-54", value: "45-54" },
        confidence: "high",
        reason: "Model guessed."
      }
    ]
  });

  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0].answer, null);
  assert.equal(suggestions[0].confidence, "low");
});
