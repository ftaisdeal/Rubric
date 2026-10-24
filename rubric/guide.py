"""The text of the user guide (Guide menu).

Lines starting "# ", "## " and "### " are headings; everything else is plain text. The
criteria section is generated from rubric.py, so it follows any edits to the rubric.
"""

from .rubric import CRITERIA, MAX_SCORE, MIN_SCORE

_INTRO = """\
# Rubric User Guide

Rubric helps you compare business ideas fairly. You describe each idea, score it from 1 to 5 on eight criteria, explain your scores, and Rubric ranks the ideas by a weighted total so you can see them side by side.

## Getting started

1. Choose File > New Idea (Command+N).
2. In the Settings display, type a name, pick a status and a color if you like, and fill in the four description boxes. Click Save.
3. The rubric display opens next. Score the idea on each criterion, then click Save.
4. The idea appears in the main window, ranked with your other ideas.

## The main window

The main window is a table with one row per idea. The columns are the idea's name, its status, its total score, a small bar chart of the total, and one column for each criterion.

- Total: a score from 0 to 100. It reads "incomplete" until the idea has a score for every criterion.
- The bar beside the total shows the same score as a bar in the idea's color, which makes ideas easy to compare at a glance.
- A dash (–) in a criterion column means that criterion has not been scored yet.
- Click a column heading to sort by it. Click it again to reverse the order. Totals and scores sort from highest to lowest first; names and statuses sort A to Z.
- Hover over an idea's name to read its description. Hover over a score to see what that score means, the reason you gave for it, and how much it adds to the total.
- Double-click a row, or select it and press Return, to edit that idea.

## The three displays for an idea

Each idea is edited in three displays. Use the buttons in the top right corner of each one to move between them.

### Settings

This is where an idea starts. It holds the idea's name, its status (considering, pursuing or dropped), its color, and a four-part description: the idea itself, who it is for and how it makes money, your edge (the skills, audience or assets you bring), and your constraints (budget, timeline, how soon you need the first dollar). Only the name is required. The color is used for the idea's bar in the main window. Click the color swatch to choose a color, or click the small × beside it to clear the color.

An idea must have a name. Click Save to store these details.

### Rubric

This is the scoring display. Each criterion has its own box with a row of choices, Unscored and 1 to 5. As you pick a score, the meaning of that score appears beside the choices. Under that is a box where you can write your reason for the score. Reasons are optional, but they are the most useful thing to look back on later, so Rubric reminds you when a scored criterion has none.

Each criterion also has a weight, in percent, shown at the right of its row. See "Weights" below.

Click Save to store your scores, reasons and weights. Click Cancel to close without keeping changes made in this display. Delete, which appears when you are editing an existing idea, permanently removes the idea after asking you to confirm.

### SWOT

Four boxes for your own notes: Strengths, Weaknesses, Opportunities and Threats. They are free text and are not part of the score. Use them for anything the criteria do not capture.

## Saving

The Settings and SWOT displays each have their own Save button, and it stores that display's information immediately. You do not need to save again in the Rubric display.

The Rubric display's Save stores scores, reasons and weights. Moving between displays with the buttons at the top does not save anything by itself, except that a name, status and color you have typed in the Settings display are kept for the moment while you move on to the Rubric display. Click Save in the Rubric display or in the Settings display to make them permanent.

If you close the Settings display on a brand new idea without saving, the idea is not created.

## Scoring

Every criterion is scored from 1 to 5. A 1 is the worst case for that criterion and a 5 is the best, so a higher score always means a better idea. The list at the end of this guide describes what 1 and 5 mean for each criterion; the Rubric display shows what every score from 1 to 5 means.

The total is a weighted average on a scale of 0 to 100. If every criterion scores 1, the total is 0. If every criterion scores 5, the total is 100.

## Weights

Each criterion has a weight, which says how much it counts toward the total. By default, all eight criteria count equally, at 12.5% each.

You can change the weights for any idea in the Rubric display. Choose a weight from the list, or type your own. The eight weights must total exactly 100%. The "Weights total" figure at the bottom of the display turns red when they do not, and Rubric will not save until they add up.

Changing the weights for one idea does not affect any other idea.

## Keyboard shortcuts

- Command+N: New Idea
- Command+W: close the active window (it does nothing in the main window; use Command+Q to quit Rubric)
- Return: edit the selected idea in the main window

## Your data

Rubric keeps all of your ideas in a single file, ideas.json. On a Mac it is in your Library folder, at Library/Application Support/Rubric. Each time you save, the previous version is kept beside it as ideas.json.bak, so a mistake can be undone by restoring that file.

## The criteria
"""


def guide_text() -> str:
    parts = [_INTRO]
    for c in CRITERIA:
        low, high = c.levels[0], c.levels[MAX_SCORE - MIN_SCORE]
        parts.append(
            f"### {c.name}\n"
            f"{MIN_SCORE}: {low}.\n"
            f"{MAX_SCORE}: {high}.\n"
        )
    return "\n".join(parts)
