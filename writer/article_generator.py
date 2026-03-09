"""
Generate article drafts for approved CapCut opportunities.
"""
from __future__ import annotations

import html
import json
import logging
import re

import config

logger = logging.getLogger(__name__)

try:
    from google import genai
except Exception:
    genai = None


def generate_article(opportunity: dict, existing_pages: list[dict]) -> dict:
    prompt = build_article_prompt(opportunity, existing_pages)
    article = _generate_with_gemini(prompt)
    if article is None:
        article = _build_template_article(opportunity, existing_pages)
    article["topic_key"] = opportunity["topic_key"]
    article["slug"] = opportunity["slug"]
    article["bucket"] = opportunity["bucket"]
    article["score"] = opportunity["score"]
    article["word_count"] = _count_words(_strip_html(article["content"]))
    return article


def build_article_prompt(opportunity: dict, existing_pages: list[dict]) -> str:
    internal_links = [
        page["url"]
        for page in existing_pages
        if page["slug"] not in config.EXCLUDE_SLUG_HINTS and page["slug"] != "home"
    ][:8]
    return f"""
You are writing for {config.SITE_NAME}, a niche blog about CapCut and CapCut Pro APK topics.

Write a complete SEO article in clean HTML.

Requirements:
- Focus keyword: {opportunity['query']}
- Suggested title: {opportunity['title']}
- Article type: {opportunity['bucket']}
- Tone: {config.ARTICLE_TONE}
- Length: {config.ARTICLE_MIN_WORDS}-{config.ARTICLE_MAX_WORDS} words
- Cover beginner intent first, then advanced considerations.
- Include direct comparisons when relevant and mention risks or limitations honestly.
- Add an FAQ section with 4 questions.
- Add a short conclusion with a light CTA.
- Use only HTML tags: h2, h3, p, ul, ol, li, table, tr, td, strong.
- Do not mention AI, prompts, or that the article was generated.
- Suggest 3 relevant internal links from this pool when natural:
  {json.dumps(internal_links, ensure_ascii=False)}

Return strict JSON with:
title, seo_title, meta_description, excerpt, content

Planning brief:
{opportunity['brief']}
"""


def _generate_with_gemini(prompt: str) -> dict | None:
    if not config.GEMINI_API_KEYS or genai is None:
        return None
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEYS[0])
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        raw_text = getattr(response, "text", "") or ""
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            logger.warning("Gemini response was not valid JSON")
            return None
        payload = json.loads(match.group(0))
        if "content" not in payload:
            return None
        return payload
    except Exception as exc:
        logger.warning("Gemini generation failed: %s", exc)
        return None


def _build_template_article(opportunity: dict, existing_pages: list[dict]) -> dict:
    keyword = opportunity["query"]
    title = opportunity["title"]
    comparison_note = ""
    if opportunity["bucket"] == "comparison":
        comparison_note = (
            "<h2>Quick comparison table</h2>"
            "<table><tr><td><strong>Area</strong></td><td><strong>CapCut</strong></td><td><strong>Alternative</strong></td></tr>"
            "<tr><td>Learning curve</td><td>Beginner friendly</td><td>Varies by tool</td></tr>"
            "<tr><td>Templates</td><td>Strong short-form ecosystem</td><td>Depends on app</td></tr>"
            "<tr><td>Export workflow</td><td>Fast for social content</td><td>May suit other formats better</td></tr></table>"
        )
    internal_links = [
        page["url"]
        for page in existing_pages
        if page["slug"] not in config.EXCLUDE_SLUG_HINTS and page["slug"] != "home"
    ][:3]
    related_links = "".join(f"<li><strong>Related:</strong> {html.escape(url)}</li>" for url in internal_links)
    content = f"""
<p><strong>{html.escape(keyword.title())}</strong> is a strong content opportunity for {html.escape(config.SITE_NAME)} because readers are actively searching for practical answers, honest trade-offs, and up-to-date guidance.</p>
<h2>What users usually want to know</h2>
<p>Most people searching for {html.escape(keyword)} want a clear answer fast. They are usually deciding whether CapCut can solve a real editing need, whether it works on their device, and what limitations they should expect before investing time in it.</p>
<h2>How to approach it the right way</h2>
<p>Start with the exact use case behind the query. Explain who this feature or workflow is best for, what version differences matter, and where users are most likely to hit friction. Keep the steps direct, especially for mobile users and creators publishing to TikTok, YouTube Shorts, and Instagram Reels.</p>
{comparison_note}
<h2>Common mistakes and realistic limitations</h2>
<ul>
<li>Users often expect every premium feature to behave the same across Android, iOS, and PC.</li>
<li>Template-heavy workflows can change quickly, so trend examples need regular refreshing.</li>
<li>Mod APK topics need careful safety, privacy, and legal framing instead of hype.</li>
</ul>
<h2>Best internal follow-up links</h2>
<ul>{related_links}</ul>
<h2>FAQ</h2>
<h3>Is this topic still relevant?</h3>
<p>Yes. It maps to ongoing search demand around CapCut features, setup, troubleshooting, and comparisons.</p>
<h3>Should the article mention alternatives?</h3>
<p>Yes. Balanced comparison improves trust and helps the page rank for broader commercial-intent searches.</p>
<h3>What format works best?</h3>
<p>A practical guide with steps, trade-offs, and FAQs is the safest default for this type of query.</p>
<h3>How should the article end?</h3>
<p>Summarize the best choice for the reader and point them toward a closely related tutorial on your site.</p>
<h2>Conclusion</h2>
<p>{html.escape(keyword.title())} deserves a dedicated page because it aligns with real user questions and expands your topical authority around CapCut. Publish it as a draft first, review the examples, and then link it into the rest of your CapCut content cluster.</p>
"""
    return {
        "title": title,
        "seo_title": title[:60],
        "meta_description": f"{title} explained with practical steps, honest pros and cons, and answers to the questions users actually search for."[:155],
        "excerpt": f"A practical guide to {keyword} for users comparing features, setup, and real-world results.",
        "content": _cleanup_html(content),
    }


def _cleanup_html(value: str) -> str:
    return re.sub(r"\n\s+", "", value).strip()


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _count_words(value: str) -> int:
    return len([word for word in value.split() if word.strip()])
