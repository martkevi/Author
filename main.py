"""Telegram interface (button navigation) for the Author Agent. Entry point for Railway."""
import asyncio
import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import config
import engine
import exporter
import llm
import memory
import storage

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("main")

H = ParseMode.HTML
JOBS: dict = {}   # book_id -> {"task": Task, "stop": bool}

GENRES = {
    "psych": "Psychological Thriller", "crime": "Mystery / Crime", "romance": "Romance",
    "horror": "Gothic Horror", "drama": "Literary Drama", "scifi": "Science Fiction",
    "fantasy": "Fantasy", "suspense": "Domestic Suspense",
}
GENRE_BUTTONS = [("🔪 Psych Thriller", "psych"), ("🕵️ Mystery / Crime", "crime"),
                 ("💔 Romance", "romance"), ("🏚 Gothic Horror", "horror"),
                 ("🧠 Literary Drama", "drama"), ("🚀 Sci-Fi", "scifi"),
                 ("⚔️ Fantasy", "fantasy"), ("🏠 Domestic Suspense", "suspense")]
LABELS = {"emotion": "Emotion", "hook": "Hook", "prose": "Prose", "originality": "Originality",
          "voice": "Voice", "pacing": "Pacing", "realism": "Realism", "dialogue": "Dialogue",
          "continuity": "Continuity"}


# ---- small helpers -------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s))


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in r] for r in rows])


def authorized(uid: int) -> bool:
    if config.OWNER_IDS:
        return uid in config.OWNER_IDS
    owner = storage.meta_get("owner")
    return owner is not None and int(owner) == uid


async def show(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, markup=None) -> None:
    q = update.callback_query
    if q:
        try:
            await q.edit_message_text(text, reply_markup=markup, parse_mode=H, disable_web_page_preview=True)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
    await ctx.bot.send_message(update.effective_chat.id, text, reply_markup=markup,
                               parse_mode=H, disable_web_page_preview=True)


async def send_long(bot, chat_id, text: str, markup=None, limit: int = 3800) -> None:
    chunks, cur = [], ""
    for para in text.split("\n"):
        while len(para) > limit:
            chunks.append(para[:limit]); para = para[limit:]
        if len(cur) + len(para) + 1 > limit:
            chunks.append(cur); cur = ""
        cur += para + "\n"
    if cur.strip():
        chunks.append(cur)
    for i, c in enumerate(chunks):
        await bot.send_message(chat_id, c, parse_mode=H, disable_web_page_preview=True,
                               reply_markup=markup if i == len(chunks) - 1 else None)


