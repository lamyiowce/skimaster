"""Send the ski search results summary by email via Resend."""

import os

import httpx
import markdown as md
from tenacity import retry

from http_utils import RETRY_HTTP


# ── HTML template ────────────────────────────────────────────────────────────

_HTML_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  /* Reset */
  body, p, h1, h2, h3, h4, ul, ol, li, table, td, th {{
    margin: 0; padding: 0; box-sizing: border-box;
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: #f0f4f8;
    color: #1a202c;
    line-height: 1.6;
  }}

  .wrapper {{
    max-width: 720px;
    margin: 32px auto;
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
  }}

  /* Header */
  .header {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
    padding: 36px 40px 28px;
    text-align: center;
  }}
  .header .logo {{
    font-size: 28px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 1px;
  }}
  .header .logo span {{
    color: #7ec8e3;
  }}
  .header .tagline {{
    font-size: 14px;
    color: #a8d4ec;
    margin-top: 4px;
    letter-spacing: 0.5px;
  }}

  /* Meta cards */
  .meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 0;
    background: #f7fafc;
    border-bottom: 1px solid #e2e8f0;
  }}
  .meta-item {{
    flex: 1 1 160px;
    padding: 16px 24px;
    border-right: 1px solid #e2e8f0;
  }}
  .meta-item:last-child {{ border-right: none; }}
  .meta-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #718096;
    font-weight: 600;
    margin-bottom: 4px;
  }}
  .meta-value {{
    font-size: 15px;
    font-weight: 700;
    color: #1a202c;
  }}

  /* Body */
  .body {{
    padding: 32px 40px;
  }}

  h1 {{ font-size: 24px; color: #1e3a5f; margin: 0 0 20px; }}
  h2 {{
    font-size: 18px; color: #1e3a5f;
    margin: 32px 0 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid #bee3f8;
  }}
  h3 {{ font-size: 15px; color: #2d6a9f; margin: 24px 0 8px; font-weight: 700; }}

  p {{ margin: 0 0 14px; font-size: 15px; color: #2d3748; }}

  ul, ol {{ margin: 0 0 14px 20px; }}
  li {{ margin-bottom: 6px; font-size: 15px; color: #2d3748; }}
  li p {{ margin: 0; }}

  /* Top-level numbered list items — one card per property */
  ol > li {{
    margin-bottom: 20px;
    padding: 14px 16px;
    background: #f7fafc;
    border-radius: 8px;
    border-left: 4px solid #2d6a9f;
  }}
  ol > li > strong:first-child {{
    font-size: 17px;
    color: #1e3a5f;
    display: block;
    margin-bottom: 8px;
  }}
  /* Field bullets inside a property card — no card styling */
  ol > li ul {{
    margin: 4px 0 0 0;
    padding-left: 0;
    list-style: none;
  }}
  ol > li ul li,
  ol > li ol > li {{
    margin-bottom: 4px;
    padding: 0;
    background: none;
    border-radius: 0;
    border-left: none;
    font-size: 14px;
    color: #2d3748;
  }}

  strong {{ color: #1a202c; }}
  em {{ color: #718096; }}

  a {{ color: #2d6a9f; text-decoration: none; font-weight: 600; }}
  a:hover {{ text-decoration: underline; }}

  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 28px 0;
  }}

  /* Tables (fallback ranking) */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin: 16px 0 24px;
  }}
  th {{
    background: #1e3a5f;
    color: #ffffff;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  td {{
    padding: 9px 12px;
    border-bottom: 1px solid #e2e8f0;
    color: #2d3748;
    vertical-align: top;
  }}
  tr:nth-child(even) td {{ background: #f7fafc; }}
  tr:hover td {{ background: #ebf8ff; }}

  blockquote {{
    border-left: 3px solid #bee3f8;
    margin: 0 0 14px;
    padding: 8px 16px;
    color: #4a5568;
    background: #f7fafc;
    border-radius: 0 4px 4px 0;
  }}

  /* Fit-status banner */
  .status-banner {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 28px;
    letter-spacing: 0.2px;
  }}
  .status-perfect  {{ background: #c6f6d5; color: #276749; border: 1px solid #9ae6b4; }}
  .status-potential {{ background: #fefcbf; color: #744210; border: 1px solid #f6e05e; }}
  .status-none     {{ background: #fed7d7; color: #742a2a; border: 1px solid #fc8181; }}
  .status-icon {{ font-size: 20px; line-height: 1; }}

  /* Footer */
  .footer {{
    background: #f7fafc;
    border-top: 1px solid #e2e8f0;
    padding: 20px 40px;
    text-align: center;
    font-size: 12px;
    color: #a0aec0;
  }}
  .footer a {{ color: #718096; font-weight: normal; }}
</style>
</head>
<body>
<div class="wrapper">

  <div class="header">
    <div class="logo">⛷ Ski<span>Master</span></div>
    <div class="tagline">Automated Group Ski Accommodation Search</div>
  </div>

  <div class="meta">
    {meta_items}
  </div>

  <div class="body">
    {status_banner}
    {body_html}
  </div>

  <div class="footer">
    Generated by SkiMaster &nbsp;·&nbsp; {resorts_searched} resorts searched
    &nbsp;·&nbsp; <a href="https://github.com/lamyiowce/skimaster">github.com/lamyiowce/skimaster</a>
  </div>

</div>
</body>
</html>
"""

_META_ITEM = """\
    <div class="meta-item">
      <div class="meta-label">{label}</div>
      <div class="meta-value">{value}</div>
    </div>"""


# ── HTML builder ──────────────────────────────────────────────────────────────

def _meta_item(label: str, value: str) -> str:
    return _META_ITEM.format(label=label, value=value)


def _extract_meta(markdown_text: str) -> dict:
    """Pull key-value pairs from the metadata block at the top of results.md."""
    meta = {}
    for line in markdown_text.splitlines():
        for key, pattern in [
            ("dates",      "**Dates:**"),
            ("group",      "**Group size:**"),
            ("budget",     "**Budget:**"),
            ("walk",       "**Max walk to lift:**"),
            ("analyzed",   "**Properties analyzed:**"),
            ("fit_status", "**Fit status:**"),
        ]:
            if pattern in line:
                meta[key] = line.split(pattern, 1)[1].strip()
    return meta


def _strip_meta_block(markdown_text: str) -> str:
    """Remove the top metadata block (up to and including the first ---)."""
    lines = markdown_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            return "\n".join(lines[i + 1:]).lstrip()
    return markdown_text


def _strip_footer(markdown_text: str) -> str:
    """Remove the trailing --- and footer line."""
    lines = markdown_text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "---":
            return "\n".join(lines[:i]).rstrip()
    return markdown_text


_STATUS_BANNER = {
    "perfect":   ('<span class="status-icon">✓</span> Perfect fit found',   "status-perfect"),
    "potential": ('<span class="status-icon">⚠</span> Potential fits found', "status-potential"),
    "none":      ('<span class="status-icon">✗</span> No suitable accommodation found', "status-none"),
}


def _build_html(markdown_text: str) -> str:
    import re
    meta = _extract_meta(markdown_text)

    meta_items = "\n".join([
        _meta_item("Dates",              meta.get("dates", "—")),
        _meta_item("Group size",         meta.get("group", "—")),
        _meta_item("Budget",             meta.get("budget", "—")),
        _meta_item("Walk to lift",       meta.get("walk", "—")),
        _meta_item("Properties checked", meta.get("analyzed", "—")),
    ])

    body_md = _strip_footer(_strip_meta_block(markdown_text))
    body_html = md.markdown(
        body_md,
        extensions=["tables"],
        output_format="html",
    )

    resorts_match = re.search(r"(\d+) resorts searched", markdown_text)
    resorts_searched = resorts_match.group(1) if resorts_match else "?"

    fit_key = meta.get("fit_status", "potential")
    label, css_class = _STATUS_BANNER.get(fit_key, _STATUS_BANNER["potential"])
    status_banner = f'<div class="status-banner {css_class}">{label}</div>'

    return _HTML_WRAPPER.format(
        meta_items=meta_items,
        status_banner=status_banner,
        body_html=body_html,
        resorts_searched=resorts_searched,
    )


@retry(**RETRY_HTTP)
def _resend_post(api_key: str, payload: dict) -> httpx.Response:
    """POST to the Resend API with automatic retry on rate-limit / transient errors."""
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp


# ── Public API ────────────────────────────────────────────────────────────────

def send_summary_email(results_md_path: str) -> None:
    """Send results_md_path to EMAIL_TO via the Resend API.

    Required environment variables:
        RESEND_API_KEY  API key from resend.com
        EMAIL_TO        Recipient address
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    recipient = os.environ.get("EMAIL_TO", "")

    if not api_key or not recipient:
        missing = [n for n, v in {"RESEND_API_KEY": api_key, "EMAIL_TO": recipient}.items() if not v]
        print(f"Email not sent — missing env vars: {', '.join(missing)}")
        return

    try:
        with open(results_md_path) as f:
            markdown_text = f.read()
    except FileNotFoundError:
        print(f"Email not sent — results file not found: {results_md_path}")
        return

    html_body = _build_html(markdown_text)

    print(f"Sending results email to {recipient} via Resend...")
    response = _resend_post(api_key, {
        "from": "SkiMaster <onboarding@resend.dev>",
        "to": [recipient],
        "subject": "⛷ SkiMaster — Ski Accommodation Search Results",
        "html": html_body,
        "text": markdown_text,
    })
    print(f"Email sent successfully (id={response.json().get('id')}).")
