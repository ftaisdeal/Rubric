"""Tkinter desktop UI: comparison table and idea editor."""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, font as tkfont, messagebox, ttk

from . import apikey, roast
from .guide import guide_text
from .rubric import CRITERIA, DEFAULT_WEIGHTS, MAX_SCORE, MIN_SCORE
from .scoring import total_score
from .storage import DESCRIPTION_FIELDS, STATUSES, SWOT_FIELDS, Idea, Storage, StorageError

UNSCORED = 0

# Editor background; lighter than the aspect boxes so they stand out.
PAGE_BG = "#f8f8f8"
FOCUS_RING = "#a9c4e8"  # light blue ring around a focused SWOT text box
TIP_BG = "#f3f9ff"  # background of every tooltip: a very light blue
DESCRIPTION_TIP_W = 600  # wrap width of the description tooltip over an idea name
BORDER = "#cfcfcf"  # 1px outline of the aspect boxes and the description text

# Colors offered to new ideas, cycled in order.
PALETTE = (
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
)
DELETE_FG = "#e57f7f"  # pastel red text for the editor's Delete button

# Fixed column widths of the comparison table, and the frame padding around it.
NAME_W, STATUS_W, VERDICT_W, TOTAL_W, CRITERION_W = 160, 95, 90, 80, 115
BAR_W = 100  # the in-table bar chart column
BAR_PAD = 4  # space around each bar inside that column
APP_PADDING = 10
TREE_SLACK = 6  # the Treeview's own border


_bold = None


def _bold_font() -> tkfont.Font:
    """The default font in bold (created once; Tk drops fonts nobody references)."""
    global _bold
    if _bold is None:
        _bold = tkfont.nametofont("TkDefaultFont").copy()
        _bold.configure(weight="bold")
    return _bold


def _titled_box(parent: tk.Misc, title: str) -> tuple[tk.Frame, ttk.Frame]:
    """A 1px-outlined box with a bold heading; returns (outline, inner frame).

    The caller packs or grids the outline and fills the inner frame.
    """
    outline = tk.Frame(parent, background=BORDER)
    box = ttk.Frame(outline, padding=8)
    box.pack(fill="both", expand=True, padx=1, pady=1)
    ttk.Label(box, text=title, font=_bold_font()).pack(anchor="w", pady=(0, 4))
    return outline, box


def _text_boxes(
    body: tk.Frame, values: dict[str, str], fields, titles: dict[str, str],
    first_row: int = 0,
) -> dict[str, tk.Text]:
    """One titled, equal-height text box per field, stacked down `body`."""
    body.columnconfigure(0, weight=1)
    texts: dict[str, tk.Text] = {}
    for row, field in enumerate(fields, start=first_row):
        body.rowconfigure(row, weight=1, uniform="boxes")
        outline, box = _titled_box(body, titles[field])
        outline.grid(row=row, column=0, sticky="nsew", pady=3)
        # The focus ring is the Text's highlight: 1px, and light (white when idle).
        text = tk.Text(
            box, wrap="word", height=3, borderwidth=0, highlightthickness=1,
            highlightbackground="white", highlightcolor=FOCUS_RING,
        )
        text.insert("1.0", values[field])
        text.pack(fill="both", expand=True)
        texts[field] = text
    return texts


