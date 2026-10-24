"""Tkinter desktop UI: comparison table and idea editor."""

import tkinter as tk
from tkinter import colorchooser, font as tkfont, messagebox, ttk

from .rubric import CRITERIA, DEFAULT_WEIGHTS, MAX_SCORE, MIN_SCORE
from .scoring import total_score
from .storage import STATUSES, SWOT_FIELDS, Idea, Storage, StorageError

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
NAME_W, STATUS_W, TOTAL_W, CRITERION_W = 160, 95, 80, 115
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


class IdeaEditor(tk.Toplevel):
    """Modal dialog for creating or editing one idea."""

    def __init__(
        self, parent: tk.Misc, idea: Idea, can_delete: bool = False,
        save_fields=None, start_on_description: bool = False,
    ):
        """`save_fields(**values) -> bool` writes just those fields to storage.

        The Description and SWOT displays save through it, independently of this
        dialog's Save. It is None for an idea that isn't stored yet; those fields
        are then kept with the idea and stored when the idea itself is first saved.
        """
        super().__init__(parent)
        # A new idea starts on the Description display (name and description first)
        # with this dialog kept out of sight until the user moves on to the rubric.
        self._hidden = start_on_description
        if self._hidden:
            self.withdraw()
        self.idea = idea
        self.can_delete = can_delete
        self._save_fields = save_fields
        self.saved = False
        self.deleted = False
        # Name, status, color, description and SWOT text; written to the idea by this dialog's Save.
        self.pending = {f: getattr(idea, f) for f in ("name", "status", "color", "description", *SWOT_FIELDS)}
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
            self._show_description()
        else:
            self.grab_set()

    def request_close(self) -> None:
        """Command-W: same as Cancel."""
        self.destroy()

    def reveal(self) -> None:
        """Show this dialog after the Description display a new idea starts on."""
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
        self._button(head, "SWOT", self._show_swot).pack(side="right")
        self._button(head, "Description", self._show_description).pack(
            side="right", padx=(0, 8)
        )

    def _commit(self, values: dict[str, str]) -> bool:
        """Store Description/SWOT text on its own, without this dialog's Save."""
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

    def _show_description(self) -> None:
        DescriptionEditor(self, self._commit, self._goto)

    def _show_swot(self) -> None:
        SwotEditor(self, self._commit, self._goto)

    def _goto(self, target: str) -> None:
        """Called by Description/SWOT after they close, to switch displays."""
        if target == "description":
            self._show_description()
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
                "Name required", "Give the idea a name (in the Description display).",
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


NO_COLOR = "#9ca3af"  # bar color for ideas with no color chosen


class _SubEditor(tk.Toplevel):
    """A full-size display opened from the idea editor (Description, SWOT).

    Layout: bold title and navigation buttons on top, the body, then Save.
    Save stores this display's fields on their own, via `commit`.
    """

    title_text = ""
    other = ""  # the sibling display offered next to "Rubric": "description" or "swot"

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

        top = tk.Frame(self, padx=10, pady=10, background=PAGE_BG)
        top.pack(fill="x")
        tk.Label(
            top, text=self.title_text, background=PAGE_BG, font=_bold_font()
        ).pack(side="left")
        # Right-aligned; packed right-to-left, so the sibling display first.
        IdeaEditor._button(
            top, {"swot": "SWOT", "description": "Description"}[self.other],
            lambda: self._leave(self.other),
        ).pack(side="right")
        IdeaEditor._button(top, "Rubric", lambda: self._leave("rubric")).pack(
            side="right", padx=(0, 8)
        )

        # Packed before the body so a short window shrinks the body, not the button.
        bottom = tk.Frame(self, padx=10, background=PAGE_BG)
        bottom.pack(side="bottom", fill="x", pady=(8, 18))
        IdeaEditor._button(bottom, "Save", self._save).pack(side="left")

        body = tk.Frame(self, padx=10, background=PAGE_BG)
        body.pack(fill="both", expand=True)
        self._build_body(body)

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_body(self, body: tk.Frame) -> None:
        raise NotImplementedError

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


