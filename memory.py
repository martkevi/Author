"""Story memory: a continuity ledger that tracks who knows what, secrets,
betrayals (and the clues planted for them), open plot threads, setups that
need payoffs, facts, and the timeline. It is rebuilt into the prompt for
every chapter so the author never forgets."""
import json


def new_ledger() -> dict:
    return {"_ids": {}, "characters": {}, "secrets": [], "betrayals": [], "threads": [],
            "setups": [], "timeline": [], "facts": [], "motifs": [], "flags": []}


def _nid(L: dict, kind: str) -> str:
    L["_ids"][kind] = L["_ids"].get(kind, 0) + 1
    return f"{kind}{L['_ids'][kind]}"


def _list(x) -> list:
    if isinstance(x, list):
        return x
    return [] if x in (None, "") else [x]


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _add_unique(lst: list, items) -> None:
    for i in _list(items):
        if i not in lst:
            lst.append(i)


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _char(L: dict, name: str) -> dict:
    return L["characters"].setdefault(name, {
        "role": "", "status": "alive", "location": "", "emotional_state": "",
        "knows": [], "false_beliefs": [], "relationships": {}, "secret": ""})


# ---- seeding ------------------------------------------------------------------
def seed_from_bible(bible: dict) -> dict:
    L = new_ledger()
    for c in _list(bible.get("characters")):
        c = _dict(c)
        if c.get("name"):
            ch = _char(L, c["name"])
            ch["role"] = c.get("role", "")
            ch["secret"] = c.get("secret", "")
    for s in _list(bible.get("secrets")):
        s = _dict(s)
        if s.get("secret"):
            held = _list(s.get("held_by"))
            L["secrets"].append({"id": _nid(L, "S"), "secret": s["secret"], "held_by": held,
                                 "known_by": list(held), "planted": _int(s.get("planted_chapter")),
                                 "planned_reveal": _int(s.get("reveal_chapter")), "revealed_in": None})
    for b in _list(bible.get("betrayals")):
        b = _dict(b)
        if b.get("betrayer"):
            L["betrayals"].append({"id": _nid(L, "B"), "betrayer": b.get("betrayer"),
                                   "betrayed": b.get("betrayed"), "nature": b.get("nature", ""),
                                   "state": "hidden", "clues_planned": _list(b.get("clues")),
                                   "clues_planted": [], "planted": _int(b.get("planted_chapter")),
                                   "planned_reveal": _int(b.get("reveal_chapter")),
                                   "aftermath": b.get("aftermath", ""), "revealed_in": None})
    L["motifs"] = [m for m in _list(bible.get("motifs")) if isinstance(m, str)]
    return L


