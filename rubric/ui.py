"""Tkinter desktop UI: comparison table and idea editor."""

import tkinter as tk
from tkinter import messagebox, ttk

from .rubric import CRITERIA, MAX_SCORE, MIN_SCORE
from .scoring import total_score
from .storage import STATUSES, Idea, Storage, StorageError

UNSCORED = 0


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

        ttk.Label(head, text="Description").grid(row=2, column=0, sticky="nw")
        self.desc_text = tk.Text(head, height=3, wrap="word")
        self.desc_text.insert("1.0", self.idea.description)
        self.desc_text.grid(row=2, column=1, sticky="ew", padx=6, pady=2)

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

        self.score_vars: dict[str, tk.IntVar] = {}
        self.reason_texts: dict[str, tk.Text] = {}
        for c in CRITERIA:
            self._build_criterion(body, c)

    def _build_criterion(self, parent: ttk.Frame, c) -> None:
        box = ttk.LabelFrame(parent, text=f"{c.name}  (weight {c.weight:g})", padding=8)
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
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right", padx=6)

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Give the idea a name.", parent=self)
            return
        idea = self.idea
        idea.name = name
        idea.status = self.status_var.get()
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


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, storage: Storage, ideas: list[Idea]):
        super().__init__(root, padding=10)
        self.storage = storage
        self.ideas = ideas
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

        cols = ("name", "status", "total") + tuple(c.id for c in CRITERIA)
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="Idea")
        self.tree.heading("status", text="Status")
        self.tree.heading("total", text="Total")
        self.tree.column("name", width=240, minwidth=160)
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("total", width=90, anchor="center")
        for c in CRITERIA:
            self.tree.heading(c.id, text=c.name)
            self.tree.column(c.id, width=130, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_edit_state())

    def refresh(self) -> None:
        def sort_key(idea: Idea):
            total = total_score(idea.scores)
            return (total is None, -(total or 0), idea.name.lower())

        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for idea in sorted(self.ideas, key=sort_key):
            total = total_score(idea.scores)
            row = [
                idea.name,
                idea.status,
                "incomplete" if total is None else f"{total:.1f}",
            ]
            row += [idea.scores.get(c.id, "–") for c in CRITERIA]
            self.tree.insert("", "end", iid=idea.id, values=row)
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self._update_edit_state()

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
        idea = Idea(name="")
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


def _center(root: tk.Tk, width: int, height: int) -> None:
    """Size the window (capped to the screen), centered horizontally near the top."""
    width = min(width, root.winfo_screenwidth() - 40)
    height = min(height, root.winfo_screenheight() - 80)
    x = (root.winfo_screenwidth() - width) // 2
    y = 60
    root.geometry(f"{width}x{height}+{x}+{y}")


def main() -> None:
    root = tk.Tk()
    root.title("Rubric")
    _center(root, 1460, 480)
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
    App(root, storage, ideas)
    root.mainloop()
