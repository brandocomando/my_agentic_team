const BACKEND_URL = "http://127.0.0.1:8765";
const ACTION_LABELS = ["continue", "next", "submit", "done"];
const ACTION_TEXT_RE = /\b(continue|next|submit|done)\b/i;
const QUALIFY_TEXT_RE = /\b(check|see|start|take|begin)\b.*\b(qualif|survey|study|questionnaire|available)\b|\b(qualif|survey|study|questionnaire|available)\b.*\b(check|continue|start|take|begin)\b/i;
const CHECK_ALL_DELAY_MS = 900;
const ANSWER_LOOP_DELAY_MS = 900;
const ANSWER_LOOP_MAX_STEPS = 25;
const QUALIFIER_BATCH_MAX_ITEMS = 30;
const DEBUG_PREFIX = "[Survey Copilot]";

function debugLog(message, data = undefined) {
  if (data === undefined) {
    console.log(DEBUG_PREFIX, message);
  } else {
    console.log(DEBUG_PREFIX, message, data);
  }
}

function visible(element) {
  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function querySelectorAllDeep(selector, root = document) {
  const matches = [];
  if (typeof root.querySelectorAll === "function") {
    matches.push(...root.querySelectorAll(selector));
    for (const element of root.querySelectorAll("*")) {
      if (element.shadowRoot) {
        matches.push(...querySelectorAllDeep(selector, element.shadowRoot));
      }
    }
  }
  if (root.shadowRoot) {
    matches.push(...querySelectorAllDeep(selector, root.shadowRoot));
  }
  return matches;
}

function querySelectorDeep(selector, root = document) {
  return querySelectorAllDeep(selector, root)[0] || null;
}

function closestComposed(element, selector) {
  let current = element;
  while (current) {
    if (typeof current.matches === "function" && current.matches(selector)) return current;
    const root = current.getRootNode?.();
    current = current.parentElement || root?.host || null;
  }
  return null;
}

function textContentDeep(root) {
  const parts = [];
  const ownText = root.innerText || root.textContent || "";
  if (ownText.trim()) parts.push(ownText.trim());
  if (typeof root.querySelectorAll === "function") {
    for (const element of root.querySelectorAll("*")) {
      if (element.shadowRoot) {
        const shadowText = textContentDeep(element.shadowRoot);
        if (shadowText) parts.push(shadowText);
      }
    }
  }
  return parts.join("\n");
}

function textFor(element) {
  const id = element.id;
  const label = id ? querySelectorDeep(`label[for="${CSS.escape(id)}"]`, element.getRootNode?.() || document) : null;
  if (label) return label.innerText.trim();
  const wrappingLabel = closestComposed(element, "label");
  if (wrappingLabel) return wrappingLabel.innerText.trim();
  return element.getAttribute("aria-label") || element.value || "";
}

function questionContainer(control) {
  return (
    closestComposed(control, "fieldset") ||
    closestComposed(control, "[role='radiogroup']") ||
    closestComposed(control, "[data-testid*='question' i]") ||
    closestComposed(control, "[class*='question' i]") ||
    closestComposed(control, "form") ||
    closestComposed(control, "main") ||
    document.body
  );
}

function questionText(container) {
  const legend = querySelectorDeep("legend", container);
  if (legend && legend.innerText.trim()) return legend.innerText.trim();

  const heading = querySelectorDeep("h1, h2, h3, [role='heading']", container);
  if (heading && heading.innerText.trim()) return heading.innerText.trim();

  return textContentDeep(container).split("\n").map((line) => line.trim()).filter(Boolean).slice(0, 4).join(" ");
}

function collectQuestions(options = {}) {
  const controls = querySelectorAllDeep("input, select, textarea").filter(visible);
  if (options.logControls !== false) {
    debugLog("visible controls found", controls.map((control) => ({
      tagName: control.tagName,
      type: control.type,
      id: control.id,
      name: control.name,
      value: control.value,
      label: textFor(control),
    })));
  }
  const seen = new Set();
  const questions = [];

  for (const control of controls) {
    if (control.disabled || control.readOnly) continue;
    const container = questionContainer(control);
    if (seen.has(container)) continue;
    seen.add(container);

    const groupedControls = querySelectorAllDeep("input, select, textarea", container).filter(visible);
    const radioControls = groupedControls.filter((item) => item.type === "radio");
    const checkboxControls = groupedControls.filter((item) => item.type === "checkbox");
    const selectControl = groupedControls.find((item) => item.tagName === "SELECT");
    const textControl = groupedControls.find((item) =>
      ["TEXTAREA", "INPUT"].includes(item.tagName) &&
      !["radio", "checkbox", "hidden", "submit", "button"].includes(item.type)
    );

    if (radioControls.length) {
      questions.push({
        container,
        target: radioControls[0],
        input_type: "radio",
        question_text: questionText(container),
        choices: radioControls.map((item) => ({ id: item.id || item.name || null, label: textFor(item), value: item.value || null })),
      });
    } else if (checkboxControls.length) {
      questions.push({
        container,
        target: checkboxControls[0],
        input_type: "checkbox",
        question_text: questionText(container),
        choices: checkboxControls.map((item) => ({ id: item.id || item.name || null, label: textFor(item), value: item.value || null })),
      });
    } else if (selectControl) {
      questions.push({
        container,
        target: selectControl,
        input_type: "select",
        question_text: questionText(container),
        choices: Array.from(selectControl.options).map((item) => ({ id: item.value, label: item.text, value: item.value })),
      });
    } else if (textControl) {
      questions.push({
        container,
        target: textControl,
        input_type: "text",
        question_text: questionText(container),
        choices: [],
      });
    }
  }

  return questions;
}

async function askBackend(question) {
  debugLog("asking backend", {
    question_text: question.question_text,
    input_type: question.input_type,
    choices: question.choices,
  });
  const response = await fetch(`${BACKEND_URL}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question_text: question.question_text,
      input_type: question.input_type,
      choices: question.choices,
    }),
  });
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  const answer = await response.json();
  debugLog("backend answer", answer);
  return answer;
}

async function teachBackend(question, learnedAnswer) {
  debugLog("teaching backend", {
    question_text: question.question_text,
    input_type: question.input_type,
    answer: learnedAnswer.answer,
    choice_ids: learnedAnswer.choice_ids,
  });
  const response = await fetch(`${BACKEND_URL}/learn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question_text: question.question_text,
      input_type: question.input_type,
      choices: question.choices,
      answer: learnedAnswer.answer,
      choice_ids: learnedAnswer.choice_ids,
    }),
  });
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  const result = await response.json();
  debugLog("learned answer", result);
  return result;
}

