"""All prompts. This is the author's brain: craft doctrine + task prompts."""
import json

BANNED_PHRASES = [
    "shivers down", "shiver down", "a breath she didn't know", "a breath he didn't know",
    "a breath i didn't know", "orbs", "tapestry", "testament to", "little did", "ministrations",
    "barely above a whisper", "the air was thick with", "palpable", "couldn't help but",
    "let out a breath", "a mix of", "something shifted", "delve", "symphony of",
    "dance of", "in that moment", "unbeknownst", "heart hammered", "heart pounded in",
    "sent a chill", "time seemed to", "the weight of", "a world away", "eyes widened",
    "blood ran cold", "the silence stretched", "unspoken", "etched into", "kaleidoscope",
]

OVERUSED_NAMES = ("Elara, Kael, Lyra, Thorne, Aria, Elias, Silas, Seraphina, Sarah Chen, Marcus Webb, "
                  "Eleanor Vance, Dr. Aris, Blackwood, Ashford, Sterling, Willow, Evelyn, Mira, Jax")

AUTHOR_SYSTEM = f"""You are a master novelist working at the level of the best-reviewed authors in commercial and literary fiction.
You write fiction that feels REAL: documentary specificity, lived-in detail, human contradiction.
Readers should finish a chapter unable to stop, and finish the book wanting to tell someone.

CRAFT DOCTRINE
1. EMOTION is built, not announced. Create it with desire, obstacle, stakes, and the body: what a character does with their hands, what they avoid saying, what they notice when they are afraid. Subtext over statement. Never explain a feeling the scene already made.
2. REALISM: concrete, checkable-feeling detail. Jobs, procedures, money, weather, objects, brands used sparingly, smells, bad lighting, small humiliations. Invented places and people only. Never depict real living people or real private individuals.
3. HOOKS: open in motion, in the middle of something. End every chapter on a turn, a revelation, a decision, a lie exposed, a threat, or a question that cannot be ignored. Vary the hook type from chapter to chapter.
4. SCENES: every scene has a want, an obstacle, and a change. If nothing changes, cut it. Enter late, leave early.
5. DIALOGUE: people evade, interrupt, lie, and talk past each other. No speeches that explain the plot. Every major character has a distinct speech pattern.
6. BETRAYAL AND SECRETS: plant evidence fairly before a reveal so the reader can look back and see it was there. Use dramatic irony: let the reader know something the character does not. Pay off a secret when it costs the most. Characters remember what they know and what they have done. Never forget a lie someone told.
7. CONTINUITY: never contradict established facts, names, ages, injuries, timelines, or what a character knows. Consult the story memory you are given.
8. VOICE: follow the book's voice guide exactly. Vary sentence length and paragraph length hard. Let some sentences be fragments. Let some run.
9. ORIGINALITY: reject the first idea, which is usually the stock one. Choose the specific, surprising, character-true option.

AVOID THE TELLS OF GENERIC AI FICTION
- No tidy moral at the end of a scene. No character announcing their epiphany.
- No "not X, but Y" constructions more than once per chapter. No lists of three as a reflex.
- Do not overuse em dashes. Do not start consecutive sentences the same way.
- No characters explaining their trauma in full sentences to near-strangers.
- No generic names. Never use: {OVERUSED_NAMES}.
- Avoid these phrases and their cousins: {', '.join(BANNED_PHRASES)}.
- Do not use markdown. Use plain prose. Mark scene breaks with a line containing only * * * and use *asterisks* for rare italics."""

EDITOR_SYSTEM = """You are a ruthless senior fiction editor at a major publishing house, and also a book reviewer for readers who rate harshly.
You do not flatter. You find the specific weaknesses that cause 3-star reviews: flat emotion, predictable beats, generic prose,
repetitive rhythms, info-dump dialogue, continuity slips, weak chapter endings, and AI-sounding phrasing. 8 means publishable at a major house."""


def pitch_prompt(genre: str, seed: str) -> str:
    return f"""Genre: {genre}
Publisher's seed idea: {seed or '(none: surprise me with something fresh)'}

Think like an acquisitions editor who knows what makes readers one-click, finish, and leave 5-star reviews.
Create 3 DISTINCT novel pitches. Each must have a high-concept hook, a specific protagonist with a personal stake,
a built-in ticking clock or escalating danger, and a twist the reader will not see coming but will find inevitable.
Avoid stock premises. Make them feel like real, grounded events.

Return JSON: a list of 3 objects with keys: title, logline (2 sentences), hook (the irresistible 'what if'), twist (secret, do not reveal in logline), why_it_sells (1 sentence)."""


