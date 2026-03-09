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
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if not match:
                logger.warning("Gemini response was not valid JSON for key %s", index)
                continue
            payload = json.loads(match.group(0))
            if "content" not in payload:
                logger.warning("Gemini response missed content for key %s", index)
                continue
            return payload
        except Exception as exc:
            logger.warning("Gemini generation failed for key %s: %s", index, exc)
    return None


def _build_template_article(opportunity: dict, internal_links: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    focus_keywords = _default_focus_keywords(keyword, opportunity["bucket"])
    intro_link = _link_html(internal_links[0]) if internal_links else ""
    extra_links = "".join(f"<li>{_link_html(link)}</li>" for link in internal_links[1:4])
    comparison_note = ""
    if opportunity["bucket"] == "comparison":
        comparison_note = (
            "<h2>Quick comparison table</h2>"
            "<table><tr><td><strong>Area</strong></td><td><strong>CapCut</strong></td><td><strong>Alternative</strong></td></tr>"
            "<tr><td>Learning curve</td><td>Beginner friendly</td><td>Varies by tool</td></tr>"
            "<tr><td>Templates</td><td>Strong short-form ecosystem</td><td>Depends on app</td></tr>"
            "<tr><td>Export workflow</td><td>Fast for social content</td><td>May suit other formats better</td></tr></table>"
        )
    related_guides = ""
    if intro_link or extra_links:
        related_guides = (
            "<h2>Helpful related guides</h2>"
            f"<p>{intro_link}</p>"
            f"<ul>{extra_links}</ul>"
        )
    content = f"""
<p><strong>{html.escape(keyword.title())}</strong> is worth covering because users want a fast answer, realistic setup advice, and a clear sense of whether CapCut is the right fit for their workflow.</p>
<p>The strongest version of this article answers the core question immediately, shows where CapCut performs well, and points readers toward the next step instead of burying the recommendation.</p>
<h2>Key takeaways</h2>
<ul>
<li>Lead with the direct answer users expect from search and AI overview results.</li>
<li>Explain the most likely setup path before advanced tips.</li>
<li>Link readers to the next best CapCut guide on your site while the intent is still fresh.</li>
</ul>
<h2>Quick answer</h2>
<p>Most people searching for {html.escape(keyword)} want to know whether CapCut can solve a real editing problem quickly. The best answer is usually yes, but the right recommendation depends on device support, export needs, and whether they need premium tools or simple social-ready editing.</p>
<h2>Who this is best for</h2>
<p>This topic works best for beginner creators, mobile editors, and anyone comparing fast short-form video workflows. Advanced users still care, but they usually want more detail around templates, export quality, performance, and app limitations.</p>
<h2>How to cover the topic well</h2>
<ol>
<li>Answer the main question in plain language within the introduction.</li>
<li>Walk through the setup or decision path with no fluff.</li>
<li>Call out trade-offs, privacy concerns, or version differences honestly.</li>
<li>Use internal links to keep readers moving through the CapCut content cluster.</li>
</ol>
{comparison_note}
<h2>Common mistakes and realistic limitations</h2>
<ul>
<li>Users often expect every feature to work the same across Android, iOS, and PC.</li>
<li>Template-heavy workflows change quickly, so examples need refreshing over time.</li>
<li>Mod APK topics need safety and privacy framing instead of exaggerated claims.</li>
</ul>
{related_guides}
<h2>FAQ</h2>
<h3>Is this topic still worth publishing?</h3>
<p>Yes. It matches recurring user intent around CapCut features, setup, troubleshooting, and comparison research.</p>
<h3>What helps the page rank beyond standard SEO?</h3>
<p>Answer-first copy, structured headings, direct recommendations, and clear related entities improve visibility in both classic search and AI-driven answer surfaces.</p>
<h3>How many internal links should the article include?</h3>
<p>Use at least three natural internal links to relevant tutorials, troubleshooting pages, or explainers so the article strengthens topical authority.</p>
<h3>Should the article mention drawbacks?</h3>
<p>Yes. Balanced discussion improves trust, supports better conversions, and makes the page more useful when readers compare tools.</p>
<h2>Conclusion</h2>
<p>{html.escape(keyword.title())} deserves a dedicated page because it answers a real search need and fits naturally inside your wider CapCut topic cluster. Publish the draft, review examples for freshness, and connect it to related guides that deepen the reader journey.</p>
"""
    return {
        "title": title,
        "meta_title": _trim_meta(title),
        "meta_description": _trim_description(
            f"{title} explained with practical steps, honest pros and cons, and quick answers to the questions users actually search for."
        ),
        "excerpt": f"A practical guide to {keyword} with direct answers, realistic trade-offs, and related CapCut resources.",
        "focus_keywords": focus_keywords,
        "content": _cleanup_html(content),
    }


def _normalize_article(article: dict, opportunity: dict, internal_links: list[dict]) -> dict:
    content = _cleanup_html(article.get("content") or "")
    if not content:
        content = _build_template_article(opportunity, internal_links)["content"]
    if internal_links and "<a " not in content:
        content = content.replace(
            "<h2>Conclusion</h2>",
            _build_related_links_section(internal_links[:3]) + "<h2>Conclusion</h2>",
            1,
        )

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
    candidates: list[dict] = []
    for page in existing_pages:
        slug = page.get("slug", "")
        if slug in config.EXCLUDE_SLUG_HINTS or slug == "home":
            continue
        haystack = f"{page.get('title', '')} {slug}".lower()
        overlap = len(query_tokens & _keyword_tokens(haystack))
        topical_bonus = 2 if "capcut" in haystack else 0
        score = overlap * 5 + topical_bonus
        candidates.append(
            {
                "title": page.get("title") or slug.replace("-", " ").title(),
                "url": page["url"],
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
    return compact[: limit - 1].rstrip(" -|:") + "…"


def _trim_description(value: str, min_len: int = 140, max_len: int = 155) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if len(compact) > max_len:
        compact = compact[: max_len - 1].rstrip(" -|:") + "…"
    if len(compact) >= min_len:
        return compact
    supplement = " Learn key steps, common issues, and the best CapCut follow-up resources."
    merged = (compact + supplement).strip()
    if len(merged) > max_len:
        merged = merged[: max_len - 1].rstrip(" -|:") + "…"
    return merged


def _cleanup_html(value: str) -> str:
    return re.sub(r"\n\s+", "", value).strip()


def _strip_html(value: str) -> str:
    no_scripts = SCRIPT_PATTERN.sub(" ", value)
    plain = HTML_TAG_PATTERN.sub(" ", no_scripts)
    return re.sub(r"\s+", " ", plain).strip()


def _count_words(value: str) -> int:
    return len(WORD_PATTERN.findall(value))
