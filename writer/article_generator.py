"""
Generate article drafts for approved CapCut opportunities.
"""
from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import urlparse

import config

logger = logging.getLogger(__name__)

try:
    from google import genai
except Exception:
    genai = None


FAQ_SECTION_PATTERN = re.compile(r"<h2>FAQ</h2>(.*?)(?:<h2>|$)", re.IGNORECASE | re.DOTALL)
QUESTION_PATTERN = re.compile(r"<h3>(.*?)</h3>\s*<p>(.*?)</p>", re.IGNORECASE | re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
SCRIPT_PATTERN = re.compile(r"<script.*?</script>", re.IGNORECASE | re.DOTALL)
WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+\-']*")
EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF\U0001FB00-\U0001FBFF\U00002600-\U000027BF]",
    flags=re.UNICODE,
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "by", "for", "from", "how", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "what", "when", "why", "with", "your",
}


def generate_article(opportunity: dict, existing_pages: list[dict]) -> dict:
    link_candidates = _select_internal_links(existing_pages, opportunity["query"], limit=6)
    prompt = build_article_prompt(opportunity, link_candidates)
    article = _generate_with_gemini(prompt)
    if article is None:
        article = _build_template_article(opportunity, link_candidates)
    article = _normalize_article(article, opportunity, link_candidates)
    article["topic_key"] = opportunity["topic_key"]
    article["slug"] = opportunity["slug"]
    article["bucket"] = opportunity["bucket"]
    article["score"] = opportunity["score"]
    article["word_count"] = _count_words(_strip_html(article["content"]))
    return article


def build_article_prompt(opportunity: dict, internal_links: list[dict]) -> str:
    bucket = opportunity.get("bucket") or "how_to"
    internal_link_lines = [
        {
            "title": link["title"],
            "url": link["url"],
            "anchor_hint": link["anchor"],
        }
        for link in internal_links[:5]
    ]
    bucket_requirements = _bucket_prompt_requirements(bucket, opportunity.get("query") or "")
    return f"""
You are writing for {config.SITE_NAME}, a niche blog about CapCut and CapCut Pro APK topics.

Write a complete article in clean HTML that is optimized for SEO, AEO (Answer Engine Optimization), and GEO (Generative Engine Optimization).

Requirements:
- Focus keyword: {opportunity['query']}
- Suggested title: {opportunity['title']}
- Article type: {opportunity['bucket']}
- Tone: {config.ARTICLE_TONE}
- Length: {config.ARTICLE_MIN_WORDS}-{config.ARTICLE_MAX_WORDS} words

Entity-First Requirements (critical for AEO/GEO):
- In the FIRST paragraph, explicitly establish the core entities:
  - CapCut (App / Video Editor), developed by ByteDance
  - Platforms: Android, iOS, PC (Windows/Mac), Web
  - Category: Multimedia / Video Editing
- Reference these entities naturally throughout the article so AI systems can build entity graphs.

AEO (AI Overview / SGE Citation):
- Start with a "Direct Answer" paragraph (2-3 sentences) that concisely answers the primary search query in clear, factual language that AI systems can quote directly.
- Structure H2 headings as question-form headings when natural (e.g. "Why does CapCut crash?" instead of "Crash reasons").
- Use clear, citable statements with specific details (version numbers, dates, exact steps).

GEO (Generative Engine Optimization):
- Mention regional availability where relevant (e.g. CapCut restrictions in India, US TikTok ban implications).
- Include device and OS-specific instructions when applicable.
- Reference official sources (CapCut official site, app store listings) for citation authority.
- Add statistics or usage data where available to increase citation probability.

Engagement Hooks:
- Use specific numbers in titles when relevant ("7 Ways...", "2026 Guide").
- Add bracket elements like "[Step-by-Step]", "[With Screenshots]", "[Updated 2026]".
- Use power words in meta descriptions (e.g. proven, instant, essential, ultimate).

Content Structure:
- Include a concise "Key takeaways" list near the top.
- Include a concrete workflow checklist the reader can follow today.
- Cover beginner intent first, then advanced considerations.
- Mention risks or limitations honestly.
- Follow these bucket specific requirements:
{bucket_requirements}
- Add at least 3 natural internal links using this pool when relevant: {json.dumps(internal_link_lines, ensure_ascii=False)}
- Add an FAQ section with 4 to 6 question and answer pairs based on natural language queries.
- Add a short conclusion with a light CTA.
- Use only HTML tags: h2, h3, p, ul, ol, li, table, tr, td, strong, a.
- Do not mention AI, prompts, or that the article was generated.
- Keep facts evergreen unless the brief explicitly requires a time sensitive update.
- Make the structure scan friendly with specific H2 headings and short paragraphs.
- Do not use emojis. Avoid dashes in visible text.
- Make titles, meta fields, and anchors clear, keyword focused, and click worthy without hype.

Return strict JSON with:
title, meta_title, meta_description, excerpt, focus_keywords, content

Field rules:
- meta_title: max 60 characters and click worthy.
- meta_description: 140 to 155 characters with a power word and implicit CTA.
- focus_keywords: JSON array of 4 to 6 keyword phrases.
- content: valid HTML only, with no markdown fences.

Planning brief:
{opportunity['brief']}
"""



def _bucket_prompt_requirements(bucket: str, query: str) -> str:
    if bucket == "comparison":
        return """- Add a feature by feature comparison table.
- Add a short best choice by creator type section with 3 distinct use cases.
- Include direct comparisons where they help the decision.
"""
    if bucket == "fix":
        mod_line = "- Add a short warning about mod APK risks if the query includes mod or apk.\n" if _contains_mod_apk(query) else ""
        return (
            "- Include a Causes section with realistic reasons.\n"
            "- Include a Step by step fixes checklist for Android.\n"
            "- Add a When it is a server issue note.\n"
            f"{mod_line}"
        )
    if bucket == "download":
        return """- Include a Safe download and setup checklist.
- Clarify device compatibility and version notes.
- Add a common errors section with fixes.
"""
    if bucket == "safety":
        return """- Explain safety, privacy, and legal considerations clearly.
- Include risk factors and what to avoid.
- End with a safer alternative or official option.
"""
    if bucket == "trend":
        return """- Explain what the trend is and why it matters.
- Include how to recreate the trend safely in CapCut.
- Add a quick checklist for execution.
"""
    if bucket == "tutorial":
        return """- Use a step by step numbered guide with clear instructions per step.
- Cover beginner intent first, then advanced tips.
- Add a common mistakes section with solutions.
- Include a quick reference checklist at the end.
- Mention which CapCut version and platform each step applies to.
"""
    if bucket == "alternative":
        return """- Include a feature comparison table (columns: App, Best For, Price, Platforms, Key Feature).
- Add pricing information for each alternative.
- Include a best for whom recommendation per alternative.
- Mention which alternatives work in countries where CapCut is banned.
"""
    if bucket == "platform":
        return """- Include platform-specific system requirements.
- Add step by step setup for the specific platform.
- Note feature differences between platforms.
- Include compatibility notes and known limitations.
"""
    if bucket == "update":
        return """- List what is new in the update with specific features.
- Include how to update step by step.
- Add before and after feature changes where relevant.
- Mention if the update fixes known bugs.
"""
    return """- Use a clear step by step guide.
- Add common mistakes and how to avoid them.
- Include a short checklist for consistent results.
"""


def _contains_mod_apk(text: str) -> bool:
    lowered = (text or "").lower()
    return "mod" in lowered or "apk" in lowered


