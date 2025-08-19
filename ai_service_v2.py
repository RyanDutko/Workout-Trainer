
import os
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from models import Database, User, TrainingPlan, Workout
from datetime import datetime, timedelta

class AIServiceV2:
    def __init__(self, db: Database):
        self.db = db
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.user = User(db)
        self.training_plan = TrainingPlan(db)
        self.workout = Workout(db)
        
        # Define the tools/functions that the AI can call
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weekly_plan",
                    "description": "Get the user's weekly workout plan for a specific day or all days",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "day": {
                                "type": "string", 
                                "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "all"],
                                "description": "Day of the week to get plan for, or 'all' for entire week"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_workout_history",
                    "description": "Get user's workout history with optional filtering",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Specific date (YYYY-MM-DD) to get workouts for"
                            },
                            "exercise": {
                                "type": "string",
                                "description": "Specific exercise name to filter by"
                            },
                            "days_back": {
                                "type": "integer",
                                "default": 7,
                                "description": "Number of days back to look (default 7)"
                            },
                            "limit": {
                                "type": "integer",
                                "default": 10,
                                "description": "Maximum number of workout entries to return"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_profile",
                    "description": "Get user's profile information and preferences",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_training_philosophy",
                    "description": "Get the user's current training philosophy and approach",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_progression_data",
                    "description": "Get progression data for specific exercises or overall progress",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exercise": {
                                "type": "string",
                                "description": "Specific exercise to get progression for"
                            },
                            "weeks_back": {
                                "type": "integer",
                                "default": 4,
                                "description": "Number of weeks to analyze for progression"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "log_workout",
                    "description": "Log a completed workout for the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exercise_name": {
                                "type": "string",
                                "description": "Name of the exercise performed"
                            },
                            "sets": {
                                "type": "integer",
                                "description": "Number of sets completed"
                            },
                            "reps": {
                                "type": "string",
                                "description": "Reps performed (can be range like '8-12' or specific like '10')"
                            },
                            "weight": {
                                "type": "string",
                                "description": "Weight used (e.g. '185lbs', 'bodyweight')"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes about the workout"
                            },
                            "date": {
                                "type": "string",
                                "description": "Date of workout (YYYY-MM-DD), defaults to today"
                            }
                        },
                        "required": ["exercise_name", "sets", "reps", "weight"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "modify_weekly_plan",
                    "description": "Add, update, or remove exercises from the weekly plan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["add", "update", "remove"],
                                "description": "Action to perform on the plan"
                            },
                            "day": {
                                "type": "string",
                                "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                                "description": "Day of the week to modify"
                            },
                            "exercise_name": {
                                "type": "string",
                                "description": "Name of the exercise"
                            },
                            "sets": {
                                "type": "integer",
                                "description": "Number of sets (for add/update)"
                            },
                            "reps": {
                                "type": "string",
                                "description": "Rep range (for add/update)"
                            },
                            "weight": {
                                "type": "string",
                                "description": "Weight target (for add/update)"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Explanation for the change"
                            }
                        },
                        "required": ["action", "day", "exercise_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_training_philosophy",
                    "description": "Update the user's training philosophy and approach",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "core_philosophy": {
                                "type": "string",
                                "description": "The foundational training approach and principles"
                            },
                            "current_priorities": {
                                "type": "string",
                                "description": "Specific current focuses and priorities for this training phase"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Explanation for the philosophy update"
                            }
                        },
                        "required": ["core_philosophy"]
                    }
                }
            }
        ]
    
    def get_ai_response(self, message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Get AI response using function calling for precise intent detection"""
        MAX_TOOL_CALLS = 5  # Prevent infinite loops
        MAX_ITERATIONS = 3  # Limit conversation iterations
        
        try:
            # Build conversation messages
            messages = [
                {
                    "role": "system", 
                    "content": """You are an expert personal trainer AI assistant built into a fitness app. 

You have access to various tools to help users with their fitness journey. When users ask questions or make requests, use the appropriate tools to get the information you need, then provide helpful responses.

Key principles:
- Always use tools to get current data before making recommendations
- Be encouraging and motivational
- Provide specific, actionable advice
- If logging workouts, confirm the details with the user
- For plan modifications, explain your reasoning
- Use the user's actual data to give personalized advice
- IMPORTANT: Only call tools when necessary. Don't call the same tool repeatedly.

When users mention workouts they've completed, use the log_workout tool. When they ask about their plan, use get_weekly_plan. When they want to see their history, use get_workout_history."""
                }
            ]
            
            # Add conversation history if provided
            if conversation_history:
                for conv in conversation_history[-3:]:  # Last 3 exchanges for context
                    messages.append({"role": "user", "content": conv['user_message']})
                    messages.append({"role": "assistant", "content": conv['ai_response']})
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Make the API call with tools
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                tools=self.tools,
                tool_choice="auto",  # Let AI decide which tools to use
                temperature=0.7,
                max_tokens=1000
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            
            # If AI wants to use tools, execute them
            if tool_calls:
                # SAFEGUARD: Check for too many tool calls
                if len(tool_calls) > MAX_TOOL_CALLS:
                    return {
                        'response': f"I'm trying to call too many tools at once ({len(tool_calls)}). Let me simplify my response.",
                        'tools_used': [],
                        'tool_results': [],
                        'success': False,
                        'error': 'Too many tool calls attempted'
                    }
                
                # Add the AI's response with tool calls to the conversation
                messages.append(response_message)
                
                # Track which tools we've called to prevent duplicates
                tools_called = set()
                
                # Execute each tool call
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    # SAFEGUARD: Prevent calling the same tool with same args repeatedly
                    tool_signature = f"{function_name}:{json.dumps(function_args, sort_keys=True)}"
                    if tool_signature in tools_called:
                        print(f"⚠️ Skipping duplicate tool call: {function_name}")
                        continue
                    tools_called.add(tool_signature)
                    
                    print(f"🔧 AI is calling tool: {function_name} with args: {function_args}")
                    
                    # Execute the function
                    tool_result = self._execute_tool(function_name, function_args)
                    
                    # Add tool result to conversation
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(tool_result)
                    })
                
                # Get final response from AI after processing tool results
                final_response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    tools=self.tools,  # Required when using tool_choice
                    temperature=0.7,
                    max_tokens=1000,
                    tool_choice="none"  # SAFEGUARD: Force AI to respond, no more tools
                )
                
                ai_response = final_response.choices[0].message.content
                
                return {
                    'response': ai_response,
                    'tools_used': [tc.function.name for tc in tool_calls],
                    'tool_results': [self._execute_tool(tc.function.name, json.loads(tc.function.arguments)) for tc in tool_calls],
                    'success': True
                }
            
            else:
                # No tools needed, return direct response
                return {
                    'response': response_message.content,
                    'tools_used': [],
                    'tool_results': [],
                    'success': True
                }
                
        except Exception as e:
            print(f"⚠️ AI Service V2 error: {str(e)}")
            return {
                'response': f"I'm having trouble processing that right now. Please try again. Error: {str(e)}",
                'tools_used': [],
                'tool_results': [],
                'success': False,
                'error': str(e)
            }
    
    def _execute_tool(self, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool function and return the result"""
        import time
        start_time = time.time()
        TOOL_TIMEOUT = 10  # 10 second timeout per tool
        
        try:
            if function_name == "get_weekly_plan":
                return self._get_weekly_plan(args.get('day', 'all'))
            
            elif function_name == "get_workout_history":
                return self._get_workout_history(
                    date=args.get('date'),
                    exercise=args.get('exercise'),
                    days_back=args.get('days_back', 7),
                    limit=args.get('limit', 10)
                )
            
            elif function_name == "get_user_profile":
                return self._get_user_profile()
            
            elif function_name == "get_training_philosophy":
                return self._get_training_philosophy()
            
            elif function_name == "get_progression_data":
                return self._get_progression_data(
                    exercise=args.get('exercise'),
                    weeks_back=args.get('weeks_back', 4)
                )
            
            elif function_name == "log_workout":
                return self._log_workout(
                    exercise_name=args['exercise_name'],
                    sets=args['sets'],
                    reps=args['reps'],
                    weight=args['weight'],
                    notes=args.get('notes', ''),
                    date=args.get('date', datetime.now().strftime('%Y-%m-%d'))
                )
            
            elif function_name == "modify_weekly_plan":
                return self._modify_weekly_plan(
                    action=args['action'],
                    day=args['day'],
                    exercise_name=args['exercise_name'],
                    sets=args.get('sets'),
                    reps=args.get('reps'),
                    weight=args.get('weight'),
                    reasoning=args.get('reasoning', '')
                )
            
            elif function_name == "update_training_philosophy":
                return self._update_training_philosophy(
                    core_philosophy=args['core_philosophy'],
                    current_priorities=args.get('current_priorities', ''),
                    reasoning=args.get('reasoning', '')
                )
            
            else:
                return {"error": f"Unknown function: {function_name}"}
                
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}
        
        finally:
            # SAFEGUARD: Check if tool took too long
            execution_time = time.time() - start_time
            if execution_time > TOOL_TIMEOUT:
                print(f"⚠️ Tool {function_name} took {execution_time:.2f}s (timeout: {TOOL_TIMEOUT}s)")
                return {"error": f"Tool execution timeout after {execution_time:.2f}s"}
    
    def _get_weekly_plan(self, day: str) -> Dict[str, Any]:
        """Get weekly plan data"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if day == 'all':
            cursor.execute('''
                SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
                FROM weekly_plan
                ORDER BY 
                    CASE day_of_week
                        WHEN 'monday' THEN 1
                        WHEN 'tuesday' THEN 2
                        WHEN 'wednesday' THEN 3
                        WHEN 'thursday' THEN 4
                        WHEN 'friday' THEN 5
                        WHEN 'saturday' THEN 6
                        WHEN 'sunday' THEN 7
                    END, exercise_order
            ''')
        else:
            cursor.execute('''
                SELECT day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes
                FROM weekly_plan
                WHERE day_of_week = ?
                ORDER BY exercise_order
            ''', (day,))
        
        results = cursor.fetchall()
        conn.close()
        
        plan_data = []
        for row in results:
            plan_data.append({
                'day': row[0],
                'exercise': row[1],
                'sets': row[2],
                'reps': row[3],
                'weight': row[4],
                'order': row[5],
                'notes': row[6] or ''
            })
        
        return {"plan": plan_data, "total_exercises": len(plan_data)}
    
    def _get_workout_history(self, date: str = None, exercise: str = None, days_back: int = 7, limit: int = 10) -> Dict[str, Any]:
        """Get workout history with optional filtering"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT exercise_name, sets, reps, weight, date_logged, notes FROM workouts WHERE 1=1"
        params = []
        
        if date:
            query += " AND date_logged = ?"
            params.append(date)
        else:
            cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            query += " AND date_logged >= ?"
            params.append(cutoff_date)
        
        if exercise:
            query += " AND LOWER(exercise_name) LIKE LOWER(?)"
            params.append(f"%{exercise}%")
        
        query += " ORDER BY date_logged DESC, id DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        workouts = []
        for row in results:
            workouts.append({
                'exercise': row[0],
                'sets': row[1],
                'reps': row[2],
                'weight': row[3],
                'date': row[4],
                'notes': row[5] or ''
            })
        
        return {"workouts": workouts, "total_found": len(workouts)}
    
    def _get_user_profile(self) -> Dict[str, Any]:
        """Get user profile and preferences"""
        profile = self.user.get_profile()
        ai_prefs = self.user.get_ai_preferences()
        
        return {
            "profile": profile,
            "ai_preferences": ai_prefs
        }
    
    def _get_training_philosophy(self) -> Dict[str, Any]:
        """Get current training philosophy"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT plan_philosophy, progression_strategy, weekly_structure, special_considerations
            FROM plan_context
            WHERE user_id = 1
            ORDER BY created_date DESC
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "core_philosophy": result[0] or '',
                "current_priorities": result[1] or '',
                "weekly_structure": result[2] or '',
                "special_considerations": result[3] or ''
            }
        
        return {"message": "No training philosophy set yet"}
    
    def _get_progression_data(self, exercise: str = None, weeks_back: int = 4) -> Dict[str, Any]:
        """Get progression data for exercises"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(weeks=weeks_back)).strftime('%Y-%m-%d')
        
        if exercise:
            cursor.execute('''
                SELECT date_logged, weight, sets, reps
                FROM workouts
                WHERE LOWER(exercise_name) LIKE LOWER(?) AND date_logged >= ?
                ORDER BY date_logged ASC
            ''', (f"%{exercise}%", cutoff_date))
        else:
            cursor.execute('''
                SELECT exercise_name, MAX(date_logged) as latest_date, weight, sets, reps
                FROM workouts
                WHERE date_logged >= ?
                GROUP BY exercise_name
                ORDER BY latest_date DESC
            ''', (cutoff_date,))
        
        results = cursor.fetchall()
        conn.close()
        
        progression_data = []
        for row in results:
            if exercise:
                progression_data.append({
                    'date': row[0],
                    'weight': row[1],
                    'sets': row[2],
                    'reps': row[3]
                })
            else:
                progression_data.append({
                    'exercise': row[0],
                    'latest_date': row[1],
                    'weight': row[2],
                    'sets': row[3],
                    'reps': row[4]
                })
        
        return {"progression_data": progression_data}
    
    def _log_workout(self, exercise_name: str, sets: int, reps: str, weight: str, notes: str = '', date: str = None) -> Dict[str, Any]:
        """Log a workout entry"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        workout_id = self.workout.log_workout(
            user_id=1,
            date=date,
            exercises=[{
                'name': exercise_name,
                'sets': sets,
                'reps': reps,
                'weight': weight,
                'notes': notes
            }],
            notes=notes
        )
        
        return {
            "success": True,
            "workout_id": workout_id,
            "message": f"Logged {exercise_name}: {sets}x{reps}@{weight} on {date}"
        }
    
    def _modify_weekly_plan(self, action: str, day: str, exercise_name: str, sets: int = None, reps: str = None, weight: str = None, reasoning: str = '') -> Dict[str, Any]:
        """Modify the weekly plan"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if action == "add":
            # Get next order for the day
            cursor.execute('SELECT COALESCE(MAX(exercise_order), 0) + 1 FROM weekly_plan WHERE day_of_week = ?', (day,))
            next_order = cursor.fetchone()[0]
            
            cursor.execute('''
                INSERT INTO weekly_plan
                (day_of_week, exercise_name, target_sets, target_reps, target_weight, exercise_order, notes, created_by, newly_added, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ai_v2', TRUE, ?)
            ''', (day, exercise_name, sets or 3, reps or '8-12', weight or 'bodyweight', next_order, reasoning, datetime.now().strftime('%Y-%m-%d')))
            
            message = f"Added {exercise_name} to {day}: {sets or 3}x{reps or '8-12'}@{weight or 'bodyweight'}"
        
        elif action == "update":
            cursor.execute('''
                UPDATE weekly_plan
                SET target_sets = COALESCE(?, target_sets),
                    target_reps = COALESCE(?, target_reps),
                    target_weight = COALESCE(?, target_weight),
                    notes = ?
                WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)
            ''', (sets, reps, weight, reasoning, day, exercise_name))
            
            message = f"Updated {exercise_name} on {day}"
        
        elif action == "remove":
            cursor.execute('DELETE FROM weekly_plan WHERE day_of_week = ? AND LOWER(exercise_name) = LOWER(?)', (day, exercise_name))
            message = f"Removed {exercise_name} from {day}"
        
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return {
            "success": rows_affected > 0,
            "message": message,
            "rows_affected": rows_affected
        }
    
    def _update_training_philosophy(self, core_philosophy: str, current_priorities: str = '', reasoning: str = '') -> Dict[str, Any]:
        """Update training philosophy"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO plan_context
            (user_id, plan_philosophy, progression_strategy, created_by_ai, creation_reasoning, created_date, updated_date)
            VALUES (1, ?, ?, TRUE, ?, ?, ?)
        ''', (core_philosophy, current_priorities, reasoning, datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d')))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Training philosophy updated successfully"
        }
