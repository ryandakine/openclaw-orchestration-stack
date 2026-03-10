"""
Tests for the backend API.
"""

import pytest
from main import app, process_data


@pytest.fixture
def client():
    """Create a test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get('/api/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'healthy'
    assert data['service'] == 'openclaw-backend'


def test_get_data(client):
    """Test data endpoint."""
    response = client.get('/api/data')
    assert response.status_code == 200
    data = response.get_json()
    assert 'message' in data
    assert 'data' in data


def test_process_data():
    """Test process_data function."""
    result = process_data([1, 2, 3, 4, 5])
    assert result == 15
    
    result = process_data([])
    assert result == 0
    
    result = process_data([10, -5])
    assert result == 5
