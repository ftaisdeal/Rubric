"""Tkinter desktop UI: comparison table and idea editor."""

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from .rubric import CRITERIA, DEFAULT_WEIGHTS, MAX_SCORE, MIN_SCORE
from .scoring import total_score
from .storage import STATUSES, Idea, Storage, StorageError

UNSCORED = 0

# Colors offered to new ideas, cycled in order.
PALETTE = (
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
)
SWATCH_W, SWATCH_H = 10, 12  # color block in the table, about one text line tall

# Fixed column widths of the comparison table, and the frame padding around it.
TREE_COL_W, NAME_W, STATUS_W, TOTAL_W, CRITERION_W = 30, 240, 100, 90, 130
APP_PADDING = 10
TREE_SLACK = 6  # the Treeview's own border


class IdeaEditor(tk.Toplevel):
    """Modal dialog for creating or editing one idea."""

    def __init__(self, parent: tk.Misc, idea: Idea):
        super().__init__(parent)
        self.idea = idea
        self.saved = False
        self.title(idea.name or "New idea")
        width = 720
        height = self.winfo_screenheight()
        x = (self.winfo_screenwidth() - width) // 2
        self.geometry(f"{width}x{height}+{x}+0")
        self.transient(parent)

        self._build_header()
        self._build_criteria()
        self._build_buttons()

        self.grab_set()
        self.name_entry.focus_set()

    def _build_header(self) -> None:
        head = ttk.Frame(self, padding=10)
        head.pack(fill="x")
        head.columnconfigure(1, weight=1)

        ttk.Label(head, text="Name").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=self.idea.name)
        self.name_entry = ttk.Entry(head, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=2)

        ttk.Label(head, text="Status").grid(row=1, column=0, sticky="w")
        self.status_var = tk.StringVar(value=self.idea.status)
        ttk.Combobox(
            head, textvariable=self.status_var, values=STATUSES, state="readonly"
        ).grid(row=1, column=1, sticky="w", padx=6, pady=2)

        ttk.Label(head, text="Color").grid(row=2, column=0, sticky="w")
        self.color = self.idea.color
        color_row = ttk.Frame(head)
        color_row.grid(row=2, column=1, sticky="w", padx=6, pady=2)
        self.swatch = tk.Label(color_row, width=4, relief="solid", borderwidth=1)
        self.swatch.pack(side="left")
        ttk.Button(color_row, text="Choose…", command=self._pick_color).pack(
            side="left", padx=6
        )
        ttk.Button(color_row, text="Clear", command=lambda: self._set_color("")).pack(
            side="left"
        )
        self._set_color(self.color)

        ttk.Label(head, text="Description").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.desc_text = tk.Text(head, height=7, wrap="word")
        self.desc_text.insert("1.0", self.idea.description)
        self.desc_text.grid(row=4, column=0, columnspan=2, sticky="ew", pady=2)

    def _set_color(self, color: str) -> None:
        self.color = color
        self.swatch.config(background=color or self.cget("background"))

    def _pick_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.color or None, parent=self, title="Idea color"
        )
        if hex_color:  # None if the dialog was cancelled
            self._set_color(hex_color.lower())

    def _build_criteria(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        body.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._enable_wheel_scroll(canvas)

        self.weight_vars: dict[str, tk.IntVar] = {}
        self.score_vars: dict[str, tk.IntVar] = {}
        self.reason_texts: dict[str, tk.Text] = {}
        for c in CRITERIA:
            self._build_criterion(body, c)

    def _enable_wheel_scroll(self, canvas: tk.Canvas) -> None:
        """Scroll the criteria with the mouse wheel / trackpad, anywhere in the dialog."""

        def on_wheel(event: tk.Event) -> None:
            w = event.widget
            # A text box that has its own overflow already scrolled itself.
            if isinstance(w, tk.Text) and (w is self.desc_text or w.yview() != (0.0, 1.0)):
                return
            if canvas.yview() == (0.0, 1.0):  # everything fits; nothing to scroll
                return
            if event.num == 4:  # X11 wheel up
                units = -1
            elif event.num == 5:  # X11 wheel down
                units = 1
            elif self.tk.call("tk", "windowingsystem") == "aqua":
                units = -event.delta  # macOS reports small per-tick deltas
            else:
                units = -event.delta // 120
            if units:
                canvas.yview_scroll(units, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(seq, on_wheel)

    def _build_criterion(self, parent: ttk.Frame, c) -> None:
        box = ttk.LabelFrame(parent, text=c.name, padding=8)
        box.pack(fill="x", pady=4)

        var = tk.IntVar(value=self.idea.scores.get(c.id, UNSCORED))
        self.score_vars[c.id] = var

        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Radiobutton(row, text="Unscored", value=UNSCORED, variable=var).pack(
            side="left", padx=(0, 8)
        )
        for n in range(MIN_SCORE, MAX_SCORE + 1):
            ttk.Radiobutton(row, text=str(n), value=n, variable=var).pack(
                side="left", padx=4
            )

        weight = tk.IntVar(
            value=self.idea.weights.get(c.id, DEFAULT_WEIGHTS[c.id])
        )
        self.weight_vars[c.id] = weight
        weight.trace_add("write", lambda *_: self._update_weight_total())
        ttk.Label(row, text="%").pack(side="right")
        ttk.Combobox(
            row, textvariable=weight, values=list(range(101)), width=4,
            state="readonly",
        ).pack(side="right")
        ttk.Label(row, text="Weight").pack(side="right", padx=(0, 4))

        hint = ttk.Label(box, wraplength=620, foreground="gray40")
        hint.pack(fill="x", pady=(4, 2))
        warn = ttk.Label(box, text="Add a reason for this score", foreground="#b45309")

        reason = tk.Text(box, height=2, wrap="word")
        reason.insert("1.0", self.idea.reasons.get(c.id, ""))
        reason.pack(fill="x")
        self.reason_texts[c.id] = reason

        def refresh(*_):
            score = var.get()
            if score == UNSCORED:
                hint.config(text="Not scored yet")
            else:
                hint.config(text=f"{score}: {c.levels[score - MIN_SCORE]}")
            has_reason = bool(reason.get("1.0", "end").strip())
            if score != UNSCORED and not has_reason:
                warn.pack(fill="x", before=reason)
            else:
                warn.pack_forget()

        var.trace_add("write", refresh)
        reason.bind("<KeyRelease>", refresh)
        refresh()

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        self.weight_total = ttk.Label(bar)
        self.weight_total.pack(side="left")
        self._update_weight_total()
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right", padx=6)

    def _weight_sum(self) -> int:
        return sum(v.get() for v in self.weight_vars.values())

    def _update_weight_total(self) -> None:
        total = self._weight_sum()
        self.weight_total.config(
            text=f"Weights total: {total}%",
            foreground="" if total == 100 else "#b91c1c",
        )

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Give the idea a name.", parent=self)
            return
        total = self._weight_sum()
        if total != 100:
            messagebox.showwarning(
                "Weights must total 100%",
                f"The weights currently total {total}%. Adjust them to total 100%.",
                parent=self,
            )
            return
        idea = self.idea
        idea.name = name
        idea.weights = {cid: v.get() for cid, v in self.weight_vars.items()}
        idea.status = self.status_var.get()
        idea.color = self.color
        idea.description = self.desc_text.get("1.0", "end").strip()
        idea.scores = {
            cid: v.get() for cid, v in self.score_vars.items() if v.get() != UNSCORED
        }
        idea.reasons = {
            cid: t.get("1.0", "end").strip()
            for cid, t in self.reason_texts.items()
            if t.get("1.0", "end").strip()
        }
        idea.touch()
        self.saved = True
        self.destroy()


NO_COLOR = "#9ca3af"  # bar color for ideas with no color chosen


class ChartWindow(tk.Toplevel):
    """Horizontal bar chart of each idea's combined total, in the idea's color."""

    ROW_H, BAR_H, LABEL_W, VALUE_W, PAD = 34, 20, 180, 50, 16

    def __init__(self, parent: tk.Misc, ideas: list[Idea]):
        super().__init__(parent)
        self.title("Combined ratings")
        scored = [(i, total_score(i.scores, i.weights)) for i in ideas]
        self.bars = sorted(
            ((i, t) for i, t in scored if t is not None),
            key=lambda b: (-b[1], b[0].name.lower()),
        )
        self.skipped = len(ideas) - len(self.bars)
        height = max(1, len(self.bars)) * self.ROW_H + 2 * self.PAD + 24
        width = 640
        x = (self.winfo_screenwidth() - width) // 2
        self.geometry(f"{width}x{min(height, 700)}+{x}+60")
        self.minsize(360, 120)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="white")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw())

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        if not self.bars:
            c.create_text(
                self.PAD, self.PAD, anchor="nw", fill="gray40",
                text="No fully scored ideas yet.",
            )
            return
        left = self.PAD + self.LABEL_W
        right = max(left + 40, c.winfo_width() - self.PAD - self.VALUE_W)
        for n, (idea, total) in enumerate(self.bars):
            y = self.PAD + n * self.ROW_H + (self.ROW_H - self.BAR_H) // 2
            mid = y + self.BAR_H // 2
            c.create_text(
                left - 8, mid, anchor="e", text=idea.name, fill="black",
                width=self.LABEL_W - 8,
            )
            c.create_rectangle(
                left, y, left + max(1, (right - left) * total / 100), y + self.BAR_H,
                fill=idea.color or NO_COLOR, outline="",
            )
            c.create_text(
                right + 8 + 0, mid, anchor="w", text=f"{total:.1f}", fill="black"
            )
        base = self.PAD + len(self.bars) * self.ROW_H
        c.create_line(left, self.PAD, left, base, fill="gray60")
        if self.skipped:
            c.create_text(
                self.PAD, base + 8, anchor="nw", fill="gray40",
                text=f"{self.skipped} idea(s) not shown: not fully scored.",
            )


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, storage: Storage, ideas: list[Idea]):
        super().__init__(root, padding=APP_PADDING)
        self.storage = storage
        self.ideas = ideas
        self._swatches: dict[str, tk.PhotoImage] = {}  # keeps images alive
        self.pack(fill="both", expand=True)
        self._build()
        self.refresh()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="New idea", command=self.new_idea).pack(side="left")
        self.edit_button = ttk.Button(bar, text="Edit", command=self.edit_selected)
        self.edit_button.pack(side="left", padx=6)
        self.delete_button = ttk.Button(bar, text="Delete", command=self.delete_selected)
        self.delete_button.pack(side="left")
        ttk.Button(bar, text="Chart", command=self.show_chart).pack(side="left", padx=6)

        cols = ("name", "status", "total") + tuple(c.id for c in CRITERIA)
        self.tree = ttk.Treeview(
            self, columns=cols, show="tree headings", selectmode="browse"
        )
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=TREE_COL_W, minwidth=TREE_COL_W, stretch=False)
        self.sort_col, self.sort_desc = "total", True
        self._heading_text = {"name": "Idea", "status": "Status", "total": "Total"}
        self._heading_text.update({c.id: c.name for c in CRITERIA})
        self.tree.column("name", width=NAME_W, minwidth=160)
        self.tree.column("status", width=STATUS_W, anchor="center")
        self.tree.column("total", width=TOTAL_W, anchor="center")
        for c in CRITERIA:
            self.tree.column(c.id, width=CRITERION_W, anchor="center")
        for col in cols:
            self.tree.heading(col, command=lambda col=col: self.sort_by(col))
        self._update_headings()
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())
        self.tree.bind("<Motion>", self._on_hover)
        self.tree.bind("<Leave>", lambda e: self._hide_tip())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_edit_state())

    def _swatch(self, color: str) -> tk.PhotoImage | str:
        """A small solid-color image for the row's leading block ("" if no color)."""
        if not color:
            return ""
        if color not in self._swatches:
            img = tk.PhotoImage(width=SWATCH_W, height=SWATCH_H)
            img.put(color, to=(0, 0, SWATCH_W, SWATCH_H))
            self._swatches[color] = img
        return self._swatches[color]

    def sort_by(self, col: str) -> None:
        """Sort by a column; clicking the active column flips the direction."""
        if col == self.sort_col:
            self.sort_desc = not self.sort_desc
        else:
            # Scores and totals start high-to-low; text columns A-Z.
            self.sort_col, self.sort_desc = col, col not in ("name", "status")
        self._update_headings()
        self.refresh()

    def _update_headings(self) -> None:
        for col, text in self._heading_text.items():
            if col == self.sort_col:
                text += " ▼" if self.sort_desc else " ▲"
            self.tree.heading(col, text=text)

    def refresh(self) -> None:
        def sort_key(idea: Idea):
            if self.sort_col == "name":
                return (False, idea.name.lower(), idea.name.lower())
            if self.sort_col == "status":
                return (False, STATUSES.index(idea.status) if idea.status in STATUSES
                        else len(STATUSES), idea.name.lower())
            if self.sort_col == "total":
                value = total_score(idea.scores, idea.weights)
            else:
                value = idea.scores.get(self.sort_col)
            return (value is None, value or 0, idea.name.lower())

        ideas = sorted(self.ideas, key=sort_key)
        if self.sort_desc:
            # Reverse the order but keep unscored ideas at the bottom.
            scored = [i for i in ideas if not sort_key(i)[0]][::-1]
            ideas = scored + [i for i in ideas if sort_key(i)[0]]

        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for idea in ideas:
            total = total_score(idea.scores, idea.weights)
            row = [
                idea.name,
                idea.status,
                "incomplete" if total is None else f"{total:.1f}",
            ]
            row += [idea.scores.get(c.id, "–") for c in CRITERIA]
            self.tree.insert(
                "", "end", iid=idea.id, image=self._swatch(idea.color), values=row
            )
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self._update_edit_state()

    def fit_columns(self, window_width: int) -> None:
        """Shrink the criterion columns so the table never exceeds the window."""
        fixed = TREE_COL_W + NAME_W + STATUS_W + TOTAL_W
        spare = window_width - 2 * APP_PADDING - TREE_SLACK - fixed
        width = max(60, min(CRITERION_W, spare // len(CRITERIA)))
        for c in CRITERIA:
            self.tree.column(c.id, width=width)

    def _tip_text(self, row_id: str, col_id: str) -> str:
        idea = next((i for i in self.ideas if i.id == row_id), None)
        crit = next((c for c in CRITERIA if c.id == col_id), None)
        if idea is None or crit is None:
            return ""
        score = idea.scores.get(crit.id)
        if score is None:
            return "Not scored yet"
        weight = idea.weights.get(crit.id, DEFAULT_WEIGHTS[crit.id])
        points = weight * (score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)
        parts = [f"{score}: {crit.levels[score - MIN_SCORE]}"]
        reason = idea.reasons.get(crit.id, "").strip()
        if reason:
            parts.append(f"Reason: {reason}")
        parts.append(
            f"Weight: {weight}% (adds {points:.1f} of {weight} points to the total)"
        )
        return "\n\n".join(parts)

    def _on_hover(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        key = (row, col)
        if not row or self.tree.identify_region(event.x, event.y) != "cell":
            self._hide_tip()
            return
        if key == getattr(self, "_tip_key", None):
            self._move_tip(event)
            return
        self._hide_tip()
        # Displayed columns are "#1".."#N"; map back to the column id.
        index = int(col[1:]) - 1
        if index < 0:  # the color block column
            return
        col_id = self.tree.cget("columns")[index]
        text = self._tip_text(row, col_id)
        if not text:
            return
        self._tip_key = key
        tip = self._tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.configure(background="#808080")  # shows through as a 1px border
        tk.Label(
            tip, text=text, justify="left", wraplength=360, background="#e6f3ff",
            foreground="black", padx=6, pady=4,
        ).pack(padx=1, pady=1)
        self._move_tip(event)

    def _move_tip(self, event: tk.Event) -> None:
        tip = getattr(self, "_tip", None)
        if tip is not None:
            tip.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 16}")

    def _hide_tip(self) -> None:
        tip = getattr(self, "_tip", None)
        if tip is not None:
            tip.destroy()
        self._tip = None
        self._tip_key = None

    def _update_edit_state(self) -> None:
        state = ["!disabled"] if self.tree.selection() else ["disabled"]
        self.edit_button.state(state)
        self.delete_button.state(state)

    def _selected(self) -> Idea | None:
        sel = self.tree.selection()
        return next((i for i in self.ideas if i.id == sel[0]), None) if sel else None

    def _persist(self) -> bool:
        try:
            self.storage.save(self.ideas)
        except OSError as e:
            messagebox.showerror("Save failed", f"Couldn't save:\n{e}")
            return False
        return True

    def _edit(self, idea: Idea) -> bool:
        editor = IdeaEditor(self, idea)
        self.wait_window(editor)
        return editor.saved

    def new_idea(self) -> None:
        idea = Idea(name="", color=PALETTE[len(self.ideas) % len(PALETTE)])
        if self._edit(idea):
            self.ideas.append(idea)
            self._persist()
            self.refresh()
            self.tree.selection_set(idea.id)

    def edit_selected(self) -> None:
        idea = self._selected()
        if idea is None:
            return
        # Edit a copy so Cancel can't leave half-applied changes behind.
        working = Idea.from_dict(vars(idea))
        if self._edit(working):
            self.ideas[self.ideas.index(idea)] = working
            self._persist()
            self.refresh()
            self.tree.selection_set(working.id)

    def show_chart(self) -> None:
        ChartWindow(self, self.ideas)

    def delete_selected(self) -> None:
        idea = self._selected()
        if idea is None:
            return
        if not messagebox.askyesno(
            "Delete idea",
            f"Permanently delete “{idea.name}”?\n"
            "(The previous save is kept as a .bak file.)",
        ):
            return
        self.ideas.remove(idea)
        self._persist()
        self.refresh()


def _table_width() -> int:
    """Window width that exactly fits the comparison table at full column widths."""
    cols = TREE_COL_W + NAME_W + STATUS_W + TOTAL_W + CRITERION_W * len(CRITERIA)
    return cols + 2 * APP_PADDING + TREE_SLACK


def _center(root: tk.Tk, width: int, height: int) -> int:
    """Size the window (capped to the screen), centered horizontally near the top.

    Returns the width actually used.
    """
    width = min(width, root.winfo_screenwidth() - 40)
    height = min(height, root.winfo_screenheight() - 80)
    x = (root.winfo_screenwidth() - width) // 2
    y = 60
    root.geometry(f"{width}x{height}+{x}+{y}")
    return width


def main() -> None:
    root = tk.Tk()
    root.title("Business Evaluation Rubric")
    window_width = _center(root, _table_width(), 480)
    storage = Storage()
    try:
        storage.migrate_legacy()
        ideas = storage.load()
    except StorageError as e:
        messagebox.showerror(
            "Can't load ideas",
            f"{e}\n\nThe file was not modified. Fix or move it, then restart.",
        )
        root.destroy()
        raise SystemExit(1)
    app = App(root, storage, ideas)
    app.fit_columns(window_width)
    root.mainloop()
