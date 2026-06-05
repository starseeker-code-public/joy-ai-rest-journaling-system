import os
from flask import Flask, jsonify
from dotenv import load_dotenv
from app.routes.journal_routes import register_journal_routes
from app.routes.auth_routes import register_auth_routes

load_dotenv()
app = Flask(__name__)
register_journal_routes(app)
register_auth_routes(app)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    
    app.run(host=host, port=port, debug=debug)

