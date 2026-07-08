(function surveyCopilotPanel() {
  const STORAGE_KEY = "surveyCopilotMemory";
  const SETTINGS_STORAGE_KEY = "surveyCopilotSettings";
  const memoryApi = globalThis.SurveyCopilotMemory;
  const llmClient = globalThis.SurveyCopilotLlmClient;
  let activeTabId = null;
  let activeTabUrl = "";
  let scanDiagnostics = null;
  let questions = [];
  let memory = memoryApi.ensureMemory();
  let settings = llmClient.ensureSettings();
  let llmSuggestions = new Map();

  const elements = {
    answerList: document.getElementById("answer-list"),
    exportMemoryButton: document.getElementById("export-memory-button"),
    factForm: document.getElementById("fact-form"),
    factList: document.getElementById("fact-list"),
    llmStatus: document.getElementById("llm-status"),
    pageStatus: document.getElementById("page-status"),
    questionList: document.getElementById("question-list"),
    refreshButton: document.getElementById("refresh-button"),
    settingsForm: document.getElementById("settings-form"),
    testHelperButton: document.getElementById("test-helper-button")
  };

  function setStatus(message) {
    elements.pageStatus.textContent = message;
  }

  function chromePromise(fn) {
    return new Promise((resolve, reject) => {
      fn((result) => {
        const error = chrome.runtime.lastError;

        if (error) {
          reject(new Error(error.message));
          return;
        }

        resolve(result);
      });
    });
  }

  async function getActiveTab() {
    const tabs = await chromePromise((resolve) => {
      chrome.tabs.query({ active: true, currentWindow: true }, resolve);
    });
    return tabs && tabs[0] ? tabs[0] : null;
  }

  async function loadMemory() {
    const result = await chromePromise((resolve) => {
      chrome.storage.local.get({ [STORAGE_KEY]: memoryApi.ensureMemory() }, resolve);
    });
    memory = memoryApi.ensureMemory(result[STORAGE_KEY]);
  }

  async function loadSettings() {
    const result = await chromePromise((resolve) => {
      chrome.storage.local.get(
        { [SETTINGS_STORAGE_KEY]: llmClient.ensureSettings() },
        resolve
      );
    });
    settings = llmClient.ensureSettings(result[SETTINGS_STORAGE_KEY]);
  }

  async function saveMemory(nextMemory) {
    memory = memoryApi.ensureMemory(nextMemory);
    await chromePromise((resolve) => {
      chrome.storage.local.set({ [STORAGE_KEY]: memory }, resolve);
    });
  }

  async function saveSettings(nextSettings) {
    settings = llmClient.ensureSettings(nextSettings);
    await chromePromise((resolve) => {
      chrome.storage.local.set({ [SETTINGS_STORAGE_KEY]: settings }, resolve);
    });
  }

  async function scanPage() {
    const tab = await getActiveTab();

    if (!tab || !tab.id) {
      activeTabId = null;
      activeTabUrl = "";
      scanDiagnostics = null;
      questions = [];
      setStatus("No active tab");
      return;
    }

    if (!llmClient.isUrlAllowed(tab.url || "", settings)) {
      activeTabId = null;
      activeTabUrl = tab.url || "";
      scanDiagnostics = null;
      questions = [];
      setStatus("Page is not in allowed domains");
      return;
    }

    activeTabId = tab.id;
    activeTabUrl = tab.url || "";

    try {
      const response = await chromePromise((resolve) => {
        chrome.tabs.sendMessage(tab.id, { type: "survey-copilot:scan" }, resolve);
      });

      if (!response || !response.ok) {
        throw new Error((response && response.error) || "Unable to scan this page.");
      }

      questions = response.questions || [];
      scanDiagnostics = response.diagnostics || null;
      setStatus(scanStatusText(questions.length, scanDiagnostics));
    } catch (error) {
      scanDiagnostics = null;
      questions = [];
      setStatus(error.message);
    }
  }

  function scanStatusText(questionCount, diagnostics) {
    if (questionCount > 0) {
      return `${questionCount} visible question${questionCount === 1 ? "" : "s"}`;
    }

    if (!diagnostics) {
      return "No visible questions found";
    }

    return [
      "No visible questions found",
      `native controls: ${diagnostics.visibleNativeControls}`,
      `custom choices: ${diagnostics.visibleCustomChoices}`,
      `iframes: ${diagnostics.visibleIframes}`,
      `shadow roots: ${diagnostics.openShadowRoots}`
    ].join(" | ");
  }

  async function loadLlmSuggestions() {
    llmSuggestions = new Map();

    if (!settings.llmEnabled || questions.length === 0) {
      return;
    }

    try {
      setLlmStatus("Requesting LLM suggestions.");
      const response = await llmClient.suggest(settings, questions, memory);

      if (!response || !response.ok) {
        throw new Error((response && response.error) || "LLM helper returned an error.");
      }

      llmSuggestions = new Map(
        (response.suggestions || []).map((suggestion) => [suggestion.questionId, suggestion])
      );
      setLlmStatus(
        `LLM helper ready (${response.provider || "unknown"}): ${
          llmSuggestions.size
        } suggestion${llmSuggestions.size === 1 ? "" : "s"} received.`
      );
    } catch (error) {
      llmSuggestions = new Map();
      setLlmStatus(`LLM helper unavailable: ${error.message}`);
    }
  }

  function setLlmStatus(message) {
    elements.llmStatus.textContent = message;
  }

  function suggestionForQuestion(question) {
    const deterministicSuggestion = memoryApi.findSuggestion(question, memory);

    if (deterministicSuggestion) {
      return deterministicSuggestion;
    }

    return llmSuggestions.get(question.id) || null;
  }

  function optionMarkup(question, suggestion) {
    if (question.options && question.options.length > 0) {
      const suggestedValue =
        suggestion && suggestion.answer ? suggestion.answer.value || suggestion.answer.label : "";
      const options = [
        '<option value="">Choose answer</option>',
        ...question.options.map((option) => {
          const selected =
            option.value === suggestedValue || option.label === suggestedValue ? "selected" : "";
          return `<option value="${escapeHtml(option.value)}" ${selected}>${escapeHtml(
            option.label
          )}</option>`;
        })
      ].join("");

      return `
        <label>
          Answer
          <select data-answer-for="${escapeHtml(question.id)}">
            ${options}
          </select>
        </label>
      `;
    }

    const suggestedText =
      suggestion && suggestion.answer ? suggestion.answer.text || suggestion.answer.label : "";

    return `
      <label>
        Answer
        <input data-answer-for="${escapeHtml(question.id)}" type="text" value="${escapeHtml(
          suggestedText
        )}">
      </label>
    `;
  }

  function ttlMarkup(questionId) {
    return `
      <label>
        Save for
        <select data-ttl-for="${escapeHtml(questionId)}">
          <option value="">No expiry</option>
          <option value="7">7 days</option>
          <option value="30">30 days</option>
          <option value="90">90 days</option>
        </select>
      </label>
    `;
  }

  function renderQuestions() {
    if (questions.length === 0) {
      elements.questionList.innerHTML =
        '<div class="empty-state">No visible questions found on this page.</div>';
      return;
    }

    elements.questionList.innerHTML = questions
      .map((question) => {
        const suggestion = suggestionForQuestion(question);
        const hasAnswer = suggestion && suggestion.answer;
        const suggestionClass = hasAnswer ? "suggestion" : "suggestion missing";
        const suggestionText = hasAnswer
          ? `Suggested: ${escapeHtml(suggestion.answer.label)}`
          : suggestion
            ? "LLM is unsure"
            : "No saved answer";
        const source =
          suggestion && suggestion.kind ? suggestion.kind : suggestion && suggestion.source;
        const reason = suggestion
          ? `${source ? `${source}: ` : ""}${suggestion.reason}`
          : "Choose an answer to fill and save.";

        return `
          <article class="question" data-question-id="${escapeHtml(question.id)}">
            <div class="question-header">
              <h3>${escapeHtml(question.text)}</h3>
              <span class="kind">${escapeHtml(question.kind)}</span>
            </div>
            <div class="${suggestionClass}">
              <strong>${suggestionText}</strong>
              <p class="meta">${escapeHtml(reason)}</p>
            </div>
            <div class="controls">
              ${optionMarkup(question, suggestion)}
              ${ttlMarkup(question.id)}
              <div class="actions">
                <button class="primary" data-fill="${escapeHtml(question.id)}" type="button">
                  Fill
                </button>
                <button data-refresh-scan type="button">
                  Refresh
                </button>
              </div>
            </div>
          </article>
        `;
      })
      .join("");

    elements.questionList.insertAdjacentHTML(
      "beforeend",
      `
        <div class="next-page-actions">
          <button class="primary" data-next-page type="button">Next Page</button>
        </div>
      `
    );
  }

  function renderMemory() {
    elements.factList.innerHTML =
      memory.profileFacts.length === 0
        ? '<div class="empty-state">No profile facts saved.</div>'
        : memory.profileFacts
            .map((fact) => {
              return `
                <div class="memory-item">
                  <div class="memory-row">
                    <div>
                      <strong>${escapeHtml(fact.label)}</strong>
                      <p class="meta">${escapeHtml(fact.questionPattern)} -> ${escapeHtml(
                        fact.answer.label || fact.answer.text || fact.answer.value
                      )}</p>
                      <p class="meta">${expiryText(fact.expiresAt)}</p>
                    </div>
                    <button class="delete-button" data-delete-fact="${escapeHtml(
                      fact.id
                    )}" type="button">Delete</button>
                  </div>
                </div>
              `;
            })
            .join("");

    elements.answerList.innerHTML =
      memory.answers.length === 0
        ? '<div class="empty-state">No confirmed answers saved.</div>'
        : memory.answers
            .map((answer) => {
              return `
                <div class="memory-item">
                  <div class="memory-row">
                    <div>
                      <strong>${escapeHtml(answer.answer.label || answer.answer.text)}</strong>
                      <p class="meta">${escapeHtml(answer.questionText)}</p>
                      <p class="meta">${expiryText(answer.expiresAt)}</p>
                    </div>
                    <button class="delete-button" data-delete-answer="${escapeHtml(
                      answer.id
                    )}" type="button">Delete</button>
                  </div>
                </div>
              `;
            })
            .join("");
  }

  function renderSettings() {
    elements.settingsForm.elements.llmEnabled.checked = settings.llmEnabled;
    elements.settingsForm.elements.helperUrl.value = settings.helperUrl;
    elements.settingsForm.elements.allowedHosts.value = settings.allowedHosts.join("\n");

    if (!settings.llmEnabled) {
      setLlmStatus(
        "LLM suggestions are off. The extension is using saved answers and local profile facts."
      );
    } else if (!elements.llmStatus.textContent) {
      setLlmStatus(`LLM suggestions enabled. Helper URL: ${settings.helperUrl}`);
    }
  }

  function render() {
    renderQuestions();
    renderMemory();
    renderSettings();
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function expiryText(expiresAt) {
    if (!expiresAt) {
      return "No expiry";
    }

    return `Expires ${new Date(expiresAt).toLocaleDateString()}`;
  }

  function selectedAnswer(question) {
    const control = document.querySelector(`[data-answer-for="${CSS.escape(question.id)}"]`);

    if (!control) {
      return null;
    }

    if (control.tagName === "SELECT") {
      const option = question.options.find((candidate) => candidate.value === control.value);

      if (!option) {
        return null;
      }

      return {
        label: option.label,
        value: option.value,
        text: option.label
      };
    }

    const value = control.value.trim();

    if (!value) {
      return null;
    }

    return {
      label: value,
      value,
      text: value
    };
  }

  async function fillQuestion(questionId) {
    const question = questions.find((candidate) => candidate.id === questionId);

    if (!question || !activeTabId) {
      setStatus("Question is unavailable");
      return;
    }

    if (!llmClient.isUrlAllowed(activeTabUrl, settings)) {
      setStatus("Page is not in allowed domains");
      return;
    }

    const answer = selectedAnswer(question);

    if (!answer) {
      setStatus("Choose an answer first");
      return;
    }

    let response;

    try {
      response = await chromePromise((resolve) => {
        chrome.tabs.sendMessage(
          activeTabId,
          {
            type: "survey-copilot:fill",
            questionId,
            answer
          },
          resolve
        );
      });
    } catch (error) {
      setStatus(error.message);
      return;
    }

    if (!response || !response.ok) {
      setStatus((response && response.error) || "Fill failed");
      return;
    }

    const ttlControl = document.querySelector(`[data-ttl-for="${CSS.escape(questionId)}"]`);
    const ttlDays = ttlControl ? ttlControl.value : "";
    await saveMemory(memoryApi.upsertConfirmedAnswer(memory, question, answer, ttlDays));
    setStatus(`Filled: ${response.filledLabel || answer.label}`);
    render();
  }

  async function goToNextPage() {
    if (!activeTabId) {
      setStatus("Page is unavailable");
      return;
    }

    if (!llmClient.isUrlAllowed(activeTabUrl, settings)) {
      setStatus("Page is not in allowed domains");
      return;
    }

    let response;

    try {
      response = await chromePromise((resolve) => {
        chrome.tabs.sendMessage(
          activeTabId,
          {
            type: "survey-copilot:next"
          },
          resolve
        );
      });
    } catch (error) {
      setStatus(error.message);
      return;
    }

    if (!response || !response.ok) {
      setStatus((response && response.error) || "Next page failed");
      return;
    }

    setStatus(`Clicked: ${response.clickedLabel || "Next"}`);
  }

  async function handleFactSubmit(event) {
    event.preventDefault();
    const form = new FormData(elements.factForm);
    const fact = {
      label: form.get("label"),
      questionPattern: form.get("questionPattern"),
      answer: form.get("answer"),
      ttlDays: form.get("ttlDays")
    };

    try {
      await saveMemory(memoryApi.upsertProfileFact(memory, fact));
      elements.factForm.reset();
      setStatus("Saved profile fact");
      render();
    } catch (error) {
      setStatus(error.message);
    }
  }

  function settingsFromForm() {
    const form = new FormData(elements.settingsForm);

    return llmClient.ensureSettings({
      allowedHosts: form.get("allowedHosts"),
      llmEnabled: form.get("llmEnabled") === "on",
      helperUrl: form.get("helperUrl")
    });
  }

  async function handleSettingsSubmit(event) {
    event.preventDefault();
    await saveSettings(settingsFromForm());
    setLlmStatus(`Saved settings. LLM suggestions are ${settings.llmEnabled ? "on" : "off"}.`);
    await refresh();
  }

  async function testHelper() {
    const nextSettings = settingsFromForm();
    elements.testHelperButton.disabled = true;
    setLlmStatus("Testing helper connection.");

    try {
      const health = await llmClient.helperHealth(nextSettings);
      setLlmStatus(
        `Helper connected (${health.provider || "unknown"}:${health.model || "unknown"}).`
      );
    } catch (error) {
      setLlmStatus(`Helper test failed: ${error.message}`);
    }

    elements.testHelperButton.disabled = false;
  }

  async function deleteItem(collectionName, id) {
    await saveMemory(memoryApi.deleteMemoryItem(memory, collectionName, id));
    setStatus("Deleted memory item");
    render();
  }

  async function exportMemory() {
    await loadMemory();

    const exportedAt = new Date().toISOString();
    const payload = {
      exportedAt,
      storageKey: STORAGE_KEY,
      schemaVersion: 1,
      memory
    };
    const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const dateStamp = exportedAt.slice(0, 10);

    link.href = url;
    link.download = `survey-copilot-memory-${dateStamp}.json`;
    link.rel = "noopener";
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus("Exported memory JSON");
  }

  async function refresh() {
    elements.refreshButton.disabled = true;
    setStatus("Scanning page");
    await loadMemory();
    await loadSettings();
    await scanPage();
    render();
    await loadLlmSuggestions();
    render();
    elements.refreshButton.disabled = false;
  }

  document.addEventListener("click", async (event) => {
    const tabButton = event.target.closest("[data-tab]");

    if (tabButton) {
      const tabName = tabButton.dataset.tab;
      document.querySelectorAll(".tab").forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === tabName);
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `${tabName}-tab`);
      });
      return;
    }

    const fillButton = event.target.closest("[data-fill]");

    if (fillButton) {
      await fillQuestion(fillButton.dataset.fill);
      return;
    }

    const refreshButton = event.target.closest("[data-refresh-scan]");

    if (refreshButton) {
      await refresh();
      return;
    }

    const nextPageButton = event.target.closest("[data-next-page]");

    if (nextPageButton) {
      await goToNextPage();
      return;
    }

    const deleteFactButton = event.target.closest("[data-delete-fact]");

    if (deleteFactButton) {
      await deleteItem("profileFacts", deleteFactButton.dataset.deleteFact);
      return;
    }

    const deleteAnswerButton = event.target.closest("[data-delete-answer]");

    if (deleteAnswerButton) {
      await deleteItem("answers", deleteAnswerButton.dataset.deleteAnswer);
    }
  });

  elements.factForm.addEventListener("submit", handleFactSubmit);
  elements.exportMemoryButton.addEventListener("click", exportMemory);
  elements.settingsForm.addEventListener("submit", handleSettingsSubmit);
  elements.refreshButton.addEventListener("click", refresh);
  elements.testHelperButton.addEventListener("click", testHelper);
  refresh();
})();
