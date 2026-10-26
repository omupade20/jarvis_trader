"""
JARVIS NEURAL VOICE ENGINE
Dynamic, context-aware speech. Not pre-scripted. Every briefing
is written fresh based on what actually happened today.
"""
import asyncio
import edge_tts
from pathlib import Path
from config import JARVIS_VOICE, JARVIS_RATE, JARVIS_PITCH, AUDIO_PATH, STATIC_DIR, TARGET_PCT


STATIC_DIR.mkdir(parents=True, exist_ok=True)


def compose_briefing(
    genesis: dict,
    profile: dict,
    balance: dict,
    holdings: list,
    regime: dict,
    sentinel_report: dict = None,
    candidate: dict = None
) -> str:
    """
    Composes a fully dynamic, natural Jarvis briefing.
    NEVER uses a fixed template — always reacts to today's actual data.
    """
    day    = genesis.get("day_number", 1)
    name   = profile.get("user_name", "sir").split()[0] if profile.get("user_name") else "sir"
    cash   = balance.get("available_cash", 0)
    mat    = genesis.get("maturity_level", "NEWBORN")

    lines = []

    # ── GREETING (Context-aware) ─────────────────────────────────────────────
    if day == 1:
        lines.append(f"Good evening, {name}. This is Day One. Our journey begins today. I am JARVIS — your autonomous trading sentinel. I am fully connected to your Upstox account and ready to serve.")
    elif day <= 7:
        lines.append(f"Good evening, {name}. This is Day {day} of our mission. I am still in my early learning phase, but growing sharper with each session.")
    elif day <= 30:
        lines.append(f"Good evening, {name}. Day {day} of operation. I am developing a clearer understanding of market patterns relevant to your capital. Let me brief you on today's findings.")
    elif day <= 90:
        lines.append(f"Good evening, {name}. Day {day}. I have now observed {day} market sessions and my filters are becoming increasingly precise.")
    else:
        lines.append(f"Good evening, {name}. Day {day} of our partnership. With {day} sessions of experience, my conviction levels are well calibrated.")

    # ── MARKET REGIME ────────────────────────────────────────────────────────
    nifty_chg = regime.get("nifty_change", 0)
    vix       = regime.get("india_vix", 14)
    regime_label = regime.get("regime", "NORMAL")

    if nifty_chg > 0.5:
        market_mood = f"Nifty 50 had a positive session, closing up {nifty_chg} percent."
    elif nifty_chg < -1.0:
        market_mood = f"The broader market was under pressure today, with Nifty declining {abs(nifty_chg)} percent."
    else:
        market_mood = f"Nifty 50 closed broadly flat, with a change of {nifty_chg} percent."

    if regime_label == "CALM":
        vix_mood = f"India VIX stands at {vix}, indicating a calm and favorable environment for swing trades."
    elif regime_label == "HIGH_RISK":
        vix_mood = f"However, India VIX is elevated at {vix}. This is a caution zone — I will not recommend any new position today."
    else:
        vix_mood = f"India VIX is at {vix}, in a normal volatility range."

    lines.append(f"{market_mood} {vix_mood}")

    # ── PORTFOLIO STATUS ─────────────────────────────────────────────────────
    if holdings:
        h = holdings[0]
        lines.append(f"Moving to your portfolio. You currently hold {h['name']}.")
        if sentinel_report:
            lines.append(sentinel_report.get("voice_part", ""))
    else:
        lines.append(f"Your portfolio is currently 100 percent in cash, with approximately Rs. {cash:,.0f} available for deployment.")

    # ── MARKET RESEARCH VERDICT ──────────────────────────────────────────────
    if candidate and candidate.get("found"):
        best  = candidate["best"]
        score = best["score"]
        sym   = best["name"]
        lines.append(
            f"After scanning all {candidate.get('scanned', 15)} stocks in today's universe with my professional filters, "
            f"I found exactly one candidate worthy of your attention: {sym}. "
            f"My conviction score is {score} out of 100. "
            f"This stock is showing a controlled pullback with an RSI of {best['rsi']} "
            f"and is resting near its 50-day support. "
            f"I recommend entering at Rs. {best['ltp']}, targeting Rs. {best['target']} for a {TARGET_PCT} percent gain, "
            f"with a defensive stop at Rs. {best['stop']}."
        )
        lines.append("I am ready to dispatch the After-Market Order the moment you approve. What is your verdict, sir?")
    elif candidate and not candidate.get("found"):
        reason = candidate.get("reason", "No opportunity found today.")
        lines.append(
            f"Regarding today's market research: {reason} "
            f"This is entirely expected. My filters are tight by design. "
            f"Patient capital is safe capital."
        )
    else:
        lines.append("No new market candidate was evaluated today, as a position is already active.")

    # ── CLOSING ──────────────────────────────────────────────────────────────
    lines.append(f"End of Day {day} briefing. I remain on standby, sir.")

    return " ".join(lines)


async def _synthesize(text: str, path: Path) -> bool:
    try:
        comm = edge_tts.Communicate(text=text, voice=JARVIS_VOICE, rate=JARVIS_RATE, pitch=JARVIS_PITCH)
        await comm.save(str(path))
        return True
    except Exception as e:
        print(f"[VOICE] Edge TTS error: {e}")
        return _offline_tts(text, path)


def _offline_tts(text: str, path: Path) -> bool:
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.save_to_file(text, str(path))
        engine.runAndWait()
        return True
    except Exception:
        return False


async def speak_async(text: str) -> str:
    """Async — use inside FastAPI route."""
    ok = await _synthesize(text, AUDIO_PATH)
    return "/static/briefing.mp3" if ok else ""


def speak_sync(text: str) -> str:
    """Sync — use from CLI."""
    ok = asyncio.run(_synthesize(text, AUDIO_PATH))
    return "/static/briefing.mp3" if ok else ""
