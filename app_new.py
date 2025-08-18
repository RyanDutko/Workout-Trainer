
from flask import Flask, render_template, request, jsonify, Response
import json
import time
from datetime import datetime
from models import Database, User, TrainingPlan, Workout
from ai_service import AIService

app = Flask(__name__)

# Initialize services
db = Database()
ai_service = AIService(db)
user_service = User(db)
plan_service = TrainingPlan(db)
workout_service = Workout(db)

@app.route('/')
def dashboard():
    """Main dashboard with today's plan and recent activity"""
    try:
        # Get active plan
        plan = plan_service.get_active_plan()
        
        # Get recent workouts
        recent_workouts = workout_service.get_recent_workouts(limit=5)
        
        # Get today's planned exercises if plan exists
        today_plan = []
        if plan and 'weekly_schedule' in plan['plan_data']:
            today = datetime.now().strftime('%A').lower()
            today_plan = plan['plan_data']['weekly_schedule'].get(today, [])
        
        return render_template('dashboard.html', 
                             plan=plan, 
                             today_plan=today_plan,
                             recent_workouts=recent_workouts)
                             
    except Exception as e:
        app.logger.error(f"Dashboard error: {e}")
        return render_template('dashboard.html', 
                             plan=None, 
                             today_plan=[],
                             recent_workouts=[])

@app.route('/chat')
def chat():
    """AI chat interface"""
    return render_template('chat.html')

@app.route('/chat_stream', methods=['POST'])
def chat_stream():
    """Streaming AI chat responses"""
    user_message = request.form.get('message', '')
    
    def generate():
        try:
            # Get conversation history
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_message, ai_response FROM conversations 
                WHERE user_id = 1 
                ORDER BY created_at DESC LIMIT 5
            ''')
            history = [{'user_message': row[0], 'ai_response': row[1]} for row in cursor.fetchall()]
            conn.close()
            
            # Get AI response
            ai_result = ai_service.get_ai_response(user_message, history)
            
            # Stream response
            for char in ai_result['response']:
                yield f"data: {json.dumps({'content': char})}\n\n"
                time.sleep(0.01)
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
            # Save conversation
            ai_service.save_conversation(1, user_message, ai_result)
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/plain')

@app.route('/log_workout', methods=['GET', 'POST'])
def log_workout():
    """Workout logging interface"""
    if request.method == 'GET':
        # Get today's plan for reference
        plan = plan_service.get_active_plan()
        today_plan = []
        if plan and 'weekly_schedule' in plan['plan_data']:
            today = datetime.now().strftime('%A').lower()
            today_plan = plan['plan_data']['weekly_schedule'].get(today, [])
        
        return render_template('log_workout.html', today_plan=today_plan)
    
    elif request.method == 'POST':
        try:
            data = request.json
            workout_id = workout_service.log_workout(
                user_id=1,
                date=data.get('date', datetime.now().strftime('%Y-%m-%d')),
                exercises=data.get('exercises', []),
                notes=data.get('notes', '')
            )
            
            return jsonify({'success': True, 'workout_id': workout_id})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

@app.route('/weekly_plan')
def weekly_plan():
    """Weekly training plan view"""
    plan = plan_service.get_active_plan()
    return render_template('weekly_plan.html', plan=plan)

@app.route('/history')
def history():
    """Workout history view"""
    workouts = workout_service.get_recent_workouts(limit=50)
    return render_template('history.html', workouts=workouts)

@app.route('/profile')
def profile():
    """User profile and preferences"""
    profile_data = user_service.get_profile()
    ai_preferences = user_service.get_ai_preferences()
    return render_template('profile.html', 
                         profile=profile_data, 
                         ai_preferences=ai_preferences)

@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    """Update user profile"""
    try:
        data = request.json
        user_service.update_profile(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save_plan', methods=['POST'])
def save_plan():
    """Save training plan"""
    try:
        data = request.json
        plan_service.save_plan(
            user_id=1,
            name=data.get('name', 'My Plan'),
            plan_data=data.get('plan_data', {}),
            philosophy=data.get('philosophy', '')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/recent_workouts')
def api_recent_workouts():
    """API endpoint for recent workouts"""
    limit = request.args.get('limit', 10, type=int)
    workouts = workout_service.get_recent_workouts(limit=limit)
    return jsonify(workouts)

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