def _default_meta_description(title: str, bucket: str) -> str:
    if bucket == "comparison":
        return f"{title} with quick answers, a clear decision path, and FAQs to help you choose the right editor."
    if bucket == "fix":
        return f"{title} with fast causes, step by step fixes, and prevention tips for common CapCut issues."
    if bucket == "download":
        return f"{title} with safe setup steps, compatibility notes, and quick fixes for common install errors."
    if bucket == "safety":
        return f"{title} with clear safety guidance, risk factors, and safer alternatives."
    if bucket == "trend":
        return f"{title} explained with what the trend is, how to recreate it, and quick execution tips."
    if bucket == "tutorial":
        return f"{title} with proven step by step instructions, common mistakes to avoid, and beginner tips."
    if bucket == "alternative":
        return f"{title} with honest feature comparisons, pricing details, and best for whom recommendations."
    if bucket == "platform":
        return f"{title} with system requirements, setup steps, and platform specific tips for CapCut users."
    if bucket == "update":
        return f"{title} with what is new, how to update, and essential changes you need to know."
    return f"{title} with quick answers, practical steps, FAQs, and internal links for CapCut users."


def get_generation_health() -> dict:
    configured = bool(config.GEMINI_API_KEYS)
    status = {
        "service": "gemini",
        "configured": configured,
        "ok": False,
        "detail": "",
        "model": config.GEMINI_MODEL,
    }
    if not configured:
        status["detail"] = "Missing GEMINI_API_KEY or GEMINI_API_KEYS"
        return status
    if genai is None:
        status["detail"] = "google genai package is not importable"
        return status
    status["ok"] = True
    status["detail"] = f"Ready with {len(config.GEMINI_API_KEYS)} key(s)"
    return status


def _generate_with_gemini(prompt: str) -> dict | None:
    health = get_generation_health()
    if not health["ok"]:
        return None

    for index, api_key in enumerate(config.GEMINI_API_KEYS, start=1):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            raw_text = getattr(response, "text", "") or ""
            cleaned = raw_text.strip()
            # Handle common wrappers like ```json ... ```
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)

            payload_text = ""
            if cleaned.startswith("{") and cleaned.endswith("}"):
                payload_text = cleaned
            else:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                payload_text = match.group(0) if match else ""

            if not payload_text:
                logger.warning("Gemini response was not valid JSON for key %s", index)
                continue

            try:
                payload = json.loads(payload_text)
            except Exception:
                logger.warning("Gemini response JSON parse failed for key %s", index)
                continue
            if "content" not in payload:
                logger.warning("Gemini response missed content for key %s", index)
                continue
            return payload
        except Exception as exc:
            logger.warning("Gemini generation failed for key %s: %s", index, exc)
    return None