class IdeaEditor(tk.Toplevel):
    """Modal dialog for creating or editing one idea."""

    def __init__(
        self, parent: tk.Misc, idea: Idea, can_delete: bool = False,
        save_fields=None, start_on_settings: bool = False,
    ):
        """`save_fields(**values) -> bool` writes just those fields to storage.

        The Settings and SWOT displays save through it, independently of this
        dialog's Save. It is None for an idea that isn't stored yet; those fields
        are then kept with the idea and stored when the idea itself is first saved.
        """
        super().__init__(parent)
        # A new idea starts on the Settings display (name and description first)
        # with this dialog kept out of sight until the user moves on to the rubric.
        self._hidden = start_on_settings
        if self._hidden:
            self.withdraw()
        self.idea = idea
        self.can_delete = can_delete
        self._save_fields = save_fields
        self.saved = False
        self.deleted = False
        # Name, status, color, description and SWOT text; written to the idea by this dialog's Save.
        self.pending = {
            f: getattr(idea, f)
            for f in ("name", "status", "color", *DESCRIPTION_FIELDS, *SWOT_FIELDS, "roast")
        }
        self.title(idea.name or "New idea")
        width = min(860, self.winfo_screenwidth() - 40)
        height = self.winfo_screenheight()
        x = (self.winfo_screenwidth() - width) // 2
        self._width, self._x = width, x
        self.geometry(f"{width}x{height}+{x}+0")
        self.transient(parent)
        self.configure(background=PAGE_BG)

        self._build_header()
        self._build_criteria()
        self._build_buttons()
        self._fit_height()

        if self._hidden:
            self._show_settings()
        else:
            self.grab_set()

    def request_close(self) -> None:
        """Command-W: same as Cancel."""
        self.destroy()

    def reveal(self) -> None:
        """Show this dialog after the Settings display a new idea starts on."""
        if self._hidden:
            self._hidden = False
            self.deiconify()
            self.lift()
        self.grab_set()

    @staticmethod
    def _button(parent: tk.Misc, text: str, command=None, **kw) -> tk.Button:
        """A native button whose surround matches the page background.

        ttk buttons paint a system-gray rectangle behind their rounded corners.
        """
        return tk.Button(
            parent, text=text, command=command, highlightbackground=PAGE_BG, **kw
        )

    @staticmethod
    def _text_width(items) -> int:
        """Combobox width, in "0" characters, that just fits the widest item."""
        font = tkfont.nametofont("TkTextFont")
        return -(-max(font.measure(s) for s in items) // font.measure("0"))

    def _build_header(self) -> None:
        head = tk.Frame(self, padx=10, pady=10, background=PAGE_BG)
        head.pack(fill="x")
        # Right-aligned to the window edge.
        self._button(head, "Settings", self._show_settings).pack(side="right")
        self._button(head, "SWOT", self._show_swot).pack(side="right", padx=(0, 8))

    def _commit(self, values: dict[str, str]) -> bool:
        """Store Settings/SWOT fields on its own, without this dialog's Save."""
        if self._save_fields:
            if not self.idea.name:
                # Not stored yet: the first save creates the idea, so it needs the
                # name even when it comes from a display that doesn't edit it.
                values = {"name": self.pending["name"], **values}
            if not self._save_fields(**values):
                return False
        self.pending.update(values)
        if "name" in values:
            self.set_name(values["name"])
        return True

    def set_name(self, name: str) -> None:
        """Hold a name for this dialog's Save, and show it in the title."""
        self.pending["name"] = name.strip()
        self.title(self.pending["name"] or "New idea")

    def _show_settings(self) -> None:
        SettingsEditor(self, self._commit, self._goto)

    def _show_swot(self) -> None:
        SwotEditor(self, self._commit, self._goto)

    def _goto(self, target: str) -> None:
        """Called by Settings/SWOT after they close, to switch displays."""
        if target == "settings":
            self._show_settings()
        elif target == "swot":
            self._show_swot()

    def _build_criteria(self) -> None:
        outer = tk.Frame(self, background=PAGE_BG)
        outer.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(outer, highlightthickness=0, background=PAGE_BG)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, background=PAGE_BG)
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
        self._criteria_outer = outer
        self._criteria_canvas, self._criteria_body = canvas, body

    def _fit_height(self) -> None:
        """Shrink the window to its content so no blank gap opens above the buttons."""
        self.update_idletasks()
        self._criteria_canvas.configure(height=self._criteria_body.winfo_reqheight())
        self.update_idletasks()
        height = min(self.winfo_reqheight(), self.winfo_screenheight() - 60)
        # Not winfo_width/x: they're meaningless while the window is withdrawn.
        self.window_geometry = f"{self._width}x{height}+{self._x}+0"
        self.geometry(self.window_geometry)

    def _enable_wheel_scroll(self, canvas: tk.Canvas) -> None:
        """Scroll the criteria with the mouse wheel / trackpad, anywhere in the dialog."""

        def on_wheel(event: tk.Event) -> None:
            w = event.widget
            # A text box that has its own overflow already scrolled itself.
            if isinstance(w, tk.Text) and w.yview() != (0.0, 1.0):
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
        border, box = _titled_box(parent, c.name)
        border.pack(fill="x", pady=3)

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

        hint = ttk.Label(row, wraplength=520, foreground="gray40", justify="left")
        hint.pack(side="left", fill="x", padx=(12, 8))
        warn = ttk.Label(box, text="Add a reason for this score", foreground="#b45309")

        reason = tk.Text(box, height=2, wrap="word")
        reason.insert("1.0", self.idea.reasons.get(c.id, ""))
        reason.pack(fill="x", pady=(4, 0))
        self.reason_texts[c.id] = reason

        def refresh(*_):
            score = var.get()
            if score == UNSCORED:
                hint.config(text="Not scored yet")
            else:
                hint.config(text=c.levels[score - MIN_SCORE])
            has_reason = bool(reason.get("1.0", "end").strip())
            if score != UNSCORED and not has_reason:
                warn.pack(fill="x", before=reason)
            else:
                warn.pack_forget()

        var.trace_add("write", refresh)
        reason.bind("<KeyRelease>", refresh)
        refresh()

    def _build_buttons(self) -> None:
        bar = tk.Frame(self, padx=10, background=PAGE_BG)
        # Packed ahead of the criteria so that, when the window is too short, the
        # scrolling criteria shrink instead of squashing these buttons.
        bar.pack(side="bottom", fill="x", pady=(2, 10), before=self._criteria_outer)
        self._button(bar, "Save", self._save).pack(side="left")
        self._button(bar, "Cancel", self.destroy).pack(side="left", padx=6)
        if self.can_delete:
            self._button(bar, "Delete", self._delete, foreground=DELETE_FG).pack(
                side="left"
            )
        self.weight_total = tk.Label(bar, background=PAGE_BG)
        self.weight_total.pack(side="right")
        self._update_weight_total()

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
            foreground="black" if total == 100 and self._weights_valid() else "#b91c1c",
        )

    def _save(self) -> None:
        name = self.pending["name"].strip()
        if not name:
            messagebox.showwarning(
                "Name required", "Give the idea a name (in the Settings display).",
                parent=self,
            )
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
        for field, value in self.pending.items():
            setattr(idea, field, value)
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


