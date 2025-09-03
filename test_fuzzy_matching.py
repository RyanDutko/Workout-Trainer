#!/usr/bin/env python3
"""Test the improved fuzzy matching for exercise names"""

import sys
import os
sys.path.append('.')

from ai_service_v2 import AIServiceV2
from models import Database

def test_fuzzy_matching():
    """Test the fuzzy matching functionality"""
    print("🧪 Testing fuzzy exercise name matching...")
    
    # Initialize the service
    db = Database()
    ai_service = AIServiceV2(db)
    
    # Test cases that should work with fuzzy matching
    test_cases = [
        ("chest supported rows", "friday", "105lbs"),  # Should match "chest supported row (light)"
        ("chest supported row", "friday", "105lbs"),   # Should match "chest supported row (light)"
        ("lat pulldown", "friday", "105lbs"),          # Should match "Lat Pulldown"
        ("lat pulldowns", "friday", "105lbs"),         # Should match "Lat Pulldown"
        ("goblet split squat", "friday", "40lbs"),     # Should match "goblet split squats"
    ]
    
    for exercise_name, day, new_weight in test_cases:
        print(f"\nTesting: '{exercise_name}' on {day} → {new_weight}")
        result = ai_service._update_exercise_weight(day, exercise_name, new_weight)
        print(f"Result: {result.get('success', False)} - {result.get('message', result.get('error', 'Unknown'))}")

if __name__ == "__main__":
    test_fuzzy_matching()

