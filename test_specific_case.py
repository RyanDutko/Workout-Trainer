#!/usr/bin/env python3
"""Test the specific case that was failing"""

import sys
import os
sys.path.append('.')

from ai_service_v2 import AIServiceV2
from models import Database

def test_specific_case():
    """Test the specific case that was failing"""
    print("🧪 Testing the specific failing case...")
    
    # Initialize the service
    db = Database()
    ai_service = AIServiceV2(db)
    
    # Test the exact case that was failing
    print("\nTesting: 'chest supported rows' on friday → 105lbs")
    result = ai_service.get_ai_response("Change my Friday chest supported rows from 100lbs to 105lbs")
    print(f"AI Response: {result.get('response', 'No response')}")
    print(f"Tools used: {result.get('tools_used', [])}")
    print(f"Success: {result.get('success', False)}")
    print(f"Token usage: {result.get('token_usage', {})}")

if __name__ == "__main__":
    test_specific_case()

