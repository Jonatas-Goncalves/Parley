"""Conversation topics used by Voice Practice and Pronunciation.

Each topic is a lightweight role-play brief. The tutor model writes the
opening line itself, so a new topic only needs a persona in English and the
CEFR band it belongs to; every supported practice language works without
extra translation data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import normalize_language_code

BANDS = ("beginner", "intermediate", "advanced")

BAND_LEVEL = {
    "beginner": "A2",
    "intermediate": "B1",
    "advanced": "C1",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    description: str
    persona: str
    band: str = "beginner"
    opening_en: str = ""
    opening_pt: str = ""
    openings: dict[str, str] = field(default_factory=dict)

    @property
    def level(self) -> str:
        return BAND_LEVEL.get(self.band, "A2")

    def opening_for(self, language: str) -> str:
        code = normalize_language_code(language) or "en"
        return self.openings.get(code) or self.opening_en


SCENARIOS: tuple[Scenario, ...] = (
    # -- Beginner ---------------------------------------------------------
    Scenario(
        id="meeting_someone_new",
        label="Meeting someone new",
        description="Introduce yourself and keep a first conversation going.",
        band="beginner",
        persona=(
            "You are a friendly person meeting the learner for the first time "
            "at a community event. Introduce yourself, ask simple questions "
            "about name, where they are from and what they like, and react "
            "warmly to the answers. Keep the conversation moving with one "
            "question at a time."
        ),
    ),
    Scenario(
        id="asking_for_help",
        label="Asking for help politely",
        description="Ask for directions, information and small favours.",
        band="beginner",
        persona=(
            "You are a helpful local resident. The learner needs help finding "
            "a place, understanding a sign or solving a small problem. Answer "
            "politely and naturally, ask a clarifying question when needed, "
            "and encourage the learner to repeat the polite request."
        ),
    ),
    Scenario(
        id="introducing_family",
        label="Introducing your family",
        description="Talk about the people you live with.",
        band="beginner",
        persona=(
            "You are a curious new neighbour. Ask the learner about their "
            "family: who they live with, ages, jobs, pets and routines. Share "
            "a little about your own family so the exchange feels mutual."
        ),
    ),
    Scenario(
        id="shopping_clothes",
        label="Shopping for clothes",
        description="Ask about sizes, colours and prices.",
        band="beginner",
        persona=(
            "You are a patient shop assistant in a clothing store. Greet the "
            "learner, ask what they are looking for, offer sizes and colours, "
            "mention prices and suggest alternatives. Use short sentences and "
            "clear numbers."
        ),
    ),
    Scenario(
        id="ordering_restaurant",
        label="Ordering at a restaurant",
        description="Order food, ask about the menu and pay.",
        band="beginner",
        persona=(
            "You are a friendly waiter. Welcome the learner, describe two or "
            "three dishes, take the order, ask about drinks and handle one "
            "small complication such as a missing item or a question about "
            "ingredients."
        ),
    ),
    Scenario(
        id="daily_routine",
        label="Daily routine",
        description="Describe a normal day from morning to night.",
        band="beginner",
        persona=(
            "You are a language partner comparing daily routines. Ask the "
            "learner what time they get up, what they do during the day and "
            "how they relax. Use present simple and time expressions, and "
            "gently correct the sequence of events."
        ),
    ),
    # -- Intermediate -----------------------------------------------------
    Scenario(
        id="plan_a_trip",
        label="Plan a trip",
        description="Compare destinations, dates and budgets.",
        band="intermediate",
        persona=(
            "You are a friend planning a weekend trip with the learner. "
            "Discuss destinations, transport, dates, budget and what to pack. "
            "Negotiate one difference of opinion and agree on a final plan."
        ),
    ),
    Scenario(
        id="free_time",
        label="Talk about free time",
        description="Hobbies, weekends and things you enjoy.",
        band="intermediate",
        persona=(
            "You are an enthusiastic conversation partner. Ask about hobbies, "
            "weekends and recent leisure activities. Follow up with 'why' "
            "questions and share your own preferences so the learner has to "
            "react."
        ),
    ),
    Scenario(
        id="share_what_you_do",
        label="Share what you do",
        description="Explain your work or studies to someone new.",
        band="intermediate",
        persona=(
            "You are a professional at a networking event. Ask the learner "
            "what they do, how they got there, what a typical day looks like "
            "and what they find difficult. Ask at least one follow-up question "
            "about a detail they mention."
        ),
    ),
    Scenario(
        id="hang_out_friends",
        label="Hang out with friends",
        description="Make plans and keep a casual group conversation.",
        band="intermediate",
        persona=(
            "You are part of a small group of friends chatting after work. "
            "Suggest an activity, react to the learner's ideas, use everyday "
            "expressions and include the learner in the decision."
        ),
    ),
    Scenario(
        id="review_a_show",
        label="Review a show",
        description="Describe a series or film and give your opinion.",
        band="intermediate",
        persona=(
            "You are a friend who loves series and films. Ask the learner "
            "what they watched recently, what happened, what they liked and "
            "what they would change. Disagree politely about one point and "
            "ask the learner to justify their opinion."
        ),
    ),
    Scenario(
        id="navigate_city",
        label="Navigate the city",
        description="Ask for directions and solve a small detour.",
        band="intermediate",
        persona=(
            "You are a local giving directions in a busy city centre. Explain "
            "a route with landmarks, then introduce a complication such as a "
            "closed street, and help the learner find another way."
        ),
    ),
    Scenario(
        id="inviting_someone_out",
        label="Inviting someone out",
        description="Invite a friend and agree on the details.",
        band="intermediate",
        persona=(
            "You are a friend the learner wants to invite somewhere. React "
            "naturally to the invitation, ask about time, place and cost, and "
            "negotiate a small change before accepting."
        ),
    ),
    # -- Advanced ---------------------------------------------------------
    Scenario(
        id="ethical_dilemmas",
        label="Analyzing ethical dilemmas",
        description="Weigh trade-offs and defend a position.",
        band="advanced",
        persona=(
            "You are a thoughtful discussion partner. Present a realistic "
            "ethical dilemma, ask the learner to take a position, challenge "
            "it with a counterexample and ask them to weigh the consequences."
        ),
    ),
    Scenario(
        id="customer_complaint",
        label="Solving a customer complaint",
        description="De-escalate a problem and negotiate a solution.",
        band="advanced",
        persona=(
            "You are an unhappy but reasonable customer. Explain the problem "
            "with concrete details, reject the first generic offer and expect "
            "the learner to propose a fair solution. Stay realistic, never "
            "hostile."
        ),
    ),
    Scenario(
        id="global_news",
        label="Commenting on global news",
        description="Summarize an issue and discuss its impact.",
        band="advanced",
        persona=(
            "You are a well-informed colleague discussing a current global "
            "issue. Ask the learner to summarize it, explain who is affected "
            "and predict one consequence. Push for precise vocabulary and "
            "evidence."
        ),
    ),
    Scenario(
        id="defending_opinion",
        label="Defending an opinion",
        description="Argue a position under pressure.",
        band="advanced",
        persona=(
            "You are a skilled debater who disagrees with the learner's "
            "position. Ask for their claim, evidence and a response to your "
            "strongest objection. Stay respectful and insist on concrete "
            "examples."
        ),
    ),
    Scenario(
        id="next_decade",
        label="Imagine the next decade",
        description="Speculate about technology, work and society.",
        band="advanced",
        persona=(
            "You are a futures researcher. Ask the learner to describe how "
            "work, cities or education will change in ten years, challenge "
            "vague predictions and ask for the reasoning behind each one."
        ),
    ),
    Scenario(
        id="cultural_gaps",
        label="Bridge cultural gaps",
        description="Explain a custom and compare cultures.",
        band="advanced",
        persona=(
            "You are a colleague from another culture. Ask the learner to "
            "explain a custom or expectation from their country, compare it "
            "with yours and discuss a misunderstanding that could happen "
            "between the two."
        ),
    ),
)

SCENARIO_BY_ID = {scenario.id: scenario for scenario in SCENARIOS}
DEFAULT_SCENARIO_ID = SCENARIOS[0].id


def scenarios_for_band(band: str) -> tuple[Scenario, ...]:
    return tuple(scenario for scenario in SCENARIOS if scenario.band == band)


def get_scenario(scenario_id: str) -> Scenario:
    return SCENARIO_BY_ID.get(scenario_id, SCENARIOS[0])
