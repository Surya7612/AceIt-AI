import os
from app import app

if __name__ == "__main__":
    try:
        # Get the PORT from environment variable (Replit sets this)
        port = int(os.environ.get('PORT', 5000))  # Default to 5000 if PORT not set
        host = '0.0.0.0'  # Bind to all available interfaces
        print(f"Starting server on {host}:{port}")
        app.run(host=host, port=port, debug=True)
    except Exception as e:
        print(f"Error starting server: {e}")
        raise  # Re-raise the exception for proper error handling