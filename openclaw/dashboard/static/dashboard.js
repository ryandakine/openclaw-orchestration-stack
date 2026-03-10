/**
 * OpenClaw Observability Dashboard - JavaScript
 * Real-time updates and interactive charts
 */

// Global state
let refreshInterval;
let charts = {};
let lastMetrics = null;

// Configuration
const config = window.DASHBOARD_CONFIG || {
    refreshInterval: 10,
    title: "OpenClaw Observability Dashboard"
};

// Chart colors
const colors = {
    primary: '#58a6ff',
    success: '#238636',
    warning: '#f0883e',
    danger: '#da3633',
    info: '#1f6feb',
    gray: '#6e7681',
    chartColors: [
        '#58a6ff',
        '#238636',
        '#f0883e',
        '#da3633',
        '#8957e5',
        '#d29922',
        '#3fb950',
        '#a371f7'
    ]
};

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initCharts();
    initEventListeners();
    refreshData();
    startAutoRefresh();
});

// Theme handling
function initTheme() {
    const savedTheme = localStorage.getItem('dashboard-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeButton(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('dashboard-theme', newTheme);
    updateThemeButton(newTheme);
    
    // Update charts for new theme
    updateChartColors();
}

function updateThemeButton(theme) {
    const btn = document.getElementById('themeToggle');
    if (btn) {
        btn.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
    }
}

// Initialize charts
function initCharts() {
    // Queue Depth Bar Chart
    const queueDepthCtx = document.getElementById('queueDepthChart');
    if (queueDepthCtx) {
        charts.queueDepth = new Chart(queueDepthCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Tasks',
                    data: [],
                    backgroundColor: colors.chartColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: getComputedStyle(document.body).color
                        }
                    },
                    x: {
                        ticks: {
                            color: getComputedStyle(document.body).color
                        }
                    }
                }
            }
        });
    }

    // Status Pie Chart
    const statusPieCtx = document.getElementById('statusPieChart');
    if (statusPieCtx) {
        charts.statusPie = new Chart(statusPieCtx, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: colors.chartColors,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: getComputedStyle(document.body).color,
                            font: {
                                size: 11
                            }
                        }
                    }
                }
            }
        });
    }

    // Cycle Time Line Chart
    const cycleTimeCtx = document.getElementById('cycleTimeChart');
    if (cycleTimeCtx) {
        charts.cycleTime = new Chart(cycleTimeCtx, {
            type: 'line',
            data: {
                labels: ['Avg', 'Median', 'P95', 'Min', 'Max'],
                datasets: [{
                    label: 'Seconds',
                    data: [],
                    borderColor: colors.primary,
                    backgroundColor: `${colors.primary}20`,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: getComputedStyle(document.body).color,
                            callback: function(value) {
                                return formatDuration(value);
                            }
                        }
                    },
                    x: {
                        ticks: {
                            color: getComputedStyle(document.body).color
                        }
                    }
                }
            }
        });
    }

    // Review Pass/Fail Chart
    const reviewCtx = document.getElementById('reviewChart');
    if (reviewCtx) {
        charts.review = new Chart(reviewCtx, {
            type: 'pie',
            data: {
                labels: ['Passed', 'Failed', 'Blocked'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: [colors.success, colors.danger, colors.warning],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: getComputedStyle(document.body).color
                        }
                    }
                }
            }
        });
    }
}

function updateChartColors() {
    const textColor = getComputedStyle(document.body).color;
    
    Object.values(charts).forEach(chart => {
        if (chart.options.scales?.x?.ticks) {
            chart.options.scales.x.ticks.color = textColor;
        }
        if (chart.options.scales?.y?.ticks) {
            chart.options.scales.y.ticks.color = textColor;
        }
        if (chart.options.plugins?.legend?.labels) {
            chart.options.plugins.legend.labels.color = textColor;
        }
        chart.update();
    });
}

// Event listeners
function initEventListeners() {
    // Theme toggle
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', toggleTheme);
    }

    // Refresh button
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            refreshBtn.classList.add('updating');
            refreshData().then(() => {
                setTimeout(() => refreshBtn.classList.remove('updating'), 500);
            });
        });
    }
}

