"""Roast: a council of five personas attacks an idea, then a Judge gives one verdict.

This is the /roast skill (admin/SKILL (roast).md) as plain Messages API calls: five
persona calls in parallel, then one Judge call over their reports.
"""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic

from . import apikey
from .storage import DESCRIPTION_FIELDS, Idea

PERSONA_MODEL = "claude-sonnet-5-5"
JUDGE_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
MAX_CONTINUATIONS = 5  # re-sends after a web search pauses the turn
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

VERDICTS = ("GO", "RESHAPE", "KILL")

BRIEF_LABELS = {
    "concept": "The idea",
    "customer": "Who it's for and how it makes money",
    "edge": "The founder's edge",
    "constraints": "Constraints",
}


class RoastError(Exception):
    """A roast can't run or finish. The message is safe to show the user."""


@dataclass(frozen=True)
class Persona:
    name: str
    mandate: str
    tools: tuple = ()


PERSONAS = (
    Persona(
        "Contrarian",
        "You are the Contrarian on an idea council. Assume this idea fails. Your job is "
        "to find the fatal flaws, the fastest way it dies, and the load-bearing "
        "assumptions that are probably wrong. Be ruthless and specific. No hedging, no "
        '"but it could work." Attack the weakest points.',
    ),
    Persona(
        "Expansionist",
        "You are the Expansionist on an idea council. Make the strongest possible case "
        "FOR this idea. Find the biggest upside, the 10x version, the adjacent "
        "opportunities and unlock points the founder isn't seeing. Fight for the "
        "potential. Be specific about where the real money and leverage could be.",
    ),
    Persona(
        "Logician",
        "You are the Logician on an idea council. Use NO outside research and NO web. "
        "Reason purely from first principles: does the core mechanism make sense, do the "
        "incentives line up, is the underlying logic sound, does the math even work in "
        "theory? Strip it to fundamentals and tell us if it holds together.",
    ),
    Persona(
        "Researcher",
        "You are the Researcher on an idea council. Use web search. Bring real-world "
        "evidence: who the existing competitors are, market size or demand signals, what "
        "comparable products charge, whether this is validated by what's already out "
        "there or contradicted by it. Cite what you find. Is the real world saying yes "
        "or no?",
        tools=(WEB_SEARCH,),
    ),
    Persona(
        "Buyer",
        "You are the Buyer on an idea council. Role-play the exact target customer "
        "described in the brief. React as them, in first person. Would you actually pay "
        "for this? What's your real objection? What would make you choose a competitor or "
        "just do nothing instead? What price feels right, and what would make you say "
        "yes today? Be the honest, slightly skeptical customer, not a cheerleader.",
    ),
)

PERSONA_FORMAT = (
    "Stay in character; do not hedge or soften. Reply in this shape:\n"
    "STANCE: one line.\n"
    "POINTS: your 3-5 sharpest points.\n"
    "MUST HEAR: the single most important thing the user must hear.\n"
    "The last line must be exactly `SCORE: N/10`, your score on your own dimension "
    "(1 = walk away, 10 = no-brainer)."
)

JUDGE_SYSTEM = """\
You are the Judge on an idea council. Five personas have attacked and defended an idea; \
you read their reports, weigh them, and deliver one decisive verdict. Do not just \
average the scores. Name the real tension between the personas and resolve it.

Fold in the economics lens yourself: rough pricing, realistic time-to-first-dollar, and \
whether the founder can actually ship this fast given the edge they described.

You must make an actual call. "It depends" is not a verdict: pick GO, RESHAPE, or KILL \
and own it. The cheapest 48-hour test is the most important output: the smallest, \
fastest thing the founder can do to validate the riskiest assumption BEFORE building \
anything. Keep it skimmable.

Output exactly this shape:

## THE VERDICT: GO / RESHAPE / KILL
Confidence: [low / medium / high]

**The call in one line:** [the decision, plainly]

**Why:** [2-3 sentences resolving the council's tension]

**Biggest risk:** [the single thing most likely to kill it]
**Biggest upside:** [the strongest reason to do it]

**Money read:** [rough price, time-to-first-dollar, can they ship fast]

**The cheapest 48-hour test:** [the smallest, fastest thing they can do to validate the riskiest assumption BEFORE building anything]

**If RESHAPE:** [the specific pivot that fixes the fatal flaw while keeping the upside]

Pick one of GO, RESHAPE or KILL in the heading (not all three). Omit the "If RESHAPE" \
line unless the verdict is RESHAPE."""


def missing_fields(idea: Idea) -> list[str]:
    """Titles of the description boxes still empty; a roast needs all four."""
    return [BRIEF_LABELS[f] for f in DESCRIPTION_FIELDS if not getattr(idea, f).strip()]


def build_brief(idea: Idea) -> str:
    """The one short brief pasted into every council member's prompt."""
    parts = [f"{BRIEF_LABELS[f]}: {getattr(idea, f).strip()}" for f in DESCRIPTION_FIELDS]
    return f"{idea.name.strip()}\n" + "\n".join(parts)


