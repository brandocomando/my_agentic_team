(function surveyCopilotContent() {
  const normalize = globalThis.SurveyCopilotNormalize;
  const CONTROL_SELECTOR = "input, select, textarea";
  const CHOICE_SELECTOR = "[role='radio'], [role='checkbox'], [role='option']";
  const EXTRACTED_CONTROL_SELECTOR = `${CONTROL_SELECTOR}, ${CHOICE_SELECTOR}`;
  const NEXT_CONTROL_SELECTOR = [
    "button",
    "input[type='button']",
    "input[type='submit']",
    "a[href]",
    "[role='button']"
  ].join(",");
  const NEXT_LABELS = new Set([
    "next",
    "next page",
    "continue",
    "continue survey",
    "submit",
    "done",
    "finish"
  ]);
  const SKIPPED_INPUT_TYPES = new Set([
    "button",
    "file",
    "hidden",
    "image",
    "password",
    "reset",
    "submit"
  ]);
  let registry = new Map();
  let groupIds = new WeakMap();
  let groupIdCounter = 0;

  function isVisible(element) {
    if (!element || element.disabled) {
      return false;
    }

    if (element.closest("[hidden], [aria-hidden='true']")) {
      return false;
    }

    const style = window.getComputedStyle(element);

    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number(style.opacity) === 0
    ) {
      return false;
    }

    return element.getClientRects().length > 0;
  }

  function querySelectorAllDeep(selector, root = document) {
    const results = new Set();
    const roots = [root];

    while (roots.length > 0) {
      const currentRoot = roots.shift();

      currentRoot.querySelectorAll(selector).forEach((element) => results.add(element));
      currentRoot.querySelectorAll("*").forEach((element) => {
        if (element.shadowRoot) {
          roots.push(element.shadowRoot);
        }
      });
    }

    return Array.from(results);
  }

  function rootForElement(element) {
    const root = element.getRootNode && element.getRootNode();
    return root && root.querySelector ? root : document;
  }

  function usableControl(control) {
    if (!isVisible(control)) {
      return false;
    }

    if (control.tagName === "INPUT") {
      const type = (control.type || "text").toLowerCase();
      return !SKIPPED_INPUT_TYPES.has(type);
    }

    return true;
  }

  function usableChoiceControl(control) {
    if (!isVisible(control)) {
      return false;
    }

    if (control.getAttribute("aria-disabled") === "true") {
      return false;
    }

    if (control.closest(CONTROL_SELECTOR)) {
      return false;
    }

    return ["radio", "checkbox", "option"].includes(choiceRole(control));
  }

  function textFromElement(element) {
    return normalize.normalizeText(element ? element.innerText || element.textContent : "");
  }

  function visibleText(element) {
    return (element ? element.innerText || element.textContent || "" : "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isOptionText(candidate, optionLabels = []) {
    const normalizedCandidate = normalize.normalizeText(candidate);

    if (!normalizedCandidate) {
      return true;
    }

    return optionLabels.some((label) => {
      const normalizedLabel = normalize.normalizeText(label);
      return normalizedLabel && normalizedCandidate === normalizedLabel;
    });
  }

  function usableQuestionText(candidate, optionLabels = []) {
    const text = String(candidate || "").replace(/\s+/g, " ").trim();

    if (!text || text.length > 300) {
      return "";
    }

    return isOptionText(text, optionLabels) ? "" : text;
  }

  function labelForControl(control) {
    const ariaLabel = control.getAttribute("aria-label");

    if (ariaLabel) {
      return ariaLabel.trim();
    }

    const ariaLabelledBy = control.getAttribute("aria-labelledby");

    if (ariaLabelledBy) {
      const root = rootForElement(control);
      const text = ariaLabelledBy
        .split(/\s+/)
        .map((id) => {
          return root.getElementById ? root.getElementById(id) : document.getElementById(id);
        })
        .filter(Boolean)
        .map((element) => element.innerText || element.textContent || "")
        .join(" ")
        .trim();

      if (text) {
        return text;
      }
    }

    if (control.labels && control.labels.length > 0) {
      const text = Array.from(control.labels)
        .map((label) => label.innerText || label.textContent || "")
        .join(" ")
        .trim();

      if (text) {
        return text;
      }
    }

    if (control.id) {
      const root = rootForElement(control);
      const label = root.querySelector(`label[for="${CSS.escape(control.id)}"]`);

      if (label) {
        return (label.innerText || label.textContent || "").trim();
      }
    }

    if (control.placeholder) {
      return control.placeholder.trim();
    }

    const text = (control.innerText || control.textContent || "").replace(/\s+/g, " ").trim();

    if (text) {
      return text;
    }

    return control.name || control.value || "Answer";
  }

  function optionLabel(control) {
    if (control.tagName === "OPTION") {
      return control.label || control.textContent || control.value;
    }

    const label = labelForControl(control);
    return label || control.value || "Option";
  }

  function nearestQuestionContainer(control) {
    return (
      control.closest("fieldset") ||
      control.closest("[role='radiogroup']") ||
      control.closest("[role='listbox']") ||
      control.closest("[role='group']") ||
      control.closest("[class*='question' i]") ||
      control.closest("[id*='question' i]") ||
      control.closest("li") ||
      control.closest("section") ||
      control.closest("article") ||
      control.closest("div") ||
      control.parentElement
    );
  }

  function questionTextFromContainer(container, controls, optionLabels = []) {
    if (!container) {
      return usableQuestionText(labelForControl(controls[0]), optionLabels);
    }

    const legend = container.querySelector("legend");

    if (legend && textFromElement(legend)) {
      const text = usableQuestionText(visibleText(legend), optionLabels);

      if (text) {
        return text;
      }
    }

    const labelledBy = container.getAttribute("aria-labelledby");

    if (labelledBy) {
      const root = rootForElement(container);
      const text = labelledBy
        .split(/\s+/)
        .map((id) => {
          return root.getElementById ? root.getElementById(id) : document.getElementById(id);
        })
        .filter(Boolean)
        .map((element) => element.innerText || element.textContent || "")
        .join(" ")
        .trim();

      if (text) {
        const usableText = usableQuestionText(text, optionLabels);

        if (usableText) {
          return usableText;
        }
      }
    }

    const heading = container.querySelector("h1, h2, h3, h4, h5, h6, p");

    if (heading && textFromElement(heading)) {
      const text = usableQuestionText(visibleText(heading), optionLabels);

      if (text) {
        return text;
      }
    }

    const previousText = previousTextForContainer(container, optionLabels);

    if (previousText) {
      return previousText;
    }

    const ancestorText = questionTextFromAncestors(container, controls, optionLabels);

    if (ancestorText) {
      return ancestorText;
    }

    const clone = container.cloneNode(true);
    clone
      .querySelectorAll(`${EXTRACTED_CONTROL_SELECTOR}, button, option, svg`)
      .forEach((element) => element.remove());
    const containerText = (clone.innerText || clone.textContent || "")
      .replace(/\s+/g, " ")
      .trim();

    const usableContainerText = usableQuestionText(containerText, optionLabels);

    if (usableContainerText) {
      return usableContainerText;
    }

    return usableQuestionText(labelForControl(controls[0]), optionLabels) || "Question";
  }

  function previousTextForContainer(container, optionLabels = []) {
    let current = container.previousElementSibling;
    let remaining = 3;

    while (current && remaining > 0) {
      if (isVisible(current)) {
        const text = usableQuestionText(visibleText(current), optionLabels);

        if (text) {
          return text;
        }
      }

      current = current.previousElementSibling;
      remaining -= 1;
    }

    return "";
  }

  function questionTextFromAncestors(container, controls, optionLabels = []) {
    let current = container.parentElement;
    let remaining = 4;

    while (current && remaining > 0) {
      const heading = current.querySelector("h1, h2, h3, h4, h5, h6, p, [role='heading']");

      if (heading && !controls.some((control) => control.contains(heading))) {
        const headingText = usableQuestionText(visibleText(heading), optionLabels);

        if (headingText) {
          return headingText;
        }
      }

      const clone = current.cloneNode(true);
      clone
        .querySelectorAll(`${EXTRACTED_CONTROL_SELECTOR}, button, option, svg`)
        .forEach((element) => element.remove());
      const ancestorText = usableQuestionText(visibleText(clone), optionLabels);

      if (ancestorText) {
        return ancestorText;
      }

      current = current.parentElement;
      remaining -= 1;
    }

    return "";
  }

  function choiceRole(control) {
    return String(control.getAttribute("role") || "").toLowerCase();
  }

  function choiceGroupContainer(control) {
    return (
      control.closest("fieldset") ||
      control.closest("[role='radiogroup']") ||
      control.closest("[role='listbox']") ||
      control.closest("[role='group']") ||
      control.closest("[class*='question' i]") ||
      control.closest("[id*='question' i]") ||
      control.parentElement
    );
  }

  function customChoiceKind(control) {
    const role = choiceRole(control);

    if (role === "checkbox") {
      return "multi_choice";
    }

    if (role === "option") {
      const listbox = control.closest("[role='listbox']");
      return listbox && listbox.getAttribute("aria-multiselectable") === "true"
        ? "multi_choice"
        : "single_choice";
    }

    return "single_choice";
  }

  function kindForControls(controls) {
    const first = controls[0];

    if (!first) {
      return "unknown";
    }

    if (first.tagName === "SELECT") {
      return "select";
    }

    if (first.tagName === "TEXTAREA") {
      return "text";
    }

    if (first.tagName === "INPUT") {
      const type = (first.type || "text").toLowerCase();

      if (type === "radio") {
        return "single_choice";
      }

      if (type === "checkbox") {
        return "multi_choice";
      }

      return "text";
    }

    if (choiceRole(first)) {
      return customChoiceKind(first);
    }

    return "unknown";
  }

  function serializableOption(control) {
    const label = optionLabel(control).replace(/\s+/g, " ").trim();

    return {
      label,
      value:
        control.value ||
        control.getAttribute("data-value") ||
        control.getAttribute("aria-label") ||
        label
    };
  }

  function buildQuestion(text, kind, controls, options = []) {
    const cleanText = String(text || "").replace(/\s+/g, " ").trim();
    const fallbackText = cleanText || labelForControl(controls[0]);
    const id = `q-${registry.size + 1}-${normalize.hashText(
      `${fallbackText} ${kind} ${options.map((option) => option.label).join(" ")}`
    )}`;
    const question = {
      id,
      text: fallbackText,
      questionKey: normalize.makeQuestionKey(fallbackText, options),
      kind,
      options: options.map((option) => ({
        label: option.label,
        value: option.value
      }))
    };

    registry.set(id, {
      controls,
      kind,
      options,
      question
    });

    return question;
  }

  function extractSelectQuestion(control) {
    const options = Array.from(control.options)
      .filter((option) => option.value || option.textContent)
      .filter((option) => !option.disabled)
      .map((option) => ({
        ...serializableOption(option),
        control: option
      }));

    return buildQuestion(labelForControl(control), "select", [control], options);
  }

  function extractTextQuestion(control) {
    return buildQuestion(labelForControl(control), "text", [control], []);
  }

  function extractGroupedQuestion(controls) {
    const container = nearestQuestionContainer(controls[0]);
    const kind = kindForControls(controls);
    const options = controls.map((control) => ({
      ...serializableOption(control),
      control
    }));
    const optionLabels = options.map((option) => option.label);

    return buildQuestion(
      questionTextFromContainer(container, controls, optionLabels),
      kind,
      controls,
      options
    );
  }

  function extractCustomChoiceQuestion(controls) {
    const container = choiceGroupContainer(controls[0]);
    const kind = customChoiceKind(controls[0]);
    const options = controls.map((control) => ({
      ...serializableOption(control),
      control
    }));
    const optionLabels = options.map((option) => option.label);

    return buildQuestion(
      questionTextFromContainer(container, controls, optionLabels),
      kind,
      controls,
      options
    );
  }

  function extractFieldsetQuestions(usedControls) {
    return querySelectorAllDeep("fieldset")
      .filter(isVisible)
      .map((fieldset) => {
        const controls = querySelectorAllDeep(CONTROL_SELECTOR, fieldset).filter(usableControl);

        if (controls.length === 0) {
          return null;
        }

        controls.forEach((control) => usedControls.add(control));
        return extractGroupedQuestion(controls);
      })
      .filter(Boolean);
  }

  function extractQuestions() {
    registry = new Map();
    groupIds = new WeakMap();
    groupIdCounter = 0;
    const usedControls = new WeakSet();
    const questions = extractFieldsetQuestions(usedControls);
    const controls = querySelectorAllDeep(CONTROL_SELECTOR).filter(
      (control) => usableControl(control) && !usedControls.has(control)
    );
    const groupedControls = new Map();

    controls.forEach((control) => {
      if (control.tagName === "INPUT") {
        const type = (control.type || "text").toLowerCase();

        if ((type === "radio" || type === "checkbox") && control.name) {
          const formId = control.form ? control.form.id || control.form.name || "form" : "page";
          const key = `${type}:${formId}:${control.name}`;
          const group = groupedControls.get(key) || [];
          group.push(control);
          groupedControls.set(key, group);
          return;
        }
      }

      if (control.tagName === "SELECT") {
        questions.push(extractSelectQuestion(control));
        usedControls.add(control);
        return;
      }

      questions.push(extractTextQuestion(control));
      usedControls.add(control);
    });

    groupedControls.forEach((group) => {
      group.forEach((control) => usedControls.add(control));
      questions.push(extractGroupedQuestion(group));
    });

    extractCustomChoiceQuestions().forEach((question) => {
      questions.push(question);
    });

    return questions.filter((question) => question.text);
  }

  function extractCustomChoiceQuestions() {
    const controls = querySelectorAllDeep(CHOICE_SELECTOR).filter(usableChoiceControl);
    const groupedControls = new Map();

    controls.forEach((control) => {
      const container = choiceGroupContainer(control);
      const role = choiceRole(control);
      const stableKey = container ? `${role}:${groupIdFor(container)}` : `${role}:page`;
      const group = groupedControls.get(stableKey) || [];
      group.push(control);
      groupedControls.set(stableKey, group);
    });

    return Array.from(groupedControls.values())
      .filter((group) => group.length > 0)
      .map(extractCustomChoiceQuestion);
  }

  function scanDiagnostics(questionCount) {
    const nativeControls = querySelectorAllDeep(CONTROL_SELECTOR).filter(usableControl);
    const customChoices = querySelectorAllDeep(CHOICE_SELECTOR).filter(usableChoiceControl);
    const visibleIframes = Array.from(document.querySelectorAll("iframe")).filter(isVisible);
    const openShadowHosts = querySelectorAllDeep("*").filter((element) => element.shadowRoot);

    return {
      questionCount,
      visibleNativeControls: nativeControls.length,
      visibleCustomChoices: customChoices.length,
      visibleIframes: visibleIframes.length,
      openShadowRoots: openShadowHosts.length,
      url: window.location.href
    };
  }

  function groupIdFor(container) {
    if (!groupIds.has(container)) {
      groupIdCounter += 1;
      groupIds.set(container, `scg-${groupIdCounter}`);
    }

    return groupIds.get(container);
  }

  function dispatchValueEvents(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function answerMatchesOption(option, answer) {
    const candidates = [answer.label, answer.value, answer.text]
      .map((value) => normalize.normalizeText(value))
      .filter(Boolean);
    const optionLabel = normalize.normalizeText(option.label);
    const optionValue = normalize.normalizeText(option.value);

    return candidates.some((candidate) => {
      return (
        candidate === optionLabel ||
        candidate === optionValue ||
        (optionLabel && optionLabel.includes(candidate)) ||
        (candidate && candidate.includes(optionLabel))
      );
    });
  }

  function fillSelect(record, answer) {
    const select = record.controls[0];
    const option = record.options.find((candidate) => answerMatchesOption(candidate, answer));

    if (!option) {
      throw new Error("No visible matching option found.");
    }

    select.value = option.control.value;
    dispatchValueEvents(select);
    return option.label;
  }

  function fillChoice(record, answer) {
    const option = record.options.find((candidate) => answerMatchesOption(candidate, answer));

    if (!option || !isVisible(option.control)) {
      throw new Error("No visible matching option found.");
    }

    if (!isOptionSelected(option.control)) {
      option.control.click();
    }

    dispatchValueEvents(option.control);
    return option.label;
  }

  function isOptionSelected(control) {
    if (typeof control.checked === "boolean") {
      return control.checked;
    }

    return (
      control.getAttribute("aria-checked") === "true" ||
      control.getAttribute("aria-selected") === "true"
    );
  }

  function fillText(record, answer) {
    const control = record.controls[0];
    const value = answer.text || answer.label || answer.value;

    if (!value) {
      throw new Error("No text answer provided.");
    }

    control.focus();
    control.value = value;
    dispatchValueEvents(control);
    return value;
  }

  function fillQuestion(questionId, answer) {
    const record = registry.get(questionId);

    if (!record) {
      throw new Error("Question is no longer available. Refresh and try again.");
    }

    if (!record.controls.every(isVisible)) {
      throw new Error("Question is hidden or disabled.");
    }

    if (record.kind === "select") {
      return fillSelect(record, answer);
    }

    if (record.kind === "single_choice" || record.kind === "multi_choice") {
      return fillChoice(record, answer);
    }

    return fillText(record, answer);
  }

  function navigationLabel(control) {
    return (
      control.getAttribute("aria-label") ||
      control.value ||
      control.innerText ||
      control.textContent ||
      control.title ||
      ""
    ).replace(/\s+/g, " ").trim();
  }

  function usableNavigationControl(control) {
    if (!isVisible(control)) {
      return false;
    }

    if (control.disabled || control.getAttribute("aria-disabled") === "true") {
      return false;
    }

    const label = normalize.normalizeText(navigationLabel(control));
    return NEXT_LABELS.has(label);
  }

  function findNextControl() {
    const controls = querySelectorAllDeep(NEXT_CONTROL_SELECTOR).filter(usableNavigationControl);

    return controls.sort((left, right) => {
      const leftRect = left.getBoundingClientRect();
      const rightRect = right.getBoundingClientRect();
      return rightRect.top - leftRect.top || rightRect.left - leftRect.left;
    })[0];
  }

  function goToNextPage() {
    const control = findNextControl();

    if (!control) {
      throw new Error("No visible Next, Continue, Submit, Done, or Finish button found.");
    }

    const label = navigationLabel(control) || "Next";
    control.click();
    return label;
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || !message.type) {
      return false;
    }

    if (message.type === "survey-copilot:scan") {
      try {
        const questions = extractQuestions();
        sendResponse({
          ok: true,
          questions,
          diagnostics: scanDiagnostics(questions.length)
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error.message
        });
      }

      return true;
    }

    if (message.type === "survey-copilot:fill") {
      try {
        const filledLabel = fillQuestion(message.questionId, message.answer || {});
        sendResponse({
          ok: true,
          filledLabel
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error.message
        });
      }

      return true;
    }

    if (message.type === "survey-copilot:next") {
      try {
        const clickedLabel = goToNextPage();
        sendResponse({
          ok: true,
          clickedLabel
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error.message
        });
      }

      return true;
    }

    return false;
  });
})();