DESCRIPTION_TITLES = {
    "concept": "The idea",
    "customer": "Who it's for and how it makes money",
    "edge": "Your edge",
    "constraints": "Constraints",
}

NO_COLOR = "#9ca3af"  # bar color for ideas with no color chosen


class _SubEditor(tk.Toplevel):
    """A full-size display opened from the idea editor (Settings, SWOT).

    Layout: bold title and navigation buttons on top, the body, then Save.
    Save stores this display's fields on their own, via `commit`.
    """

    title_text = ""
    show_heading = True  # False where the window title already says it
    other = ""  # the sibling display offered next to "Rubric": "settings" or "swot"

    def __init__(self, parent: IdeaEditor, commit, goto):
        super().__init__(parent.master)
        self._parent = parent
        self._commit = commit
        self._goto = goto
        self.title(self.title_text)
        self.configure(background=PAGE_BG)
        self.geometry(parent.window_geometry)
        # Over the idea dialog, or over the app while that one is still hidden.
        self.transient(parent if parent.winfo_viewable() else parent.master)

        top = self.top = tk.Frame(self, padx=10, pady=10, background=PAGE_BG)
        top.pack(fill="x")
        if self.show_heading:
            tk.Label(
                top, text=self.title_text, background=PAGE_BG, font=_bold_font()
            ).pack(side="left")
        # Right-aligned; packed right-to-left, so the sibling display first.
        IdeaEditor._button(
            top, {"swot": "SWOT", "settings": "Settings"}[self.other],
            lambda: self._leave(self.other),
        ).pack(side="right")
        IdeaEditor._button(top, "Rubric", lambda: self._leave("rubric")).pack(
            side="right", padx=(0, 8)
        )

        # Packed before the body so a short window shrinks the body, not the button.
        bottom = tk.Frame(self, padx=10, background=PAGE_BG)
        bottom.pack(side="bottom", fill="x", pady=(8, 18))
        IdeaEditor._button(bottom, "Save", self._save).pack(side="left")
        self._build_bottom(bottom)

        body = tk.Frame(self, padx=10, background=PAGE_BG)
        body.pack(fill="both", expand=True)
        self._build_body(body)

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_body(self, body: tk.Frame) -> None:
        raise NotImplementedError

    def _build_bottom(self, bottom: tk.Frame) -> None:
        """Add anything else to the bottom row, beside Save."""

    def _values(self) -> dict[str, str]:
        raise NotImplementedError

    def _valid(self) -> bool:
        return True

    def _stash(self) -> None:
        """Hand values the idea editor itself needs to it when leaving unsaved."""

    def _save(self) -> None:
        if self._valid() and self._commit(self._values()):
            self._close()

    def _leave(self, target: str) -> None:
        """Close without saving and open another display ("rubric" is the editor)."""
        self._stash()
        self._close(reveal=target == "rubric")
        self._goto(target)

    def request_close(self) -> None:
        """Command-W: same as the window's close button."""
        self._cancel()

    def _cancel(self) -> None:
        """The window's close button: leave, and drop an idea that isn't shown yet."""
        if self._parent._hidden:
            self.destroy()
            self._parent.destroy()
        else:
            self._close()

    def _close(self, reveal: bool = True) -> None:
        self.destroy()
        if self._parent._hidden:
            if reveal:
                self._parent.reveal()
        else:
            self._parent.grab_set()  # hand the modal grab back to the idea dialog