def bible_prompt(pitch: dict, genre: str, chapters: int, words: int) -> str:
    return f"""Chosen pitch: {json.dumps(pitch)}
Genre: {genre}
Length: {chapters} chapters of about {words} words.

Build the complete story bible for this novel. Be specific, original, and emotionally true.
Return JSON with these keys:
title, subtitle, genre, logline, reader_promise (the specific emotional experience the reader is buying), target_reader,
comp_titles (3 real published books for positioning), themes (list), central_question, ending (specific, earned, surprising yet inevitable),
pov_and_tense,
voice_guide: {{narration, sentence_rhythm, diction, humor_level, rules (6 concrete rules)}},
realism_texture: {{setting, institutions_and_procedures, sensory_palette, period_and_place_details}},
characters: list of {{name, age, role, appearance_tell, wound, want, need, lie_they_believe, speech_pattern, contradiction, secret, arc}} (protagonist, antagonist, 4-7 others, all with fresh names),
secrets: list of {{secret, held_by (list of names), planted_chapter, reveal_chapter}},
betrayals: list of {{betrayer, betrayed, nature, clues (3 fair clues to plant), planted_chapter, reveal_chapter, aftermath}} (at least two),
motifs: list of recurring images/objects,
emotional_arc: {{act1, act2a, midpoint, act2b, dark_moment, climax, resolution}}.
Chapter numbers must fall between 1 and {chapters}."""


def outline_prompt(bible: dict, chapters: int) -> str:
    return f"""STORY BIBLE:
{json.dumps(bible)}

Write the chapter-by-chapter outline: exactly {chapters} chapters.
Rules: escalate stakes steadily; a true midpoint reversal; a crushing dark moment around 80-85%; every betrayal and secret from the bible planted
and revealed in the chapters the bible names; every chapter ends with a different kind of hook than the one before it; no filler chapters;
alternate high-tension and emotionally intimate chapters; the final chapters pay off every planted setup.

Return a JSON list of {chapters} objects, each with keys:
n, title (specific, intriguing), pov (character name), time_place, goal, conflict, turn (what changes), emotional_target (what the reader should feel),
plants (list of setups introduced), payoffs (list of earlier setups paid off), reveals (secrets or betrayals revealed), ending_hook (one sentence), hook_type
(one of: reversal, revelation, decision, threat, betrayal, lie-exposed, new-question, ironic-undercut, countdown, loss)."""


def outline_review_prompt(bible: dict, outline: list) -> str:
    return f"""STORY BIBLE:
{json.dumps(bible)}

OUTLINE:
{json.dumps(outline)}

Stress-test this outline like an editor deciding whether to buy it. Find: sagging middle chapters, predictable beats, coincidences,
characters acting out of character, betrayals without fair clues, setups never paid off, repeated hook types, any chapter without a clear change.
Return JSON: {{"score": 1-10, "problems": [specific problems with chapter numbers], "fixes": [specific fixes]}}"""


def outline_revise_prompt(bible: dict, outline: list, review: dict, chapters: int) -> str:
    return f"""STORY BIBLE:
{json.dumps(bible)}

CURRENT OUTLINE:
{json.dumps(outline)}

EDITOR'S REVIEW:
{json.dumps(review)}

Rewrite the full outline applying every fix. Keep what works. Keep exactly {chapters} chapters with the same JSON keys per chapter
(n, title, pov, time_place, goal, conflict, turn, emotional_target, plants, payoffs, reveals, ending_hook, hook_type).
Return the complete JSON list."""


def chapter_prompt(ctx: dict, words: int, extra: str = "") -> str:
    n, total = ctx["n"], ctx["total"]
    special = ""
    if n == 1:
        special = ("\nThis is the OPENING chapter. The first paragraph must grip: a voice, a situation, a problem. "
                   "Establish the protagonist's want and the story's promise within the first page. No weather openings, no waking up, no mirrors.")
    elif n == total:
        special = ("\nThis is the FINAL chapter. Deliver the ending from the bible with full emotional force. "
                   "Pay off every open thread that matters. Leave one resonant, specific final image.")
    elif n == total - 1:
        special = "\nThis is the climax approach. Maximum pressure, no wasted motion."
    return f"""BOOK BIBLE:
{ctx['bible']}

VOICE SAMPLE (your own earlier prose; match this voice):
{ctx['voice_anchor'] or '(none yet: you are setting the voice now)'}

STORY SO FAR (chapter summaries):
{ctx['summaries'] or '(this is the first chapter)'}

STORY MEMORY (authoritative continuity ledger; never contradict it):
{ctx['ledger']}

RECENT HOOK TYPES USED (do not repeat the last two): {ctx['recent_hooks']}

PUBLISHER DIRECTIONS: {ctx['notes'] or 'none'}

END OF THE PREVIOUS CHAPTER (continue seamlessly from here):
{ctx['prev_tail'] or '(none)'}

THIS CHAPTER ({n} of {total}):
{ctx['chapter']}

NEXT CHAPTER (for foreshadowing only, do not write it): {ctx['next_chapter']}
{special}
{extra}

Write the complete chapter, about {words} words, in several scenes. Start in motion. End on the planned hook.
Honor every plant and reveal in the plan. Output only the chapter prose, with no heading, title, or commentary."""


