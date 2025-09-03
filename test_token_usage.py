#!/usr/bin/env python3
"""
Token Usage Testing Script
Tests different query types with both GPT-4o-mini and GPT-4 to analyze token efficiency
"""

import os
import json
import time
from datetime import datetime
from ai_service_v2 import AIServiceV2, classify_query_complexity
from models import Database

# Test queries categorized by complexity
TEST_QUERIES = {
    "simple": [
        "Hello",
        "What's my plan for today?",
        "Show me my recent workouts",
        "How many workouts did I do this week?",
        "What's my current weight?",
        "Yes",
        "No",
        "Thanks"
    ],
    
    "moderate": [
        "How should I progress my bench press?",
        "What should I eat after my workout?",
        "I'm feeling sore, should I still workout?",
        "Show me my Monday workout from last week",
        "What's the difference between my planned and actual workout?",
        "How do I break through a plateau?",
        "Should I increase my deadlift weight?"
    ],
    
    "complex": [
        "I want to add more glute work to my routine. Can you suggest some exercises and where to fit them in my current plan?",
        "Analyze my complete workout plan and give me your honest assessment. What would you change or improve?",
        "I've been doing the same routine for 3 months and I'm not seeing progress. Can you redesign my entire program?",
        "Create a circuit workout for my leg day that includes both strength and cardio elements",
        "I have a shoulder injury but want to keep training. How should I modify my upper body routine?",
        "Compare my performance over the last month and suggest specific improvements based on my goals"
    ],
    
    "plan_modification": [
        "Add glute drive to my Monday workout",
        "Change my Friday bench press to 4 sets of 6 reps",
        "Remove the leg press from my Wednesday routine",
        "Add a circuit of 3 exercises to my Tuesday workout",
        "Rename my Monday glute drive to 'glute drive (light load)'",
        "Update my Friday glute drive weight to 110lbs"
    ]
}

def test_query(ai_service, query, force_advanced=False):
    """Test a single query and return token usage data"""
    print(f"\n🔍 Testing: '{query}'")
    print(f"📊 Model: {'GPT-4' if force_advanced else 'Auto-detected'}")
    
    start_time = time.time()
    
    try:
        result = ai_service.get_ai_response(query, user_force_advanced=force_advanced)
        
        end_time = time.time()
        duration = end_time - start_time
        
        token_usage = result.get('token_usage', {})
        success = result.get('success', False)
        
        return {
            'query': query,
            'success': success,
            'duration': duration,
            'token_usage': token_usage,
            'response_length': len(result.get('response', '')),
            'tools_used': result.get('tools_used', []),
            'model_used': token_usage.get('model', 'unknown'),
            'auto_detected_model': classify_query_complexity(query)
        }
        
    except Exception as e:
        print(f"❌ Error testing query: {e}")
        return {
            'query': query,
            'success': False,
            'error': str(e),
            'duration': time.time() - start_time,
            'token_usage': {},
            'response_length': 0,
            'tools_used': [],
            'model_used': 'error',
            'auto_detected_model': classify_query_complexity(query)
        }

def run_comprehensive_test():
    """Run comprehensive token usage tests"""
    print("🚀 Starting Token Usage Analysis")
    print("=" * 60)
    
    # Initialize AI service
    db = Database()
    ai_service = AIServiceV2(db)
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'tests': []
    }
    
    # Test each category
    for category, queries in TEST_QUERIES.items():
        print(f"\n📋 Testing {category.upper()} queries")
        print("-" * 40)
        
        for query in queries:
            # Test with auto-detection
            result_auto = test_query(ai_service, query, force_advanced=False)
            results['tests'].append(result_auto)
            
            # Test with forced GPT-4
            result_forced = test_query(ai_service, query, force_advanced=True)
            results['tests'].append(result_forced)
            
            # Small delay between tests
            time.sleep(1)
    
    # Analyze results
    analyze_results(results)
    
    # Save results
    save_results(results)
    
    return results

