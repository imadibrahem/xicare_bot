import requests

def smtp2go_send_email(
    api_key: str,
    sender: str,
    to: list[str],
    subject: str,
    text_body: str | None = None,
    html_body: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
    headers: dict | None = None,
    timeout: int = 20,
):
    """
    Send an email using SMTP2GO HTTP API:
    https://developers.smtp2go.com/docs/send-an-email

    attachments format (optional):
    [
        {
        "filename": "report.txt",
        "fileblob": "<base64 string>",
        "mimetype": "text/plain"
        }
    ]
    """
    print("Start smtp2go_send_email()")
    url = "https://eu-api.smtp2go.com/v3/email/send"

    payload = {
        "api_key": api_key,
        "sender": sender,
        "to": to,  # array of recipients (as in docs)
        "subject": subject,
    }

    if cc:
        payload["cc"] = cc
    if bcc:
        payload["bcc"] = bcc
    if text_body is not None:
        payload["text_body"] = text_body
    if html_body is not None:
        payload["html_body"] = html_body
    if attachments:
        payload["attachments"] = attachments
    if headers:
        payload["headers"] = headers

    resp = requests.post(url, json=payload, timeout=timeout)

    # Print raw HTTP info + parsed JSON for debugging
    print("HTTP:", resp.status_code)
    try:
        data = resp.json()
    except ValueError:
        print(resp.text)
        resp.raise_for_status()
        return None
    print("Response JSON:", data)
    print("Note: An email with multiple recipients is classed as 1 email. Therefore if on recipient did not get the mail its still a success. But admin gets an mail. And activity will be logged with smtp2go_activity_by_email_id()")


    # Raise for HTTP errors (4xx/5xx)
    resp.raise_for_status()

    # SMTP2GO API can return success=false in JSON even with 200 sometimes;
    # handle that explicitly.
    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"SMTP2GO API error: {data}")

    print("End smtp2go_send_email()")
    return data

def smtp2go_activity_by_email_id(
    api_key: str,
    email_id: str,
) -> dict:
    """
    Fetch activity events for a specific SMTP2GO email_id using /v3/activity/search.

    SMTP2GO uses the 'search' parameter to match the Email_id.
    Docs: https://developers.smtp2go.com/reference/search-activity
    """
    print("Start smtp2go_activity_by_email_id()")
    url = "https://eu-api.smtp2go.com/v3/activity/search"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Smtp2go-Api-Key": api_key,
    }

    payload = {
        "search_email_id": email_id,          # <-- email_id goes here

    }

    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    print("HTTP:", resp.status_code)
    data = resp.json()
    print("Response JSON:", data)
    print("Look for 'event' to see if someone got rejected")
    resp.raise_for_status()
    
    print("End smtp2go_activity_by_email_id()")
    return data