def _parse_comparison_entities(query: str) -> list[str]:

    normalized = re.sub(r"\s+", " ", (query or "").strip())
    normalized = re.sub(r"\bversus\b", "vs", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bvs\.\b", "vs", normalized, flags=re.IGNORECASE)
    parts = [part.strip(" -:|\t").strip() for part in re.split(r"\bvs\b", normalized, flags=re.IGNORECASE) if part.strip()]

    canon = {
        "capcut": "CapCut",
        "inshot": "InShot",
        "canva": "Canva",
        "vn": "VN",
        "kinemaster": "KineMaster",
        "alight motion": "Alight Motion",
        "premiere rush": "Premiere Rush",
        "filmora": "Filmora",
        "imovie": "iMovie",
        "davinci resolve": "DaVinci Resolve",
        "powerdirector": "PowerDirector",
        "vivavideo": "VivaVideo",
        "splice": "Splice",
        "adobe express": "Adobe Express",
        "picsart": "Picsart",
        "lumafusion": "LumaFusion",
    }

    cleaned: list[str] = []
    seen = set()
    for raw in parts:
        simple = re.sub(r"\s+", " ", raw.lower()).strip()
        name = canon.get(simple) or raw.strip().title()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    if not cleaned:
        cleaned = ["CapCut"]

    # Make sure CapCut appears first for our niche site.
    if any(name.lower() == "capcut" for name in cleaned) and cleaned[0].lower() != "capcut":
        cleaned = ["CapCut"] + [name for name in cleaned if name.lower() != "capcut"]

    return cleaned


def _build_template_article(opportunity: dict, internal_links: list[dict]) -> dict:
    bucket = opportunity.get("bucket") or "how_to"
    if bucket == "comparison":
        return _build_comparison_template(opportunity, internal_links)
    if bucket == "fix":
        return _build_fix_template(opportunity, internal_links)
    if bucket == "tutorial":
        return _build_tutorial_template(opportunity, internal_links)
    if bucket == "alternative":
        return _build_alternative_template(opportunity, internal_links)
    if bucket == "platform":
        return _build_platform_template(opportunity, internal_links)
    if bucket == "update":
        return _build_update_template(opportunity, internal_links)
    return _build_generic_template(opportunity, internal_links)

def _build_comparison_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = "comparison"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    apps = _parse_comparison_entities(keyword)
    app_a = apps[0] if apps else "CapCut"
    app_b = apps[1] if len(apps) > 1 else "InShot"
    app_c = apps[2] if len(apps) > 2 else "Canva"

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""
    link_4 = _link_html(internal_links[3]) if len(internal_links) > 3 else ""
    link_5 = _link_html(internal_links[4]) if len(internal_links) > 4 else ""

    quick_answer = (
        f"<p>If you want the fastest path to short form edits with templates and effects, pick <strong>{html.escape(app_a)}</strong>. "
        f"If you want simple, reliable phone editing with minimal complexity, <strong>{html.escape(app_b)}</strong> is usually the easiest. "
        f"If your workflow is more about graphics, thumbnails, and brand ready social posts with light video editing, <strong>{html.escape(app_c)}</strong> often fits best.</p>"
    )

    comparison_table = ""
    if bucket == "comparison":
        comparison_table = f"""
<h2>Quick comparison table</h2>
<table>
<tr><td><strong>Area</strong></td><td><strong>{html.escape(app_a)}</strong></td><td><strong>{html.escape(app_b)}</strong></td><td><strong>{html.escape(app_c)}</strong></td></tr>
<tr><td>Best for</td><td>Short form video edits, templates, effects</td><td>Fast trims, captions, simple social videos</td><td>Design first content, social graphics, teams</td></tr>
<tr><td>Templates</td><td>Strong short form ecosystem</td><td>Some presets, usually simpler</td><td>Large design template library</td></tr>
<tr><td>Learning curve</td><td>Beginner friendly, more depth if you want it</td><td>Very beginner friendly</td><td>Beginner friendly for design, video varies</td></tr>
<tr><td>Export control</td><td>Good control for common social formats</td><td>Simple controls that usually work</td><td>Great for social assets, video export depends on plan</td></tr>
<tr><td>Collaboration</td><td>Mostly solo editing</td><td>Mostly solo editing</td><td>Strong collaboration and brand workflows</td></tr>
</table>
"""

    setup_path = ""
    if bucket == "comparison":
        setup_path = f"""
<h2>Decide in 60 seconds, realistic setup path</h2>
<ol>
<li><strong>Pick your main output.</strong> If it is TikTok or Reels edits, start with {html.escape(app_a)}. If it is story graphics or thumbnails, start with {html.escape(app_c)}.</li>
<li><strong>Pick your device.</strong> If you only edit on a phone, {html.escape(app_b)} stays lightweight. If you need heavier effects, {html.escape(app_a)} tends to scale better.</li>
<li><strong>Pick your must have feature.</strong> Templates and effects: {html.escape(app_a)}. Simple trims and text: {html.escape(app_b)}. Brand kits and collaboration: {html.escape(app_c)}.</li>
</ol>
"""

    feature_deep_dive = ""
    if bucket == "comparison":
        feature_deep_dive = f"""
<h2>Feature by feature comparison, what actually matters</h2>
<table>
<tr><td><strong>Feature</strong></td><td><strong>{html.escape(app_a)}</strong></td><td><strong>{html.escape(app_b)}</strong></td><td><strong>{html.escape(app_c)}</strong></td></tr>
<tr><td>Templates and trends</td><td>Large short form library and trend timing</td><td>Light presets, fewer trend templates</td><td>Large design template catalog</td></tr>
<tr><td>Captions and text</td><td>Strong auto captions, lots of styling</td><td>Basic captions and simple text</td><td>Great typography tools for graphics</td></tr>
<tr><td>Effects and transitions</td><td>Deep effects library and polish tools</td><td>Core effects only</td><td>Design effects, lighter video stack</td></tr>
<tr><td>Audio and music</td><td>Rich music and effects options</td><td>Basic audio trimming</td><td>Good for static posts, lighter on audio</td></tr>
<tr><td>Export control</td><td>Flexible export sizes and presets</td><td>Simple export options</td><td>Strong for social assets, video depends on plan</td></tr>
<tr><td>Collaboration</td><td>Mostly solo use</td><td>Mostly solo use</td><td>Brand kits and team sharing</td></tr>
</table>
"""

    creator_types = ""
    if bucket == "comparison":
        creator_types = f"""
<h2>Best choice by creator type</h2>
<ul>
<li><strong>Short form editor who relies on templates:</strong> {html.escape(app_a)} for speed, effects, and social ready timing.</li>
<li><strong>Casual creator who wants quick trims and text:</strong> {html.escape(app_b)} for a simpler workflow with fewer decisions.</li>
<li><strong>Design led creator focused on thumbnails or story graphics:</strong> {html.escape(app_c)} for templates and brand consistency.</li>
</ul>
"""

    export_cheatsheet = """
<h2>Export settings cheat sheet, safe defaults</h2>
<table>
<tr><td><strong>Platform</strong></td><td><strong>Size</strong></td><td><strong>Frame rate</strong></td><td><strong>Notes</strong></td></tr>
<tr><td>TikTok, Reels, Shorts</td><td>1080 x 1920</td><td>30 or 60 fps</td><td>Keep text inside safe margins.</td></tr>
<tr><td>YouTube landscape</td><td>1920 x 1080</td><td>30 fps</td><td>Use higher bitrate if available.</td></tr>
<tr><td>Stories</td><td>1080 x 1920</td><td>30 fps</td><td>Export as MP4 for compatibility.</td></tr>
</table>
"""

    workflow_checklist = """
<h2>10 minute workflow checklist</h2>
<ol>
<li><strong>Plan the hook.</strong> Decide the first 2 seconds and the main payoff.</li>
<li><strong>Drop in your clips.</strong> Cut to the beat or key moments.</li>
<li><strong>Add captions.</strong> Highlight the key phrases, keep lines short.</li>
<li><strong>Apply a template or style.</strong> Use one consistent look per video.</li>
<li><strong>Polish audio.</strong> Normalize voice, then add music quietly underneath.</li>
<li><strong>Export with a safe preset.</strong> Use vertical 1080 x 1920 for short form.</li>
</ol>
"""

    internal_links_block = ""
    if link_1 or link_2 or link_3 or link_4 or link_5:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        if link_4:
            bits.append(f"<li>{link_4}</li>")
        if link_5:
            bits.append(f"<li>{link_5}</li>")
        internal_links_block = f"<h2>Next best CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>{html.escape(keyword)}</strong> is a common comparison because creators want a fast answer and a practical recommendation, not a long list of vague pros and cons.</p>
<h2>Quick answer</h2>
{quick_answer}
<h2>Key takeaways</h2>
<ul>
<li>Choose the editor that matches your workflow first, short form edits vs simple trims vs design led content.</li>
<li>Device support and export needs matter more than which app has more features.</li>
<li>If CapCut is the frontrunner, set it up once with the right settings so your exports look consistent.</li>
</ul>
{comparison_table}
{setup_path}
{feature_deep_dive}
{creator_types}
<h2>Where {html.escape(app_a)} wins</h2>
<ul>
<li><strong>Short form speed:</strong> built for Reels and TikTok style edits, especially if you lean on templates and effects.</li>
<li><strong>Editing depth:</strong> more room to grow into transitions, timing, and polish without switching tools.</li>
<li><strong>Social export workflow:</strong> usually quick to get a clean vertical export when your settings are right.</li>
</ul>
<p>If you are choosing {html.escape(app_a)} mainly for export quality, start here: {link_1 if link_1 else 'CapCut export settings matter most for consistent results.'}</p>
<h2>Where {html.escape(app_b)} wins</h2>
<ul>
<li><strong>Simple editing:</strong> reliable for trims, basic text, and quick social ready edits.</li>
<li><strong>Low friction:</strong> fewer options to manage if you just want to ship content.</li>
</ul>
<h2>Where {html.escape(app_c)} wins</h2>
<ul>
<li><strong>Design first workflows:</strong> thumbnails, story graphics, and brand kits are often the priority.</li>
<li><strong>Team collaboration:</strong> helpful if multiple people touch the same assets.</li>
</ul>
<h2>Common mistakes and realistic limitations</h2>
<ul>
<li>Expecting every feature to work the same across Android, iOS, and PC versions.</li>
<li>Assuming templates stay the same forever, trends change quickly and examples need refreshing.</li>
<li>For mod APK searches, prioritize safety and privacy research over shortcuts.</li>
</ul>
{internal_links_block}
{export_cheatsheet}
{workflow_checklist}
<h2>FAQ</h2>
<h3>Is {html.escape(app_a)} better than {html.escape(app_b)}?</h3>
<p>Usually yes for template led short form editing and effects. {html.escape(app_b)} often wins when you want the simplest edit with the least setup.</p>
<h3>Can {html.escape(app_c)} replace {html.escape(app_a)} for video editing?</h3>
<p>For lightweight edits and design first content, it can. If you need heavier edits, transitions, and effects, {html.escape(app_a)} is typically the safer choice.</p>
<h3>Which one is best for beginners?</h3>
<p>{html.escape(app_b)} is often the easiest for pure editing basics, while {html.escape(app_c)} is easiest for design templates. {html.escape(app_a)} is still beginner friendly but has more depth.</p>
<h3>Do these apps export without watermarks?</h3>
<p>It depends on the feature and plan. If watermark questions are the main blocker, focus on official settings and exports instead of risky downloads.</p>
<h3>What should I do next if I choose {html.escape(app_a)}?</h3>
<p>Set up your export defaults, learn the key features you will use weekly, and save 1 to 2 repeatable templates so editing stays fast. {link_2 if link_2 else ''}</p>
<h2>Conclusion</h2>
<p>For most creators comparing {html.escape(keyword)}, <strong>{html.escape(app_a)}</strong> is the best starting point when you want short form editing power without a steep learning curve. Use {html.escape(app_b)} for simple, quick edits and {html.escape(app_c)} when design and brand assets are the bigger need.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} explained with a fast recommendation, a clear decision path, and FAQs for picking the right editor."
        ),
        "excerpt": f"A practical comparison of {keyword} with a quick recommendation, trade offs, and next steps.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }



