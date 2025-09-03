#!/usr/bin/env python3
"""Test the improved AI service with weight updates"""

import sys
import os
sys.path.append('.')

from ai_service_v2 import AIServiceV2
from models import Database

def test_weight_update():
    """Test the new update_exercise_weight function"""
    print("🧪 Testing weight update functionality...")
    
    # Initialize the service
    db = Database()
    ai_service = AIServiceV2(db)
    
    # Test direct weight update
    print("\n1. Testing direct weight update...")
    result = ai_service._update_exercise_weight("tuesday", "tricep rope pushdown", "35lbs")
    print(f"Result: {result}")
    
    # Test AI response with weight update
    print("\n2. Testing AI response with weight update request...")
    ai_result = ai_service.get_ai_response("Change my Tuesday tricep rope pushdown from 30lbs to 35lbs")
    print(f"AI Response: {ai_result.get('response', 'No response')}")
    print(f"Tools used: {ai_result.get('tools_used', [])}")
    print(f"Success: {ai_result.get('success', False)}")

if __name__ == "__main__":
    test_weight_update()

