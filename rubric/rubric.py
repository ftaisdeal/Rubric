"""The rubric: criteria, weights, and what each score level means.

Edit this file to change the rubric. Criterion ids are stored in the data
file, so don't rename an id once you've scored ideas with it. Weights are
percentages and the defaults must total 100; each idea can override them.
"""

from dataclasses import dataclass

MIN_SCORE = 1
MAX_SCORE = 5


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    weight: float  # default percentage; see Idea.weights for per-idea overrides
    levels: tuple[str, str, str, str, str]  # descriptions for scores 1..5


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        "market_size", "Market Size", 14,
        (
            "Tiny niche; few potential customers",
            "Small market; limited room to grow",
            "Moderate market; enough for a good business",
            "Large market; many potential customers",
            "Huge market; billions in potential revenue",
        ),
    ),
    Criterion(
        "solution_importance", "Solution Importance", 20,
        (
            "Nice-to-have; nobody would notice if it vanished",
            "Mild annoyance; people tolerate it",
            "Real problem; some people actively look for fixes",
            "Painful problem; people pay for workarounds today",
            "Critical problem; people urgently need a solution",
        ),
    ),
    Criterion(
        "competition", "Competition", 14,
        (
            "Dominated by entrenched incumbents; no opening",
            "Crowded; hard to stand out",
            "Competitive, but there is room for a differentiated offer",
            "Few competitors, none serving the segment well",
            "No real competition; open field",
        ),
    ),
    Criterion(
        "founder_fit", "Founder Fit", 14,
        (
            "No relevant skills, interest or network",
            "Little relevant experience; steep learning curve",
            "Some relevant skills; gaps could be filled",
            "Strong skills and genuine interest in the domain",
            "Ideal fit: deep expertise, passion and a network",
        ),
    ),
    Criterion(
        "startup_cost", "Startup Cost", 10,
        (
            "Requires major capital before any revenue",
            "Requires substantial outside funding",
            "Affordable with savings, but a real commitment",
            "Low cost; can bootstrap comfortably",
            "Almost free to start",
        ),
    ),
    Criterion(
        "time_to_revenue", "Time to Revenue", 10,
        (
            "Several years before any revenue",
            "More than a year to first revenue",
            "Six to twelve months to first revenue",
            "A few months to first revenue",
            "Revenue within weeks",
        ),
    ),
    Criterion(
        "scalability", "Scalability", 10,
        (
            "Revenue grows only with proportional effort",
            "Limited scaling; mostly linear with effort",
            "Scales moderately with some added headcount",
            "Scales well; costs grow slower than revenue",
            "Highly scalable; near-zero marginal cost",
        ),
    ),
    Criterion(
        "defensibility", "Defensibility", 8,
        (
            "Trivially copied; no moat",
            "Easy to copy; weak advantages",
            "Some advantages (brand, relationships) that take time to copy",
            "Meaningful moat such as switching costs or proprietary data",
            "Strong, durable moat (network effects, IP, scale)",
        ),
    ),
)

CRITERIA_BY_ID: dict[str, Criterion] = {c.id: c for c in CRITERIA}

DEFAULT_WEIGHTS: dict[str, int] = {c.id: int(c.weight) for c in CRITERIA}