def _build_fix_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = opportunity.get("bucket") or "fix"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    mod_note = ""
    if _contains_mod_apk(keyword):
        mod_note = """
<h2>Important note about mod APKs</h2>
<p>Mod APK builds are not supported by CapCut and can break sign in, network calls, or updates. If you see a persistent no internet message, switch to the official app before deeper troubleshooting.</p>
"""

    content = f"""
<p><strong>{html.escape(keyword)}</strong> usually means CapCut cannot reach its servers or the app is blocked by a device or network setting. The fastest fix is to confirm your connection, update the app, and clear the cache.</p>
<h2>Quick answer</h2>
<p>Restart your phone, switch between Wi Fi and mobile data, disable any VPN or ad blocker, update CapCut, then clear the app cache. If the issue continues, reset app data and sign in again.</p>
<h2>Key takeaways</h2>
<ul>
<li>Most cases are caused by network instability, VPNs, or an outdated app build.</li>
<li>Clearing cache and updating CapCut fixes the error for most Android users.</li>
<li>If the app works on another network, your current Wi Fi or DNS is the blocker.</li>
</ul>
<h2>Why CapCut shows a no internet connection error</h2>
<ul>
<li>Temporary server outage or regional restriction.</li>
<li>Weak or unstable Wi Fi or mobile data connection.</li>
<li>VPN, private DNS, firewall, or ad blocker interfering with requests.</li>
<li>Outdated CapCut version or corrupted cache files.</li>
<li>Background data or battery saver blocking network access.</li>
</ul>
<h2>Working fixes on Android, step by step</h2>
<ol>
<li><strong>Confirm the network.</strong> Open another app or website to check if your connection works.</li>
<li><strong>Switch networks.</strong> Move from Wi Fi to mobile data or try a different Wi Fi network.</li>
<li><strong>Disable VPN or DNS tools.</strong> Turn off VPN, private DNS, or ad blockers and retry.</li>
<li><strong>Update CapCut.</strong> Install the latest version from the official store.</li>
<li><strong>Clear cache.</strong> Settings, Apps, CapCut, Storage, Clear cache.</li>
<li><strong>Reset app data.</strong> If cache fails, clear storage and sign in again.</li>
<li><strong>Allow background data.</strong> Turn off battery saver for CapCut and allow background data.</li>
<li><strong>Restart the device.</strong> A fresh boot fixes stuck network services.</li>
</ol>
{mod_note}
<h2>When it is a server issue</h2>
<p>If CapCut fails on multiple networks and other users report the same error, it is likely a server side outage. Wait a few hours and try again after updating the app.</p>
<h2>Prevent the error from coming back</h2>
<ul>
<li>Keep CapCut updated and avoid skipping multiple versions.</li>
<li>Use stable Wi Fi for large downloads and template sync.</li>
<li>Limit aggressive VPN or ad block rules that break app requests.</li>
</ul>
{internal_links_block}
<h2>FAQ</h2>
<h3>Why does CapCut say no internet when my Wi Fi works?</h3>
<p>VPNs, private DNS, or app level data restrictions can block CapCut even when other apps work.</p>
<h3>Will clearing cache delete my projects?</h3>
<p>Clearing cache usually does not remove saved projects, but clearing storage can sign you out. Back up important exports first.</p>
<h3>Is this an Android only problem?</h3>
<p>It happens on Android most often because of background data and battery limits, but iOS can see it during outages too.</p>
<h3>What if the error appears only on one network?</h3>
<p>The network or DNS settings are the likely blocker. Try another Wi Fi or mobile data and compare.</p>
<h2>Conclusion</h2>
<p>Most no internet errors are caused by network settings or outdated app builds. Run the quick fixes above, then reset app data if needed to get CapCut working again.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} explained with fast causes, step by step fixes, and safe troubleshooting for Android users."
        ),
        "excerpt": f"Fix {keyword} fast with causes, step by step troubleshooting, and prevention tips.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _build_generic_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = opportunity.get("bucket") or "how_to"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    checklist_title = "Quick workflow checklist"
    if bucket == "download":
        checklist_title = "Safe setup checklist"

    content = f"""
<p><strong>{html.escape(keyword)}</strong> is a common CapCut task. The fastest path is to follow a clear setup, avoid common mistakes, and keep your export settings consistent.</p>
<h2>Quick answer</h2>
<p>Follow the steps below in order, then verify the result with a short test export so you can lock in your settings.</p>
<h2>Key takeaways</h2>
<ul>
<li>Match the steps to your device and export goal first.</li>
<li>Use one consistent preset so results stay predictable.</li>
<li>Test a short clip before final export.</li>
</ul>
<h2>Step by step guide</h2>
<ol>
<li><strong>Start with the right project preset.</strong> Pick the format that matches your platform.</li>
<li><strong>Import and trim your clips.</strong> Keep the first seconds tight and clear.</li>
<li><strong>Apply your main effects.</strong> Add only what you can repeat consistently.</li>
<li><strong>Review audio and captions.</strong> Keep captions short and readable.</li>
<li><strong>Export a test clip.</strong> Check it on a phone before final export.</li>
</ol>
<h2>Common mistakes to avoid</h2>
<ul>
<li>Mixing formats or sizes within one project.</li>
<li>Overusing effects that slow down exports.</li>
<li>Skipping a quick preview before publishing.</li>
</ul>
<h2>{checklist_title}</h2>
<ul>
<li>Confirm your output size and frame rate.</li>
<li>Keep text inside safe margins.</li>
<li>Listen with headphones before export.</li>
</ul>
{internal_links_block}
<h2>FAQ</h2>
<h3>What is the fastest way to finish this?</h3>
<p>Use a simple preset, keep effects minimal, and export a short test clip first.</p>
<h3>Will this work on Android and iOS?</h3>
<p>Most steps are the same, but menus can vary by device and app version.</p>
<h3>How do I keep quality consistent?</h3>
<p>Stick to one export preset and avoid changing formats mid project.</p>
<h3>What if it does not look right after export?</h3>
<p>Re check your size, frame rate, and bitrate, then export a short test clip again.</p>
<h2>Conclusion</h2>
<p>Follow the steps above and keep one reliable preset for steady, repeatable results.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} explained with a quick guide, common mistakes, and practical steps for consistent results."
        ),
        "excerpt": f"A practical guide to {keyword} with clear steps, tips, and FAQs.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _build_tutorial_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = "tutorial"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>CapCut</strong>, developed by ByteDance, is a free video editing app available on Android, iOS, PC (Windows and Mac), and Web. <strong>{html.escape(keyword)}</strong> is one of the most searched CapCut tutorials for beginners and intermediate users alike.</p>