def analyze_results(results):
    """Analyze and display test results"""
    print("\n" + "=" * 60)
    print("📊 TOKEN USAGE ANALYSIS")
    print("=" * 60)
    
    tests = results['tests']
    
    # Group by model
    gpt4_tests = [t for t in tests if t.get('model_used') == 'gpt-4']
    gpt4o_mini_tests = [t for t in tests if t.get('model_used') == 'gpt-4o-mini']
    
    print(f"\n🤖 GPT-4 Tests: {len(gpt4_tests)}")
    if gpt4_tests:
        avg_tokens = sum(t.get('token_usage', {}).get('total_tokens', 0) for t in gpt4_tests) / len(gpt4_tests)
        avg_duration = sum(t.get('duration', 0) for t in gpt4_tests) / len(gpt4_tests)
        print(f"   Average tokens: {avg_tokens:.0f}")
        print(f"   Average duration: {avg_duration:.2f}s")
    
    print(f"\n⚡ GPT-4o-mini Tests: {len(gpt4o_mini_tests)}")
    if gpt4o_mini_tests:
        avg_tokens = sum(t.get('token_usage', {}).get('total_tokens', 0) for t in gpt4o_mini_tests) / len(gpt4o_mini_tests)
        avg_duration = sum(t.get('duration', 0) for t in gpt4o_mini_tests) / len(gpt4o_mini_tests)
        print(f"   Average tokens: {avg_tokens:.0f}")
        print(f"   Average duration: {avg_duration:.2f}s")
    
    # Analyze by category
    print(f"\n📈 BY CATEGORY ANALYSIS")
    print("-" * 40)
    
    for category in TEST_QUERIES.keys():
        category_tests = [t for t in tests if any(q in t.get('query', '') for q in TEST_QUERIES[category])]
        
        if category_tests:
            avg_tokens = sum(t.get('token_usage', {}).get('total_tokens', 0) for t in category_tests) / len(category_tests)
            avg_duration = sum(t.get('duration', 0) for t in category_tests) / len(category_tests)
            success_rate = sum(1 for t in category_tests if t.get('success')) / len(category_tests) * 100
            
            print(f"\n{category.title()}:")
            print(f"   Tests: {len(category_tests)}")
            print(f"   Success rate: {success_rate:.1f}%")
            print(f"   Average tokens: {avg_tokens:.0f}")
            print(f"   Average duration: {avg_duration:.2f}s")
    
    # Find most and least efficient queries
    successful_tests = [t for t in tests if t.get('success')]
    
    if successful_tests:
        most_tokens = max(successful_tests, key=lambda x: x.get('token_usage', {}).get('total_tokens', 0))
        least_tokens = min(successful_tests, key=lambda x: x.get('token_usage', {}).get('total_tokens', 0))
        
        print(f"\n🏆 EFFICIENCY HIGHLIGHTS")
        print("-" * 40)
        print(f"Most tokens: {most_tokens.get('query')[:50]}... ({most_tokens.get('token_usage', {}).get('total_tokens', 0)} tokens)")
        print(f"Least tokens: {least_tokens.get('query')[:50]}... ({least_tokens.get('token_usage', {}).get('total_tokens', 0)} tokens)")

def save_results(results):
    """Save test results to file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"token_usage_test_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")

def run_quick_test():
    """Run a quick test with a few sample queries and return results"""
    print("⚡ Quick Token Usage Test")
    print("=" * 40)
    
    db = Database()
    ai_service = AIServiceV2(db)
    
    quick_queries = [
        "Hello",
        "Show me my Monday workout",
        "How should I progress my bench press?",
        "I want to add more glute work to my routine"
    ]
    
    results = []
    for query in quick_queries:
        result = test_query(ai_service, query)
        results.append(result)
        if result.get('success'):
            tokens = result.get('token_usage', {}).get('total_tokens', 0)
            model = result.get('model_used', 'unknown')
            print(f"✅ {query[:30]}... → {tokens} tokens ({model})")
        else:
            print(f"❌ {query[:30]}... → Failed")
        
        time.sleep(0.5)
    
    return results

def quick_test():
    """Legacy function for command line usage"""
    run_quick_test()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        quick_test()
    else:
        run_comprehensive_test()
