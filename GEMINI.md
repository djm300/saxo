Status: OK i have code to keep access/refresh tokens with Saxo alive and also to issue an order. I would like to build a python app (Flask maybe? anything is fine) which can in one thread keep the access/refresh token alive, in another thread at a certain time send a order


Roadmap:
Here's a practical and clean structure using Flask + threading to:
Keep your access token alive in the background
Send an order at a scheduled time
(Optionally) expose basic API endpoints to check health/status

Structure:
saxo_trading_app/
├── app.py              # Main Flask app
├── token_manager.py    # Token management logic
├── order_scheduler.py  # Order scheduling logic
├── config.py           # Config for API keys, schedule
└── requirements.txt    # Flask, requests, etc.

Description:
A Flask-based Python app with:
TokenManager class: handles refreshing access tokens
OrderScheduler class: runs in a thread and sends the order at a specified time
Flask app: simple endpoints (optional)
Threaded architecture: 1 thread for tokens, 1 for scheduled order