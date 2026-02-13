"""
GM Career Mode — entry point.
Runs the Flask web app (character creation and future UI).
"""
from app import app

if __name__ == "__main__":
    app.run(debug=True, port=5000)