# ---- applying updates from the continuity editor -------------------------------
def apply_delta(L: dict, delta: dict, ch: int) -> dict:
    """ch is the 1-based chapter number. Returns counts of what changed."""
    delta = _dict(delta)
    cnt = {"characters": 0, "secrets": 0, "betrayals": 0, "threads": 0, "setups": 0}

    for name, u in _dict(delta.get("character_updates")).items():
        u = _dict(u)
        c = _char(L, name)
        for k in ("status", "location", "emotional_state"):
            if u.get(k):
                c[k] = u[k]
        _add_unique(c["knows"], u.get("knows_add"))
        _add_unique(c["false_beliefs"], u.get("false_beliefs_add"))
        for fb in _list(u.get("false_beliefs_remove")):
            if fb in c["false_beliefs"]:
                c["false_beliefs"].remove(fb)
        for other, desc in _dict(u.get("relationships")).items():
            c["relationships"][other] = desc
        cnt["characters"] += 1

    for s in _list(delta.get("new_secrets")):
        s = _dict(s)
        if s.get("secret"):
            held = _list(s.get("held_by"))
            L["secrets"].append({"id": _nid(L, "S"), "secret": s["secret"], "held_by": held,
                                 "known_by": list(held), "planted": ch,
                                 "planned_reveal": _int(s.get("planned_reveal")), "revealed_in": None})
            cnt["secrets"] += 1
    for u in _list(delta.get("secret_updates")):
        u = _dict(u)
        for s in L["secrets"]:
            if s["id"] == u.get("id"):
                _add_unique(s["known_by"], u.get("known_by_add"))
                if u.get("revealed") and s["revealed_in"] is None:
                    s["revealed_in"] = ch
                cnt["secrets"] += 1

    for b in _list(delta.get("new_betrayals")):
        b = _dict(b)
        if b.get("betrayer"):
            L["betrayals"].append({"id": _nid(L, "B"), "betrayer": b["betrayer"],
                                   "betrayed": b.get("betrayed"), "nature": b.get("nature", ""),
                                   "state": "hidden", "clues_planned": [], "clues_planted": [],
                                   "planted": ch, "planned_reveal": _int(b.get("planned_reveal")),
                                   "aftermath": "", "revealed_in": None})
            cnt["betrayals"] += 1
    for u in _list(delta.get("betrayal_updates")):
        u = _dict(u)
        for b in L["betrayals"]:
            if b["id"] == u.get("id"):
                if u.get("state"):
                    b["state"] = u["state"]
                    if u["state"] in ("exposed", "confronted", "resolved") and b["revealed_in"] is None:
                        b["revealed_in"] = ch
                if u.get("clue_added"):
                    b["clues_planted"].append(f"Ch{ch}: {u['clue_added']}")
                cnt["betrayals"] += 1

    for t in _list(delta.get("new_threads")):
        t = _dict(t)
        if t.get("question") and not any(x["question"] == t["question"] and x["resolved"] is None for x in L["threads"]):
            L["threads"].append({"id": _nid(L, "T"), "question": t["question"], "opened": ch,
                                 "resolve_planned": _int(t.get("resolve_planned")), "resolved": None})
            cnt["threads"] += 1
    for tid in _list(delta.get("resolved_threads")):
        for t in L["threads"]:
            if t["id"] == tid and t["resolved"] is None:
                t["resolved"] = ch
                cnt["threads"] += 1

    for s in _list(delta.get("new_setups")):
        s = _dict(s)
        if s.get("setup") and not any(x["setup"] == s["setup"] and x["paid_off"] is None for x in L["setups"]):
            L["setups"].append({"id": _nid(L, "P"), "setup": s["setup"], "planted": ch,
                                "payoff_planned": _int(s.get("payoff_planned")), "paid_off": None})
            cnt["setups"] += 1
    for pid in _list(delta.get("paid_off")):
        for s in L["setups"]:
            if s["id"] == pid and s["paid_off"] is None:
                s["paid_off"] = ch
                cnt["setups"] += 1

    for t in _list(delta.get("timeline")):
        t = _dict(t)
        if t.get("event"):
            L["timeline"].append({"ch": ch, "when": t.get("when", ""), "event": t["event"]})
    for f in _list(delta.get("new_facts")):
        if isinstance(f, str) and f not in L["facts"]:
            L["facts"].append(f)
    for fl in _list(delta.get("continuity_flags")):
        if isinstance(fl, str) and fl:
            L["flags"].append(f"Ch{ch}: {fl}")
    return cnt


# ---- building prompt context -----------------------------------------------------
def compact(L: dict) -> str:
    """Small JSON of the live ledger for the continuity editor."""
    return json.dumps({
        "characters": L["characters"],
        "secrets": [s for s in L["secrets"] if s["revealed_in"] is None],
        "betrayals": [b for b in L["betrayals"] if b["state"] != "resolved"],
        "threads": [t for t in L["threads"] if t["resolved"] is None],
        "setups": [s for s in L["setups"] if s["paid_off"] is None],
    }, ensure_ascii=False)