async def edit_status(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass


def friendly_error(e: Exception) -> str:
    if isinstance(e, llm.FatalLLMError):
        return ("OpenRouter rejected the request. Check that OPENROUTER_API_KEY is correct, your account "
                f"has credits, and the model names are valid.\n\nDetails: {str(e)[:250]}")
    return f"{type(e).__name__}: {str(e)[:300]}"


# ---- screens -------------------------------------------------------------------------------
HOME_KB = kb([("✍️ New Novel", "gm")], [("📚 My Books", "bl")], [("❓ How it works", "help")])


def home_text() -> str:
    return ("📖 <b>Author Agent</b>\n\nI plan, write, edit and remember full novels: characters, secrets, "
            "betrayals, hooks, and continuity. Every chapter is scored by a harsh editor and rewritten "
            "until it passes.\n\nWhat would you like to do?")


HELP_TEXT = (
    "<b>How it works</b>\n\n"
    "1. <b>New Novel</b>: pick a genre, give an idea (or let me surprise you), choose one of 3 pitches and a length.\n"
    "2. I build a story bible and a chapter-by-chapter plan, then an editor stress-tests it.\n"
    "3. <b>Write next chapter</b> or <b>Auto-write</b>. Each chapter: draft → editor scores 9 craft dimensions → rewrite until it passes → memory update.\n"
    "4. <b>Story Memory</b> shows what I remember: who knows which secret, betrayals and the clues planted, open threads, setups awaiting payoff.\n"
    "5. <b>Add Direction</b> steers upcoming chapters. <b>Redo Last</b> rewrites the latest chapter and rolls memory back.\n"
    "6. When done, export <b>PDF / DOCX / EPUB</b> and get the <b>KDP Kit</b> (blurb, keywords, categories, cover brief).\n\n"
    "<b>Publishing note:</b> Amazon KDP requires you to disclose AI-generated content when you publish. "
    "Read the whole manuscript before you publish it.")


def bar(done: int, total: int, width: int = 10) -> str:
    filled = round(width * done / total) if total else 0
    return "▰" * filled + "▱" * (width - filled)


def dash_text(book: dict) -> str:
    d = book["data"]
    chs = storage.get_chapters(book["id"], with_text=False)
    total = len(d.get("outline") or []) or d.get("chapter_target", 0)
    words = sum(c["words"] for c in chs)
    avgs = [a for a in (engine.avg_score(c["scores"]) for c in chs) if a]
    q = f"{sum(avgs) / len(avgs):.1f}/10" if avgs else "n/a"
    status = {"building": "🛠 planning", "ready": "🟢 ready to write", "writing": "✍️ writing",
              "complete": "🏁 complete"}.get(book["status"], book["status"])
    if book["id"] in JOBS and book["status"] != "building":
        status = "✍️ writing now…"
    nxt = ""
    if d.get("outline") and len(chs) < total:
        nxt = f"\nNext: <i>{esc(d['outline'][len(chs)].get('title', ''))}</i>"
    return (f"📕 <b>{esc(book['title'])}</b>\n{esc(book['genre'])} · {status}\n"
            f"{bar(len(chs), total)} {len(chs)}/{total} chapters\n"
            f"{words:,} words · quality {q} · {d.get('tokens', 0):,} tokens used{nxt}")


def dash_kb(book: dict) -> InlineKeyboardMarkup:
    bid = book["id"]
    rows = []
    if book["status"] == "building" and bid not in JOBS:
        return kb([("🔁 Retry planning", f"rb:{bid}")], [("🗑 Delete", f"dl:{bid}"), ("⬅️ Back", "bl")])
    if bid in JOBS:
        rows.append([("⏹ Stop after this chapter", f"st:{bid}")])
        rows.append([("🔄 Refresh", f"bk:{bid}")])
    else:
        if book["status"] != "complete":
            rows.append([("▶️ Write next chapter", f"wr:{bid}"), ("⚡ Auto-write book", f"au:{bid}")])
        rows.append([("📖 Outline", f"ol:{bid}"), ("🧠 Story Memory", f"mm:{bid}")])
        rows.append([("📚 Read chapters", f"rd:{bid}"), ("↩️ Redo last chapter", f"rx:{bid}")])
        rows.append([("📝 Add direction", f"nt:{bid}"), ("🛒 KDP Kit", f"kd:{bid}")])
        rows.append([("📄 PDF", f"ex:{bid}:pdf"), ("📘 DOCX", f"ex:{bid}:docx"), ("📗 EPUB", f"ex:{bid}:epub")])
        rows.append([("🔄 Refresh", f"bk:{bid}"), ("🗑 Delete", f"dl:{bid}"), ("⬅️ Back", "bl")])
    return kb(*rows)


def bible_summary(book: dict) -> str:
    b = book["data"]["bible"]
    chars = ", ".join(f"{esc(c.get('name'))} ({esc(c.get('role', ''))})" for c in b.get("characters", [])[:6]
                      if isinstance(c, dict))
    return (f"✅ <b>{esc(b.get('title', book['title']))}</b>\n<i>{esc(b.get('logline', ''))}</i>\n\n"
            f"<b>Reader promise:</b> {esc(b.get('reader_promise', ''))}\n"
            f"<b>For fans of:</b> {esc(', '.join(map(str, b.get('comp_titles', []))))}\n"
            f"<b>Cast:</b> {chars}\n"
            f"<b>Secrets:</b> {len(b.get('secrets', []))} · <b>Betrayals:</b> {len(b.get('betrayals', []))} · "
            f"<b>Chapters:</b> {len(book['data']['outline'])}\n\nThe plan is locked in memory. Ready when you are.")


def chapter_report(res: dict, total: int) -> str:
    s = res["scores"]
    scores = " · ".join(f"{LABELS[k]} {s[k]:g}" for k in engine.DIMS if isinstance(s.get(k), (int, float)))
    m = res["memory"]
    mem = ", ".join(f"{v} {k}" for k, v in m.items() if v) or "no changes"
    out = (f"✅ <b>Chapter {res['n'] + 1}/{total}: {esc(res['title'])}</b>\n"
           f"{res['words']:,} words · quality <b>{res['avg'] if res['avg'] is not None else 'n/a'}/10</b> · "
           f"{res['attempts']} editor pass{'es' if res['attempts'] != 1 else ''}\n{scores}\n"
           f"🧠 Memory updated: {esc(mem)}")
    if s.get("strongest_line"):
        out += f"\n\n✨ <i>“{esc(s['strongest_line'])}”</i>"
    if res.get("overdue"):
        out += "\n\n⚠️ " + esc("; ".join(res["overdue"][:3]))
    return out


# ---- commands --------------------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not config.OWNER_IDS and storage.meta_get("owner") is None:
        storage.meta_set("owner", uid)
        log.info("Owner claimed by %s", uid)
    if not authorized(uid):
        await update.effective_message.reply_text("🔒 This is a private bot.")
        return
    ctx.user_data.pop("await", None)
    await update.effective_message.reply_text(home_text(), reply_markup=HOME_KB, parse_mode=H)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if authorized(update.effective_user.id):
        await update.effective_message.reply_text(HELP_TEXT, parse_mode=H, reply_markup=kb([("⬅️ Menu", "home")]))


# ---- job runners ---------------------------------------------------------------------------------
async def run_build(app, book_id: int, chat_id: int) -> None:
    loop = asyncio.get_running_loop()
    msg = await app.bot.send_message(chat_id, "🧬 Starting…")

    def progress(t: str) -> None:
        asyncio.run_coroutine_threadsafe(edit_status(msg, t), loop)

    err = None
    try:
        await asyncio.to_thread(engine.build_book, book_id, progress)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("build failed")
        err = e
    JOBS.pop(book_id, None)
    book = storage.get_book(book_id)
    if err:
        await app.bot.send_message(chat_id, f"⚠️ Planning failed.\n{esc(friendly_error(err))}",
                                   parse_mode=H, reply_markup=dash_kb(book))
    else:
        await edit_status(msg, "✅ Novel planned.")
        await app.bot.send_message(chat_id, bible_summary(book), parse_mode=H, reply_markup=dash_kb(book))


async def run_writer(app, book_id: int, chat_id: int, count: int, resumed: bool = False) -> None:
    loop = asyncio.get_running_loop()
    holder = {"msg": await app.bot.send_message(
        chat_id, "♻️ Resuming where I left off…" if resumed else "✍️ Starting…")}
    job = JOBS[book_id]

    def progress(t: str) -> None:
        asyncio.run_coroutine_threadsafe(edit_status(holder["msg"], t), loop)

    err = None
    try:
        for _ in range(count):
            if job["stop"]:
                break
            book = storage.get_book(book_id)
            if not book:
                break
            done = storage.count_chapters(book_id)
            total = len(book["data"]["outline"])
            if done >= total:
                break
            res = await asyncio.to_thread(engine.write_chapter, book_id, done, progress)
            await edit_status(holder["msg"], f"✅ Chapter {done + 1}/{total} finished.")
            await app.bot.send_message(chat_id, chapter_report(res, total), parse_mode=H)
            holder["msg"] = await app.bot.send_message(chat_id, "…")
    except asyncio.CancelledError:
        raise  # redeploy: keep the auto flag so we resume on restart
    except Exception as e:
        log.exception("writer failed")
        err = e
    JOBS.pop(book_id, None)
    book = storage.get_book(book_id)
    if book:
        book["data"]["auto"] = False
        storage.save_book(book)
        head = "⚠️ Stopped by an error. Progress is saved.\n" + esc(friendly_error(err)) + "\n\n" if err else ""
        if book["status"] == "complete":
            head = "🎉 <b>Your novel is finished.</b> Export it below or build the KDP Kit.\n\n"
        await app.bot.send_message(chat_id, head + dash_text(book), parse_mode=H, reply_markup=dash_kb(book))


def start_writer(app, book_id: int, chat_id: int, count: int, resumed: bool = False) -> None:
    JOBS[book_id] = {"stop": False, "task": None}
    JOBS[book_id]["task"] = asyncio.create_task(run_writer(app, book_id, chat_id, count, resumed))


# ---- guided "new novel" flow -------------------------------------------------------------------
def pitch_text(pitches: list) -> str:
    out = ["🎲 <b>Three pitches. Choose one:</b>\n"]
    for i, p in enumerate(pitches, 1):
        out.append(f"<b>{i}. {esc(p.get('title'))}</b>\n{esc(p.get('logline', ''))}\n"
                   f"<i>Hook:</i> {esc(p.get('hook', ''))}\n<i>Why it sells:</i> {esc(p.get('why_it_sells', ''))}\n")
    return "\n".join(out)


async def do_pitches(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat.id
    msg = await ctx.bot.send_message(chat, "🎲 Developing three market-tested pitches… (about 30 seconds)")
    try:
        pitches = await asyncio.to_thread(engine.make_pitches, ctx.user_data["genre"], ctx.user_data.get("seed", ""))
    except Exception as e:
        log.exception("pitches failed")
        await msg.edit_text(f"⚠️ Could not create pitches.\n{friendly_error(e)}",
                            reply_markup=kb([("🔄 Try again", "pr")], [("⬅️ Menu", "home")]))
        return
    ctx.user_data["pitches"] = pitches
    rows = [[(f"{i + 1}️⃣ Pick #{i + 1}", f"p:{i}") for i in range(len(pitches))],
            [("🔄 New pitches", "pr")], [("⬅️ Menu", "home")]]
    await msg.edit_text(pitch_text(pitches), parse_mode=H, reply_markup=kb(*rows))


# ---- button router -----------------------------------------------------------------------------------
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    uid = update.effective_user.id
    if not authorized(uid):
        await q.answer("Private bot", show_alert=True)
        return
    parts = q.data.split(":")
    a = parts[0]
    chat = update.effective_chat.id

    def owned(bid_str):
        b = storage.get_book(int(bid_str))
        return b if b and b["owner"] == uid else None

    if a == "home":
        ctx.user_data.pop("await", None)
        await q.answer()
        await show(update, ctx, home_text(), HOME_KB)
    elif a == "help":
        await q.answer()
        await show(update, ctx, HELP_TEXT, kb([("⬅️ Menu", "home")]))
    elif a == "gm":
        await q.answer()
        gb = [(label, f"g:{key}") for label, key in GENRE_BUTTONS]
        rows = [[gb[i], gb[i + 1]] for i in range(0, len(gb), 2)]
        rows += [[("✨ Custom genre", "g:custom")], [("⬅️ Menu", "home")]]
        await show(update, ctx, "✍️ <b>Choose a genre</b>", kb(*rows))
    elif a == "g":
        await q.answer()
        key = parts[1]
        if key == "custom":
            ctx.user_data["await"] = ("genre",)
            await show(update, ctx, "Type the genre (example: <i>cozy mystery</i>, <i>cyberpunk noir</i>, <i>historical romance</i>).",
                       kb([("⬅️ Back", "gm")]))
        else:
            ctx.user_data["genre"] = GENRES[key]
            ctx.user_data["await"] = ("seed",)
            await show(update, ctx, f"<b>{esc(GENRES[key])}</b>\n\nSend me your idea in a message (a premise, a character, "
                                    "a 'what if'), or let me surprise you.",
                       kb([("🎲 Surprise me", "sur")], [("⬅️ Back", "gm")]))
    elif a == "sur":
        await q.answer()
        ctx.user_data["seed"] = ""
        ctx.user_data.pop("await", None)
        await show(update, ctx, "Great, I'll come up with something fresh.")
        await do_pitches(update, ctx)
    elif a == "pr":
        await q.answer()
        await do_pitches(update, ctx)
    elif a == "p":
        await q.answer()
        ctx.user_data["pick"] = int(parts[1])
        await show(update, ctx, "📏 <b>How long should the novel be?</b>\n\nLonger books cost more to write and take longer.",
                   kb([("Short · 18 ch (~54k words)", "ln:short")],
                      [("Standard · 26 ch (~78k words)", "ln:standard")],
                      [("Long · 34 ch (~100k words)", "ln:long")],
                      [("⬅️ Back to pitches", "pr")]))
    elif a == "ln":
        pitches = ctx.user_data.get("pitches")
        if not pitches:
            await q.answer("Session expired. Start a new novel.", show_alert=True)
            return
        await q.answer("Planning your novel…")
        pitch = pitches[ctx.user_data.get("pick", 0)]
        bid = storage.create_book(uid, chat, ctx.user_data.get("genre", "Fiction"), pitch.get("title", "Untitled"),
                                  {"pitch": pitch, "chapter_target": config.LENGTHS[parts[1]], "tokens": 0})
        await show(update, ctx, f"📕 <b>{esc(pitch.get('title'))}</b> selected.")
        JOBS[bid] = {"stop": False, "task": None}
        JOBS[bid]["task"] = asyncio.create_task(run_build(ctx.application, bid, chat))
    elif a == "bl":
        await q.answer()
        books = storage.list_books(uid)
        if not books:
            await show(update, ctx, "You have no books yet.", kb([("✍️ New Novel", "gm")], [("⬅️ Menu", "home")]))
            return
        rows = [[(f"📕 {b['title'][:40]}", f"bk:{b['id']}")] for b in books[:12]]
        rows.append([("⬅️ Menu", "home")])
        await show(update, ctx, "📚 <b>Your books</b>", kb(*rows))
    elif a in ("bk", "wr", "au", "st", "ol", "mm", "rd", "rc", "rx", "rxc", "nt", "kd", "ex", "dl", "dlc", "rb"):
        book = owned(parts[1])
        if not book:
            await q.answer("Book not found", show_alert=True)
            return
        await handle_book_action(update, ctx, a, parts, book)
    else:
        await q.answer()


async def handle_book_action(update, ctx, a: str, parts: list, book: dict) -> None:
    q = update.callback_query
    chat = update.effective_chat.id
    bid = book["id"]
    d = book["data"]
    done = storage.count_chapters(bid)

    if a == "bk":
        await q.answer()
        await show(update, ctx, dash_text(book), dash_kb(book))

    elif a in ("wr", "au"):
        if bid in JOBS:
            await q.answer("Already working on this book", show_alert=True)
            return
        if book["status"] in ("building",) or not d.get("outline"):
            await q.answer("Planning is not finished yet", show_alert=True)
            return
        await q.answer("Started")
        if a == "au":
            d["auto"] = True
            storage.save_book(book)
        start_writer(ctx.application, bid, chat, 999 if a == "au" else 1)
        await show(update, ctx, dash_text(storage.get_book(bid)), dash_kb(storage.get_book(bid)))

    elif a == "st":
        if bid in JOBS:
            JOBS[bid]["stop"] = True
            await q.answer("Stopping after the current chapter", show_alert=True)
        else:
            await q.answer("Nothing running")

    elif a == "rb":
        if bid in JOBS:
            await q.answer("Already running", show_alert=True)
            return
        await q.answer("Retrying…")
        JOBS[bid] = {"stop": False, "task": None}
        JOBS[bid]["task"] = asyncio.create_task(run_build(ctx.application, bid, chat))

    elif a == "ol":
        await q.answer()
        lines = [f"🗺 <b>Outline: {esc(book['title'])}</b>\n"]
        for c in d.get("outline", []):
            mark = "✅" if c["n"] <= done else "▫️"
            lines.append(f"{mark} <b>{c['n']}. {esc(c.get('title'))}</b>\n   {esc(c.get('ending_hook', ''))}")
        await send_long(ctx.bot, chat, "\n".join(lines), kb([("⬅️ Back to book", f"bk:{bid}")]))

    elif a == "mm":
        if not d.get("ledger"):
            await q.answer("Not planned yet", show_alert=True)
            return
        await q.answer()
        text = memory.render_for_user(d["ledger"], done + 1)
        await send_long(ctx.bot, chat, "🧠 <b>Story Memory</b>\n\n" + esc(text), kb([("⬅️ Back to book", f"bk:{bid}")]))

    elif a == "rd":
        if not done:
            await q.answer("Nothing written yet", show_alert=True)
            return
        await q.answer()
        btns = [(str(i + 1), f"rc:{bid}:{i}") for i in range(done)]
        rows = [btns[i:i + 6] for i in range(0, len(btns), 6)] + [[("⬅️ Back to book", f"bk:{bid}")]]
        await show(update, ctx, "📚 <b>Pick a chapter to read</b>", kb(*rows))

    elif a == "rc":
        await q.answer()
        n = int(parts[2])
        c = storage.get_chapter(bid, n)
        if not c:
            return
        nav = []
        if n > 0:
            nav.append(("◀️ Prev", f"rc:{bid}:{n - 1}"))
        nav.append(("📚 Chapters", f"rd:{bid}"))
        if n + 1 < done:
            nav.append(("Next ▶️", f"rc:{bid}:{n + 1}"))
        await send_long(ctx.bot, chat, f"<b>Chapter {n + 1}: {esc(c['title'])}</b>\n\n" + esc(c["text"]), kb(nav))

    elif a == "rx":
        if not done:
            await q.answer("Nothing to redo", show_alert=True)
            return
        await q.answer()
        await show(update, ctx, f"↩️ Rewrite chapter {done} from scratch? Memory rolls back to before it.",
                   kb([("Yes, redo it", f"rxc:{bid}")], [("Cancel", f"bk:{bid}")]))

    elif a == "rxc":
        if bid in JOBS:
            await q.answer("Already working on this book", show_alert=True)
            return
        await q.answer("Redoing…")
        JOBS[bid] = {"stop": False, "task": None}
        JOBS[bid]["task"] = asyncio.create_task(run_redo(ctx.application, bid, chat))
        await show(update, ctx, "↩️ Rewriting the last chapter…")

    elif a == "nt":
        await q.answer()
        ctx.user_data["await"] = ("note", bid)
        notes = d.get("notes", [])
        cur = ("\n\n<b>Current directions:</b>\n" + "\n".join(f"• {esc(n)}" for n in notes[-6:])) if notes else ""
        await show(update, ctx, "📝 Send your direction for upcoming chapters (a plot change, tone, a character to "
                                "feature, a betrayal to land harder). It applies from the next chapter on." + cur,
                   kb(*(([("🧹 Clear directions", f"ntc:{bid}")],) if notes else ()), [("⬅️ Back", f"bk:{bid}")]))

    elif a == "kd":
        if not done:
            await q.answer("Write at least one chapter first", show_alert=True)
            return
        await q.answer()
        msg = await ctx.bot.send_message(chat, "🛒 Building your KDP kit…")
        try:
            kit = await asyncio.to_thread(engine.kdp_kit, bid)
        except Exception as e:
            await msg.edit_text(f"⚠️ {friendly_error(e)}")
            return
        await msg.delete()
        await send_long(ctx.bot, chat, kdp_text(kit), kb([("⬅️ Back to book", f"bk:{bid}")]))

    elif a == "ex":
        fmt = parts[2]
        if not done:
            await q.answer("Nothing written yet", show_alert=True)
            return
        await q.answer("Building file…")
        msg = await ctx.bot.send_message(chat, f"📦 Typesetting your {fmt.upper()}…")
        try:
            path = await asyncio.to_thread(exporter.EXPORTERS[fmt], bid)
            with open(path, "rb") as f:
                await ctx.bot.send_document(chat, f, filename=path.split("/")[-1], read_timeout=120,
                                            write_timeout=300,
                                            caption=f"{book['title']} ({done}/{len(d['outline'])} chapters)"
                                                    + ("" if book["status"] == "complete" else " · partial manuscript"))
            await msg.delete()
        except Exception as e:
            log.exception("export failed")
            await msg.edit_text(f"⚠️ Export failed: {friendly_error(e)}")

    elif a == "dl":
        await q.answer()
        await show(update, ctx, f"🗑 Delete <b>{esc(book['title'])}</b> permanently?",
                   kb([("Yes, delete", f"dlc:{bid}")], [("Cancel", f"bk:{bid}")]))

    elif a == "dlc":
        if bid in JOBS:
            await q.answer("Stop the running job first", show_alert=True)
            return
        storage.delete_book(bid)
        await q.answer("Deleted")
        await show(update, ctx, "Deleted.", kb([("📚 My Books", "bl"), ("⬅️ Menu", "home")]))


async def run_redo(app, book_id: int, chat_id: int) -> None:
    loop = asyncio.get_running_loop()
    msg = await app.bot.send_message(chat_id, "↩️ Starting rewrite…")

    def progress(t: str) -> None:
        asyncio.run_coroutine_threadsafe(edit_status(msg, t), loop)

    err, res = None, None
    try:
        res = await asyncio.to_thread(engine.redo_last, book_id, progress)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("redo failed")
        err = e
    JOBS.pop(book_id, None)
    book = storage.get_book(book_id)
    total = len(book["data"]["outline"])
    text = (f"⚠️ {esc(friendly_error(err))}\n\n" if err else chapter_report(res, total) + "\n\n") + dash_text(book)
    await app.bot.send_message(chat_id, text, parse_mode=H, reply_markup=dash_kb(book))


def kdp_text(kit: dict) -> str:
    def lst(x):
        return "\n".join(f"• {esc(i)}" for i in x) if isinstance(x, list) else esc(x)
    return (f"🛒 <b>KDP Publishing Kit</b>\n\n<b>Title:</b> {esc(kit.get('title', ''))}\n"
            f"<b>Subtitle:</b> {esc(kit.get('subtitle', ''))}\n<b>Tagline:</b> {esc(kit.get('tagline', ''))}\n\n"
            f"<b>Description (paste into KDP):</b>\n{esc(kit.get('blurb', ''))}\n\n"
            f"<b>7 Keywords:</b>\n{lst(kit.get('keywords', []))}\n\n<b>Categories:</b>\n{lst(kit.get('categories', []))}\n\n"
            f"<b>For readers of:</b>\n{lst(kit.get('comps', []))}\n\n<b>Cover brief:</b>\n{esc(kit.get('cover_brief', ''))}\n\n"
            f"<b>Author note:</b>\n{esc(kit.get('author_note', ''))}\n\n"
            "⚠️ <b>Before you publish:</b> read the full manuscript, get a human proofread, and answer KDP's "
            "AI-generated content question honestly when you upload. Check KDP's current content guidelines.")


# ---- free-text input ------------------------------------------------------------------------------------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not authorized(uid):
        return
    state = ctx.user_data.get("await")
    text = (update.message.text or "").strip()
    if not state:
        await update.message.reply_text("Use the menu:", reply_markup=HOME_KB)
        return
    if state[0] == "genre":
        ctx.user_data["genre"] = text[:60]
        ctx.user_data["await"] = ("seed",)
        await update.message.reply_text(f"Genre: {text[:60]}\n\nNow send your idea, or tap Surprise me.",
                                        reply_markup=kb([("🎲 Surprise me", "sur")]))
    elif state[0] == "seed":
        ctx.user_data["seed"] = text[:1500]
        ctx.user_data.pop("await", None)
        await do_pitches(update, ctx)
    elif state[0] == "note":
        book = storage.get_book(state[1])
        if book and book["owner"] == uid:
            book["data"].setdefault("notes", []).append(text[:800])
            storage.save_book(book)
            ctx.user_data.pop("await", None)
            await update.message.reply_text("📝 Noted. I'll apply it from the next chapter.",
                                            reply_markup=kb([("⬅️ Back to book", f"bk:{book['id']}")]))


async def on_clear_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not authorized(update.effective_user.id):
        return
    book = storage.get_book(int(q.data.split(":")[1]))
    if book and book["owner"] == update.effective_user.id:
        book["data"]["notes"] = []
        storage.save_book(book)
    await q.answer("Directions cleared")
    await show(update, ctx, dash_text(book), dash_kb(book))


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error", exc_info=ctx.error)


# ---- startup ---------------------------------------------------------------------------------------------
async def post_init(app: Application) -> None:
    """Resume any auto-write jobs interrupted by a restart or redeploy."""
    for b in storage.books_auto():
        if b["id"] not in JOBS and b["status"] in ("ready", "writing"):
            log.info("Resuming auto-write for book %s", b["id"])
            start_writer(app, b["id"], b["chat_id"], 999, resumed=True)


def main() -> None:
    config.validate()
    storage.init()
    app = (Application.builder().token(config.TELEGRAM_TOKEN).concurrent_updates(True)
           .read_timeout(30).write_timeout(60).post_init(post_init).build())
    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(on_clear_notes, pattern=r"^ntc:"))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    log.info("Author Agent running. Data dir: %s", config.DATA_DIR)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