function applyAnswer(question, answer) {
  if (!answer.answer && !answer.choice_id) {
    debugLog("no answer to apply", { question: question.question_text, answer });
    return false;
  }

  if (question.input_type === "text") {
    question.target.focus();
    question.target.value = answer.answer;
    question.target.dispatchEvent(new Event("input", { bubbles: true }));
    question.target.dispatchEvent(new Event("change", { bubbles: true }));
    debugLog("applied text answer", { answer: answer.answer });
    return true;
  }

  if (question.input_type === "select") {
    question.target.value = answer.choice_id || answer.answer;
    question.target.dispatchEvent(new Event("change", { bubbles: true }));
    debugLog("applied select answer", { answer: answer.answer, choice_id: answer.choice_id });
    return true;
  }

  const requestedChoiceIds = answer.choice_ids && answer.choice_ids.length ? answer.choice_ids : [answer.choice_id];
  const matches = querySelectorAllDeep("input", question.container).filter((item) =>
    requestedChoiceIds.includes(item.id) ||
    requestedChoiceIds.includes(item.name) ||
    requestedChoiceIds.includes(item.value) ||
    textFor(item) === answer.answer
  );
  if (!matches.length) {
    debugLog("could not find matching input", {
      answer,
      available_inputs: querySelectorAllDeep("input", question.container).map((item) => ({
        id: item.id,
        name: item.name,
        value: item.value,
        label: textFor(item),
        type: item.type,
      })),
    });
    return false;
  }
  for (const match of matches) {
    match.click();
  }
  debugLog("applied choice answer", { answer: answer.answer, choice_id: answer.choice_id, choice_ids: answer.choice_ids });
  return true;
}

