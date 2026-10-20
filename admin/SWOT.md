# SWOT: design notes

Status: ideas only, nothing built yet.

## Purpose

Add SWOT (strengths, weaknesses, opportunities, threats) to each idea as
discursive notes: food for thought and reminders about aspects of the idea.

## Decisions so far

1. **Not part of scoring.** SWOT never feeds the weighted total. It is
   descriptive only, and it would double-count factors already scored.
2. **Entered in the idea editor.** Both "New Idea" and "Edit" get two tabs,
   **Rubric** and **SWOT**, and the user can switch back and forth freely.
3. **Stored in `ideas.json`.** Four free-text string fields per idea
   (strengths, weaknesses, opportunities, threats). Old files load with empty
   defaults, so the schema version probably doesn't need to change.
4. **Shown in the main display** as a small cell labeled "SWOT" in each row.
   Hovering it opens a potentially large tooltip with the SWOT text.

## Editor layout

- Use a `ttk.Notebook` in `IdeaEditor`.
- Name, status, color and description stay above the tabs, since they apply to
  the whole idea.
- Save, Cancel and Delete stay below the tabs and apply to both. Switching tabs
  must not lose edits (a Notebook keeps both tabs' widgets alive).
- Rubric is the default tab. Optionally, open on SWOT when the user came from
  the SWOT cell.
- The entry and editing form for SWOT should be the four entries stacked.
- Optional: mark the tab label ("SWOT •") when it has content.

## Main table cell and tooltip

- `ttk.Treeview` has no per-cell tooltips. Bind mouse motion on the tree, use
  `identify_row` / `identify_column`, and show a `Toplevel` tooltip when the
  pointer is over the "swot" column.
- Fixed column width of roughly 50-60px, like the bars column.
- Show the label only for ideas that have SWOT text, so an empty cell means no
  notes.
- The tooltip needs text wrapping and a maximum size, and must hide on leave,
  on scroll, and when a dialog opens.
- Cost: one more column on a table that was recently narrowed.

## Possible later ideas

- Compare the SWOT of the top two or three ideas side by side.
- Opportunities and threats are external factors the criteria likely don't
  capture; strengths and weaknesses largely overlap with the scoring reasons.
