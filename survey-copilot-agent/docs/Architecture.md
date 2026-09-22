# Survey Copilot Architecture

## Components

- Chrome extension: a Manifest V3 content script injected only on configured survey dashboard domains.
- Backend: FastAPI service on `127.0.0.1:8765`.
- Memory: SQLite database storing facts and Ollama embedding vectors.
- Laya Decision Engine: sub-35ms System 1 decision engine using typed `choice` and `noul` primitives to resolve multiple-choice and checkbox survey questions before falling back to Ollama.
- Ollama: local embedding provider plus System 2 fallback choice reasoning when deterministic and Laya matching cannot map a confident fact to visible options.
- Answer cache: in-process cache keyed by question, choices, and the top retrieved fact.
- Learning endpoint: stores user-confirmed visible answers as embedded local facts.

## Answer Flow

1. The content script finds visible form controls for the current page state.
2. It groups controls by fieldset, radiogroup, form, main, or body.
3. For each detected question, it posts `question_text`, `input_type`, and choices to `/answer`.
4. The backend embeds the question with Ollama.
5. The backend retrieves the nearest local facts from SQLite.
6. Deterministic answer logic maps facts to text inputs or choices. For example, exact age can be converted into an age-range radio answer.
7. If retrieval is confident but deterministic choice matching fails, the backend first queries **Laya System 1** (`LayaSurveySolver`, ~33ms) over the choices and retrieved fact.
8. If Laya provides an answer meeting `LAYA_MIN_CONFIDENCE`, it is returned immediately with calibrated confidence.
9. If Laya cannot confidently resolve the choices, the backend falls back to local Ollama (System 2) to choose from the provided options.
10. If no fact clears the confidence threshold, or Ollama chooses a label unsupported by the retrieved fact, the backend returns `answer: null`.
11. The content script fills only non-null answers.
12. If the answer was filled, the content script clicks a visible `Continue`, `Next`, `Submit`, or `Done` control. On UserTesting v2 screeners, it also checks the `.screener-question__button-container` footer for the question's `Next` button.
13. It waits for the page question signature to change, then repeats until no question is found, the backend returns `null`, no next button is found, the page does not change, or the max step count is reached.

## Qualification Check Flow

1. The content script finds visible buttons, submit inputs, button inputs, and links.
2. It excludes its own toolbar controls.
3. It keeps only `Continue`, `Check if you qualify`, and `See if you qualify` controls whose nearby card text looks like a survey or qualification prompt.
4. It clicks one candidate, waits briefly, rescans the page, and continues until no unclicked candidates remain.
5. Each element is clicked at most once per run so a stale card cannot loop forever.

## UserTesting Batch Flow

1. `Run Survey Copilot` first checks whether a screener question is already visible.
2. If a question is visible, it answers that screener one question at a time.
3. If the backend returns `null`, that visible question is marked as needing manual input and left untouched.
4. The batch continues with the next visible question or next visible qualification invitation.
5. If a screener completes, closes, disqualifies, or returns to the available-tests list, the extension opens the next visible qualification invitation.
6. The loop continues until no invitation buttons remain or the max qualifier count is reached.

## Local Data

`config/profile.local.json` is the source file for private facts. It is ignored by Git. `POST /profile/load` embeds and stores those facts in `data/memory.sqlite` with `source=profile`.

`POST /learn` stores manually confirmed answers in the same local SQLite memory with `source=learned`. It does not edit `config/profile.local.json`.

`GET /learned` lists only facts created by the learning flow. When retrieval scores tie, `source=profile` facts rank above `source=learned` facts.

`DELETE /learned/{key}` removes only `source=learned` facts. It cannot delete profile-loaded facts.

## Next Work

- Add a popup with backend status and dry-run mode.
- Add a site-specific adapter for PaidViewpoint once real DOM patterns are observed.
- Add a visible activity log for qualification checks.
- Add backend reasoning with Ollama chat for ambiguous survey wording.
- Add a review log that stores only question metadata and never stores private answers by default.
