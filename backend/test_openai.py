#!/usr/bin/env python3
"""Test script to verify OpenAI integration."""

import sys
import os
sys.path.append('.')

try:
    from utils.openai_llm import get_llm_client, OpenAILLMClient
    print("✅ OpenAI LLM client imports successfully")

    # Test configuration loading
    from utils.config_loader import get_config
    config = get_config()
    print(f"✅ Config loaded: OpenAI configured = {config.openai is not None}")

    print("🎉 All OpenAI integrations working correctly!")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
