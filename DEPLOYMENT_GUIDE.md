# Workout Trainer - Mobile Deployment Guide

## Quick Deploy Options

### Option 1: Railway (Recommended - Free)
1. Go to [railway.app](https://railway.app) and sign up
2. Connect your GitHub account
3. Create a new project from your GitHub repo
4. Add environment variables:
   - `OPENAI_API_KEY` = your OpenAI API key
   - `GROK_API_KEY` = your Grok API key (if using)
5. Deploy! Your app will be available at `https://your-app-name.railway.app`

### Option 2: Render (Free tier)
1. Go to [render.com](https://render.com) and sign up
2. Connect your GitHub account
3. Create a new Web Service
4. Point to your GitHub repo
5. Set build command: `pip install -r requirements.txt`
6. Set start command: `python app.py`
7. Add environment variables (same as Railway)
8. Deploy!

### Option 3: Local Network Access (For testing)
1. Find your computer's IP address:
   - Windows: Open CMD and type `ipconfig`
   - Look for "IPv4 Address" (usually 192.168.x.x)
2. Run your app: `python app.py`
3. On your phone, open browser and go to: `http://YOUR_IP:5000`
   - Example: `http://192.168.1.100:5000`

## Environment Variables Needed
Create a `.env` file in your project root:
```
OPENAI_API_KEY=your_openai_api_key_here
GROK_API_KEY=your_grok_api_key_here
```

## Mobile Access
Once deployed, you can:
1. **Add to Home Screen** (iOS): Open Safari → Share → Add to Home Screen
2. **Add to Home Screen** (Android): Open Chrome → Menu → Add to Home Screen
3. **Use as PWA**: The app will work like a native app when added to home screen

## Troubleshooting
- If you get database errors, the cloud service will create a fresh database
- Make sure all environment variables are set in your deployment platform
- Check the deployment logs if the app doesn't start

## Local Development
To test locally before deploying:
```bash
pip install -r requirements.txt
python app.py
```
Then visit `http://localhost:5000` in your browser.
