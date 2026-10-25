"""The author engine. Pipeline per novel:

  pitches -> story bible -> outline -> editor stress-test -> revised outline
  per chapter: draft -> harsh editor scoring -> rewrites until it passes
               -> continuity editor updates story memory -> save

Every function is synchronous (run it in a thread from the Telegram layer).
"""
import json
import logging
import re

import config
import llm
import memory
import prompts
import storage

log = logging.getLogger(__name__)
DIMS = ["emotion", "hook", "prose", "originality", "voice", "pacing", "realism", "dialogue", "continuity"]


def _noop(msg: str) -> None:
    pass


# ---- helpers -------------------------------------------------------------------
def _clean(text: str) -> str:
    """Strip headings, fences and meta lines the model sometimes adds."""
    text = re.sub(r"```\w*", "", text).strip()
    lines = text.split("\n")
    while lines and (re.match(r"^\s*(#+\s|chapter\s+\d+|\*\*chapter)", lines[0], re.I) or not lines[0].strip()):
        lines.pop(0)
    while lines and re.match(r"^\s*[\(\[]?\s*(word count|end of chapter)", lines[-1], re.I):
        lines.pop()
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _banned(text: str) -> list:
    low = text.lower()
    return [b for b in prompts.BANNED_PHRASES if b in low]