class SettingsEditor(_SubEditor):
    """The idea's name, status, color and its four-part description."""

    title_text = "Settings"
    show_heading = False  # the window title is "Settings"
    other = "swot"

    def _build_body(self, body: tk.Frame) -> None:
        # The name shares the top line with the Rubric and SWOT buttons.
        name_row = tk.Frame(self.top, background=PAGE_BG)
        name_row.pack(side="left")
        tk.Label(name_row, text="Name", background=PAGE_BG).pack(side="left")
        self.name_var = tk.StringVar(value=self._parent.pending["name"])
        self.name_entry = ttk.Entry(name_row, textvariable=self.name_var, width=40)
        self.name_entry.pack(side="left", padx=6)

        pending = self._parent.pending
        body.columnconfigure(0, weight=1)
        detail_row = tk.Frame(body, background=PAGE_BG)
        tk.Label(detail_row, text="Status", background=PAGE_BG).pack(side="left")
        self.status_var = tk.StringVar(value=pending["status"])
        ttk.Combobox(
            detail_row, textvariable=self.status_var, values=STATUSES, state="readonly",
            width=IdeaEditor._text_width(STATUSES),
        ).pack(side="left", padx=6)
        tk.Label(detail_row, text="Color", background=PAGE_BG).pack(
            side="left", padx=(16, 6)
        )
        self.swatch = tk.Label(
            detail_row, width=6, relief="solid", borderwidth=1, cursor="hand2",
            foreground="gray50",
        )
        self.swatch.pack(side="left")
        self.swatch.bind("<Button-1>", lambda e: self._pick_color())
        self.clear_btn = tk.Label(detail_row, text="×", cursor="hand2", background=PAGE_BG)
        self.clear_btn.bind("<Button-1>", lambda e: self._set_color(""))
        self._set_color(pending["color"])

        detail_row.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.texts = _text_boxes(
            body, self._parent.pending, DESCRIPTION_FIELDS, DESCRIPTION_TITLES, first_row=1
        )
        (
            self.texts[DESCRIPTION_FIELDS[0]] if self.name_var.get() else self.name_entry
        ).focus_set()

    def _build_bottom(self, bottom: tk.Frame) -> None:
        # Centered in the row; Save stays at the left.
        IdeaEditor._button(bottom, "Roast", self._roast).place(
            relx=0.5, rely=0.5, anchor="center"
        )

    def _roast(self) -> None:
        # Deferred so the window doesn't open from inside the button's own callback.
        self.after_idle(
            lambda: RoastWindow(
                self, self._parent.pending["roast"], self._prepare_roast, self._commit
            )
        )

    def _prepare_roast(self) -> Idea | None:
        """Check the idea is ready to roast and store what is on screen.

        Returns the idea as it now stands, or None (after saying why).
        """
        values = self._values()
        if not values["name"]:
            messagebox.showwarning("Name required", "Give the idea a name.", parent=self)
            return None
        snapshot = Idea(
            **{f: values[f] for f in ("name", "status", "color", *DESCRIPTION_FIELDS)}
        )
        missing = roast.missing_fields(snapshot)
        if missing:
            messagebox.showwarning(
                "Fill in the description",
                "A roast needs all four boxes. Still empty:\n\n" + "\n".join(missing),
                parent=self,
            )
            return None
        # The roast judges what is stored, so store the screen first.
        return snapshot if self._commit(values) else None

    def _set_color(self, color: str) -> None:
        self.color = color
        self.swatch.config(
            background=color or PAGE_BG, text="" if color else "none"
        )
        if color:
            self.clear_btn.pack(side="left", padx=6)
        else:
            self.clear_btn.pack_forget()

    def _pick_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.color or None, parent=self, title="Idea color"
        )
        if hex_color:  # None if the dialog was cancelled
            self._set_color(hex_color.lower())

    def _valid(self) -> bool:
        if self.name_var.get().strip():
            return True
        messagebox.showwarning("Name required", "Give the idea a name.", parent=self)
        return False

    def _stash(self) -> None:
        self._parent.set_name(self.name_var.get())
        self._parent.pending.update(status=self.status_var.get(), color=self.color)

    def _values(self) -> dict[str, str]:
        return {
            "name": self.name_var.get().strip(),
            "status": self.status_var.get(),
            "color": self.color,
            **{f: t.get("1.0", "end").strip() for f, t in self.texts.items()},
        }


class SwotEditor(_SubEditor):
    """Strengths, weaknesses, opportunities and threats: four boxes, one text each."""

    title_text = "SWOT"
    other = "settings"

    def __init__(self, parent: IdeaEditor, commit, goto):
        super().__init__(parent, commit, goto)
        self.title(parent.pending["name"] or "New idea")  # window title: the idea's name

    def _build_body(self, body: tk.Frame) -> None:
        self.texts = _text_boxes(
            body, self._parent.pending, SWOT_FIELDS, {f: f.capitalize() for f in SWOT_FIELDS}
        )
        self.texts[SWOT_FIELDS[0]].focus_set()

    def _values(self) -> dict[str, str]:
        return {f: t.get("1.0", "end").strip() for f, t in self.texts.items()}