def parse_score(text: str) -> int | None:
    """The persona's final `SCORE: N/10`, or None if it didn't give one."""
    found = re.findall(r"SCORE:\s*\**\s*(\d{1,2})\s*/\s*10", text, re.IGNORECASE)
    return min(max(int(found[-1]), 1), 10) if found else None


def parse_verdict(text: str) -> tuple[str, str]:
    """(verdict, confidence) from the Judge's report; "" for whatever isn't found."""
    verdict = re.search(r"THE VERDICT:\s*\**\s*(GO|RESHAPE|KILL)\b", text, re.IGNORECASE)
    confidence = re.search(r"Confidence:\s*\**\s*(low|medium|high)\b", text, re.IGNORECASE)
    return (
        verdict.group(1).upper() if verdict else "",
        confidence.group(1).lower() if confidence else "",
    )


@dataclass
class RoastResult:
    verdict: str  # GO / RESHAPE / KILL, or "" if the Judge's report had none
    confidence: str
    report: str  # the Judge's full report
    reports: dict[str, str] = field(default_factory=dict)  # persona -> its report
    scores: dict[str, int] = field(default_factory=dict)  # persona -> score
    failed: dict[str, str] = field(default_factory=dict)  # persona -> why it's missing

    def to_dict(self) -> dict:
        """What is stored on the idea."""
        return dict(vars(self))


def _text(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text").strip()


def _ask(client, *, model: str, system: str, user: str, tools=(), effort: str = "medium") -> str:
    """One streamed call, resumed while a web search pauses the turn. Returns its text."""
    messages = [{"role": "user", "content": user}]
    for _ in range(MAX_CONTINUATIONS + 1):
        kwargs = {"tools": list(tools)} if tools else {}
        with client.messages.stream(
            model=model, max_tokens=MAX_TOKENS, system=system, messages=messages,
            output_config={"effort": effort}, **kwargs,
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise RoastError("The model declined to answer.")
        if message.stop_reason != "pause_turn":
            text = _text(message)
            if not text:
                raise RoastError("The model returned no text.")
            return text
        messages.append({"role": "assistant", "content": message.content})
    raise RoastError("The web search didn't finish.")


def _explain(e: Exception) -> str:
    """A short, key-free reason for a failed call."""
    if isinstance(e, RoastError):
        return str(e)
    if isinstance(e, anthropic.AuthenticationError):
        return "The API key was rejected."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "The API key isn't allowed to do this."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate limited; try again in a minute."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach the API."
    if isinstance(e, anthropic.APIStatusError):
        return f"API error {e.status_code}: {e.message}"
    return f"{type(e).__name__}"


def make_client() -> anthropic.Anthropic:
    try:
        key = apikey.get_key()
    except apikey.ApiKeyError as e:
        raise RoastError(str(e)) from e
    if not key:
        raise RoastError("No API key. Add one with File > API Key…")
    # The five persona calls run together, so ride out brief rate limits.
    return anthropic.Anthropic(api_key=key, max_retries=4)


def run_council(
    idea: Idea, client=None, on_progress: Callable[[str, str], None] | None = None
) -> RoastResult:
    """Roast `idea`. `on_progress(who, state)` is called from worker threads, with
    who a persona name or "Judge" and state "working", "done" or "failed".
    """
    missing = missing_fields(idea)
    if missing:
        raise RoastError("Fill in these first: " + "; ".join(missing) + ".")
    client = client or make_client()
    brief = build_brief(idea)
    note = on_progress or (lambda who, state: None)

    def consult(persona: Persona) -> str:
        note(persona.name, "working")
        return _ask(
            client, model=PERSONA_MODEL, system=f"{persona.mandate}\n\n{PERSONA_FORMAT}",
            user=f"THE BRIEF:\n{brief}", tools=persona.tools,
        )

    reports: dict[str, str] = {}
    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(PERSONAS)) as pool:
        futures = {p.name: pool.submit(consult, p) for p in PERSONAS}
        for name, future in futures.items():
            try:
                reports[name] = future.result()
                note(name, "done")
            except Exception as e:  # one failed persona must not sink the roast
                failed[name] = _explain(e)
                note(name, "failed")
    if not reports:
        raise RoastError("Every council member failed. " + next(iter(failed.values())))

    scores = {n: s for n, t in reports.items() if (s := parse_score(t)) is not None}
    sections = [f"### {name}\n{text}" for name, text in reports.items()]
    if failed:
        sections.append("Missing from the council: " + ", ".join(failed) + ".")
    note("Judge", "working")
    try:
        report = _ask(
            client, model=JUDGE_MODEL, system=JUDGE_SYSTEM, effort="high",
            user=f"THE BRIEF:\n{brief}\n\nTHE COUNCIL'S REPORTS:\n\n" + "\n\n".join(sections),
        )
    except Exception as e:
        note("Judge", "failed")
        raise RoastError(f"The Judge failed: {_explain(e)}") from e
    note("Judge", "done")
    verdict, confidence = parse_verdict(report)
    return RoastResult(verdict, confidence, report, reports, scores, failed)