def avg_score(scores: dict):
    vals = [scores[k] for k in DIMS if isinstance(scores.get(k), (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else None


def _norm_outline(o, n_target: int) -> list:
    if isinstance(o, dict):
        o = o.get("outline") or o.get("chapters") or next((v for v in o.values() if isinstance(v, list)), [])
    out = []
    for c in o if isinstance(o, list) else []:
        if isinstance(c, dict):
            c["n"] = len(out) + 1
            c.setdefault("title", f"Chapter {c['n']}")
            c.setdefault("hook_type", "revelation")
            out.append(c)
    if len(out) < max(6, int(n_target * 0.75)):
        raise ValueError(f"outline too short ({len(out)}/{n_target})")
    return out


def _fmt_plan(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False, indent=1)


# ---- 1. pitches ----------------------------------------------------------------
def make_pitches(genre: str, seed: str) -> list:
    data = llm.chat_json(prompts.AUTHOR_SYSTEM, prompts.pitch_prompt(genre, seed),
                         config.MODEL_PLANNER, temperature=1.0, max_tokens=3500)
    if isinstance(data, dict):
        data = data.get("pitches") or next((v for v in data.values() if isinstance(v, list)), [])
    data = [p for p in data if isinstance(p, dict) and p.get("title")]
    if not data:
        raise ValueError("No pitches came back")
    return data[:3]


# ---- 2. bible + outline -------------------------------------------------------------
def build_book(book_id: int, progress=_noop) -> None:
    book = storage.get_book(book_id)
    d = book["data"]
    total = d["chapter_target"]

    progress("🧬 Designing the story bible: characters, secrets, betrayals, voice…")
    bible = llm.chat_json(prompts.AUTHOR_SYSTEM,
                          prompts.bible_prompt(d["pitch"], book["genre"], total, config.WORDS_PER_CHAPTER),
                          config.MODEL_PLANNER, temperature=0.9, max_tokens=9000)
    if not isinstance(bible, dict):
        raise ValueError("Bible was not an object")

    progress(f"🗺 Mapping all {total} chapters with hooks and payoffs…")
    outline = None
    for attempt in range(2):
        try:
            outline = _norm_outline(llm.chat_json(prompts.AUTHOR_SYSTEM, prompts.outline_prompt(bible, total),
                                                  config.MODEL_PLANNER, temperature=0.75, max_tokens=16000), total)
            break
        except ValueError as e:
            log.warning("outline attempt %d failed: %s", attempt + 1, e)
    if outline is None:
        raise ValueError("Could not build a full outline. Tap retry.")

    progress("🔍 Senior editor is stress-testing the plot…")
    try:
        review = llm.chat_json(prompts.EDITOR_SYSTEM, prompts.outline_review_prompt(bible, outline),
                               config.MODEL_EDITOR, temperature=0.3, max_tokens=3000)
        revised = _norm_outline(llm.chat_json(prompts.AUTHOR_SYSTEM,
                                              prompts.outline_revise_prompt(bible, outline, review, total),
                                              config.MODEL_PLANNER, temperature=0.6, max_tokens=16000), total)
        if len(revised) >= int(len(outline) * 0.9):
            outline = revised
    except Exception as e:  # the revision is a bonus; never fail the build over it
        log.warning("outline revision skipped: %s", e)

    ledger = memory.seed_from_bible(bible)
    book["title"] = str(bible.get("title") or d["pitch"].get("title") or book["title"])[:120]
    d.update({"bible": bible, "outline": outline, "ledger": ledger, "ledger0": json.loads(json.dumps(ledger)),
              "notes": [], "voice_anchor": "", "tokens": d.get("tokens", 0) + llm.take_usage(), "auto": False})
    book["status"] = "ready"
    storage.save_book(book)


# ---- 3. writing a chapter ----------------------------------------------------------
def _context(book: dict, n: int, chapters: list) -> dict:
    d = book["data"]
    outline = d["outline"]
    ch = n + 1
    prior = [c for c in chapters if c["n"] < n]
    bible_short = {k: v for k, v in d["bible"].items() if k not in ("comp_titles", "target_reader")}
    return {
        "n": ch, "total": len(outline),
        "bible": json.dumps(bible_short, ensure_ascii=False),
        "voice": json.dumps(d["bible"].get("voice_guide", {})),
        "voice_anchor": d.get("voice_anchor", ""),
        "summaries": "\n".join(f"Ch{c['n']+1} {c['title']}: {c['summary']}" for c in prior),
        "ledger": memory.context_for_chapter(d["ledger"], ch, outline[n]),
        "recent_hooks": ", ".join(c["hook_type"] or "?" for c in prior[-5:]) or "none yet",
        "notes": "; ".join(d.get("notes", [])),
        "prev_tail": prior[-1]["text"][-3000:] if prior and prior[-1].get("text") else "",
        "chapter": _fmt_plan(outline[n]),
        "next_chapter": json.dumps(outline[n + 1]) if n + 1 < len(outline) else "none (this is the final chapter)",
    }


def _critique(ctx: dict, text: str) -> dict:
    s = llm.chat_json(prompts.EDITOR_SYSTEM, prompts.critic_prompt(ctx, text),
                      config.MODEL_EDITOR, temperature=0.2, max_tokens=2000)
    return s if isinstance(s, dict) else {}


def _extract(book: dict, n: int, text: str) -> dict:
    d = book["data"]
    try:
        r = llm.chat_json(prompts.EDITOR_SYSTEM,
                          prompts.extract_prompt(memory.compact(d["ledger"]), _fmt_plan(d["outline"][n]), n + 1, text),
                          config.MODEL_EDITOR, temperature=0.1, max_tokens=4000)
        if isinstance(r, dict) and r.get("summary"):
            return r
    except llm.FatalLLMError:
        raise
    except Exception as e:
        log.warning("memory extraction failed: %s", e)
    summary = llm.chat("You summarize fiction chapters precisely.",
                       f"Summarize in 110 words (events, new facts, end emotional state, open questions):\n\n{text}",
                       config.MODEL_FAST, 0.2, 500)
    return {"summary": summary, "hook_type": "", "delta": {"continuity_flags": ["memory extraction failed for this chapter"]}}


def write_chapter(book_id: int, n: int, progress=_noop, extra: str = "") -> dict:
    book = storage.get_book(book_id)
    d = book["data"]
    total = len(d["outline"])
    item = d["outline"][n]
    chapters = storage.get_chapters(book_id)
    words_target = config.WORDS_PER_CHAPTER
    ctx = _context(book, n, chapters)
    max_tok = int(words_target * 2) + 1500

    progress(f"✍️ Chapter {n+1}/{total}: “{item.get('title')}”\nDrafting…")
    text = _clean(llm.chat(prompts.AUTHOR_SYSTEM, prompts.chapter_prompt(ctx, words_target, extra),
                           config.MODEL_WRITER, temperature=0.9, max_tokens=max_tok))

    best = None
    attempts = 0
    for attempt in range(config.MAX_REWRITES + 1):
        attempts = attempt + 1
        words = len(text.split())
        banned = _banned(text)
        progress(f"🧐 Chapter {n+1}/{total}: editor reviewing (pass {attempt+1})…")
        try:
            scores = _critique(ctx, text)
        except llm.FatalLLMError:
            raise
        except Exception as e:
            log.warning("critique failed: %s", e)
            scores = {}
        vals = [scores[k] for k in DIMS if isinstance(scores.get(k), (int, float))]
        avg = sum(vals) / len(vals) if vals else 0
        low = min(vals) if vals else 0
        too_short = words < 0.7 * words_target
        quality = avg - 0.4 * len(banned) - (2 if too_short else 0)
        if best is None or quality > best["q"]:
            best = {"q": quality, "text": text, "scores": scores}
        if (vals and low >= config.MIN_SCORE and not banned and not too_short) or attempt == config.MAX_REWRITES:
            break
        fixes = list(scores.get("fixes") or []) + list(scores.get("ai_tells") or [])
        progress(f"🔁 Chapter {n+1}/{total}: lowest score {low:g}. Rewriting (pass {attempt+1})…")
        text = _clean(llm.chat(prompts.AUTHOR_SYSTEM,
                               prompts.rewrite_prompt(ctx, text, fixes[:12], banned, words_target, too_short),
                               config.MODEL_WRITER, temperature=0.85, max_tokens=max_tok))

    final, scores = best["text"], best["scores"]
    progress(f"🧠 Chapter {n+1}/{total}: updating story memory (secrets, betrayals, threads)…")
    mem = _extract(book, n, final)
    counts = memory.apply_delta(d["ledger"], mem.get("delta"), n + 1)
    if n == 0:
        d["voice_anchor"] = " ".join(final.split()[:650])
    d["tokens"] = d.get("tokens", 0) + llm.take_usage()
    hook = str(mem.get("hook_type") or item.get("hook_type") or "")
    scores = dict(scores)
    scores["strongest_line"] = mem.get("strongest_line", "")
    storage.save_chapter(book_id, n, str(item.get("title", f"Chapter {n+1}")), final,
                         str(mem.get("summary", "")), scores, hook, d["ledger"])
    book["status"] = "complete" if n + 1 >= total else "writing"
    storage.save_book(book)
    return {"n": n, "title": item.get("title"), "words": len(final.split()), "scores": scores,
            "avg": avg_score(scores), "attempts": attempts, "memory": counts,
            "overdue": memory.overdue(d["ledger"], n + 2)}


def redo_last(book_id: int, progress=_noop) -> dict:
    """Discard the latest chapter, roll memory back, and write it again."""
    chs = storage.get_chapters(book_id, with_text=False)
    if not chs:
        raise ValueError("Nothing to redo yet")
    n = chs[-1]["n"]
    book = storage.get_book(book_id)
    prev = storage.get_chapter(book_id, n - 1) if n > 0 else None
    book["data"]["ledger"] = (prev["ledger_after"] if prev and prev.get("ledger_after")
                              else json.loads(json.dumps(book["data"]["ledger0"])))
    storage.delete_chapter(book_id, n)
    book["status"] = "writing"
    storage.save_book(book)
    return write_chapter(book_id, n, progress,
                         extra="The publisher rejected the previous version of this chapter. "
                               "Take a clearly different and stronger approach: new opening image, sharper conflict, a more surprising turn.")


# ---- 4. publishing kit ------------------------------------------------------------
def kdp_kit(book_id: int) -> dict:
    book = storage.get_book(book_id)
    chapters = storage.get_chapters(book_id, with_text=False)
    summaries = "\n".join(f"Ch{c['n']+1} {c['title']}: {c['summary']}" for c in chapters)
    kit = llm.chat_json(prompts.AUTHOR_SYSTEM, prompts.kdp_prompt(book["data"]["bible"], summaries),
                        config.MODEL_PLANNER, temperature=0.7, max_tokens=3000)
    return kit if isinstance(kit, dict) else {}