// Auto refresh
function startAutoRefresh() {
    refreshInterval = setInterval(refreshData, config.refreshInterval * 1000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}

// Fetch and update data
async function refreshData() {
    try {
        updateStatus('checking');
        
        // Fetch all data in parallel
        const [metricsResponse, auditResponse, alertsResponse] = await Promise.all([
            fetch('/api/metrics'),
            fetch('/api/audit-events?limit=20'),
            fetch('/api/alerts')
        ]);

        const metricsData = await metricsResponse.json();
        const auditData = await auditResponse.json();
        const alertsData = await alertsResponse.json();

        if (metricsData.success) {
            lastMetrics = metricsData.data;
            updateDashboard(metricsData.data);
            updateStatus(metricsData.data.system_health?.status || 'unknown');
        } else {
            console.error('Metrics error:', metricsData.error);
            updateStatus('error');
        }

        if (auditData.success) {
            updateAuditTable(auditData.events);
        }

        if (alertsData.success) {
            updateAlertsPanel(alertsData.alerts);
        }

        updateLastUpdateTime();

    } catch (error) {
        console.error('Refresh error:', error);
        updateStatus('error');
    }
}

// Update dashboard components
function updateDashboard(data) {
    updateQueueDepth(data.queue_depth);
    updateStatusPie(data.queue_depth?.by_status);
    updateCycleTime(data.cycle_time);
    updateStuckTasks(data.stuck_tasks);
    updateReviewMetrics(data.review_metrics);
    updateSystemHealth(data.system_health);
    updateRetryRate(data.retry_rate);
    updateDeadLetter(data.dead_letter);
}

function updateQueueDepth(queueDepth) {
    if (!queueDepth || !charts.queueDepth) return;

    const statusLabels = {
        'queued': 'Queued',
        'executing': 'Executing',
        'review_queued': 'Review Queue',
        'approved': 'Approved',
        'merged': 'Merged',
        'failed': 'Failed',
        'blocked': 'Blocked',
        'review_failed': 'Review Failed',
        'remediation_queued': 'Remediation'
    };

    const labels = [];
    const values = [];
    
    Object.entries(queueDepth.by_status || {}).forEach(([status, count]) => {
        labels.push(statusLabels[status] || status);
        values.push(count);
    });

    charts.queueDepth.data.labels = labels;
    charts.queueDepth.data.datasets[0].data = values;
    charts.queueDepth.update();

    // Update stats
    const statsContainer = document.getElementById('queueDepthStats');
    if (statsContainer) {
        const activeCount = 
            (queueDepth.by_status?.queued || 0) +
            (queueDepth.by_status?.executing || 0) +
            (queueDepth.by_status?.review_queued || 0);
        
        statsContainer.innerHTML = `
            <div class="stat-item">
                <div class="stat-value">${queueDepth.total || 0}</div>
                <div class="stat-label">Total</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${activeCount}</div>
                <div class="stat-label">Active</div>
            </div>
        `;
    }
}

function updateStatusPie(byStatus) {
    if (!byStatus || !charts.statusPie) return;

    const labels = [];
    const values = [];
    
    Object.entries(byStatus).forEach(([status, count]) => {
        if (count > 0) {
            labels.push(status);
            values.push(count);
        }
    });

    charts.statusPie.data.labels = labels;
    charts.statusPie.data.datasets[0].data = values;
    charts.statusPie.update();
}

function updateCycleTime(cycleTime) {
    if (!cycleTime || !charts.cycleTime) return;

    const data = [
        cycleTime.avg_seconds || 0,
        cycleTime.median_seconds || 0,
        cycleTime.p95_seconds || 0,
        cycleTime.min_seconds || 0,
        cycleTime.max_seconds || 0
    ];

    charts.cycleTime.data.datasets[0].data = data;
    charts.cycleTime.update();

    // Update stats
    const statsContainer = document.getElementById('cycleTimeStats');
    if (statsContainer && cycleTime.count > 0) {
        statsContainer.innerHTML = `
            <div class="stat-item">
                <div class="stat-value">${formatDuration(cycleTime.avg_seconds)}</div>
                <div class="stat-label">Average</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${formatDuration(cycleTime.p95_seconds)}</div>
                <div class="stat-label">P95</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${cycleTime.count}</div>
                <div class="stat-label">Tasks</div>
            </div>
        `;
    }
}

function updateStuckTasks(stuckTasks) {
    const container = document.getElementById('stuckTasksList');
    const card = document.getElementById('stuckTasksCard');
    
    if (!container || !stuckTasks) return;

    if (stuckTasks.count === 0) {
        container.innerHTML = '<p class="empty">No stuck tasks detected</p>';
        card.style.borderColor = '';
        return;
    }

    // Highlight card if there are stuck tasks
    card.style.borderColor = colors.warning;

    const tasks = stuckTasks.tasks.slice(0, 5);
    container.innerHTML = tasks.map(task => `
        <div class="stuck-task-item">
            <span class="stuck-task-id">${truncateId(task.id)}</span>
            <span class="stuck-task-status">${task.status}</span>
            <span class="stuck-task-reason">${task.stuck_reason}</span>
            <span class="stuck-task-time">${formatDuration(task.minutes_stuck * 60)} stuck</span>
        </div>
    `).join('');

    if (stuckTasks.count > 5) {
        container.innerHTML += `
            <p class="empty">...and ${stuckTasks.count - 5} more</p>
        `;
    }
}

function updateReviewMetrics(reviewMetrics) {
    if (!reviewMetrics || !charts.review) return;

    charts.review.data.datasets[0].data = [
        reviewMetrics.passed || 0,
        reviewMetrics.failed || 0,
        reviewMetrics.blocked || 0
    ];
    charts.review.update();

    // Update stats
    const statsContainer = document.getElementById('reviewStats');
    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="stat-item">
                <div class="stat-value" style="color: ${colors.success}">${reviewMetrics.pass_rate || 0}%</div>
                <div class="stat-label">Pass Rate</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${reviewMetrics.total_reviews || 0}</div>
                <div class="stat-label">Total</div>
            </div>
        `;
    }
}

function updateSystemHealth(health) {
    if (!health) return;

    const statusContainer = document.getElementById('healthStatus');
    const statsContainer = document.getElementById('healthStats');

    if (statusContainer) {
        const statusClass = `health-${health.status}`;
        statusContainer.innerHTML = `
            <div class="health-indicator ${statusClass}">${health.status}</div>
        `;
    }

    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="stat-item">
                <div class="stat-value">${health.active_tasks || 0}</div>
                <div class="stat-label">Active</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${health.error_rate || 0}%</div>
                <div class="stat-label">Error Rate</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${health.stuck_tasks_count || 0}</div>
                <div class="stat-label">Stuck</div>
            </div>
        `;
    }
}

