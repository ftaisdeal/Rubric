"""Tkinter desktop UI: comparison table and idea editor."""

import math
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
DELETE_BG = "#f4b6b6"  # pastel red for the editor's Delete button

# Fixed column widths of the comparison table, and the frame padding around it.
NAME_W, STATUS_W, TOTAL_W, CRITERION_W = 160, 100, 90, 130
BAR_W = 100  # the in-table bar chart column
BAR_PAD = 4  # space around each bar inside that column
APP_PADDING = 10
TREE_SLACK = 6  # the Treeview's own border


class IdeaEditor(tk.Toplevel):
    """Modal dialog for creating or editing one idea."""

    def __init__(self, parent: tk.Misc, idea: Idea, can_delete: bool = False):
        super().__init__(parent)
        self.idea = idea
        self.can_delete = can_delete
        self.saved = False
        self.deleted = False
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

        self.weight_vars: dict[str, tk.DoubleVar] = {}
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

        weight = tk.DoubleVar(
            value=self.idea.weights.get(c.id, DEFAULT_WEIGHTS[c.id])
        )
        self.weight_vars[c.id] = weight
        weight.trace_add("write", lambda *_: self._update_weight_total())
        ttk.Label(row, text="%").pack(side="right")
        ttk.Combobox(
            row, textvariable=weight, values=list(range(10, 51, 10)), width=5,
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
        save = ttk.Button(bar, text="Save", command=self._save)
        save.pack(side="left")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="left", padx=6)
        if self.can_delete:
            self._rounded_button(bar, "Delete", self._delete, ref=save).pack(side="left")
        self.weight_total = ttk.Label(bar)
        self.weight_total.pack(side="right")
        self._update_weight_total()

    def _rounded_button(self, parent, text, command, ref) -> tk.Canvas:
        """A rounded, pastel-red button; native buttons ignore colors on macOS."""
        w, h, r = ref.winfo_reqwidth(), ref.winfo_reqheight(), 6
        # Native buttons draw their bezel inset from the widget's frame.
        inset_x, inset_top, inset_bottom = 1, 4, 3
        c = tk.Canvas(
            parent, width=w, height=h, highlightthickness=0,
            background=self.cget("background"), cursor="hand2",
        )
        x0, y0, x1, y1 = inset_x, inset_top, w - inset_x, h - inset_bottom
        # True quarter-circle corners; smoothing a plain polygon rounds too little.
        pts = []
        for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                              (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for step in range(0, 91, 10):
                a = math.radians(start + step)
                pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        c.create_polygon(pts, fill=DELETE_BG, outline="#e39a9a")
        c.create_text(w // 2, h // 2, text=text, fill="#7f1d1d")
        c.bind("<Button-1>", lambda e: command())
        return c

    def _delete(self) -> None:
        if messagebox.askyesno(
            "Delete idea",
            f"Permanently delete “{self.idea.name}”?\n"
            "(The previous save is kept as a .bak file.)",
            parent=self,
        ):
            self.deleted = True
            self.destroy()

    @staticmethod
    def _weight_value(var: tk.DoubleVar) -> float | None:
        """The typed weight, or None if it isn't a number from 0 to 100."""
        try:
            value = var.get()
        except tk.TclError:
            return None
        return value if 0 <= value <= 100 else None

    def _weight_sum(self) -> float:
        return sum(self._weight_value(v) or 0 for v in self.weight_vars.values())

    def _weights_valid(self) -> bool:
        return all(self._weight_value(v) is not None for v in self.weight_vars.values())

    def _update_weight_total(self) -> None:
        total = self._weight_sum()
        self.weight_total.config(
            text=f"Weights total: {total:g}%",
            foreground="" if total == 100 and self._weights_valid() else "#b91c1c",
        )

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Give the idea a name.", parent=self)
            return
        if not self._weights_valid():
            messagebox.showwarning(
                "Invalid weight",
                "Each weight must be a number from 0 to 100.",
                parent=self,
            )
            return
        total = self._weight_sum()
        if total != 100:
            messagebox.showwarning(
                "Weights must total 100%",
                f"The weights currently total {total:g}%. Adjust them to total 100%.",
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


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, storage: Storage, ideas: list[Idea]):
        super().__init__(root, padding=APP_PADDING)
        self.storage = storage
        self.ideas = ideas
        self.pack(fill="both", expand=True)
        self._build()
        self.refresh()

    def _build_menu(self) -> None:
        mod = "Command" if self.tk.call("tk", "windowingsystem") == "aqua" else "Control"
        root = self.winfo_toplevel()
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="New Idea", accelerator=f"{mod}+N", command=self.new_idea
        )
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)
        root.bind(f"<{mod}-n>", lambda e: self.new_idea())

    def _build(self) -> None:
        self._build_menu()

        cols = ("name", "status", "total", "bars") + tuple(c.id for c in CRITERIA)
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings", selectmode="browse"
        )
        self.sort_col, self.sort_desc = "total", True
        self._heading_text = {"name": "Idea", "status": "Status", "total": "Total"}
        self._heading_text.update({c.id: c.name for c in CRITERIA})
        self.tree.column("name", width=NAME_W, minwidth=160)
        self.tree.column("status", width=STATUS_W, anchor="w")
        self.tree.column("total", width=TOTAL_W, anchor="center")
        self.tree.column("bars", width=BAR_W, minwidth=BAR_W, stretch=False)
        for c in CRITERIA:
            self.tree.column(c.id, width=CRITERION_W, anchor="center")
        for col in cols:
            if col != "bars":
                self.tree.heading(col, command=lambda col=col: self.sort_by(col))
        self.tree.heading("bars", text="")
        self._update_headings()
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())
        self.tree.bind("<Motion>", self._on_hover)
        self.tree.bind("<Leave>", lambda e: self._hide_tip())
        self._build_bars()

    def _build_bars(self) -> None:
        """Overlay a canvas on the "bars" column; Treeview cells can't hold graphics."""
        self.bars = tk.Canvas(self.tree, highlightthickness=0, background="white")
        self._bars_pending = False
        style = ttk.Style(self)
        self._row_bg = style.lookup("Treeview", "background") or "white"
        self._sel_bg = style.lookup("Treeview", "background", ["selected"]) or "#0a64d6"
        self.bars.configure(background=self._row_bg)
        for event in ("<Configure>", "<<TreeviewSelect>>", "<MouseWheel>",
                      "<ButtonRelease-1>", "<KeyRelease>"):
            self.tree.bind(event, lambda e: self._schedule_bars(), add=True)
        self.bars.bind("<Enter>", lambda e: self._hide_tip())
        self.bars.bind("<Button-1>", self._bars_click)
        self.bars.bind("<Double-1>", lambda e: self.edit_selected())
        self.bars.bind(
            "<MouseWheel>",
            lambda e: (self.tree.yview_scroll(-1 if e.delta > 0 else 1, "units"),
                       self._schedule_bars()),
        )

    def _bars_click(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y + self.bars.winfo_y())
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)

    def _schedule_bars(self) -> None:
        if not self._bars_pending:
            self._bars_pending = True
            self.after_idle(self._draw_bars)

    def _draw_bars(self) -> None:
        self._bars_pending = False
        rows = [r for r in self.tree.get_children() if self.tree.bbox(r, "bars")]
        if not rows:
            self.bars.place_forget()
            return
        x, top, width, _ = self.tree.bbox(rows[0], "bars")
        _, last_y, _, last_h = self.tree.bbox(rows[-1], "bars")
        self.bars.place(x=x, y=top, width=width, height=last_y + last_h - top)
        c = self.bars
        c.delete("all")
        selected = set(self.tree.selection())
        ideas = {i.id: i for i in self.ideas}
        for row in rows:
            _, y, _, h = self.tree.bbox(row, "bars")
            y -= top
            if row in selected:
                c.create_rectangle(0, y, width, y + h, fill=self._sel_bg, outline="")
            idea = ideas.get(row)
            total = total_score(idea.scores, idea.weights) if idea else None
            if total is None:
                continue
            span = width - 2 * BAR_PAD
            c.create_rectangle(
                BAR_PAD, y + 3, BAR_PAD + max(1, span * total / 100), y + h - 3,
                fill=idea.color or NO_COLOR, outline="",
            )

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
                "",
            ]
            row += [idea.scores.get(c.id, "–") for c in CRITERIA]
            self.tree.insert(
                "", "end", iid=idea.id, values=row
            )
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self._schedule_bars()

    def fit_columns(self, window_width: int) -> None:
        """Shrink the criterion columns so the table never exceeds the window."""
        fixed = NAME_W + STATUS_W + TOTAL_W + BAR_W
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
            f"Weight: {weight:g}% (adds {points:.1f} of {weight:g} points to the total)"
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

    def _edit(self, idea: Idea, can_delete: bool = False) -> IdeaEditor:
        editor = IdeaEditor(self, idea, can_delete)
        self.wait_window(editor)
        return editor

    def new_idea(self) -> None:
        idea = Idea(name="", color=PALETTE[len(self.ideas) % len(PALETTE)])
        if self._edit(idea).saved:
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
        editor = self._edit(working, can_delete=True)
        if editor.deleted:
            self.ideas.remove(idea)
            self._persist()
            self.refresh()
        elif editor.saved:
            self.ideas[self.ideas.index(idea)] = working
            self._persist()
            self.refresh()
            self.tree.selection_set(working.id)


def _table_width() -> int:
    """Window width that exactly fits the comparison table at full column widths."""
    cols = NAME_W + STATUS_W + TOTAL_W + BAR_W + CRITERION_W * len(CRITERIA)
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
