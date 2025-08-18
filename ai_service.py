
import os
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from models import Database, User, TrainingPlan, Workout

class AIService:
    def __init__(self, db: Database):
        self.db = db
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.user = User(db)
        self.training_plan = TrainingPlan(db)
        self.workout = Workout(db)
    
    def analyze_user_message(self, message: str) -> Dict[str, Any]:
        """Analyze user intent and extract key information"""
        intent_keywords = {
            'workout_logging': ['completed', 'finished', 'did', 'performed', 'sets', 'reps', 'x'],
            'plan_discussion': ['plan', 'routine', 'schedule', 'workout plan', 'weekly plan'],
            'historical_query': ['show me', 'what did i', 'my workout', 'yesterday', 'last week'],
            'progression': ['progress', 'increase', 'heavier', 'stronger', 'next week'],
            'general_chat': ['hello', 'hi', 'how are', 'advice', 'tips']
        }
        
        message_lower = message.lower()
        detected_intents = {}
        
        for intent, keywords in intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                detected_intents[intent] = score
        
        primary_intent = max(detected_intents.items(), key=lambda x: x[1])[0] if detected_intents else 'general_chat'
        
        return {
            'primary_intent': primary_intent,
            'confidence': detected_intents.get(primary_intent, 0),
            'all_intents': detected_intents
        }
    
    def build_context(self, message: str, intent: str) -> str:
        """Build appropriate context based on user intent"""
        context_parts = []
        
        # Always include user preferences
        ai_prefs = self.user.get_ai_preferences()
        context_parts.append(f"AI Preferences: {json.dumps(ai_prefs)}")
        
        if intent in ['plan_discussion', 'progression']:
            # Include training plan
            plan = self.training_plan.get_active_plan()
            if plan:
                context_parts.append(f"Current Training Plan: {json.dumps(plan['plan_data'])}")
                if plan['philosophy']:
                    context_parts.append(f"Training Philosophy: {plan['philosophy']}")
        
        if intent in ['historical_query', 'progression']:
            # Include recent workouts
            recent_workouts = self.workout.get_recent_workouts(limit=5)
            context_parts.append(f"Recent Workouts: {json.dumps(recent_workouts)}")
        
        if intent == 'workout_logging':
            # Include today's plan and recent performance
            plan = self.training_plan.get_active_plan()
            if plan:
                context_parts.append(f"Training Plan: {json.dumps(plan['plan_data'])}")
        
        return "\n".join(context_parts)
    
    def get_ai_response(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Get AI response with proper context and error handling"""
        try:
            # Analyze intent
            analysis = self.analyze_user_message(message)
            intent = analysis['primary_intent']
            
            # Build context
            context = self.build_context(message, intent)
            
            # Create system prompt based on intent
            system_prompts = {
                'workout_logging': "You are a fitness tracking assistant. Help users log their workouts accurately and provide immediate feedback.",
                'plan_discussion': "You are a personal trainer. Discuss training plans, modifications, and programming decisions.",
                'historical_query': "You are a fitness analyst. Help users understand their workout history and patterns.",
                'progression': "You are a progression coach. Analyze performance trends and suggest next steps.",
                'general_chat': "You are a knowledgeable fitness assistant. Provide helpful, motivational guidance."
            }
            
            system_prompt = system_prompts.get(intent, system_prompts['general_chat'])
            
            # Get user preferences for response style
            ai_prefs = self.user.get_ai_preferences()
            tone = ai_prefs.get('tone', 'motivational')
            detail_level = ai_prefs.get('detail_level', 'concise')
            
            system_prompt += f" Use a {tone} tone and provide {detail_level} responses."
            
            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            
            if conversation_history:
                for conv in conversation_history[-3:]:  # Last 3 for context
                    messages.append({"role": "user", "content": conv['user_message']})
                    messages.append({"role": "assistant", "content": conv['ai_response']})
            
            # Add context and current message
            full_message = f"Context: {context}\n\nUser Message: {message}"
            messages.append({"role": "user", "content": full_message})
            
            # Get AI response
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            ai_response = response.choices[0].message.content
            
            # Check for actionable items in response
            actions = self.extract_actions(ai_response, intent)
            
            return {
                'response': ai_response,
                'intent': intent,
                'confidence': analysis['confidence'],
                'actions': actions,
                'context_used': context
            }
            
        except Exception as e:
            return {
                'response': f"I'm having trouble processing that right now. Please try again. Error: {str(e)}",
                'intent': 'error',
                'confidence': 0,
                'actions': [],
                'error': str(e)
            }
    
    def extract_actions(self, ai_response: str, intent: str) -> List[Dict[str, Any]]:
        """Extract actionable items from AI response"""
        actions = []
        
        if intent == 'workout_logging':
            # Look for workout data patterns
            import re
            workout_patterns = re.findall(r'(\d+)x(\d+)(?:@|\s*at\s*)(\d+(?:\.\d+)?)\s*(?:lbs?|kg)?\s+([a-zA-Z\s]+)', ai_response)
            for sets, reps, weight, exercise in workout_patterns:
                actions.append({
                    'type': 'log_workout',
                    'data': {
                        'exercise': exercise.strip(),
                        'sets': int(sets),
                        'reps': reps,
                        'weight': f"{weight}lbs"
                    }
                })
        
        elif intent == 'plan_discussion':
            # Look for plan modifications
            if any(word in ai_response.lower() for word in ['modify', 'change', 'update', 'add', 'remove']):
                actions.append({
                    'type': 'plan_modification_suggested',
                    'data': {'suggestion': ai_response}
                })
        
        return actions
    
    def save_conversation(self, user_id: int, message: str, ai_response_data: Dict[str, Any]):
        """Save conversation for context and analysis"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations 
            (user_id, conversation_type, user_message, ai_response, context_data, actions_taken)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            ai_response_data['intent'],
            message,
            ai_response_data['response'],
            json.dumps({'intent': ai_response_data['intent'], 'confidence': ai_response_data['confidence']}),
            json.dumps(ai_response_data.get('actions', []))
        ))
        
        conn.commit()
        conn.close()