function selectedAnswer(question) {
  if (question.input_type === "text") {
    const value = question.target.value?.trim();
    return value ? { answer: value, choice_ids: [] } : null;
  }

  if (question.input_type === "select") {
    const selected = Array.from(question.target.options).find((option) => option.selected);
    if (!selected || !selected.value) return null;
    return { answer: selected.text.trim(), choice_ids: [selected.value] };
  }

  const inputs = querySelectorAllDeep("input", question.container);
  const selected = inputs.filter((input) => input.checked);
  if (!selected.length) return null;

  return {
    answer: selected.map((input) => textFor(input) || input.value).filter(Boolean).join(", "),
    choice_ids: selected.map((input) => input.id || input.value || input.name).filter(Boolean),
  };
}

function clickNext(question = null) {
  const scope = activeActionScope(question);
  const buttons = clickableElements(scope);
  const userTestingButtons = question ? userTestingScreenerActionButtons(question) : [];
  for (const button of userTestingButtons) {
    if (!buttons.includes(button)) buttons.push(button);
  }
  debugLog("next candidates", buttons.map((button) => ({
    tagName: button.tagName,
    text: clickableText(button),
    disabled: isDisabled(button),
    testId: button.getAttribute?.("data-testid"),
    ariaLabel: button.getAttribute?.("aria-label"),
  })));
  const next = buttons.find((button) => ACTION_TEXT_RE.test(clickableText(button)) && !isDisabled(button));
  if (next) {
    debugLog("clicking next", {
      tagName: next.tagName,
      text: clickableText(next),
      testId: next.getAttribute?.("data-testid"),
      ariaLabel: next.getAttribute?.("aria-label"),
    });
    return clickElement(next);
  }
  return false;
}

function activeActionScope(question) {
  if (!question) return document;
  if (window.location.hostname === "app.usertesting.com") {
    const screenerQuestion = closestComposed(question.target, ".screener-question");
    if (screenerQuestion) return screenerQuestion;
  }
  return (
    closestComposed(question.target, "form") ||
    closestComposed(question.target, "[data-testid*='screener' i]") ||
    closestComposed(question.target, "[class*='screener' i]") ||
    closestComposed(question.target, "main") ||
    document
  );
}

function userTestingScreenerActionButtons(question) {
  if (window.location.hostname !== "app.usertesting.com") return [];

  const screenerQuestion = closestComposed(question.target, ".screener-question") || document;
  return querySelectorAllDeep(
    ".screener-question__button-container button, .screener-question__button button",
    screenerQuestion
  ).filter((element) => visible(element));
}

function clickableElements(root = document) {
  return querySelectorAllDeep("button, input[type='submit'], input[type='button'], a, [role='button'], tk-button, [data-testid='action-button']", root)
    .filter((element) => visible(element) && !closestComposed(element, "[data-survey-copilot-toolbar='true']"))
    .filter((element) => window.location.hostname !== "app.usertesting.com" || element.getAttribute?.("data-testid") !== "action-button");
}

function clickableText(element) {
  const root = element.getRootNode?.();
  const hostText = root?.host ? root.host.innerText || root.host.textContent || root.host.getAttribute?.("aria-label") : "";
  return (element.innerText || element.textContent || element.value || element.getAttribute("aria-label") || hostText || "").trim();
}

function clickElement(element) {
  const shadowButton = element.shadowRoot?.querySelector("button");
  if (shadowButton && visible(shadowButton) && !isDisabled(shadowButton)) {
    shadowButton.click();
    return true;
  }
  if (isDisabled(element)) return false;
  element.click();
  return true;
}

