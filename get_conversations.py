import click
import requests
import pandas as pd
from datetime import datetime

# This script fetches all messages from a PocketBase backend, including expanded conversation,
# user, and configuration details, and exports the data to an Excel file.


# fmt: off
@click.command()
@click.argument('url', type=str)
@click.argument('email', type=str)
@click.argument('password', type=str)
@click.option('--output', '-o', default=None, help="Output XLSX filename")
# fmt: on
def get_conversations(url: str, email: str, password: str, output: str = None) -> None:
    """
    Fetch all messages from a PocketBase backend, including expanded conversation,
    user, and configuration details, and export them to an Excel file.

    Args:
        url (str): The base URL of the PocketBase instance.
        email (str): Superuser email for authentication.
        password (str): Superuser password for authentication.
        output (str, optional): Output Excel filename. If not provided, a timestamped filename is used.
    """
    # Log into pocketbase as superuser and get the auth token
    auth_url = f"{url}/api/collections/_superusers/auth-with-password"
    auth_data = {"identity": email, "password": password}

    try:
        # Authenticate and retrieve the auth token
        response = requests.post(auth_url, json=auth_data)
        response.raise_for_status()
        auth_token = response.json()["token"]
        headers = {"Authorization": f"Bearer {auth_token}"}
        click.echo("Authentication successful")
    except requests.exceptions.RequestException as e:
        click.echo(f"Authentication failed: {e}")
        return

    # Get all messages with expanded fields for conversation, user, and configuration
    messages_url = f"{url}/api/collections/messages/records"
    params = {
        "expand": "conversation,conversation.user,conversation.configuration",
        "sort": "created",
        "perPage": 100,
    }

    all_messages = []
    page = 1

    try:
        # Paginate through all message records
        while True:
            params["page"] = page
            response = requests.get(messages_url, headers=headers, params=params)
            response.raise_for_status()

            result = response.json()
            items = result.get("items", [])
            if not items:
                break

            all_messages.extend(items)

            if page >= result.get("totalPages", 1):
                break

            page += 1
            click.echo(f"Fetched page {page-1} of {result.get('totalPages', 1)}")

        click.echo(f"Successfully fetched {len(all_messages)} messages")
    except requests.exceptions.RequestException as e:
        click.echo(f"Failed to fetch messages: {e}")
        return

    # Prepare data for DataFrame: flatten nested fields for user and configuration
    data = []
    for msg in all_messages:
        expand = msg.get("expand", {})
        conversation = expand.get("conversation", {})

        user = None
        config = None
        if conversation and "expand" in conversation:
            conv_expand = conversation["expand"]
            user = conv_expand.get("user", {})
            config = conv_expand.get("configuration", {})

        data.append(
            {
                "user_id": user.get("id", "") if user else "",
                "user_username": user.get("username", "") if user else "",
                "conversation_id": conversation.get("id", ""),
                "conversation_created": conversation.get("created", ""),
                "conversation_updated": conversation.get("updated", ""),
                "message_id": msg.get("id", ""),
                "message_role": msg.get("role", ""),
                "message_text": msg.get("text", ""),
                "message_rating": msg.get("rating", ""),
                "message_comment": msg.get("comment", ""),
                "message_created": msg.get("created", ""),
                "configuration_id": config.get("id", "") if config else "",
                "configuration_model_name": (
                    config.get("model_name", "") if config else ""
                ),
                "configuration_temperature": (
                    config.get("temperature", "") if config else ""
                ),
                "configuration_top_p": config.get("top_p", "") if config else "",
                "configuration_top_k": config.get("top_k", "") if config else "",
                "configuration_max_output_tokens": (
                    config.get("max_output_tokens", "") if config else ""
                ),
                "configuration_system_prompt": (
                    config.get("system_prompt", "") if config else ""
                ),
                "configuration_datastore": (
                    config.get("datastore", "") if config else ""
                ),
                "configuration_rag_corpus": (
                    config.get("rag_corpus", "") if config else ""
                ),
                "configuration_rag_similarity_top_k": (
                    config.get("rag_similarity_top_k", "") if config else ""
                ),
                "configuration_rag_vector_distance_threshold": (
                    config.get("rag_vector_distance_threshold", "") if config else ""
                ),
                "configuration_block_hate_speech": (
                    config.get("block_hate_speech", "") if config else ""
                ),
                "configuration_block_dangerous_content": (
                    config.get("block_dangerous_content", "") if config else ""
                ),
                "configuration_block_sexually_explicit_content": (
                    config.get("block_sexually_explicit_content", "") if config else ""
                ),
                "configuration_block_harassment_content": (
                    config.get("block_harassment_content", "") if config else ""
                ),
                "configuration_comment": config.get("comment", "") if config else "",
                "configuration_created": config.get("created", "") if config else "",
                "configuration_updated": config.get("updated", "") if config else "",
            }
        )

    # Create DataFrame and sort by user, conversation, and message creation time
    df = pd.DataFrame(data)

    if not df.empty:
        df = df.sort_values(by=["user_id", "conversation_id", "message_created"])

    # Save the DataFrame to an Excel file
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"conversations_{timestamp}.csv"

    df.to_excel(output, index=False)
    click.echo(f"Saved {len(df)} messages to {output}")


if __name__ == "__main__":
    get_conversations()