def context_for_chapter(L: dict, ch: int, outline_item: dict) -> str:
    """Human-readable memory briefing for writing chapter ch (1-based)."""
    plan_text = json.dumps(outline_item, ensure_ascii=False).lower()
    lines = []

    chars = []
    for i, (name, c) in enumerate(L["characters"].items()):
        if i < 6 or name.lower() in plan_text:
            chars.append((name, c))
    lines.append("CHARACTER STATES:")
    for name, c in chars:
        bits = [f"{name} ({c['role']})" if c["role"] else name]
        if c["status"] and c["status"] != "alive":
            bits.append(f"status: {c['status']}")
        if c["location"]:
            bits.append(f"at: {c['location']}")
        if c["emotional_state"]:
            bits.append(f"feeling: {c['emotional_state']}")
        if c["knows"]:
            bits.append("knows: " + "; ".join(c["knows"][-6:]))
        if c["false_beliefs"]:
            bits.append("WRONGLY believes: " + "; ".join(c["false_beliefs"][-4:]))
        if c["relationships"]:
            bits.append("relations: " + "; ".join(f"{k}: {v}" for k, v in list(c["relationships"].items())[-4:]))
        lines.append("- " + " | ".join(bits))

    open_sec = [s for s in L["secrets"] if s["revealed_in"] is None]
    if open_sec:
        lines.append("\nSECRETS STILL HIDDEN (respect who knows them):")
        for s in open_sec:
            due = f" [reveal planned ch{s['planned_reveal']}]" if s["planned_reveal"] else ""
            lines.append(f"- {s['id']}: {s['secret']} | known by: {', '.join(map(str, s['known_by']))}{due}")

    live_b = [b for b in L["betrayals"] if b["state"] != "resolved"]
    if live_b:
        lines.append("\nBETRAYALS (track state, plant clues fairly before reveal):")
        for b in live_b:
            clues = "; ".join(b["clues_planted"][-4:]) or "none yet"
            todo = [c for c in b["clues_planned"] if isinstance(c, str)][:3]
            due = f" reveal planned ch{b['planned_reveal']}" if b["planned_reveal"] else ""
            lines.append(f"- {b['id']}: {b['betrayer']} betrays {b['betrayed']} ({b['nature']}) "
                         f"| state: {b['state']}{due} | clues planted: {clues}"
                         + (f" | clues available to plant: {todo}" if b["state"] in ("hidden", "clue-planted") else ""))

    open_t = [t for t in L["threads"] if t["resolved"] is None]
    if open_t:
        lines.append("\nOPEN QUESTIONS/THREADS:")
        for t in open_t[-14:]:
            lines.append(f"- {t['id']}: {t['question']} (opened ch{t['opened']})")

    open_p = [s for s in L["setups"] if s["paid_off"] is None]
    if open_p:
        lines.append("\nSETUPS AWAITING PAYOFF:")
        for s in open_p[-14:]:
            due = ""
            if s["payoff_planned"] and s["payoff_planned"] <= ch + 2:
                due = " <<< PAYOFF DUE SOON"
            lines.append(f"- {s['id']}: {s['setup']} (planted ch{s['planted']}){due}")

    if L["facts"]:
        lines.append("\nESTABLISHED FACTS (never contradict):")
        lines += [f"- {f}" for f in L["facts"][-45:]]
    if L["timeline"]:
        lines.append("\nRECENT TIMELINE:")
        lines += [f"- ch{t['ch']} {t['when']}: {t['event']}" for t in L["timeline"][-6:]]
    if L["flags"]:
        lines.append("\nCONTINUITY ISSUES TO REPAIR OR WORK AROUND:")
        lines += [f"- {f}" for f in L["flags"][-5:]]
    if L["motifs"]:
        lines.append("\nMOTIFS to weave in lightly: " + "; ".join(L["motifs"]))
    return "\n".join(lines)


def overdue(L: dict, ch: int) -> list:
    """Things that should already be resolved by chapter ch (1-based)."""
    out = []
    for s in L["setups"]:
        if s["paid_off"] is None and s["payoff_planned"] and s["payoff_planned"] < ch:
            out.append(f"Setup {s['id']} overdue: {s['setup']}")
    for t in L["threads"]:
        if t["resolved"] is None and t["resolve_planned"] and t["resolve_planned"] < ch:
            out.append(f"Thread {t['id']} overdue: {t['question']}")
    return out


def render_for_user(L: dict, ch: int) -> str:
    """Plain-text memory report for the Telegram 'Story Memory' button."""
    out = ["CHARACTERS"]
    for name, c in L["characters"].items():
        bit = f"• {name}: {c['status']}"
        if c["emotional_state"]:
            bit += f", {c['emotional_state']}"
        if c["false_beliefs"]:
            bit += f" | wrongly believes: {c['false_beliefs'][-1]}"
        out.append(bit)
    out.append("\nSECRETS")
    for s in L["secrets"]:
        st = f"revealed ch{s['revealed_in']}" if s["revealed_in"] else "hidden"
        out.append(f"• {s['secret']} ({st})")
    out.append("\nBETRAYALS")
    for b in L["betrayals"]:
        out.append(f"• {b['betrayer']} → {b['betrayed']}: {b['nature']} [{b['state']}] "
                   f"clues planted: {len(b['clues_planted'])}")
    out.append("\nOPEN THREADS")
    out += [f"• {t['question']}" for t in L["threads"] if t["resolved"] is None][-12:] or ["• none"]
    od = overdue(L, ch)
    if od:
        out.append("\nOVERDUE")
        out += [f"• {o}" for o in od]
    if L["flags"]:
        out.append("\nCONTINUITY FLAGS")
        out += [f"• {f}" for f in L["flags"][-6:]]
    return "\n".join(out)