function isDisabled(element) {
  const shadowButton = element.shadowRoot?.querySelector("button");
  return (
    element.disabled === true ||
    element.getAttribute?.("disabled") !== null ||
    element.getAttribute?.("aria-disabled") === "true" ||
    shadowButton?.disabled === true ||
    shadowButton?.getAttribute?.("aria-disabled") === "true"
  );
}

function safeScrollIntoView(element) {
  if (typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ block: "center", inline: "center" });
    return true;
  }

  debugLog("candidate cannot scroll into view", {
    tagName: element.tagName,
    text: clickableText(element),
    testId: element.getAttribute?.("data-testid"),
  });
  return false;
}

function candidateContainer(element) {
  return (
    closestComposed(element, "tk-card") ||
    closestComposed(element, "article") ||
    closestComposed(element, "section") ||
    closestComposed(element, "[data-testid='invitation-item']") ||
    closestComposed(element, "[role='listitem']") ||
    closestComposed(element, "[class*='card' i]") ||
    closestComposed(element, "[class*='survey' i]") ||
    closestComposed(element, "li") ||
    element.parentElement
  );
}

function findQualificationButtons(clickedElements = new WeakSet()) {
  if (window.location.hostname === "app.usertesting.com") {
    const userTestingButtons = Array.from(
      querySelectorAllDeep("tk-card[data-testid='invitation-item'] tk-button[data-testid='action-button']")
    ).filter((element) => visible(element) && !clickedElements.has(element));
    if (userTestingButtons.length) return userTestingButtons;
  }

  return clickableElements().filter((element) => {
    if (clickedElements.has(element)) return false;
    const label = clickableText(element).toLowerCase();
    if (!["continue", "check if you qualify", "see if you qualify"].includes(label)) return false;

    const container = candidateContainer(element);
    const nearbyText = container ? container.innerText : "";
    return QUALIFY_TEXT_RE.test(nearbyText);
  });
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function pageSignature() {
  const questions = collectQuestions({ logControls: false });
  return questions.map((question) => `${question.input_type}:${question.question_text}:${question.choices.map((choice) => choice.label).join("|")}`).join("||");
}

function questionSignature(question) {
  return `${question.input_type}:${question.question_text}:${question.choices.map((choice) => choice.label).join("|")}`;
}

async function waitForPageChange(previousSignature) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await wait(ANSWER_LOOP_DELAY_MS);
    const currentSignature = pageSignature();
    if (currentSignature && currentSignature !== previousSignature) return true;
    if (!currentSignature && currentSignature !== previousSignature) return true;
  }
  return false;
}

async function waitForQuestionOrInvitationChange(previousSignature = "") {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await wait(ANSWER_LOOP_DELAY_MS);
    const questions = collectQuestions({ logControls: false });
    const signature = pageSignature();
    if (questions.length && signature !== previousSignature) return true;
    if (findQualificationButtons().length) return true;
  }
  return false;
}

async function runCheckAll() {
  checkAllButton.disabled = true;
  checkAllButton.textContent = "Checking...";
  let clicked = 0;
  const clickedElements = new WeakSet();

  try {
    while (true) {
      const candidates = findQualificationButtons(clickedElements);
      checkAllButton.textContent = `Found ${candidates.length}`;
      const next = candidates[0];
      if (!next) break;
      debugLog("qualification candidate", {
        tagName: next.tagName,
        text: clickableText(next),
        testId: next.getAttribute?.("data-testid"),
      });
      safeScrollIntoView(next);
      await wait(150);
      clickedElements.add(next);
      clickElement(next);
      clicked += 1;
      checkAllButton.textContent = `Checked ${clicked}`;
      await wait(CHECK_ALL_DELAY_MS);
    }
    checkAllButton.textContent = clicked ? `Checked ${clicked}` : "None found";
  } catch (error) {
    checkAllButton.textContent = "Check failed";
    console.error("Survey Copilot check-all failed", error);
  } finally {
    window.setTimeout(() => {
      checkAllButton.disabled = false;
      checkAllButton.textContent = "Check All";
    }, 2000);
  }
}

