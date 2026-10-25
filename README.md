# Author Agent

A Telegram-controlled AI novelist. It plans a full novel (characters, secrets, betrayals, voice, chapter-by-chapter outline),
writes each chapter, has a harsh "editor" score it on 9 craft dimensions and force rewrites until it passes, and keeps a
**story memory** (who knows which secret, betrayals + clues planted, open threads, setups awaiting payoff) so it never forgets.
Exports **PDF (6x9 KDP trim), DOCX, EPUB** and builds a **KDP kit** (blurb, 7 keywords, categories, cover brief).

## Files
| File | Job |
|---|---|
| `main.py` | Telegram buttons and background jobs (run this) |
| `engine.py` | The author: pitches, bible, outline, drafting, editor loop |
| `memory.py` | Continuity ledger (secrets, betrayals, threads, setups, facts) |
| `prompts.py` | Craft doctrine and every prompt |
| `llm.py` | OpenRouter client (retries, JSON repair) |
| `storage.py` | SQLite database |
| `exporter.py` | PDF / DOCX / EPUB |
| `config.py` | Settings from environment variables |

## Deploy on Railway
1. Upload all files in this folder to a GitHub repo (the files go in the repo root).
2. Railway > **New Project > Deploy from GitHub repo** > pick the repo.
3. In the service: **Settings > Volumes > Add Volume**, mount path `/data`. This keeps your books across redeploys.
   (Railway sets `RAILWAY_VOLUME_MOUNT_PATH` automatically; the bot uses it.)
4. **Variables**: add `OPENROUTER_API_KEY` and `TELEGRAM_TOKEN`. Optional: `OWNER_IDS`, model names (see `.env.example`).
5. Deploy. Open your bot in Telegram, send `/start`. **The first person to send /start becomes the only owner.**

If Railway redeploys mid-book, auto-write resumes by itself from the last finished chapter.

## Using it
New Novel > genre > your idea (or Surprise me) > pick 1 of 3 pitches > length > **Auto-write book**.
Use **Add direction** any time to steer upcoming chapters, **Redo last chapter** if one disappoints, and **Story Memory** to see what it remembers.

## Cost and quality
- Each chapter = 1 draft + 1-3 editor reviews + up to 2 rewrites + 1 memory pass. A full novel is many model calls; watch your OpenRouter balance.
  Set `MODEL_WRITER` to a cheaper model to cut cost, or raise `MIN_SCORE` / `MAX_REWRITES` for more polish.
- Models can still produce flat spots or small continuity slips. **Read the whole manuscript yourself** before publishing, and consider a human proofread.

## Publishing on KDP
- KDP requires you to disclose AI-generated content when you publish. Answer honestly.
- Income depends on cover, blurb, pricing, categories, launch, and reviews. No tool can guarantee sales. Treat this as a long-term publishing pipeline.
