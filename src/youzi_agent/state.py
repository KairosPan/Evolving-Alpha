"""Parent + sub-graph TypedDicts."""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal, Optional, TypedDict


class ThemeProfile(TypedDict, total=False):
    name: str
    members: list[str]
    leader: Optional[str]
    catalysts: list[str]
    phase: Literal["budding", "horizontal", "vertical", "switching", "exhausted"]
    resonance_score: float


class LeaderProfile(TypedDict, total=False):
    code: str
    name: str
    consec_boards: int
    role: Literal["total", "capacity", "complement", "companion"]
    sealed_amount: float
    blast_today: bool
    div_count: int


class PatternHit(TypedDict):
    pattern_id: str
    filter_desc: str
    target_subagent: str


class Candidate(TypedDict, total=False):
    code: str
    name: str
    pattern_id: str
    score: float
    reason: str
    suggested_position: float
    consec_boards: int


class TradePlan(TypedDict, total=False):
    date: str
    position_total_max: float
    candidates: list[Candidate]
    avoid_list: list[str]
    notes: str


EmotionPhase = Literal[
    "chaos", "recovery", "warming", "main_rise",
    "climax", "divergence", "decay_1", "decay_mid", "decay_2",
]
IndexPhase = Literal["uptrend", "top", "downtrend", "bottom", "oscillation"]
SuccessionStatus = Literal["healthy", "first_div", "second_div", "broken", "trans"]
ThemeAxis = Literal["horizontal", "vertical", "switching", "exhausted"]


class MarketState(TypedDict, total=False):
    target_date: str
    use_llm: bool
    raw: dict

    index_phase: IndexPhase
    sz_macd: dict
    cyb_macd: dict
    market_volume: float
    big_cap_volume_ratio: float

    five_day_pos: Literal["above", "top_horizontal", "below", "bottom_grinding"]
    money_effect: Literal["positive", "neutral", "negative"]
    is_new_cycle_day: bool
    is_only_rebound: bool

    emotion_phase: EmotionPhase
    sentiment_value: int
    limit_up_count: int
    consec_top: int
    blast_rate: float

    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    theme_axis: ThemeAxis
    leader_stack: list[LeaderProfile]
    succession_status: SuccessionStatus

    pattern_hits: Annotated[list[PatternHit], add]
    candidates: Annotated[list[Candidate], add]
    final_candidates: list[Candidate]
    arb_opportunities: Annotated[list[Candidate], add]
    risk_flags: Annotated[list[str], add]
    plan: Optional[TradePlan]

    review: Optional[dict]
    errors: Annotated[list[str], add]


class FirstBoardState(TypedDict, total=False):
    target_date: str
    pattern_hits: list[PatternHit]
    raw: dict
    leader_stack: list[LeaderProfile]
    themes: dict[str, ThemeProfile]
    main_theme: Optional[str]
    candidates: Annotated[list[Candidate], add]
    errors: Annotated[list[str], add]
    # private intra-subgraph keys
    _fb_pool: list[dict]
    _fb_scored: list[dict]


class WeakToStrongState(FirstBoardState):
    _w2s_pool: list[dict]
    _w2s_scored: list[dict]


class ContinuousState(FirstBoardState):
    _con_pool: list[dict]
    _con_scored: list[dict]


class SetbackReversalState(FirstBoardState):
    pass