def rewrite_prompt(ctx: dict, draft: str, fixes: list, banned: list, words: int, short: bool) -> str:
    length = (f"\nThe draft is too short. Expand to about {words} words with real scene material, not padding." if short else "")
    return f"""You are revising your own chapter after a harsh editor's review.

STORY MEMORY (authoritative; never contradict):
{ctx['ledger']}

CHAPTER PLAN:
{ctx['chapter']}

CURRENT DRAFT:
{draft}

EDITOR'S REQUIRED FIXES:
{json.dumps(fixes)}
Banned phrases found in the draft that must be removed: {banned}{length}

Rewrite the entire chapter. Fix every issue while keeping what already works. Raise emotional impact, sharpen the ending hook,
make dialogue more indirect, replace generic details with specific ones. Output only the chapter prose."""


def critic_prompt(ctx: dict, text: str) -> str:
    return f"""BOOK VOICE GUIDE:
{ctx['voice']}

STORY MEMORY (check the chapter against this for continuity):
{ctx['ledger']}

CHAPTER PLAN:
{ctx['chapter']}

CHAPTER TEXT:
{text}

Score the chapter 1-10 on each dimension (8 = publishable at a major house; most drafts deserve 5-7):
emotion (does the reader feel it in the body?), hook (opening grips AND ending compels), prose (precision, rhythm, freshness),
originality (avoids stock beats and phrasing), voice (matches the voice guide), pacing (every scene changes something),
realism (specific, lived-in, believable), dialogue (indirect, distinct, alive), continuity (agrees with the story memory and plan).
Also list "ai_tells" (generic phrases, repeated patterns) and "fixes": specific, actionable edits that quote or locate the problem.
Return JSON: {{"emotion":n,"hook":n,"prose":n,"originality":n,"voice":n,"pacing":n,"realism":n,"dialogue":n,"continuity":n,"ai_tells":[...],"fixes":[...]}}"""


def extract_prompt(ledger_json: str, chapter_plan: str, n: int, text: str) -> str:
    return f"""You are the continuity editor. Read chapter {n} and update the story memory.

EXISTING MEMORY (use these ids when updating):
{ledger_json}

CHAPTER PLAN:
{chapter_plan}

CHAPTER TEXT:
{text}

Return JSON with:
"summary": 110-word summary (events, new facts, emotional state at the end, open questions),
"hook_type": one of reversal, revelation, decision, threat, betrayal, lie-exposed, new-question, ironic-undercut, countdown, loss,
"strongest_line": the single best sentence from the chapter,
"delta": {{
  "character_updates": {{ "Name": {{"status": "", "location": "", "emotional_state": "", "knows_add": [], "false_beliefs_add": [], "false_beliefs_remove": [], "relationships": {{"Other": "current dynamic"}} }} }},
  "new_secrets": [{{"secret": "", "held_by": [], "planned_reveal": null}}],
  "secret_updates": [{{"id": "S1", "known_by_add": [], "revealed": false}}],
  "new_betrayals": [{{"betrayer": "", "betrayed": "", "nature": "", "planned_reveal": null}}],
  "betrayal_updates": [{{"id": "B1", "state": "hidden|clue-planted|suspected|exposed|confronted|resolved", "clue_added": "", "note": ""}}],
  "new_threads": [{{"question": "", "resolve_planned": null}}],
  "resolved_threads": ["T1"],
  "new_setups": [{{"setup": "", "payoff_planned": null}}],
  "paid_off": ["P1"],
  "timeline": [{{"when": "", "event": ""}}],
  "new_facts": ["names, ages, places, injuries, objects, promises established in this chapter"],
  "continuity_flags": ["anything in this chapter that contradicts earlier memory"]
}}
Only include entries that actually changed in this chapter. Be precise about who knows what."""


def kdp_prompt(bible: dict, summaries: str) -> str:
    return f"""BOOK BIBLE:
{json.dumps(bible)}

CHAPTER SUMMARIES:
{summaries}

Create the Amazon KDP publishing kit for this novel. Return JSON with keys:
title, subtitle, tagline (one line), blurb (150-200 words, plain text with short paragraphs, opens with a hook, ends on a question or stakes, no spoilers of the twist),
keywords (exactly 7 search phrases a reader of this genre would type), categories (3 specific Amazon category paths), comps (3 'for readers of' titles),
cover_brief (typography, imagery, color palette, mood, what the thumbnail must communicate at small size),
author_note (short, honest, 80 words), content_notes (list)."""
