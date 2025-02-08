from app import app

if __name__ == "__main__":
    # In production, use Gunicorn
    # For development, use Flask's built-in server
    app.run(host="0.0.0.0", port=5000, debug=False)