async function answerCurrentQualifier(options = {}) {
  let answered = 0;
  const seenSignatures = new Set();
  const skippedQuestionSignatures = options.skippedQuestionSignatures || new Set();
  const continueOnNeedsInput = options.continueOnNeedsInput === true;

  answerLoop:
  for (let step = 0; step < ANSWER_LOOP_MAX_STEPS; step += 1) {
    const questions = collectQuestions();
    debugLog("collected questions", questions.map((question) => ({
      question_text: question.question_text,
      input_type: question.input_type,
      choices: question.choices,
    })));

    if (!questions.length) {
      return { answered, reason: answered ? "completed" : "no_questions" };
    }

    let attemptedVisibleQuestion = false;

    for (const [index, question] of questions.entries()) {
      const signature = `${index}:${questionSignature(question)}`;
      if (skippedQuestionSignatures.has(signature)) continue;

      attemptedVisibleQuestion = true;
      if (seenSignatures.has(signature)) {
        debugLog("stopping on repeated question signature", signature);
        return { answered, reason: "repeated_question" };
      }
      seenSignatures.add(signature);

      const answer = await askBackend(question);
      if (applyAnswer(question, answer)) {
        answered += 1;
        status.textContent = `${question.input_type}: ${answer.answer || answer.choice_id}`;
      } else {
        status.textContent = `Needs input: ${answer.reason || "no match"}`;
        skippedQuestionSignatures.add(signature);
        if (continueOnNeedsInput) {
          debugLog("skipping unanswered question and continuing", {
            index,
            question_text: question.question_text,
            input_type: question.input_type,
            reason: answer.reason,
          });
          await wait(150);
          continue;
        }
        return { answered, reason: "needs_input" };
      }

      const previousPageSignature = pageSignature();
      await wait(250);
      const clickedNext = clickNext(question);
      if (!clickedNext) {
        return { answered, reason: "no_next" };
      }

      const changed = await waitForPageChange(previousPageSignature);
      if (!changed) {
        debugLog("stopping because page did not change after next", signature);
        return { answered, reason: "no_change" };
      }
      continue answerLoop;
    }

    if (!attemptedVisibleQuestion) {
      return { answered, reason: "all_visible_questions_need_input" };
    }
  }

  return { answered, reason: "max_steps" };
}

async function runUserTestingBatch() {
  let answered = 0;
  let opened = 0;
  const clickedInvitations = new WeakSet();

  for (let item = 0; item < QUALIFIER_BATCH_MAX_ITEMS; item += 1) {
    const currentQuestions = collectQuestions({ logControls: false });
    if (currentQuestions.length) {
      const result = await answerCurrentQualifier({
        continueOnNeedsInput: true,
        skippedQuestionSignatures: new Set(),
      });
      answered += result.answered;
      debugLog("qualifier result", result);
      if (result.reason === "all_visible_questions_need_input") {
        debugLog("all visible questions need input; looking for another qualifier");
      } else if (!["completed", "no_questions"].includes(result.reason)) {
        debugLog("continuing batch after qualifier stop", result);
      }
      await waitForQuestionOrInvitationChange();
    }

    const invitations = findQualificationButtons(clickedInvitations);
    if (!invitations.length) {
      return { answered, opened, reason: "no_invitations" };
    }

    const invitation = invitations[0];
    clickedInvitations.add(invitation);
    safeScrollIntoView(invitation);
    debugLog("opening next qualifier", {
      tagName: invitation.tagName,
      text: clickableText(invitation),
      testId: invitation.getAttribute?.("data-testid"),
    });
    clickElement(invitation);
    opened += 1;
    status.textContent = `Opened ${opened}; answered ${answered}`;
    await waitForQuestionOrInvitationChange(pageSignature());
  }

  return { answered, opened, reason: "max_items" };
}

