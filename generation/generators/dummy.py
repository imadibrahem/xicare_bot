"""
Dummy generator module providing a placeholder implementation for AI chat generation.
This module is used for testing or when actual AI generation is not required.
"""

from typing import Awaitable
import time
import asyncio


class Dummy:
    """
    A placeholder class that mimics an AI chat generation service interface.
    Instead of actual AI-generated content, this class returns Lorem Ipsum text.
    Used for testing, development, or when actual AI generation is not available/required.
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize the Dummy generator.

        Args:
            *args: Variable length argument list, included for compatibility with actual generator classes.
                  These arguments are ignored in this implementation.
        """
        pass

    def generate_content(self, *args, **kwargs) -> str:
        """
        Generate dummy content synchronously.
        Returns Lorem Ipsum text instead of actual AI-generated content.

        Args:
            *args: Variable length argument list, included for compatibility with actual generator classes.
                  These arguments are ignored in this implementation.

        Returns:
            str: Lorem Ipsum placeholder text.
        """
        time.sleep(2)
        return "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vivamus neque mauris, pulvinar sed elit ac, rhoncus molestie purus. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec accumsan, nibh at pharetra finibus, eros elit ullamcorper nisi, quis suscipit felis massa sit amet urna. Phasellus tempus leo justo, in dictum augue feugiat eget. Suspendisse quis varius dolor, at vulputate nisl. Quisque ullamcorper cursus molestie. Nullam dignissim ultrices mattis.\n\nhttps://www.lipsum.com/"

    async def generate_content_async(self, *args, **kwargs) -> Awaitable[str]:
        """
        Generate dummy content asynchronously.
        Returns Lorem Ipsum text instead of actual AI-generated content.

        Args:
            *args: Variable length argument list, included for compatibility with actual generator classes.
                  These arguments are ignored in this implementation.

        Returns:
            Awaitable[str]: Lorem Ipsum placeholder text as an awaitable.
        """
        await asyncio.sleep(2)
        return "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vivamus neque mauris, pulvinar sed elit ac, rhoncus molestie purus. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Donec accumsan, nibh at pharetra finibus, eros elit ullamcorper nisi, quis suscipit felis massa sit amet urna. Phasellus tempus leo justo, in dictum augue feugiat eget. Suspendisse quis varius dolor, at vulputate nisl. Quisque ullamcorper cursus molestie. Nullam dignissim ultrices mattis.\n\nhttps://www.lipsum.com/"
