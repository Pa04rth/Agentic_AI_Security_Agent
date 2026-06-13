"""
fetchers/youtube.py
-------------------
The Video Matchmaker. Given a paper title, searches the YouTube Data API v3
for a matching explainer — but STRICTLY constrained to the channel IDs marked
active in the Source Directory. If a plausible match is found, its watch URL is
returned so it can be attached to the paper's "Matched Explainer Video" field.
"""

import requests

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def find_explainer(paper_title, channel_ids, api_key):
    """
    Search each active channel for a video matching the paper title.
    Returns a YouTube watch URL on the first hit, else None.

    `channel_ids` is a list of channel ID strings (e.g. ["UCabc...", ...]).
    """
    if not api_key or not channel_ids:
        return None

    # Trim very long titles so the query stays focused on the core name.
    query = paper_title.strip()
    if len(query) > 80:
        query = query[:80]

    for channel_id in channel_ids:
        params = {
            "key": api_key,
            "part": "snippet",
            "channelId": channel_id,
            "q": query,
            "type": "video",
            "maxResults": 1,
            "order": "relevance",
        }
        try:
            resp = requests.get(SEARCH_URL, params=params, timeout=20)
            if resp.status_code != 200:
                # Quota exhausted or bad key — fail soft, don't kill the run.
                continue
            items = resp.json().get("items", [])
            if items:
                video_id = items[0]["id"].get("videoId")
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"
        except requests.RequestException:
            continue
    return None
