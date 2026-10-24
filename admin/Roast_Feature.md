# Roast Feature

Plan for building the `/roast` skill (see [SKILL (roast).md](SKILL%20(roast).md)) into the Rubric app. Status: proposal, not started.

## Goal

Let the user roast an idea from inside Rubric. A form with four text fields is sent to the Anthropic API, and a verdict (GO / RESHAPE / KILL) comes back and is shown in the app. The user already has an Anthropic API key.

## Calling the skill from the app

`/roast` is a Claude Code skill, so the app can't invoke it through the API. Instead, reimplement it as plain Messages API calls, using the persona prompts from the skill file:

- Five persona calls run in parallel, in threads: Contrarian, Expansionist, Logician, Researcher, Buyer.
- One Judge call then receives the five outputs and returns the verdict in the skill's format.
- The Researcher call uses Anthropic's server-side web search tool. The other four need no tools.
- Each persona returns a one-line stance, 3-5 sharpest points, the one thing the user must hear, and a 1-10 score.

## Form fields

1. The idea, in one or two sentences (prefilled from the idea's description).
2. Who it's for and how it makes money (buyer and price or model).
3. Your edge (skills, audience, assets).
4. Constraints (budget, timeline, time to first dollar).

The four answers are assembled into the single-paragraph brief that is pasted into every persona prompt.

## UI

- A "Roast…" button in the idea editor, next to Settings and SWOT, opening a new `_SubEditor` window ([ui.py:373](../rubric/ui.py#L373)).
- A progress state while the council runs, then a results view: verdict on top, the five persona reports below.
- Save the verdict on the `Idea` (GO / RESHAPE / KILL, the 48-hour test, the five scores). This needs new fields in [storage.py](../rubric/storage.py) and a `SCHEMA_VERSION` bump. The verdict could also appear in the comparison table.

## Constraints and risks

- **No third-party dependencies.** The README promises none, so call the API with `urllib` rather than the `anthropic` SDK (about 40 lines). Revisit if the SDK is preferred.
- **Threading.** Tk freezes on a blocking call. Run the calls on worker threads and return results through `after()`. Keep modal dialogs out of macOS menu callbacks (the Tk menu modal freeze).
- **API key.** Read it from `ANTHROPIC_API_KEY`, with a fallback to a file in the app's data folder. Never store it in `ideas.json`, since that file may be shared. A GUI app launched from Finder doesn't see shell env vars, so a Settings field is probably needed.
- **Cost.** Each roast is six calls, one with web search: roughly a few cents to 30 cents depending on model. Show a confirm before running.
- **Partial failure.** One failed persona should not abort the run. The Judge proceeds with the rest and says which are missing.

## Open decisions

1. **Model.** Default proposal: a mid-tier model for the personas and a stronger one for the Judge.
2. **API key.** Environment variable only, or also editable in the app?
3. **Persistence.** Store the verdict on the idea, or only display it?

## Suggested build order

1. API client (`urllib`) and prompt assembly, with tests.
2. Council orchestration: parallel persona calls, then the Judge, with partial-failure handling.
3. Storage fields and schema bump, with tests.
4. Roast window and the editor button.
5. API key handling and cost confirm.
6. README and CHANGELOG updates.
