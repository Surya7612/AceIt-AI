import os
from app import app

if __name__ == "__main__":
    # Get the PORT from environment variable (Replit sets this)
    port = int(os.environ.get('PORT', 5000))
    # Run the app with the correct host and port
    app.run(host='0.0.0.0', port=port)