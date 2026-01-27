import os, json
from datetime import datetime
import httpx
import pandas as pd
from dotenv import load_dotenv
from typing import List, Dict
import requests 
import asyncio

# ENV + AUTH
config = load_dotenv()
GENERATION_PB_URL = os.environ.get("GENERATION_PB_URL")
PB_API_USER_EMAIL = os.environ.get("PB_API_USER_EMAIL")
PB_API_USER_PASSWORD = os.environ.get("PB_API_USER_PASSWORD")

_api_superuser_token = None

async def pb_api_superuser_token() -> str:
    # could also cache in the future
    # but then again needs check if token from cache is ok etc. -> no real benefit
    global _api_superuser_token
    async with httpx.AsyncClient(timeout=5.0) as client:
        if _api_superuser_token:
            resp = await client.post(
                f"{GENERATION_PB_URL}/api/collections/_superusers/auth-refresh",
                headers={"Authorization": f"Bearer {_api_superuser_token}"}
            )
            if resp.status_code == 200:
                _api_superuser_token = resp.json()["token"]
                return _api_superuser_token
        # (re)login when no token or refresh failed
        resp = await client.post(
            f"{GENERATION_PB_URL}/api/collections/_superusers/auth-with-password",
            json={"identity": PB_API_USER_EMAIL, "password": PB_API_USER_PASSWORD}
        )
        resp.raise_for_status()
        _api_superuser_token = resp.json()["token"]
        return _api_superuser_token

    token = await pb_api_superuser_token()

# FETCH + EXPORT
async def fetch_all_api_events(per_page: int = 100, sort: str = "created") -> List[Dict]:
    """
    Pull every record from the 'api_events' collection (paginated).
    """
    token = await pb_api_superuser_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GENERATION_PB_URL}/api/collections/api_events/records"

    all_items: List[Dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params = {"page": page, "perPage": per_page, "sort": sort}
            resp = await client.get(url, headers=headers, params=params)
            # If token ever expires mid-run, refresh once and retry this page
            if resp.status_code == 401:
                token = await pb_api_superuser_token()
                headers = {"Authorization": f"Bearer {token}"}
                resp = await client.get(url, headers=headers, params=params)

            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            all_items.extend(items)

            total_pages = data.get("totalPages", page)
            if page >= total_pages:
                break
            page += 1

    return all_items

def flatten_event(rec: Dict) -> Dict:
    """
    Keep only the fields you care about + id/created/updated.
    Adjust/extend as needed.
    """
    # top-level PB fields always exist
    base = {
        "id": rec.get("id", ""),
        "created": rec.get("created", ""),
        "updated": rec.get("updated", ""),
    }

    # your custom fields from the example
    fields = {
        "conversationId": rec.get("conversationId", ""),
        "conversationId_supplied": rec.get("conversationId_supplied", ""),
        "endpoint": rec.get("endpoint", ""),
        "status_code": rec.get("status_code", ""),
        "duration_ms": rec.get("duration_ms", ""),
        "origin": rec.get("origin", ""),
        "chatMessages": rec.get("chatMessages", ""),
        "noContext": rec.get("noContext", ""),
        "expiresAt": rec.get("expiresAt", ""),
        "error_message": rec.get("error_message", ""),
    }

    return {**base, **fields}

def to_dataframe(items: List[Dict]) -> pd.DataFrame:
    rows = [flatten_event(it) for it in items]
    df = pd.DataFrame(rows)
    if not df.empty:
        # try nice sorting: by created timestamp
        sort_cols = [c for c in ["created"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols, kind="stable")
    return df


def save_df(df: pd.DataFrame, output: str | None = None) -> str:
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"api_events_{ts}.xlsx"

    if output.lower().endswith(".csv"):
        df.to_csv(output, index=False)
    else:
        df.to_excel(output, index=False)

    return output

# ----------------------------
# ENTRY POINT
# ----------------------------
async def get_api_events(output: str | None = None):
    print("Start get_api_events()")
    items = await fetch_all_api_events(per_page=100, sort="created")
    df = to_dataframe(items)
    out_path = save_df(df, output)
    print(f"Saved {len(df)} api_events to {out_path}")
    print("End get_api_events()")
    return out_path


if __name__ == "__main__":
    # pass an explicit filename if wanted
    out_path = asyncio.run(get_api_events())