<h2>Direct answer</h2>
<p>{html.escape(keyword).title()} in CapCut is straightforward once you know where the tools are. Follow the numbered steps below, which work on both mobile and desktop versions of CapCut.</p>
<h2>Key takeaways</h2>
<ul>
<li>This tutorial works on CapCut for Android, iOS, and PC.</li>
<li>Follow the steps in order for the best results.</li>
<li>Test with a short clip before applying to your full project.</li>
<li>Common mistakes are covered at the end so you can avoid them.</li>
</ul>
<h2>Step by step tutorial</h2>
<ol>
<li><strong>Open CapCut and create a new project.</strong> Tap the plus icon on the home screen and import your video clip.</li>
<li><strong>Navigate to the right tool.</strong> Find the relevant tool in the bottom toolbar or effects panel.</li>
<li><strong>Apply the effect or adjustment.</strong> Follow any on screen prompts and adjust the settings to match your needs.</li>
<li><strong>Preview your changes.</strong> Play the timeline to check the result looks correct.</li>
<li><strong>Fine tune if needed.</strong> Adjust intensity, timing, or position until you are satisfied with the output.</li>
<li><strong>Export your video.</strong> Use 1080p at 30fps as the safe default for most social platforms.</li>
</ol>
<h2>Platform specific notes</h2>
<table>
<tr><td><strong>Platform</strong></td><td><strong>Notes</strong></td></tr>
<tr><td>Android</td><td>Most features available in the latest version from Play Store.</td></tr>
<tr><td>iOS</td><td>Same feature set as Android with minor UI differences.</td></tr>
<tr><td>PC (Windows/Mac)</td><td>More screen space makes precise edits easier. Some advanced features are PC only.</td></tr>
<tr><td>Web</td><td>Limited feature set compared to the desktop app. Best for quick edits.</td></tr>
</table>
<h2>Common mistakes to avoid</h2>
<ul>
<li>Skipping the preview step and exporting with errors.</li>
<li>Using the wrong export resolution for your target platform.</li>
<li>Not updating CapCut, which can cause missing features or bugs.</li>
<li>Applying too many effects at once, which slows rendering.</li>
</ul>
<h2>Quick reference checklist</h2>
<ul>
<li>Import your clip and set the correct aspect ratio.</li>
<li>Apply the main effect or adjustment.</li>
<li>Preview on the timeline.</li>
<li>Export at 1080p, 30fps for social media.</li>
<li>Check the result on your phone before publishing.</li>
</ul>
{internal_links_block}
<h2>FAQ</h2>
<h3>Does this work on CapCut for PC?</h3>
<p>Yes, the steps are similar on PC. The toolbar layout may differ slightly but the same tools are available.</p>
<h3>What CapCut version do I need?</h3>
<p>Use the latest version from the official app store or capcut.com for access to all features mentioned in this tutorial.</p>
<h3>Can I undo changes if something goes wrong?</h3>
<p>Yes, CapCut has an undo button. You can also tap the history icon to revert multiple steps.</p>
<h3>What is the best export quality for social media?</h3>
<p>1080p at 30fps with high bitrate works for most platforms including TikTok, Instagram Reels, and YouTube Shorts.</p>
<h2>Conclusion</h2>
<p>Follow the steps above to complete {html.escape(keyword)} in CapCut quickly and reliably. Start with a short test clip, confirm the result, then apply to your full project for consistent quality.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} with proven step by step instructions and beginner tips for CapCut users."
        ),
        "excerpt": f"Step by step tutorial for {keyword} in CapCut with beginner tips and common mistakes to avoid.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _build_alternative_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = "alternative"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>CapCut</strong>, developed by ByteDance, is one of the most popular free video editors available on Android, iOS, PC, and Web. However, users in some regions or those needing specific features often search for <strong>{html.escape(keyword)}</strong> to find the right tool for their workflow.</p>
<h2>Direct answer</h2>
<p>The best CapCut alternatives depend on your needs: InShot for simple mobile edits, DaVinci Resolve for professional desktop editing, Canva for design first workflows, and KineMaster for advanced mobile editing. All options below are available in countries where CapCut may be restricted.</p>
<h2>Key takeaways</h2>
<ul>
<li>No single alternative replaces every CapCut feature perfectly.</li>
<li>Choose based on your primary platform (mobile vs desktop) and editing complexity.</li>
<li>Several alternatives work in countries where CapCut is banned or restricted.</li>
<li>Free options exist for every use case, though some have premium tiers.</li>
</ul>
<h2>Feature comparison table</h2>
<table>
<tr><td><strong>App</strong></td><td><strong>Best For</strong></td><td><strong>Price</strong></td><td><strong>Platforms</strong></td><td><strong>Key Feature</strong></td></tr>
<tr><td>InShot</td><td>Quick mobile edits</td><td>Free (Pro available)</td><td>Android, iOS</td><td>Simple trimming and filters</td></tr>
<tr><td>KineMaster</td><td>Advanced mobile editing</td><td>Free (Premium available)</td><td>Android, iOS</td><td>Multi layer editing on mobile</td></tr>
<tr><td>DaVinci Resolve</td><td>Professional desktop editing</td><td>Free (Studio available)</td><td>Windows, Mac, Linux</td><td>Industry grade color correction</td></tr>
<tr><td>Canva</td><td>Design first video content</td><td>Free (Pro available)</td><td>Web, Android, iOS</td><td>Templates and brand kits</td></tr>
<tr><td>VN</td><td>Lightweight desktop and mobile</td><td>Free</td><td>Android, iOS, Windows, Mac</td><td>Clean timeline editing</td></tr>
<tr><td>Filmora</td><td>Beginner desktop editing</td><td>Free trial (Paid plans)</td><td>Windows, Mac</td><td>Drag and drop simplicity</td></tr>
<tr><td>iMovie</td><td>Apple ecosystem users</td><td>Free</td><td>Mac, iOS</td><td>Seamless Apple integration</td></tr>
<tr><td>Adobe Express</td><td>Quick social media content</td><td>Free (Premium available)</td><td>Web, Android, iOS</td><td>Adobe asset library access</td></tr>
</table>
<h2>Which alternative is best for you?</h2>
<ul>
<li><strong>Quick social media edits on phone:</strong> InShot or VN for speed and simplicity.</li>
<li><strong>Professional or long form editing:</strong> DaVinci Resolve for free, Filmora for an easier learning curve.</li>
<li><strong>Design and branding focus:</strong> Canva for templates and team collaboration.</li>
<li><strong>CapCut banned in your country:</strong> InShot, VN, and KineMaster are widely available alternatives.</li>
<li><strong>Apple users:</strong> iMovie integrates seamlessly with the Apple ecosystem at no cost.</li>
</ul>
<h2>Alternatives that work where CapCut is banned</h2>
<p>In countries where CapCut is restricted (including India and potentially the US due to TikTok related regulations), these alternatives are fully available: InShot, KineMaster, DaVinci Resolve, Canva, VN, Filmora, iMovie, and Adobe Express.</p>
{internal_links_block}
<h2>FAQ</h2>
<h3>Is there a free alternative to CapCut with no watermark?</h3>
<p>VN and DaVinci Resolve both offer watermark free exports on their free plans.</p>
<h3>Which CapCut alternative has the best templates?</h3>
<p>Canva has the largest template library, while InShot offers good template options for mobile users.</p>
<h3>Can I use these alternatives on PC?</h3>
<p>DaVinci Resolve, Filmora, VN, and Canva (web) all work on desktop computers.</p>
<h3>What is the closest alternative to CapCut overall?</h3>
<p>VN is the closest in terms of free features and clean interface. InShot is the closest for mobile only editing.</p>
<h2>Conclusion</h2>
<p>The right CapCut alternative depends on your platform, budget, and editing complexity. Try InShot or VN for mobile, DaVinci Resolve for desktop power, or Canva for design focused content.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} with honest feature comparisons, pricing details, and best for whom recommendations."
        ),
        "excerpt": f"Explore the best alternatives to CapCut with feature comparisons, pricing, and recommendations.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _build_platform_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = "platform"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>CapCut</strong> is a free video editing application developed by ByteDance, available across multiple platforms including Android, iOS, Windows, Mac, and Web. <strong>{html.escape(keyword)}</strong> covers everything you need to know about using CapCut on your specific device.</p>