class GuideWindow(tk.Toplevel):
    """The user guide: a read-only, scrollable text. Not modal."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Guide")
        self.configure(background=PAGE_BG)
        width = min(760, self.winfo_screenwidth() - 40)
        height = min(800, self.winfo_screenheight() - 100)
        x = (self.winfo_screenwidth() - width) // 2
        self.geometry(f"{width}x{height}+{x}+40")

        tk.Label(
            self, text="Guide", background=PAGE_BG, font=_bold_font(), padx=10, pady=10
        ).pack(anchor="w")
        body = tk.Frame(self, padx=10, background=PAGE_BG)
        body.pack(fill="both", expand=True, pady=(0, 18))
        scroll = ttk.Scrollbar(body, orient="vertical")
        outline = tk.Frame(body, background=BORDER)
        self.text = tk.Text(
            outline, wrap="word", yscrollcommand=scroll.set, borderwidth=0,
            highlightthickness=0, font="TkDefaultFont", padx=8, pady=8,
        )
        scroll.config(command=self.text.yview)
        scroll.pack(side="right", fill="y")
        outline.pack(side="left", fill="both", expand=True)
        self.text.pack(fill="both", expand=True, padx=1, pady=1)
        self._fill(guide_text())
        self.text.config(state="disabled")  # read-only

    def _fill(self, content: str) -> None:
        """Insert the guide, styling "#" heading lines and indenting list items."""
        base = tkfont.nametofont("TkDefaultFont")
        size = base.cget("size")
        self._fonts = []  # keep references: Tk drops fonts nobody holds
        for tag, delta, before, after in (("h1", 6, 0, 10), ("h2", 2, 16, 4), ("h3", 0, 8, 0)):
            font = base.copy()
            font.configure(weight="bold", size=size + delta if size > 0 else size - delta)
            self._fonts.append(font)
            self.text.tag_configure(tag, font=font, spacing1=before, spacing3=after)
        self.text.tag_configure("item", lmargin1=14, lmargin2=30, spacing3=3)
        self.text.tag_configure("para", spacing3=8)
        for line in content.splitlines():
            if not line.strip():
                continue  # spacing comes from the tags, not from blank lines
            tag = "para"
            for prefix, name in (("### ", "h3"), ("## ", "h2"), ("# ", "h1")):
                if line.startswith(prefix):
                    line, tag = line[len(prefix):], name
                    break
            else:
                if line[:2] == "- " or line[:3].rstrip(".").isdigit() and ". " in line[:4]:
                    tag = "item"
            self.text.insert("end", line + "\n", tag)

    def request_close(self) -> None:
        """Command-W."""
        self.destroy()


VERDICT_FG = {"GO": "#15803d", "RESHAPE": "#b45309", "KILL": "#b91c1c"}
STATE_MARK = {"waiting": "·", "working": "…", "done": "✓", "failed": "✗"}
COST_NOTE = (
    "A roast makes six calls to Claude, one of them with web search, and costs "
    "roughly 10 to 30 cents.\n\nRun it?"
)


class RoastWindow(tk.Toplevel):
    """Runs the Roast council on an idea and shows the verdict. Modal over Settings.

    `prepare() -> Idea | None` checks and stores the idea before a run; `commit(values)`
    stores the result on it. The council runs on a worker thread; it talks to the UI
    only through a queue that this window polls.
    """

    NAMES = [p.name for p in roast.PERSONAS] + ["Judge"]

    def __init__(self, parent: "SettingsEditor", previous: dict, prepare, commit):
        super().__init__(parent)
        self._settings = parent
        self._prepare = prepare
        self._commit = commit
        self._result = previous
        self._running = False
        self._queue: queue.Queue = queue.Queue()
        self.title("Roast")
        self.configure(background=PAGE_BG)
        self.geometry(parent.geometry())
        self.transient(parent)

        top = tk.Frame(self, padx=10, pady=10, background=PAGE_BG)
        top.pack(fill="x")
        tk.Label(top, text="Roast", background=PAGE_BG, font=_bold_font()).pack(side="left")
        self.run_btn = IdeaEditor._button(top, "Roast again", self._start)
        self.run_btn.pack(side="right")

        bottom = tk.Frame(self, padx=10, background=PAGE_BG)
        bottom.pack(side="bottom", fill="x", pady=(8, 18))
        IdeaEditor._button(bottom, "Close", self.request_close).pack(side="left")
        self.status = tk.Label(bottom, background=PAGE_BG, foreground="gray40")
        self.status.pack(side="left", padx=12)

        self.progress = tk.Frame(self, padx=10, background=PAGE_BG)
        self.marks = {}
        for name in self.NAMES:
            row = tk.Frame(self.progress, background=PAGE_BG)
            row.pack(anchor="w")
            mark = tk.Label(row, width=2, background=PAGE_BG)
            mark.pack(side="left")
            tk.Label(row, text=name, background=PAGE_BG).pack(side="left")
            self.marks[name] = mark

        body = tk.Frame(self, padx=10, background=PAGE_BG)
        body.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(body, orient="vertical")
        outline = tk.Frame(body, background=BORDER)
        self.text = tk.Text(
            outline, wrap="word", yscrollcommand=scroll.set, borderwidth=0,
            highlightthickness=0, font="TkDefaultFont", padx=10, pady=8, state="disabled",
        )
        scroll.config(command=self.text.yview)
        scroll.pack(side="right", fill="y")
        outline.pack(side="left", fill="both", expand=True)
        self.text.pack(fill="both", expand=True, padx=1, pady=1)
        self._configure_tags()

        self.protocol("WM_DELETE_WINDOW", self.request_close)
        self.bind("<Escape>", lambda e: self.request_close())
        self.grab_set()
        if previous:
            self._show(previous)
        else:
            self.run_btn.config(text="Roast")
            self.after(50, self._start)  # a first roast starts straight away

    def _configure_tags(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")
        size = base.cget("size")
        self._fonts = []  # keep references: Tk drops fonts nobody holds
        for tag, delta, weight in (("h2", 4, "bold"), ("h3", 1, "bold"), ("bold", 0, "bold")):
            font = base.copy()
            font.configure(weight=weight, size=size + delta if size > 0 else size - delta)
            self._fonts.append(font)
            self.text.tag_configure(tag, font=font)
        self.text.tag_configure("h2", spacing1=10, spacing3=4)
        self.text.tag_configure("h3", spacing1=14, spacing3=2)
        self.text.tag_configure("note", foreground="gray40")
        self.text.tag_configure("error", foreground="#b91c1c")
        for verdict, color in VERDICT_FG.items():
            self.text.tag_configure(verdict, foreground=color)

    def request_close(self) -> None:
        """Command-W, Escape, the close button."""
        if self._running and not messagebox.askyesno(
            "Roast running",
            "A roast is still running. Closing now discards its result "
            "(the calls already made are still billed).\n\nClose anyway?",
            parent=self,
        ):
            return
        self._running = False  # the poll loop stops; late results are ignored
        self.destroy()
        self._settings.grab_set()  # hand the modal grab back to Settings

    # -- running ---------------------------------------------------------------

    def _start(self) -> None:
        if self._running:
            return
        idea = self._prepare()
        if idea is None:
            if not self._result:
                self.request_close()  # nothing to show, nothing started
            return
        if not messagebox.askyesno("Run a roast?", COST_NOTE, parent=self):
            if not self._result:
                self.request_close()
            return
        self._running = True
        self.run_btn.config(state="disabled")
        self._set_text("")
        self.status.config(text="Convening the council…")
        for mark in self.marks.values():
            mark.config(text=STATE_MARK["waiting"])
        self.progress.pack(fill="x", before=self.text.master.master, pady=(0, 8))
        threading.Thread(target=self._work, args=(idea,), daemon=True).start()
        self.after(100, self._poll)

    def _work(self, idea: Idea) -> None:
        """Worker thread: no Tk calls in here, only the queue."""
        try:
            result = roast.run_council(
                idea, on_progress=lambda who, state: self._queue.put(("progress", who, state))
            )
        except roast.RoastError as e:
            self._queue.put(("error", str(e)))
        except Exception as e:  # keep the window from waiting forever
            self._queue.put(("error", f"Unexpected error: {type(e).__name__}"))
        else:
            self._queue.put(("done", result.to_dict()))

    def _poll(self) -> None:
        if not self._running:
            return
        try:
            while True:
                kind, *rest = self._queue.get_nowait()
                if kind == "progress":
                    who, state = rest
                    self.marks[who].config(text=STATE_MARK[state])
                else:
                    self._finish(kind, rest[0])
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, kind: str, payload) -> None:
        self._running = False
        self.progress.pack_forget()
        self.run_btn.config(state="normal", text="Roast again")
        if kind == "error":
            self.status.config(text="")
            if self._result:
                self._show(self._result)  # the earlier roast is still on the idea
            self._append(f"The roast failed: {payload}\n\n", "error", at_top=True)
            return
        self._result = payload
        self._show(payload)
        saved = self._commit({"roast": payload})
        self.status.config(text="Saved to the idea." if saved else "Couldn't save the result.")

    # -- showing ---------------------------------------------------------------

    def _set_text(self, content: str) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.config(state="disabled")

    def _append(self, content: str, *tags: str, at_top: bool = False) -> None:
        self.text.config(state="normal")
        self.text.insert("1.0" if at_top else "end", content, tags)
        self.text.config(state="disabled")

    def _markdown(self, content: str, verdict: str = "") -> None:
        """Insert the model's markdown: headings and **bold**, nothing else."""
        for line in content.splitlines():
            tag = ""
            for prefix, name in (("### ", "h3"), ("## ", "h2")):
                if line.startswith(prefix):
                    line, tag = line[len(prefix):], name
                    break
            if tag == "h2" and verdict:
                self._append(line + "\n", "h2", verdict)
                continue
            for i, piece in enumerate(line.split("**")):
                if piece:
                    self._append(piece, *(("bold",) if i % 2 else ()), *((tag,) if tag else ()))
            self._append("\n")

    def _show(self, result: dict) -> None:
        self._set_text("")
        self.status.config(text="")
        verdict = result.get("verdict", "")
        self._markdown(result.get("report", ""), verdict)
        scores = result.get("scores", {})
        if scores:
            line = " · ".join(f"{n} {s}/10" for n, s in scores.items())
            self._append("\n" + line + "\n", "note")
        failed = result.get("failed", {})
        for name, why in failed.items():
            self._append(f"{name} didn't report: {why}\n", "note")
        self._append("\nThe council\n", "h2")
        for name, report in result.get("reports", {}).items():
            self._append(name + "\n", "h3")
            self._markdown(report)
        self.text.yview_moveto(0)


