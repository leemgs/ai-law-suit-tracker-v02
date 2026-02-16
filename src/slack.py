from __future__ import annotations
import requests

def post_to_slack(webhook_url: str, text: str) -> None:
    r = requests.post(webhook_url, json={"text": text}, timeout=20)
    r.raise_for_status()
    


def post_to_slack_with_color(webhook_url: str, text: str, color: str) -> None:
    """
    Slack attachments color 지원
    예: #ff0000 (red), #36a64f (green)
    """
    payload = {
        "attachments": [
            {
                "color": color,
                "text": text,
            }
        ]
    }
    r = requests.post(webhook_url, json=payload, timeout=20)
    r.raise_for_status()    
    