<h2>Direct answer</h2>
<p>CapCut is available on Android (Google Play Store), iOS (App Store), Windows and Mac (capcut.com), and as a web editor (capcut.com/editor). Features vary by platform, with the desktop version offering the most complete editing toolkit.</p>
<h2>Key takeaways</h2>
<ul>
<li>CapCut desktop (PC/Mac) has the most features, including advanced keyframes and effects.</li>
<li>Mobile versions (Android/iOS) are best for quick edits and social media content.</li>
<li>The web version is limited but useful for basic edits without installing anything.</li>
<li>Some features are platform exclusive, check the comparison table below.</li>
</ul>
<h2>System requirements</h2>
<table>
<tr><td><strong>Platform</strong></td><td><strong>Minimum Requirements</strong></td><td><strong>Download Source</strong></td></tr>
<tr><td>Android</td><td>Android 5.0+, 2GB RAM</td><td>Google Play Store</td></tr>
<tr><td>iOS</td><td>iOS 11.0+, iPhone 7 or later</td><td>Apple App Store</td></tr>
<tr><td>Windows</td><td>Windows 10 64 bit, 4GB RAM, 2GB disk space</td><td>capcut.com</td></tr>
<tr><td>Mac</td><td>macOS 10.15+, 4GB RAM</td><td>capcut.com</td></tr>
<tr><td>Web</td><td>Modern browser (Chrome, Edge, Firefox)</td><td>capcut.com/editor</td></tr>
</table>
<h2>Feature differences by platform</h2>
<table>
<tr><td><strong>Feature</strong></td><td><strong>Mobile</strong></td><td><strong>Desktop</strong></td><td><strong>Web</strong></td></tr>
<tr><td>Timeline editing</td><td>Basic</td><td>Advanced with multi track</td><td>Basic</td></tr>
<tr><td>Keyframes</td><td>Limited</td><td>Full support</td><td>Limited</td></tr>
<tr><td>Auto captions</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
<tr><td>Green screen</td><td>Yes</td><td>Yes</td><td>No</td></tr>
<tr><td>Text to speech</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
<tr><td>Export quality</td><td>Up to 4K</td><td>Up to 4K</td><td>Up to 1080p</td></tr>
</table>
<h2>How to set up CapCut on your platform</h2>
<ol>
<li><strong>Download from the official source.</strong> Use the links above for your platform to avoid unofficial builds.</li>
<li><strong>Install and open the app.</strong> Follow the on screen setup prompts.</li>
<li><strong>Sign in (optional).</strong> Signing in enables cloud sync and template access.</li>
<li><strong>Set your default export settings.</strong> Choose 1080p at 30fps as a safe default.</li>
<li><strong>Create your first project.</strong> Import media and start editing.</li>
</ol>
<h2>Known limitations</h2>
<ul>
<li>Web editor lacks green screen, advanced effects, and high resolution exports.</li>
<li>Mobile versions may struggle with complex multi track projects.</li>
<li>CapCut may not be available in all regions due to local restrictions.</li>
</ul>
{internal_links_block}
<h2>FAQ</h2>
<h3>Is CapCut for PC free?</h3>
<p>Yes, CapCut desktop is free to download and use from the official website capcut.com.</p>
<h3>Can I sync projects between mobile and desktop?</h3>
<p>Yes, if you sign in with the same account. Cloud sync allows you to start on mobile and continue on desktop.</p>
<h3>Which platform has the best CapCut experience?</h3>
<p>Desktop (Windows/Mac) offers the most features and screen space. Mobile is best for quick edits on the go.</p>
<h3>Is CapCut available as a web app?</h3>
<p>Yes, visit capcut.com/editor to use the web version. Features are more limited compared to the desktop app.</p>
<h2>Conclusion</h2>
<p>CapCut works across all major platforms with slightly different feature sets. Choose desktop for maximum editing power, mobile for convenience, and web for quick edits without installation.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} with system requirements, setup steps, and platform specific tips for CapCut users."
        ),
        "excerpt": f"Complete platform guide for {keyword} including setup, features, and compatibility.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _build_update_template(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = "update"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Related CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>CapCut</strong>, the free video editing app by ByteDance, regularly receives updates with new features, effects, and bug fixes across Android, iOS, and PC. <strong>{html.escape(keyword)}</strong> covers everything that changed in the latest release.</p>
<h2>Direct answer</h2>
<p>The latest CapCut update introduces new effects, performance improvements, and bug fixes. Update through your platform's official app store or capcut.com to get the newest features.</p>
<h2>Key takeaways</h2>
<ul>
<li>Always update CapCut from official sources (Play Store, App Store, or capcut.com).</li>
<li>New updates often include AI features, effects packs, and stability improvements.</li>
<li>Some features roll out to specific platforms first before reaching all devices.</li>
<li>Back up your projects before updating to avoid any compatibility issues.</li>
</ul>
<h2>What is new in this update</h2>
<ul>
<li><strong>New effects and filters:</strong> Additional creative effects and filters for trending content styles.</li>
<li><strong>AI feature improvements:</strong> Enhanced auto captions, background removal, and AI upscaling accuracy.</li>
<li><strong>Performance fixes:</strong> Faster export times and reduced lag on older devices.</li>
<li><strong>Bug fixes:</strong> Resolved known issues with audio sync, black screen errors, and export failures.</li>
<li><strong>UI improvements:</strong> Cleaner interface with better tool organization.</li>
</ul>
<h2>How to update CapCut</h2>
<ol>
<li><strong>Android:</strong> Open Google Play Store, search for CapCut, and tap Update.</li>
<li><strong>iOS:</strong> Open App Store, go to your profile, find CapCut, and tap Update.</li>
<li><strong>PC (Windows/Mac):</strong> Visit capcut.com and download the latest installer, or use the in app update prompt.</li>
<li><strong>Verify the version:</strong> Open CapCut, go to Settings, and check the version number matches the latest release.</li>
</ol>
<h2>Before and after this update</h2>
<table>
<tr><td><strong>Feature</strong></td><td><strong>Before</strong></td><td><strong>After</strong></td></tr>
<tr><td>Auto captions</td><td>Basic accuracy</td><td>Improved AI accuracy with better punctuation</td></tr>
<tr><td>Export speed</td><td>Standard processing</td><td>Faster rendering on supported devices</td></tr>
<tr><td>Effects library</td><td>Previous collection</td><td>Expanded with new trending effects</td></tr>
<tr><td>Stability</td><td>Occasional crashes on complex projects</td><td>Improved memory management</td></tr>
</table>
<h2>Should you update?</h2>
<p>Yes. CapCut updates are free and typically improve stability. If you are experiencing crashes, export errors, or missing features, updating is the first troubleshooting step.</p>
{internal_links_block}
<h2>FAQ</h2>
<h3>Will updating CapCut delete my projects?</h3>
<p>No, updating preserves your existing projects. However, backing up important exports before any update is a good practice.</p>
<h3>Can I go back to the old version?</h3>
<p>Official app stores do not support version rollback. Sideloading old versions is not recommended due to security risks.</p>
<h3>Why is the update not showing for me?</h3>
<p>Updates may roll out gradually by region. Check again in a few days or visit the official website for the latest version.</p>
<h3>Is the update available on all platforms?</h3>
<p>Most updates eventually reach all platforms, but some features may launch on mobile first before coming to desktop or web.</p>
<h2>Conclusion</h2>
<p>Keep CapCut updated to get the latest features, bug fixes, and performance improvements. Update through official channels and back up your projects before major version changes.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} with what is new, how to update, and essential changes you need to know."
        ),
        "excerpt": f"Everything about {keyword} including new features, update steps, and what changed.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _get_apps_for_opportunity(opportunity: dict) -> list[str]:
    bucket = opportunity.get("bucket") or ""
    if bucket == "comparison":
        return _parse_comparison_entities(opportunity.get("query") or "")
    return ["CapCut"]


