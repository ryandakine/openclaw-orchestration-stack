# OpenClaw Observability Dashboard

Real-time monitoring and alerting dashboard for the OpenClaw Orchestration Stack.

## Features

- **Real-time Metrics**: Queue depth, cycle time, retry rates, and more
- **Visual Charts**: Interactive charts using Chart.js
- **Alert System**: Configurable alerts with Slack/Discord webhook support
- **Dark Mode**: Toggle between dark and light themes
- **Responsive Design**: Works on desktop and mobile devices
- **Auto-refresh**: Updates every 10 seconds (configurable)

## Quick Start

### Installation

```bash
# Install dependencies
pip install flask

# Set environment variables (optional)
export DASHBOARD_HOST=0.0.0.0
export DASHBOARD_PORT=5000
export OPENCLAW_DB_PATH=data/openclaw.db

# Run the dashboard
python web_dashboard.py
```

### Access the Dashboard

Open your browser to `http://localhost:5000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard HTML page |
| `/api/health` | GET | Health check endpoint |
| `/api/metrics` | GET | All system metrics |
| `/api/metrics/<name>` | GET | Specific metric (queue_depth, stuck_tasks, etc.) |
| `/api/tasks` | GET | Task list with filters |
| `/api/audit-events` | GET | Recent audit events |
| `/api/alerts` | GET | Active alerts |
| `/api/alerts/rules` | GET/POST | Alert rules management |
| `/api/alerts/rules/<name>` | DELETE | Delete alert rule |
| `/api/alerts/acknowledge` | POST | Acknowledge alert |
| `/api/send-alert` | POST | Send manual alert |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_HOST` | `0.0.0.0` | Server bind address |
| `DASHBOARD_PORT` | `5000` | Server port |
| `DASHBOARD_TITLE` | `OpenClaw Observability Dashboard` | Page title |
| `DASHBOARD_REFRESH_INTERVAL` | `10` | Auto-refresh interval in seconds |
| `OPENCLAW_DB_PATH` | `data/openclaw.db` | SQLite database path |
| `ALERT_WEBHOOK_URL` | - | Generic webhook URL for alerts |
| `SLACK_WEBHOOK_URL` | - | Slack webhook URL |
| `DISCORD_WEBHOOK_URL` | - | Discord webhook URL |

### Alert Rules

Default alert rules are configured for:

- **High Queue Depth**: Warning at >100, Critical at >500
- **Stuck Tasks**: Warning at >10, Critical at >20
- **High Fail Rate**: Warning at >30%, Critical at >50%
- **Dead Letter Queue**: Warning at >5, Critical at >10 in 24h
- **High Cycle Time**: Warning at >1 hour average

## Metrics Collected

### Queue Depth
- Count by task status (queued, executing, review_queued, etc.)
- Count by priority level

### Stuck Tasks
- Tasks in executing/review_queued with expired leases
- Tasks not updated within threshold (default: 30 minutes)

### Cycle Time
- Average time from queued to approved
- Min, max, median, and P95 statistics

### Retry Rate
- Percentage of tasks requiring multiple attempts
- Average and maximum retry counts

### Review Metrics
- Pass/fail/block counts and percentages
- 24-hour rolling window

### Dead Letter Queue
- Total count of permanently failed tasks
- Recent failures (last 24 hours)

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_metrics_collector.py -v
python -m pytest tests/test_alerts.py -v
python -m pytest tests/test_web_dashboard.py -v

# Run dashboard rendering test
python test_dashboard_server.py
```

## File Structure

```
openclaw/dashboard/
├── __init__.py              # Package initialization
├── metrics_collector.py     # Metrics collection logic
├── alerts.py                # Alert system
├── web_dashboard.py         # Flask web application
├── static/
│   ├── index.html          # Static HTML (reference)
│   ├── style.css           # Dashboard styles (dark/light mode)
│   └── dashboard.js        # Frontend JavaScript
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # Pytest fixtures
│   ├── test_metrics_collector.py
│   ├── test_alerts.py
│   └── test_web_dashboard.py
├── test_dashboard_server.py # Integration test script
└── README.md               # This file
```

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers

## License

MIT License - See project root LICENSE file