async function runCopilot() {
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const result = window.location.hostname === "app.usertesting.com"
      ? await runUserTestingBatch()
      : await answerCurrentQualifier();

    status.textContent = `${result.reason}: ${result.answered}`;
    button.textContent = result.answered ? `Answered ${result.answered}` : "No answer";
  } catch (error) {
    button.textContent = "Backend error";
    console.error("Survey Copilot failed", error);
  } finally {
    window.setTimeout(() => {
      button.disabled = false;
      button.textContent = "Run Survey Copilot";
    }, 2000);
  }
}

async function runLearnVisible() {
  learnButton.disabled = true;
  learnButton.textContent = "Learning...";
  try {
    const questions = collectQuestions();
    let learned = 0;
    for (const question of questions) {
      const answer = selectedAnswer(question);
      if (!answer) continue;
      await teachBackend(question, answer);
      learned += 1;
      status.textContent = `Learned ${learned}`;
    }
    learnButton.textContent = learned ? `Learned ${learned}` : "Nothing selected";
  } catch (error) {
    learnButton.textContent = "Learn failed";
    console.error("Survey Copilot learn failed", error);
  } finally {
    window.setTimeout(() => {
      learnButton.disabled = false;
      learnButton.textContent = "Learn Visible";
    }, 2000);
  }
}

const toolbar = document.createElement("div");
toolbar.dataset.surveyCopilotToolbar = "true";
toolbar.style.position = "fixed";
toolbar.style.right = "16px";
toolbar.style.bottom = "16px";
toolbar.style.zIndex = "2147483647";
toolbar.style.display = "flex";
toolbar.style.gap = "8px";
toolbar.style.alignItems = "center";
toolbar.style.maxWidth = "min(560px, calc(100vw - 32px))";

const status = document.createElement("span");
status.textContent = "Idle";
status.style.maxWidth = "220px";
status.style.overflow = "hidden";
status.style.textOverflow = "ellipsis";
status.style.whiteSpace = "nowrap";
status.style.padding = "10px 12px";
status.style.border = "1px solid #bbb";
status.style.borderRadius = "6px";
status.style.background = "#fff";
status.style.color = "#111";
status.style.font = "13px system-ui, sans-serif";

const button = document.createElement("button");
button.textContent = "Run Survey Copilot";
button.type = "button";
button.style.padding = "10px 14px";
button.style.border = "1px solid #333";
button.style.borderRadius = "6px";
button.style.background = "#111";
button.style.color = "#fff";
button.style.font = "13px system-ui, sans-serif";
button.style.cursor = "pointer";
button.addEventListener("click", runCopilot);

const checkAllButton = document.createElement("button");
checkAllButton.textContent = "Check All";
checkAllButton.type = "button";
checkAllButton.style.padding = "10px 14px";
checkAllButton.style.border = "1px solid #333";
checkAllButton.style.borderRadius = "6px";
checkAllButton.style.background = "#fff";
checkAllButton.style.color = "#111";
checkAllButton.style.font = "13px system-ui, sans-serif";
checkAllButton.style.cursor = "pointer";
checkAllButton.addEventListener("click", runCheckAll);

const learnButton = document.createElement("button");
learnButton.textContent = "Learn Visible";
learnButton.type = "button";
learnButton.style.padding = "10px 14px";
learnButton.style.border = "1px solid #333";
learnButton.style.borderRadius = "6px";
learnButton.style.background = "#fff";
learnButton.style.color = "#111";
learnButton.style.font = "13px system-ui, sans-serif";
learnButton.style.cursor = "pointer";
learnButton.addEventListener("click", runLearnVisible);

toolbar.appendChild(checkAllButton);
toolbar.appendChild(button);
toolbar.appendChild(learnButton);
toolbar.appendChild(status);
document.documentElement.appendChild(toolbar);