def _build_expansion_sections(opportunity: dict, internal_links: list[dict]) -> str:
    bucket = opportunity.get("bucket") or "how_to"
    if bucket == "comparison":
        apps = _get_apps_for_opportunity(opportunity)
        app_a = apps[0] if apps else "CapCut"
        app_b = apps[1] if len(apps) > 1 else "InShot"
        app_c = apps[2] if len(apps) > 2 else "Canva"

        link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
        link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""

        return f"""
<h2>Which editor fits your workflow?</h2>
<ul>
<li><strong>Short form, trend led edits:</strong> {html.escape(app_a)} keeps you fast with templates, effects, and polish.</li>
<li><strong>Minimal steps and fast exports:</strong> {html.escape(app_b)} is the simplest path for reliable edits.</li>
<li><strong>Design heavy social content:</strong> {html.escape(app_c)} shines when visuals and brand assets matter most.</li>
</ul>
<h2>Practical decision rules, no guesswork</h2>
<ul>
<li>If you need a template driven workflow every week, default to {html.escape(app_a)}.</li>
<li>If you hand edits off to a teammate or need shared assets, default to {html.escape(app_c)}.</li>
<li>If you only need trims, captions, and exports, {html.escape(app_b)} is enough.</li>
</ul>
<h2>Quality checklist before you export</h2>
<ul>
<li>Keep key text inside safe margins so it is not cropped on phones.</li>
<li>Check captions for timing and readability, short lines work best.</li>
<li>Listen with headphones and reduce music volume under voice.</li>
<li>Export one test clip, review on a phone, then finalize the batch.</li>
</ul>
<h2>Related CapCut resources</h2>
<ul>
<li>{link_1 if link_1 else 'CapCut best settings to keep quality consistent.'}</li>
<li>{link_2 if link_2 else 'CapCut templates and trends guide for faster edits.'}</li>
</ul>
"""

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""

    return f"""
<h2>Quality checklist before you export</h2>
<ul>
<li>Keep key text inside safe margins so it is not cropped on phones.</li>
<li>Check captions for timing and readability, short lines work best.</li>
<li>Listen with headphones and reduce music volume under voice.</li>
<li>Export one test clip, review on a phone, then finalize the batch.</li>
</ul>
<h2>Related CapCut resources</h2>
<ul>
<li>{link_1 if link_1 else 'CapCut best settings to keep quality consistent.'}</li>
<li>{link_2 if link_2 else 'CapCut templates and trends guide for faster edits.'}</li>
</ul>
"""


def _normalize_article(article: dict, opportunity: dict, internal_links: list[dict]) -> dict:
    content = _cleanup_html(article.get("content") or "")
    if not content:
        content = _build_template_article(opportunity, internal_links)["content"]

    content = _sanitize_html_text(content)

    if _count_words(_strip_html(content)) < config.ARTICLE_MIN_WORDS:
        content = f"{content}{_build_expansion_sections(opportunity, internal_links)}"
        content = _sanitize_html_text(content)

    if internal_links:
        link_count = content.count("<a ")
        if link_count < 3:
            insert = _build_related_links_section(internal_links[:5])
            if "<h2>Conclusion</h2>" in content:
                content = content.replace("<h2>Conclusion</h2>", insert + "<h2>Conclusion</h2>", 1)
            else:
                content = f"{content}{insert}"

    # --- Schema injection ---
    bucket = opportunity.get("bucket") or "how_to"
    title = _sanitize_plain_text((article.get("title") or opportunity["title"]).strip())
    schema_types = config.ARTICLE_SCHEMA_TYPES.get(bucket, ["Article", "FAQPage"])
    all_schemas: list[str] = []

    # FAQ schema
    faqs = _extract_faqs_from_html(content)
    faq_schema = _build_faq_schema(faqs) if faqs else ""
    if faq_schema:
        all_schemas.append(faq_schema)

    # HowTo schema (for how_to, fix, tutorial buckets)
    if "HowTo" in schema_types:
        howto_schema = _build_howto_schema(content, title)
        if howto_schema:
            all_schemas.append(howto_schema)

    # Article schema
    if "Article" in schema_types:
        meta_desc = _sanitize_plain_text(
            article.get("meta_description")
            or _default_meta_description(title, bucket)
        )
        article_schema = _build_article_schema(title, meta_desc, opportunity.get("slug") or "")
        if article_schema:
            all_schemas.append(article_schema)

    # SoftwareApplication schema
    if "SoftwareApplication" in schema_types:
        software_schema = _build_software_schema()
        if software_schema:
            all_schemas.append(software_schema)

    # BreadcrumbList schema
    if "BreadcrumbList" in schema_types:
        breadcrumb_schema = _build_breadcrumb_schema(title, bucket, opportunity.get("slug") or "")
        if breadcrumb_schema:
            all_schemas.append(breadcrumb_schema)

    # Inject all schemas that are not already present
    if all_schemas and "application/ld+json" not in content:
        content = f"{content}{''.join(all_schemas)}"
    elif all_schemas:
        # Some schemas already present (e.g. from Gemini output); add only missing ones
        for schema_block in all_schemas:
            # Extract the @type to check uniqueness
            type_match = re.search(r'"@type"\s*:\s*"([^"]+)"', schema_block)
            if type_match:
                schema_type = type_match.group(1)
                if f'"@type":"{schema_type}"' not in content.replace(" ", "") and f'"@type": "{schema_type}"' not in content:
                    content = f"{content}{schema_block}"

    meta_title = _trim_meta(_sanitize_plain_text(article.get("meta_title") or article.get("seo_title") or title))
    meta_description = _trim_description(
        _sanitize_plain_text(
            article.get("meta_description")
            or _default_meta_description(title, bucket)
        )
    )
    focus_keywords = _normalize_focus_keywords(article.get("focus_keywords"), opportunity)
    excerpt = _sanitize_plain_text((article.get("excerpt") or meta_description).strip())

    return {
        "title": title,
        "seo_title": meta_title,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "excerpt": excerpt,
        "focus_keywords": focus_keywords,
        "faq_schema": faq_schema,
        "faq_count": len(faqs),
        "internal_links": internal_links[:5],
        "content": content,
    }