function updateRetryRate(retryRate) {
    if (!retryRate) return;

    const container = document.getElementById('retryRateStats');
    if (container) {
        container.innerHTML = `
            <div class="stat-item">
                <div class="stat-value" style="color: ${retryRate.retry_rate > 20 ? colors.danger : colors.success}">${retryRate.retry_rate}%</div>
                <div class="stat-label">Retry Rate</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${retryRate.avg_retries || 0}</div>
                <div class="stat-label">Avg Retries</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${retryRate.total_tasks || 0}</div>
                <div class="stat-label">Total</div>
            </div>
        `;
    }
}

function updateDeadLetter(dlq) {
    if (!dlq) return;

    const container = document.getElementById('dlqStats');
    if (container) {
        const recentColor = dlq.recent_24h > 0 ? colors.danger : colors.success;
        container.innerHTML = `
            <div class="stat-item">
                <div class="stat-value" style="color: ${recentColor}">${dlq.recent_24h}</div>
                <div class="stat-label">Last 24h</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">${dlq.total_count || 0}</div>
                <div class="stat-label">Total</div>
            </div>
        `;
    }
}

function updateAuditTable(events) {
    const tbody = document.getElementById('auditTableBody');
    if (!tbody || !events) return;

    tbody.innerHTML = events.slice(0, 10).map(event => `
        <tr>
            <td>${formatTimestamp(event.timestamp)}</td>
            <td><span class="badge badge-${event.actor}">${event.actor}</span></td>
            <td>${event.action}</td>
            <td><code>${truncateId(event.correlation_id)}</code></td>
        </tr>
    `).join('');
}

function updateAlertsPanel(alerts) {
    const section = document.getElementById('alertsSection');
    const container = document.getElementById('alertsList');
    
    if (!section || !container) return;

    if (alerts.length === 0) {
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    
    container.innerHTML = alerts.map(alert => `
        <div class="alert-item ${alert.severity}">
            <span class="alert-severity">${alert.severity}</span>
            <span class="alert-message">${alert.message}</span>
            <span class="alert-time">${formatTimestamp(alert.timestamp)}</span>
        </div>
    `).join('');
}

// Utility functions
function updateStatus(status) {
    const indicator = document.getElementById('statusIndicator');
    if (!indicator) return;

    const statusClasses = {
        healthy: 'status-healthy',
        degraded: 'status-degraded',
        critical: 'status-critical',
        error: 'status-critical',
        checking: 'status-unknown',
        unknown: 'status-unknown'
    };

    indicator.className = `status-badge ${statusClasses[status] || 'status-unknown'}`;
    indicator.textContent = status === 'checking' ? 'Checking...' : status;
}

function updateLastUpdateTime() {
    const element = document.getElementById('lastUpdate');
    if (element) {
        element.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
    }
}

function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '-';
    
    if (seconds < 60) {
        return `${Math.round(seconds)}s`;
    } else if (seconds < 3600) {
        return `${Math.round(seconds / 60)}m`;
    } else if (seconds < 86400) {
        return `${Math.round(seconds / 3600 * 10) / 10}h`;
    } else {
        return `${Math.round(seconds / 86400 * 10) / 10}d`;
    }
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) {
        return 'just now';
    } else if (diff < 3600) {
        return `${Math.floor(diff / 60)}m ago`;
    } else if (diff < 86400) {
        return `${Math.floor(diff / 3600)}h ago`;
    } else {
        return date.toLocaleDateString();
    }
}

function truncateId(id) {
    if (!id) return '-';
    if (id.length <= 12) return id;
    return id.substring(0, 8) + '...';
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// Handle visibility changes to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        refreshData();
        startAutoRefresh();
    }
});
