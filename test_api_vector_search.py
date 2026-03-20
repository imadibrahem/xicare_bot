#!/usr/bin/env python3
"""
Integration test: Call actual /generation/imperia endpoint with Vector Search config
Run: python3 test_api_vector_search.py "your test query"
"""

import sys
import os
import json
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("GENERATION_API_URL", "http://localhost:8000")
TEST_CONVERSATION_ID = "test-vector-search"
TEST_TOKEN = os.getenv("TEST_TOKEN", "your-test-token")

query = sys.argv[1] if len(sys.argv) > 1 else "pflegeleistungen demenz"

print(f"[INFO] Testing API: {API_URL}/v1/generation/imperia")
print(f"[INFO] Query: {query}")
print()

async def test_api():
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{API_URL}/v1/generation/imperia",
                json={
                    "conversationId": TEST_CONVERSATION_ID,
                    "message": query
                },
                headers={
                    "Authorization": f"Bearer {TEST_TOKEN}",
                    "Origin": "http://localhost:3000"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ API Response (status {response.status_code})")
                print(f"  ConversationId: {data.get('conversationId')}")
                print(f"  Response length: {len(data.get('response', ''))} chars")
                print(f"  Chat messages: {data.get('chatMessages')}")
                print()
                print("=" * 60)
                print("Response preview:")
                print("=" * 60)
                print(data.get('response', '')[:500])
                if len(data.get('response', '')) > 500:
                    print("...")
            else:
                print(f"✗ API Error (status {response.status_code})")
                print(response.text)
                
        except Exception as e:
            print(f"✗ Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