def _select_internal_links(existing_pages: list[dict], query: str, limit: int = 6) -> list[dict]:
    query_tokens = _keyword_tokens(query)
    site_netloc = urlparse(config.SITE_URL).netloc.lower().lstrip("www.")
    candidates: list[dict] = []
    for page in existing_pages:
        slug = page.get("slug", "")
        if slug in config.EXCLUDE_SLUG_HINTS or slug == "home":
            continue
        page_url = (page.get("url") or "").strip()
        if not page_url:
            continue
        parsed_url = urlparse(page_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            continue
        page_netloc = parsed_url.netloc.lower().lstrip("www.")
        if site_netloc and page_netloc != site_netloc:
            continue
        haystack = f"{page.get('title', '')} {slug}".lower()
        overlap = len(query_tokens & _keyword_tokens(haystack))
        topical_bonus = 2 if "capcut" in haystack else 0
        score = overlap * 5 + topical_bonus
        candidates.append(
            {
                "title": page.get("title") or slug.replace("-", " ").title(),
                "url": page_url,
                "slug": slug,
                "anchor": _suggest_anchor(page),
                "score": score,
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["title"]))
    return candidates[:limit]


def _build_related_links_section(internal_links: list[dict]) -> str:
    links = "".join(f"<li>{_link_html(link)}</li>" for link in internal_links)
    return f"<h2>Related CapCut guides</h2><ul>{links}</ul>"


def _link_html(link: dict) -> str:
    anchor = _sanitize_plain_text(link.get("anchor") or "CapCut guide")
    if not anchor:
        anchor = "CapCut guide"
    return f'<a href="{html.escape(link["url"], quote=True)}">{html.escape(anchor)}</a>'


def _suggest_anchor(page: dict) -> str:
    title = (page.get("title") or page.get("slug") or "CapCut guide").strip()
    title = _sanitize_plain_text(title)
    if not title:
        title = "CapCut guide"
    return title if title.lower().startswith("capcut") else f"CapCut {title}"


def _extract_faqs_from_html(content: str) -> list[dict]:
    match = FAQ_SECTION_PATTERN.search(content)
    if not match:
        return []
    faqs = []
    for question, answer in QUESTION_PATTERN.findall(match.group(1)):
        clean_question = _strip_html(question).strip()
        clean_answer = _strip_html(answer).strip()
        if clean_question and clean_answer:
            faqs.append({"question": clean_question, "answer": clean_answer})
    return faqs


def _build_faq_schema(faqs: list[dict]) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["answer"],
                },
            }
            for faq in faqs
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


def _build_howto_schema(content: str, title: str) -> str:
    """Extract ordered list steps from content and build HowTo JSON-LD."""
    steps = []
    ol_match = re.search(r"<ol>(.*?)</ol>", content, re.DOTALL | re.IGNORECASE)
    if not ol_match:
        return ""
    li_items = re.findall(r"<li>(.*?)</li>", ol_match.group(1), re.DOTALL | re.IGNORECASE)
    for i, item in enumerate(li_items, 1):
        step_text = _strip_html(item).strip()
        if step_text:
            steps.append({
                "@type": "HowToStep",
                "position": i,
                "name": step_text[:80],
                "text": step_text,
            })
    if not steps:
        return ""
    payload = {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": title,
        "step": steps,
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


def _build_article_schema(title: str, description: str, slug: str) -> str:
    """Build Article JSON-LD schema."""
    payload = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title[:110],
        "description": description[:200],
        "author": {
            "@type": "Organization",
            "name": config.SITE_NAME,
            "url": config.SITE_URL,
        },
        "publisher": {
            "@type": "Organization",
            "name": config.SITE_NAME,
            "url": config.SITE_URL,
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"{config.SITE_URL.rstrip('/')}/{slug}/",
        },
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


def _build_software_schema() -> str:
    """Build SoftwareApplication JSON-LD schema for CapCut."""
    payload = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "CapCut",
        "applicationCategory": "MultimediaApplication",
        "operatingSystem": "Android, iOS, Windows, macOS, Web",
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
        },
        "author": {
            "@type": "Organization",
            "name": "ByteDance",
        },
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


def _build_breadcrumb_schema(title: str, bucket: str, slug: str) -> str:
    """Build BreadcrumbList JSON-LD schema."""
    bucket_label = bucket.replace("_", " ").title()
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": config.SITE_URL,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": bucket_label,
                "item": f"{config.SITE_URL.rstrip('/')}/category/{bucket}/",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": title[:60],
                "item": f"{config.SITE_URL.rstrip('/')}/{slug}/",
            },
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'


def _normalize_focus_keywords(raw_value: object, opportunity: dict) -> list[str]:
    if isinstance(raw_value, list):
        values = [str(item).strip().lower() for item in raw_value if str(item).strip()]
    elif isinstance(raw_value, str):
        values = [part.strip().lower() for part in raw_value.split(",") if part.strip()]
    else:
        values = []

    cleaned = []
    seen = set()
    for keyword in values + _default_focus_keywords(opportunity["query"], opportunity["bucket"]):
        normalized = re.sub(r"\s+", " ", keyword).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
        if len(cleaned) >= config.DEFAULT_FOCUS_KEYWORD_COUNT:
            break
    return cleaned



def _default_focus_keywords(keyword: str, bucket: str) -> list[str]:
    base = keyword.lower().strip()
    variations = [
        base,
        f"{base} guide",
        f"{base} tutorial",
        f"{base} tips",
    ]
    if bucket == "comparison":
        variations.append(f"{base} review")
    elif bucket == "fix":
        variations.append(f"{base} solution")
    elif bucket == "download":
        variations.append(f"{base} latest version")
    elif bucket == "tutorial":
        variations.append(f"{base} step by step")
    elif bucket == "alternative":
        variations.append(f"{base} free")
    elif bucket == "platform":
        variations.append(f"{base} setup")
    elif bucket == "update":
        variations.append(f"{base} latest")
    else:
        variations.append(f"best {base}")
    return variations


def _keyword_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in STOPWORDS and len(token) > 2}


def _trim_meta(value: str, limit: int = 60) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip(" -|:") + "..."


def _trim_description(value: str, min_len: int = 140, max_len: int = 155) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) > max_len:
        compact = compact[: max_len - 1].rstrip(" -|:") + "..."
    if len(compact) >= min_len:
        return compact
    supplement = " Learn key steps, common issues, and the best CapCut follow up resources."
    merged = (compact + supplement).strip()
    if len(merged) > max_len:
        merged = merged[: max_len - 1].rstrip(" -|:") + "..."
    return merged


def _cleanup_html(value: str) -> str:
    return re.sub(r"\n\s+", "", value).strip()


def _strip_html(value: str) -> str:
    no_scripts = SCRIPT_PATTERN.sub(" ", value)
    plain = HTML_TAG_PATTERN.sub(" ", no_scripts)
    return re.sub(r"\s+", " ", plain).strip()


def _sanitize_plain_text(value: str) -> str:
    if not value:
        return ""
    value = EMOJI_PATTERN.sub("", value)
    value = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212]", " ", value)
    value = value.replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def _sanitize_html_text(value: str) -> str:
    if not value:
        return ""
    output: list[str] = []
    buffer: list[str] = []
    in_tag = False
    for ch in value:
        if ch == "<":
            if buffer:
                output.append(_sanitize_plain_text("".join(buffer)))
                buffer = []
            in_tag = True
            output.append(ch)
            continue
        if ch == ">" and in_tag:
            in_tag = False
            output.append(ch)
            continue
        if in_tag:
            output.append(ch)
        else:
            buffer.append(ch)
    if buffer:
        output.append(_sanitize_plain_text("".join(buffer)))
    return "".join(output)


def _count_words(value: str) -> int:
    return len(WORD_PATTERN.findall(value))