class DescriptionEditor(_SubEditor):
    """The idea's name, status, color and its full-height long description."""

    title_text = "Description"
    other = "swot"

    def _build_body(self, body: tk.Frame) -> None:
        name_row = tk.Frame(body, background=PAGE_BG)
        name_row.pack(fill="x", pady=(0, 10))
        tk.Label(name_row, text="Name", background=PAGE_BG).pack(side="left")
        self.name_var = tk.StringVar(value=self._parent.pending["name"])
        self.name_entry = ttk.Entry(name_row, textvariable=self.name_var, width=40)
        self.name_entry.pack(side="left", padx=6)

        pending = self._parent.pending
        detail_row = tk.Frame(body, background=PAGE_BG)
        detail_row.pack(fill="x", pady=(0, 10))
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

        scroll = ttk.Scrollbar(body, orient="vertical")
        outline = tk.Frame(body, background=BORDER)
        self.text = tk.Text(
            outline, wrap="word", yscrollcommand=scroll.set, borderwidth=0,
            highlightthickness=0, font="TkDefaultFont",
        )
        scroll.config(command=self.text.yview)
        scroll.pack(side="right", fill="y")
        outline.pack(side="left", fill="both", expand=True)
        self.text.pack(fill="both", expand=True, padx=1, pady=1)  # 1px border
        self.text.insert("1.0", self._parent.pending["description"])
        (self.text if self.name_var.get() else self.name_entry).focus_set()

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
            "description": self.text.get("1.0", "end").strip(),
        }


class SwotEditor(_SubEditor):
    """Strengths, weaknesses, opportunities and threats: four boxes, one text each."""

    title_text = "SWOT"
    other = "description"

    def __init__(self, parent: IdeaEditor, commit, goto):
        super().__init__(parent, commit, goto)
        self.title(parent.pending["name"] or "New idea")  # window title: the idea's name

    def _build_body(self, body: tk.Frame) -> None:
        body.columnconfigure(0, weight=1)
        self.texts: dict[str, tk.Text] = {}
        for row, field in enumerate(SWOT_FIELDS):
            body.rowconfigure(row, weight=1, uniform="swot")
            outline, box = _titled_box(body, field.capitalize())
            outline.grid(row=row, column=0, sticky="nsew", pady=3)
            # The focus ring is the Text's highlight: 1px, and light (white when idle).
            text = tk.Text(
                box, wrap="word", height=3, borderwidth=0, highlightthickness=1,
                highlightbackground="white", highlightcolor=FOCUS_RING,
            )
            text.insert("1.0", self._parent.pending[field])
            text.pack(fill="both", expand=True)
            self.texts[field] = text
        self.texts[SWOT_FIELDS[0]].focus_set()

    def _values(self) -> dict[str, str]:
        return {f: t.get("1.0", "end").strip() for f, t in self.texts.items()}


class GuideWindow(tk.Toplevel):
    """The user guide: a read-only, scrollable text. Not modal."""

    CONTENT = "The user guide will go here."

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
        self.text.insert("1.0", self.CONTENT)
        self.text.config(state="disabled")  # read-only

    def request_close(self) -> None:
        """Command-W."""
        self.destroy()


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
        """Close the active window: a dialog is cancelled, the main window quits."""
        try:
            focused = self.focus_get()
        except KeyError:  # tkinter can't name some native popups
            focused = None
        window = focused.winfo_toplevel() if focused else self.grab_current()
        window = window or self.winfo_toplevel()
        getattr(window, "request_close", window.destroy)()

    def _new_idea_soon(self) -> None:
        # Not inside the menu's own callback: a modal dialog opened (and waited on)
        # from within a native macOS menu action can leave the app unresponsive.
        self.after(50, self.new_idea)

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
        if idea is not None and col_id == "name":
            return idea.description.strip()  # no description, no tooltip
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
        start_on_description: bool = False,
    ) -> IdeaEditor:
        editor = IdeaEditor(self, idea, can_delete, save_fields, start_on_description)
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

        saved = self._edit(idea, save_fields=save_fields, start_on_description=True).saved
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
