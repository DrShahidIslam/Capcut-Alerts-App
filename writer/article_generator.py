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
    internal_link_lines = [
        {
            "title": link["title"],
            "url": link["url"],
            "anchor_hint": link["anchor"],
        }
        for link in internal_links[:5]
    ]
    return f"""
You are writing for {config.SITE_NAME}, a niche blog about CapCut and CapCut Pro APK topics.

Write a complete article in clean HTML that is optimized for traditional search, answer engines, and generative search experiences.

Requirements:
- Focus keyword: {opportunity['query']}
- Suggested title: {opportunity['title']}
- Article type: {opportunity['bucket']}
- Tone: {config.ARTICLE_TONE}
- Length: {config.ARTICLE_MIN_WORDS}-{config.ARTICLE_MAX_WORDS} words
- Start with a direct answer summary in the first 2 paragraphs.
- Use clear entities, practical steps, and honest trade-offs so the article can be cited by AI overviews.
- Include a concise "Key takeaways" list near the top.
- Cover beginner intent first, then advanced considerations.
- Include direct comparisons when relevant and mention risks or limitations honestly.
- Add at least 3 natural internal links using this pool when relevant: {json.dumps(internal_link_lines, ensure_ascii=False)}
- Add an FAQ section with 4 to 6 question-and-answer pairs based on natural language queries.
- Add a short conclusion with a light CTA.
- Use only HTML tags: h2, h3, p, ul, ol, li, table, tr, td, strong, a.
- Do not mention AI, prompts, or that the article was generated.
- Keep facts evergreen unless the brief explicitly requires a time-sensitive update.
- Make the structure scan-friendly with specific H2 headings and short paragraphs.

Return strict JSON with:
title, meta_title, meta_description, excerpt, focus_keywords, content

Field rules:
- meta_title: max 60 characters and click-worthy.
- meta_description: 140 to 155 characters.
- focus_keywords: JSON array of 4 to 6 keyword phrases.
- content: valid HTML only, with no markdown fences.

Planning brief:
{opportunity['brief']}
"""


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
        status["detail"] = "google-genai package is not importable"
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
    keyword = opportunity["query"]
    title = opportunity["title"]
    bucket = opportunity.get("bucket") or "how_to"
    focus_keywords = _default_focus_keywords(keyword, bucket)

    apps = _parse_comparison_entities(keyword) if bucket == "comparison" else ["CapCut"]
    app_a = apps[0] if apps else "CapCut"
    app_b = apps[1] if len(apps) > 1 else "InShot"
    app_c = apps[2] if len(apps) > 2 else "Canva"

    link_1 = _link_html(internal_links[0]) if len(internal_links) > 0 else ""
    link_2 = _link_html(internal_links[1]) if len(internal_links) > 1 else ""
    link_3 = _link_html(internal_links[2]) if len(internal_links) > 2 else ""

    quick_answer = (
        f"<p>If you want the fastest path to short-form edits with templates and effects, pick <strong>{html.escape(app_a)}</strong>. "
        f"If you want simple, reliable phone editing with minimal complexity, <strong>{html.escape(app_b)}</strong> is usually the easiest. "
        f"If your workflow is more about graphics, thumbnails, and brand-ready social posts (with light video editing), <strong>{html.escape(app_c)}</strong> often fits best.</p>"
    )

    comparison_table = ""
    if bucket == "comparison":
        comparison_table = f"""
<h2>Quick comparison table</h2>
<table>
<tr><td><strong>Area</strong></td><td><strong>{html.escape(app_a)}</strong></td><td><strong>{html.escape(app_b)}</strong></td><td><strong>{html.escape(app_c)}</strong></td></tr>
<tr><td>Best for</td><td>Short-form video edits, templates, effects</td><td>Fast trims, captions, simple social videos</td><td>Design-first content, social graphics, teams</td></tr>
<tr><td>Templates</td><td>Strong short-form ecosystem</td><td>Some presets, usually simpler</td><td>Huge design template library</td></tr>
<tr><td>Learning curve</td><td>Beginner friendly, more depth if you want it</td><td>Very beginner friendly</td><td>Beginner friendly for design, video varies</td></tr>
<tr><td>Export control</td><td>Good control for common social formats</td><td>Simple controls that usually work</td><td>Great for social assets, video export depends on plan</td></tr>
<tr><td>Collaboration</td><td>Mostly solo editing</td><td>Mostly solo editing</td><td>Strong collaboration and brand workflows</td></tr>
</table>
"""

    setup_path = ""
    if bucket == "comparison":
        setup_path = f"""
<h2>Decide in 60 seconds (realistic setup path)</h2>
<ol>
<li><strong>Pick your main output.</strong> If it is TikTok/Reels edits, start with {html.escape(app_a)}. If it is story graphics or thumbnails, start with {html.escape(app_c)}.</li>
<li><strong>Pick your device.</strong> If you only edit on a phone, {html.escape(app_b)} stays lightweight. If you need heavier effects, {html.escape(app_a)} tends to scale better.</li>
<li><strong>Pick your "must-have" feature.</strong> Templates and effects: {html.escape(app_a)}. Simple trims and text: {html.escape(app_b)}. Brand kits and collaboration: {html.escape(app_c)}.</li>
</ol>
"""

    internal_links_block = ""
    if link_1 or link_2 or link_3:
        bits = []
        if link_1:
            bits.append(f"<li>{link_1}</li>")
        if link_2:
            bits.append(f"<li>{link_2}</li>")
        if link_3:
            bits.append(f"<li>{link_3}</li>")
        internal_links_block = f"<h2>Next best CapCut guides</h2><ul>{''.join(bits)}</ul>"

    content = f"""
<p><strong>{html.escape(keyword)}</strong> is a common comparison because creators want a fast answer and a practical recommendation, not a long list of vague pros and cons.</p>
<h2>Quick answer</h2>
{quick_answer}
<h2>Key takeaways</h2>
<ul>
<li>Choose the editor that matches your workflow first (short-form edits vs simple trims vs design-led content).</li>
<li>Device support and export needs matter more than "which app has more features".</li>
<li>If CapCut is the frontrunner, set it up once with the right settings so your exports look consistent.</li>
</ul>
{comparison_table}
{setup_path}
<h2>Where {html.escape(app_a)} wins</h2>
<ul>
<li><strong>Short-form speed:</strong> built for Reels/TikTok style edits, especially if you lean on templates and effects.</li>
<li><strong>Editing depth:</strong> more room to grow into transitions, timing, and polish without switching tools.</li>
<li><strong>Social export workflow:</strong> usually quick to get a clean vertical export when your settings are right.</li>
</ul>
<p>If you are choosing {html.escape(app_a)} mainly for export quality, start here: {link_1 if link_1 else 'CapCut export settings matter most for consistent results.'}</p>
<h2>Where {html.escape(app_b)} wins</h2>
<ul>
<li><strong>Simple editing:</strong> reliable for trims, basic text, and quick social-ready edits.</li>
<li><strong>Low friction:</strong> fewer options to manage if you just want to ship content.</li>
</ul>
<h2>Where {html.escape(app_c)} wins</h2>
<ul>
<li><strong>Design-first workflows:</strong> thumbnails, story graphics, and brand kits are often the priority.</li>
<li><strong>Team collaboration:</strong> helpful if multiple people touch the same assets.</li>
</ul>
<h2>Common mistakes and realistic limitations</h2>
<ul>
<li>Expecting every feature to work the same across Android, iOS, and PC versions.</li>
<li>Assuming templates stay the same forever; trends change quickly and examples need refreshing.</li>
<li>For "mod APK" searches: prioritize safety and privacy research over shortcuts.</li>
</ul>
{internal_links_block}
<h2>FAQ</h2>
<h3>Is {html.escape(app_a)} better than {html.escape(app_b)}?</h3>
<p>Usually yes for template-led short-form editing and effects. {html.escape(app_b)} often wins when you want the simplest edit with the least setup.</p>
<h3>Can {html.escape(app_c)} replace {html.escape(app_a)} for video editing?</h3>
<p>For lightweight edits and design-first content, it can. If you need heavier edits, transitions, and effects, {html.escape(app_a)} is typically the safer choice.</p>
<h3>Which one is best for beginners?</h3>
<p>{html.escape(app_b)} is often the easiest for pure editing basics, while {html.escape(app_c)} is easiest for design templates. {html.escape(app_a)} is still beginner friendly but has more depth.</p>
<h3>Do these apps export without watermarks?</h3>
<p>It depends on the feature and plan. If watermark questions are the main blocker, focus on official settings and exports instead of risky downloads.</p>
<h3>What should I do next if I choose {html.escape(app_a)}?</h3>
<p>Set up your export defaults, learn the key features you will use weekly, and save 1 to 2 repeatable templates so editing stays fast. {link_2 if link_2 else ''}</p>
<h2>Conclusion</h2>
<p>For most creators comparing {html.escape(keyword)}, <strong>{html.escape(app_a)}</strong> is the best starting point when you want short-form editing power without a steep learning curve. Use {html.escape(app_b)} for simple, quick edits and {html.escape(app_c)} when design and brand assets are the bigger need.</p>
"""

    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} explained with a fast recommendation, a clear decision path, and FAQs for picking the right editor."
        ),
        "excerpt": f"A practical comparison of {keyword} with a quick recommendation, trade-offs, and next steps.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }
def _normalize_article(article: dict, opportunity: dict, internal_links: list[dict]) -> dict:
    content = _cleanup_html(article.get("content") or "")
    if not content:
        content = _build_template_article(opportunity, internal_links)["content"]
    if internal_links:
        link_count = content.count("<a ")
        if link_count < 3:
            insert = _build_related_links_section(internal_links[:5])
            if "<h2>Conclusion</h2>" in content:
                content = content.replace("<h2>Conclusion</h2>", insert + "<h2>Conclusion</h2>", 1)
            else:
                content = f"{content}{insert}"

    faqs = _extract_faqs_from_html(content)
    faq_schema = _build_faq_schema(faqs) if faqs else ""
    if faq_schema and "application/ld+json" not in content:
        content = f"{content}{faq_schema}"

    title = (article.get("title") or opportunity["title"]).strip()
    meta_title = _trim_meta(article.get("meta_title") or article.get("seo_title") or title)
    meta_description = _trim_description(
        article.get("meta_description")
        or f"{title} with quick answers, practical steps, FAQs, and internal links for readers comparing the best CapCut workflow."
    )
    focus_keywords = _normalize_focus_keywords(article.get("focus_keywords"), opportunity)
    excerpt = (article.get("excerpt") or meta_description).strip()

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
    return f'<a href="{html.escape(link["url"], quote=True)}">{html.escape(link["anchor"])}</a>'


def _suggest_anchor(page: dict) -> str:
    title = (page.get("title") or page.get("slug") or "CapCut guide").strip()
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
    supplement = " Learn key steps, common issues, and the best CapCut follow-up resources."
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


def _count_words(value: str) -> int:
    return len(WORD_PATTERN.findall(value))









