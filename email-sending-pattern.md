# Email Sending Pattern (Resend + Python)

## Dependencies

```
httpx
tenacity
markdown
```

## Environment Variables

```
RESEND_API_KEY=your_key
EMAIL_TO=recipient@example.com
```

## Core Implementation

### 1. HTTP sender with retry

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _resend_post(api_key: str, payload: dict) -> httpx.Response:
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp
```

### 2. Send function

```python
import os

def send_email(subject: str, html: str, text: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    recipient = os.environ.get("EMAIL_TO", "")
    if not api_key or not recipient:
        print("Email skipped — missing RESEND_API_KEY or EMAIL_TO")
        return

    resp = _resend_post(api_key, {
        "from": "YourApp <onboarding@resend.dev>",  # resend.dev sender works without domain setup
        "to": [recipient],
        "subject": subject,
        "html": html,
        "text": text,
    })
    print(f"Email sent: {resp.json().get('id')}")
```

## Notes

- `onboarding@resend.dev` works as the sender **without any domain verification** (Resend's sandbox sender)
- To use your own domain as sender, verify it in the Resend dashboard
- The `text` field is a plain-text fallback; `html` is the rich version
- Get a free API key at resend.com — generous free tier (3k emails/month)
- In CI, store `RESEND_API_KEY` and `EMAIL_TO` as secrets and inject them into the job env
