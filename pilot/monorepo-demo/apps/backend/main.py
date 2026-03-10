"""
Backend API application for the OpenClaw monorepo demo.
"""

from flask import Flask, jsonify

app = Flask(__name__)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'openclaw-backend',
        'version': '1.0.0'
    })


@app.route('/api/data', methods=['GET'])
def get_data():
    """Sample data endpoint."""
    return jsonify({
        'message': 'Hello from OpenClaw backend',
        'data': [1, 2, 3, 4, 5]
    })


def process_data(data: list[int]) -> int:
    """
    Process data by summing all elements.
    
    Args:
        data: List of integers to sum
        
    Returns:
        Sum of all elements
    """
    return sum(data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