class ApiKeyWindow(tk.Toplevel):
    """Set or remove the Anthropic API key. The key is never shown, only whether it is set."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("API Key")
        self.configure(background=PAGE_BG)
        self.resizable(False, False)
        self.transient(parent)

        body = tk.Frame(self, padx=16, pady=14, background=PAGE_BG)
        body.pack(fill="both", expand=True)
        self.status = tk.Label(body, background=PAGE_BG, anchor="w", justify="left")
        self.status.pack(fill="x")
        tk.Label(
            body, text="Anthropic API key", background=PAGE_BG, anchor="w"
        ).pack(fill="x", pady=(10, 2))
        self.key_var = tk.StringVar()
        self.entry = ttk.Entry(body, textvariable=self.key_var, show="•", width=44)
        self.entry.pack(fill="x")
        self.hint = tk.Label(
            body, background=PAGE_BG, anchor="w", justify="left", foreground="gray40"
        )
        self.hint.pack(fill="x", pady=(6, 0))

        buttons = tk.Frame(body, background=PAGE_BG)
        buttons.pack(fill="x", pady=(12, 0))
        IdeaEditor._button(buttons, "Save", self._save).pack(side="left")
        IdeaEditor._button(buttons, "Cancel", self.destroy).pack(side="left", padx=6)
        self.remove_btn = IdeaEditor._button(
            buttons, "Remove key", self._remove, foreground=DELETE_FG
        )
        self.remove_btn.pack(side="right")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self._refresh()
        self.entry.focus_set()
        self.grab_set()

    def request_close(self) -> None:
        """Command-W."""
        self.destroy()

    def _refresh(self) -> None:
        """Show whether a key is set, and where it would come from."""
        try:
            key = apikey.get_key()
        except apikey.ApiKeyError as e:
            self.status.config(text=str(e), foreground="#b91c1c")
            self.remove_btn.config(state="disabled")
            return
        from_env = bool(os.environ.get(apikey.ENV_VAR, "").strip())
        if from_env:
            text = f"Using the {apikey.ENV_VAR} environment variable."
        else:
            text = "A key is saved." if key else "No key is saved."
        self.status.config(text=text, foreground="black")
        self.remove_btn.config(state="normal" if key and not from_env else "disabled")
        self.hint.config(
            text="Saved in your Keychain." if sys.platform == "darwin"
            else "Saved in a file only you can read."
        )

    def _save(self) -> None:
        try:
            apikey.set_key(self.key_var.get())
        except apikey.ApiKeyError as e:
            messagebox.showwarning("API key", str(e), parent=self)
            return
        self.key_var.set("")
        self._refresh()
        self.destroy()

    def _remove(self) -> None:
        if not messagebox.askyesno(
            "Remove API key", "Remove the saved API key?", parent=self
        ):
            return
        try:
            apikey.delete_key()
        except apikey.ApiKeyError as e:
            messagebox.showwarning("API key", str(e), parent=self)
            return
        self._refresh()


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
            label="New Idea", accelerator=f"{mod}+N", command=self._new_idea_soon
        )
        file_menu.add_separator()
        file_menu.add_command(label="API Key…", command=self._show_api_key_soon)
        file_menu.add_separator()
        file_menu.add_command(
            label="Close Window", accelerator=f"{mod}+W", command=self._close_window
        )
        menubar.add_cascade(label="File", menu=file_menu)
        guide_menu = tk.Menu(menubar, tearoff=False)
        guide_menu.add_command(label="User Guide", command=self._show_guide_soon)
        menubar.add_cascade(label="Guide", menu=guide_menu)
        root.config(menu=menubar)
        root.bind(f"<{mod}-n>", lambda e: self._new_idea_soon())
        self.bind_all(f"<{mod}-w>", lambda e: self._close_window())

    def _show_api_key_soon(self) -> None:
        # After the menu action returns, like _new_idea_soon.
        self.after(50, self.show_api_key)

    def show_api_key(self) -> None:
        """Open the API key window, or bring it forward if it is already open."""
        win = getattr(self, "_api_key", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        self._api_key = ApiKeyWindow(self.winfo_toplevel())

    def _show_guide_soon(self) -> None:
        # After the menu action returns, like _new_idea_soon.
        self.after(50, self.show_guide)

    def show_guide(self) -> None:
        """Open the user guide, or bring it forward if it is already open."""
        guide = getattr(self, "_guide", None)
        if guide is not None and guide.winfo_exists():
            guide.deiconify()
            guide.lift()
            return
        self._guide = GuideWindow(self)

    def _close_window(self) -> None:
        """Close the active dialog. The main window isn't closed this way; quit with Command+Q."""
        try:
            focused = self.focus_get()
        except KeyError:  # tkinter can't name some native popups
            focused = None
        window = focused.winfo_toplevel() if focused else self.grab_current()
        window = window or self.winfo_toplevel()
        if window is self.winfo_toplevel():
            return  # closing the main window would quit the app
        getattr(window, "request_close", window.destroy)()

    def _new_idea_soon(self) -> None:
        # Not inside the menu's own callback: a modal dialog opened (and waited on)
        # from within a native macOS menu action can leave the app unresponsive.
        self.after(50, self.new_idea)

    def _build(self) -> None:
        self._build_menu()

        cols = ("name", "status", "verdict", "total", "bars") + tuple(c.id for c in CRITERIA)
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings", selectmode="browse"
        )
        self.sort_col, self.sort_desc = "total", True
        self._heading_text = {"name": "Idea", "status": "Status", "verdict": "Roast", "total": "Total"}
        self._heading_text.update({c.id: c.name for c in CRITERIA})
        self.tree.column("name", width=NAME_W, minwidth=160)
        self.tree.column("status", width=STATUS_W, anchor="w")
        self.tree.column("verdict", width=VERDICT_W, anchor="w")
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
            # Scores and totals start high-to-low; text columns A-Z; verdicts GO first.
            self.sort_col, self.sort_desc = col, col not in ("name", "status", "verdict")
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
            if self.sort_col == "verdict":
                verdict = idea.roast.get("verdict")
                value = roast.VERDICTS.index(verdict) if verdict in roast.VERDICTS else None
            elif self.sort_col == "total":
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
                idea.roast.get("verdict", ""),
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
        fixed = NAME_W + STATUS_W + VERDICT_W + TOTAL_W + BAR_W
        spare = window_width - 2 * APP_PADDING - TREE_SLACK - fixed
        width = max(60, min(CRITERION_W, spare // len(CRITERIA)))
        for c in CRITERIA:
            self.tree.column(c.id, width=width)

    def _tip_text(self, row_id: str, col_id: str) -> str:
        idea = next((i for i in self.ideas if i.id == row_id), None)
        if idea is not None and col_id == "name":
            return idea.concept.strip()  # no concept, no tooltip
        if idea is not None and col_id == "verdict":
            confidence = idea.roast.get("confidence")
            return f"Confidence: {confidence}" if confidence else ""
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
            tip, text=text, justify="left",
            background=TIP_BG,
            wraplength=DESCRIPTION_TIP_W if col_id == "name" else 360,
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

    def _edit(
        self, idea: Idea, can_delete: bool = False, save_fields=None,
        start_on_settings: bool = False,
    ) -> IdeaEditor:
        editor = IdeaEditor(self, idea, can_delete, save_fields, start_on_settings)
        self.wait_window(editor)
        return editor

    def new_idea(self) -> None:
        idea = Idea(name="", color=PALETTE[len(self.ideas) % len(PALETTE)])

        def save_fields(**values: str) -> bool:
            """Create the idea on the first save (once it has a name), then update it.

            Everything the user hasn't filled in yet keeps the Idea defaults:
            empty text, no scores, default weights.
            """
            if not (values.get("name") or idea.name):
                messagebox.showwarning(
                    "Name required", "Give the idea a name first.", parent=self
                )
                return False
            old = {k: getattr(idea, k) for k in values}
            for k, v in values.items():
                setattr(idea, k, v)
            is_new = idea not in self.ideas
            if is_new:
                self.ideas.append(idea)
            if self._persist():
                self.refresh()
                return True
            for k, v in old.items():
                setattr(idea, k, v)
            if is_new:
                self.ideas.remove(idea)
            return False

        saved = self._edit(idea, save_fields=save_fields, start_on_settings=True).saved
        if saved and idea not in self.ideas:
            self.ideas.append(idea)
        if idea in self.ideas:  # created along the way, or just saved
            self._persist()
            self.refresh()
            self.tree.selection_set(idea.id)

    def edit_selected(self) -> None:
        idea = self._selected()
        if idea is None:
            return
        # Edit a copy so Cancel can't leave half-applied changes behind.
        working = Idea.from_dict(vars(idea))

        def save_fields(**values: str) -> bool:
            # Independent of the editor's Save: only these stored fields change.
            old = {k: getattr(idea, k) for k in values}
            for k, v in values.items():
                setattr(idea, k, v)
            if self._persist():
                self.refresh()  # the name may have changed
                return True
            for k, v in old.items():
                setattr(idea, k, v)
            return False

        editor = self._edit(working, can_delete=True, save_fields=save_fields)
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
    cols = NAME_W + STATUS_W + VERDICT_W + TOTAL_W + BAR_W + CRITERION_W * len(CRITERIA)
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
    root.title("Rubric Business Evaluation")
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
