import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Activity, MessageSquare, Server, ShieldAlert, BarChart2, Database,
  LogOut, Send, Power, RefreshCw, Users, CheckCircle, AlertTriangle,
  XCircle, Clock, Download, Plus, Trash2, Lock, Unlock, Layers, FileText, Zap, Play
} from 'lucide-react';
import './style.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [me, setMe] = useState(null);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('AdminPass123!');
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [authError, setAuthError] = useState('');
  
  // Navigation
  const [activeTab, setActiveTab] = useState('Overview');
  const [notice, setNotice] = useState(null);

  // Chat State
  const [rooms, setRooms] = useState([]);
  const [currentRoom, setCurrentRoom] = useState('general');
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [socketStatus, setSocketStatus] = useState('disconnected');
  const [connectedGateway, setConnectedGateway] = useState('unknown');
  const [newRoomName, setNewRoomName] = useState('');
  const [newRoomPrivate, setNewRoomPrivate] = useState(false);
  const [showRoomModal, setShowRoomModal] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Admin Monitoring Data
  const [overviewData, setOverviewData] = useState(null);
  const [gatewaysList, setGatewaysList] = useState([]);
  const [infraData, setInfraData] = useState(null);
  const [servicesData, setServicesData] = useState([]);
  const [benchmarksData, setBenchmarksData] = useState([]);
  const [logsData, setLogsData] = useState([]);
  const [logFilterType, setLogFilterType] = useState('');
  const [logFilterComp, setLogFilterComp] = useState('');

  // Dynamic Benchmark State
  const [benchClients, setBenchClients] = useState(25);
  const [benchMessages, setBenchMessages] = useState(20);
  const [benchRoom, setBenchRoom] = useState('benchmark-live');
  const [benchRunning, setBenchRunning] = useState(false);
  const [latestLiveRun, setLatestLiveRun] = useState(null);

  // Confirmation Modal
  const [confirmModal, setConfirmModal] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Unified list of all gateways merging Docker container discovery and live metrics
  const allGateways = useMemo(() => {
    const map = new Map();
    (servicesData || []).filter(s => s.is_gateway).forEach(s => {
      map.set(s.name, {
        node_name: s.name,
        instance_id: s.name,
        status: s.status === 'running' ? 'ok' : s.status,
        uptime_seconds: 0,
        requests_handled: 0,
        active_connections: 0,
        postgres: s.status === 'running' ? 'ok' : 'unavailable',
        redis: s.status === 'running' ? 'ok' : 'unavailable',
        container_id: s.container_id
      });
    });
    (gatewaysList || []).forEach(g => {
      const existing = map.get(g.node_name) || {};
      map.set(g.node_name, { ...existing, ...g });
    });
    const result = Array.from(map.values()).sort((a, b) => a.node_name.localeCompare(b.node_name));
    return result.length > 0 ? result : gatewaysList;
  }, [servicesData, gatewaysList]);

  // Helper for API calls
  const apiFetch = async (path, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers
    };
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
      localStorage.removeItem('token');
      setToken('');
      setMe(null);
      throw new Error('Session expired. Please sign in again.');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.message || `Request failed (${res.status})`);
    }
    return data;
  };

  const showNotification = (msg, type = 'info') => {
    setNotice({ msg, type, time: new Date().toLocaleTimeString() });
    setTimeout(() => setNotice(null), 6000);
  };

  // Auth Submit
  const handleAuth = async (e) => {
    e.preventDefault();
    setAuthError('');
    try {
      const endpoint = isRegisterMode ? '/api/auth/register' : '/api/auth/login';
      const data = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({ username, password })
      });
      localStorage.setItem('token', data.access_token);
      setToken(data.access_token);
      setMe({ username: data.username, role: data.role });
      setActiveTab(data.role === 'admin' ? 'Overview' : 'Chat');
      showNotification(`Welcome, ${data.username}! Signed in as ${data.role}.`, 'success');
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken('');
    setMe(null);
    if (wsRef.current) wsRef.current.close();
  };

  // Verify token on mount
  useEffect(() => {
    if (token) {
      apiFetch('/api/me')
        .then(user => {
          setMe(user);
          if (user.role !== 'admin' && activeTab !== 'Chat') {
            setActiveTab('Chat');
          }
        })
        .catch(() => {
          setToken('');
          setMe(null);
        });
    }
  }, [token]);

  // Periodic Polling for Admin Dashboards
  useEffect(() => {
    if (!me) return;

    const fetchRooms = () => {
      apiFetch('/api/rooms')
        .then(data => setRooms(data))
        .catch(() => {});
    };

    const fetchAdminStats = () => {
      if (me.role !== 'admin') return;

      // Always poll core health and gateway topology
      apiFetch('/api/admin/overview').then(setOverviewData).catch(() => {});
      apiFetch('/api/admin/gateways').then(res => setGatewaysList(res.gateways || [])).catch(() => {});
      apiFetch('/api/admin/fault/services').then(setServicesData).catch(() => {});

      // Only poll secondary tabs when active to prevent network congestion
      if (activeTab === 'Infrastructure') {
        apiFetch('/api/admin/infrastructure').then(setInfraData).catch(() => {});
      } else if (activeTab === 'Benchmarks') {
        apiFetch('/api/admin/benchmarks').then(setBenchmarksData).catch(() => {});
      } else if (activeTab === 'Logs') {
        apiFetch('/api/admin/logs?limit=50').then(setLogsData).catch(() => {});
      }
    };

    fetchRooms();
    fetchAdminStats();
    const interval = setInterval(() => {
      fetchRooms();
      fetchAdminStats();
    }, 3000);

    return () => clearInterval(interval);
  }, [me, activeTab]);

  // Chat WebSocket Connection & History
  useEffect(() => {
    if (!me || !currentRoom || !token) return;

    apiFetch(`/api/rooms/${currentRoom}/messages`)
      .then(history => {
        setMessages(history);
      })
      .catch(err => {
        showNotification(`Could not load room history: ${err.message}`, 'error');
      });

    let isSubscribed = true;
    const connectSocket = () => {
      if (!isSubscribed) return;
      setSocketStatus('connecting');

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/${currentRoom}?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setSocketStatus('connected');
      };

      ws.onclose = () => {
        if (!isSubscribed) return;
        setSocketStatus('disconnected');
        setConnectedGateway('reconnecting...');
        reconnectTimeoutRef.current = setTimeout(connectSocket, 3000);
      };

      ws.onerror = () => {
        if (!isSubscribed) return;
        setSocketStatus('disconnected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'connected') {
            setConnectedGateway(data.instance_id || 'gateway');
          } else if (data.type === 'ack') {
            setMessages(prev => {
              if (prev.some(m => m.id === data.message.id)) return prev;
              return [...prev, data.message];
            });
          } else if (data.type === 'message') {
            setMessages(prev => {
              if (prev.some(m => m.id === data.message.id)) return prev;
              return [...prev, data.message];
            });
          } else if (data.type === 'error') {
            showNotification(`Chat Error: ${data.message}`, 'error');
          }
        } catch (e) {
          console.error(e);
        }
      };
    };

    connectSocket();

    return () => {
      isSubscribed = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [me, currentRoom, token]);

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!draft.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ content: draft.trim() }));
    setDraft('');
  };

  const handleCreateRoom = async (e) => {
    e.preventDefault();
    const name = newRoomName.trim().toLowerCase();
    if (!name) return;
    try {
      const created = await apiFetch('/api/rooms', {
        method: 'POST',
        body: JSON.stringify({ name, is_private: newRoomPrivate })
      });
      setRooms(prev => [...prev.filter(r => r.name !== created.name), created]);
      setCurrentRoom(created.name);
      setNewRoomName('');
      setNewRoomPrivate(false);
      setShowRoomModal(false);
      showNotification(`Room #${created.name} created successfully!`, 'success');
    } catch (err) {
      showNotification(err.message, 'error');
    }
  };

  // Fault Control Action
  const executeFaultAction = async (service, action) => {
    setActionLoading(true);
    try {
      const res = await apiFetch(`/api/admin/fault/services/${service}/${action}`, { method: 'POST' });
      showNotification(`Operation ${action.toUpperCase()} on '${service}' executed successfully (${res.duration_ms || 0}ms)`, 'success');
      const updated = await apiFetch('/api/admin/fault/services');
      setServicesData(updated);
      const gwRes = await apiFetch('/api/admin/gateways');
      setGatewaysList(gwRes.gateways || []);
    } catch (err) {
      showNotification(`Fault injection error: ${err.message}`, 'error');
    } finally {
      setActionLoading(false);
      setConfirmModal(null);
    }
  };

  // Dynamic Scale Out: Add Gateway Node
  const handleScaleOutGateway = async () => {
    setActionLoading(true);
    showNotification('Scaling out cluster: provisioning and starting new gateway node...', 'info');
    try {
      const res = await apiFetch('/api/admin/gateways/scale', { method: 'POST' });
      showNotification(`Node '${res.node_name}' spawned and added to Nginx load balancing!`, 'success');
      // Refresh cluster
      const gwRes = await apiFetch('/api/admin/gateways');
      setGatewaysList(gwRes.gateways || []);
      const svcs = await apiFetch('/api/admin/fault/services');
      setServicesData(svcs);
    } catch (err) {
      showNotification(`Scale out failed: ${err.message}`, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  // Dynamic Scale In: Decommission Gateway Node
  const handleDecommissionGateway = async (nodeName) => {
    setActionLoading(true);
    showNotification(`Decommissioning node '${nodeName}' from cluster...`, 'info');
    try {
      await apiFetch(`/api/admin/gateways/${nodeName}`, { method: 'DELETE' });
      showNotification(`Node '${nodeName}' safely removed and Nginx upstreams updated!`, 'success');
      const gwRes = await apiFetch('/api/admin/gateways');
      setGatewaysList(gwRes.gateways || []);
      const svcs = await apiFetch('/api/admin/fault/services');
      setServicesData(svcs);
    } catch (err) {
      showNotification(`Decommission failed: ${err.message}`, 'error');
    } finally {
      setActionLoading(false);
      setConfirmModal(null);
    }
  };

  // Stack Action
  const executeStackAction = async (action) => {
    setActionLoading(true);
    try {
      if (action === 'start') {
        await apiFetch('/api/recovery/start', { method: 'POST' });
        showNotification('Stack recovery initiated! All services starting.', 'success');
      } else {
        await apiFetch(`/api/admin/fault/stack/${action}`, { method: 'POST' });
        showNotification(`Stack ${action.toUpperCase()} initiated!`, 'warning');
      }
      setTimeout(async () => {
        try {
          const s = await apiFetch('/api/admin/fault/services');
          setServicesData(s);
          const gwRes = await apiFetch('/api/admin/gateways');
          setGatewaysList(gwRes.gateways || []);
        } catch (e) {}
      }, 2000);
    } catch (err) {
      showNotification(`Stack action error: ${err.message}`, 'error');
    } finally {
      setActionLoading(false);
      setConfirmModal(null);
    }
  };

  // Dynamic Live Benchmark Run
  const handleRunLiveBenchmark = async (e) => {
    e.preventDefault();
    setBenchRunning(true);
    showNotification(`Starting live stress test with ${benchClients} concurrent clients (${benchClients * benchMessages} msgs)...`, 'info');
    try {
      const runRes = await apiFetch('/api/admin/benchmarks/run', {
        method: 'POST',
        body: JSON.stringify({
          clients: parseInt(benchClients),
          messages_per_client: parseInt(benchMessages),
          room: benchRoom
        })
      });
      setLatestLiveRun(runRes);
      setBenchmarksData(prev => [runRes, ...prev]);
      showNotification(`Benchmark completed! Throughput: ${runRes.results.throughput_msg_per_sec} msg/s (P95: ${runRes.results.p95_latency_ms}ms)`, 'success');
    } catch (err) {
      showNotification(`Benchmark execution failed: ${err.message}`, 'error');
    } finally {
      setBenchRunning(false);
    }
  };

  // Login Screen
  if (!me) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="brand-header">
            <div className="brand-icon">⚡</div>
            <h2>SocketScale</h2>
            <p className="subtitle">Elastic Fault-Tolerant Pub/Sub WebSocket Gateway</p>
          </div>

          <div className="auth-tabs">
            <button
              className={`auth-tab ${!isRegisterMode ? 'active' : ''}`}
              onClick={() => { setIsRegisterMode(false); setAuthError(''); }}
            >
              Sign In
            </button>
            <button
              className={`auth-tab ${isRegisterMode ? 'active' : ''}`}
              onClick={() => { setIsRegisterMode(true); setAuthError(''); }}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleAuth} className="auth-form">
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                required
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Enter username"
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter password"
              />
            </div>

            {authError && <div className="error-banner">{authError}</div>}

            <button type="submit" className="btn-primary w-full">
              {isRegisterMode ? 'Register & Continue' : 'Sign In'}
            </button>
          </form>

          <div className="demo-credentials">
            <strong>Pre-configured Demo Accounts:</strong>
            <ul>
              <li><code>admin</code> / <code>AdminPass123!</code> (Admin)</li>
              <li><code>piyush</code> / <code>UserPass123!</code> (User)</li>
              <li><code>mahek</code> / <code>UserPass123!</code> (User)</li>
            </ul>
          </div>
        </div>
      </div>
    );
  }

  // Navigation Items
  const navItems = me.role === 'admin'
    ? [
        { id: 'Overview', label: 'Admin Overview', icon: Activity },
        { id: 'Chat', label: 'User Chat', icon: MessageSquare },
        { id: 'Gateways', label: `Gateway Nodes (${allGateways.length}-Cluster)`, icon: Server },
        { id: 'Infrastructure', label: 'Infrastructure', icon: Layers },
        { id: 'FaultLab', label: 'Fault Tolerance Lab', icon: ShieldAlert },
        { id: 'Benchmarks', label: 'Dynamic Benchmarks', icon: BarChart2 },
        { id: 'Logs', label: 'System Logs', icon: FileText }
      ]
    : [
        { id: 'Chat', label: 'Live Chat', icon: MessageSquare }
      ];

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon small">⚡</div>
          <div>
            <div className="brand-title">SocketScale</div>
            <div className="brand-badge">Elastic Cluster</div>
          </div>
        </div>

        <div className="user-profile-badge">
          <div className="user-avatar">{me.username[0].toUpperCase()}</div>
          <div className="user-info">
            <span className="user-name">{me.username}</span>
            <span className={`user-role ${me.role}`}>{me.role.toUpperCase()}</span>
          </div>
        </div>

        <nav className="nav-menu">
          {navItems.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-button ${activeTab === item.id ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="nav-button logout" onClick={handleLogout}>
            <LogOut size={18} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-viewport">
        {/* Top Header */}
        <header className="top-header">
          <div>
            <span className="header-eyebrow">CLUSTER / {activeTab.toUpperCase()}</span>
            <h1 className="header-title">
              {navItems.find(i => i.id === activeTab)?.label || activeTab}
            </h1>
          </div>

          <div className="header-status-area">
            {activeTab === 'Chat' ? (
              <div className="gateway-indicator">
                <span className={`status-dot ${socketStatus === 'connected' ? 'green' : 'amber'}`}></span>
                <span>WS: <strong>{socketStatus}</strong> via <code>{connectedGateway}</code></span>
              </div>
            ) : (
              <div className="gateway-indicator">
                <span className="status-dot green"></span>
                <span>{allGateways.length} Gateway Nodes</span>
              </div>
            )}
            <button className="btn-secondary btn-icon" onClick={() => window.location.reload()} title="Refresh Page">
              <RefreshCw size={15} />
            </button>
          </div>
        </header>

        {/* Global Notice Toast */}
        {notice && (
          <div className={`notification-toast ${notice.type}`}>
            <span>{notice.msg}</span>
            <small>{notice.time}</small>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 1: OVERVIEW */}
        {/* ========================================================= */}
        {activeTab === 'Overview' && (
          <div className="view-container">
            <div className="kpi-grid">
              <div className="kpi-card">
                <div className="kpi-icon"><Users size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Registered Users</span>
                  <span className="kpi-value">{overviewData?.users ?? '—'}</span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><MessageSquare size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Persisted Messages</span>
                  <span className="kpi-value">{overviewData?.messages ?? '—'}</span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><Activity size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Cluster Active WS</span>
                  <span className="kpi-value">{overviewData?.active_connections ?? '0'}</span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><Database size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Pending Outbox</span>
                  <span className={`kpi-value ${(overviewData?.outbox_pending || 0) > 0 ? 'amber' : 'green'}`}>
                    {overviewData?.outbox_pending ?? '0'}
                  </span>
                </div>
              </div>
            </div>

            {/* Dynamic Gateway Nodes Grid */}
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3>Active Cluster Gateway Nodes & Infrastructure</h3>
                  <span className="section-desc">Real-time telemetry across all dynamically scaled gateway nodes</span>
                </div>
                <button
                  className="btn-primary btn-sm"
                  onClick={handleScaleOutGateway}
                  disabled={actionLoading}
                >
                  <Plus size={15} /> Add Gateway Node
                </button>
              </div>

              <div className="nodes-grid">
                {allGateways.map(g => (
                  <div key={g.node_name} className={`node-box ${g.status === 'ok' ? 'healthy' : 'failed'}`}>
                    <div className="node-title"><Server size={18} /> {g.node_name.toUpperCase()}</div>
                    <div className="node-status">{g.status?.toUpperCase()}</div>
                    <div className="node-meta">Connections: <strong>{g.active_connections ?? 0}</strong></div>
                    <div className="node-meta">Requests: <strong>{g.requests_handled ?? 0}</strong></div>
                    <div className="node-meta">Uptime: <strong>{g.uptime_seconds ? `${Math.round(g.uptime_seconds)}s` : '0s'}</strong></div>
                  </div>
                ))}

                <div className={`node-box ${overviewData?.redis === 'ok' ? 'healthy' : 'failed'}`}>
                  <div className="node-title"><Activity size={18} /> Redis Pub/Sub</div>
                  <div className="node-status">{overviewData?.redis?.toUpperCase() ?? 'OFFLINE'}</div>
                  <div className="node-meta">Cross-node real-time relay</div>
                </div>

                <div className={`node-box ${overviewData?.postgres === 'ok' ? 'healthy' : 'failed'}`}>
                  <div className="node-title"><Database size={18} /> PostgreSQL 16</div>
                  <div className="node-status">{overviewData?.postgres?.toUpperCase() ?? 'OFFLINE'}</div>
                  <div className="node-meta">ACID Persistence & Outbox</div>
                </div>

                <div className={`node-box ${overviewData?.worker === 'ok' ? 'healthy' : 'failed'}`}>
                  <div className="node-title"><Layers size={18} /> Outbox Worker</div>
                  <div className="node-status">{overviewData?.worker?.toUpperCase() ?? 'OFFLINE'}</div>
                  <div className="node-meta">Durable background queue</div>
                </div>
              </div>
            </div>

            {/* Quick Summary Panels */}
            <div className="two-col-grid">
              <div className="section-card">
                <div className="section-header">
                  <h3>Recent Operational Events</h3>
                  <button className="btn-link" onClick={() => setActiveTab('Logs')}>View all logs</button>
                </div>
                <div className="recent-logs-list">
                  {(logsData.slice(0, 5)).map(log => (
                    <div key={log.id} className="log-row-compact">
                      <span className={`log-badge ${log.severity.toLowerCase()}`}>{log.severity}</span>
                      <span className="log-comp">{log.component}</span>
                      <span className="log-text">{log.message}</span>
                      <span className="log-time">{new Date(log.created_at).toLocaleTimeString()}</span>
                    </div>
                  ))}
                  {logsData.length === 0 && <p className="muted">No event logs recorded yet.</p>}
                </div>
              </div>

              <div className="section-card">
                <div className="section-header">
                  <h3>Latest Benchmark Summary</h3>
                  <button className="btn-link" onClick={() => setActiveTab('Benchmarks')}>Run load test</button>
                </div>
                {benchmarksData.length > 0 ? (
                  <div className="benchmark-summary-box">
                    <div className="bench-stat-row">
                      <span>Latest Test:</span>
                      <strong>{benchmarksData[0].name}</strong>
                    </div>
                    <div className="bench-stat-row">
                      <span>Throughput:</span>
                      <strong>{benchmarksData[0].results.throughput_msg_per_sec || 0} msgs/sec</strong>
                    </div>
                    <div className="bench-stat-row">
                      <span>P95 Latency:</span>
                      <strong>{benchmarksData[0].results.p95_latency_ms || 0} ms</strong>
                    </div>
                    <div className="bench-stat-row">
                      <span>Total Acknowledged:</span>
                      <strong>{benchmarksData[0].results.acknowledged || 0} / {benchmarksData[0].total_messages}</strong>
                    </div>
                  </div>
                ) : (
                  <p className="muted">No benchmarks saved yet. Use the Benchmarks page to run a dynamic performance test.</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 2: LIVE CHAT */}
        {/* ========================================================= */}
        {activeTab === 'Chat' && (
          <div className="chat-container">
            <div className="chat-rooms-pane">
              <div className="pane-header">
                <h3>Chat Rooms</h3>
                <button
                  className="btn-primary btn-sm"
                  onClick={() => setShowRoomModal(true)}
                  title="Create New Room"
                >
                  <Plus size={16} /> New
                </button>
              </div>

              <div className="rooms-list">
                {rooms.map(r => (
                  <button
                    key={r.name}
                    className={`room-item-btn ${currentRoom === r.name ? 'active' : ''}`}
                    onClick={() => setCurrentRoom(r.name)}
                  >
                    <span className="room-icon">
                      {r.is_private ? <Lock size={14} /> : '#'}
                    </span>
                    <span className="room-name">{r.name}</span>
                  </button>
                ))}
              </div>

              <div className="room-pane-footer">
                <small className="muted">
                  Active Node: <strong>{connectedGateway}</strong>
                </small>
              </div>
            </div>

            <div className="chat-main-pane">
              <div className="conversation-header">
                <div className="conversation-title-area">
                  <h3>#{currentRoom}</h3>
                  <span className="conversation-desc">
                    Persistent history in PostgreSQL • Cross-cluster sync via Redis Pub/Sub
                  </span>
                </div>
                <div className="conversation-status">
                  <span className={`status-pill ${socketStatus === 'connected' ? 'green' : 'amber'}`}>
                    {socketStatus}
                  </span>
                </div>
              </div>

              <div className="messages-scroll-area">
                {messages.length === 0 ? (
                  <div className="empty-chat-placeholder">
                    <MessageSquare size={36} />
                    <p>No messages in #{currentRoom} yet. Send the first message below!</p>
                  </div>
                ) : (
                  messages.map(m => {
                    const isSelf = m.sender === me.username;
                    return (
                      <div key={m.id} className={`message-bubble-row ${isSelf ? 'self' : 'other'}`}>
                        <div className="message-bubble">
                          <div className="message-meta">
                            <strong className="message-sender">{m.sender}</strong>
                            <span className="message-time">
                              {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                            <span className="message-id">#{m.id}</span>
                          </div>
                          <div className="message-content">{m.content}</div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <form onSubmit={handleSendMessage} className="message-input-form">
                <input
                  type="text"
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  placeholder={`Send a real-time message to #${currentRoom}...`}
                  className="chat-input"
                  disabled={socketStatus !== 'connected'}
                />
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={!draft.trim() || socketStatus !== 'connected'}
                >
                  <Send size={16} /> Send
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 3: GATEWAY NODES (DYNAMIC ELASTIC CLUSTER) */}
        {/* ========================================================= */}
        {activeTab === 'Gateways' && (
          <div className="view-container">
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3>Elastic Multi-Node Gateway Cluster ({allGateways.length} Nodes)</h3>
                  <span className="section-desc">
                    Dynamically add or remove gateway instances. Nginx automatically hot-reloads its upstream configuration with zero downtime, balancing traffic across all available nodes.
                  </span>
                </div>
                <button
                  className="btn-primary"
                  onClick={handleScaleOutGateway}
                  disabled={actionLoading}
                >
                  <Plus size={16} /> Scale Out: Add Gateway Node
                </button>
              </div>

              <div className="gateway-comparison-grid three-nodes">
                {allGateways.map(g => (
                  <div key={g.node_name} className="gateway-card">
                    <div className="gateway-card-header">
                      <div className="gateway-title-box">
                        <Server size={22} />
                        <h4>{g.node_name.toUpperCase()}</h4>
                      </div>
                      <div className="header-tags">
                        <span className={`status-pill ${g.status === 'ok' ? 'green' : 'amber'}`}>
                          {g.status?.toUpperCase()}
                        </span>
                      </div>
                    </div>

                    <div className="gateway-metrics-table">
                      <div className="metric-row">
                        <span>Node Identifier:</span>
                        <strong><code>{g.node_name}</code></strong>
                      </div>
                      <div className="metric-row">
                        <span>Live Uptime:</span>
                        <strong>{g.uptime_seconds ? `${Math.round(g.uptime_seconds)}s` : '0s'}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Total Requests Handled:</span>
                        <strong>{g.requests_handled ?? 0}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Active WebSocket Conns:</span>
                        <strong>{g.active_connections ?? 0}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Postgres / Redis:</span>
                        <strong className="green">
                          {g.postgres === 'ok' && g.redis === 'ok' ? 'OK / OK' : 'Degraded'}
                        </strong>
                      </div>
                    </div>

                    <div className="gateway-actions">
                      <button
                        className="btn-danger btn-sm"
                        disabled={actionLoading}
                        onClick={() => setConfirmModal({
                          title: `Crash ${g.node_name.toUpperCase()}`,
                          message: `Simulate an unexpected crash of ${g.node_name}. Nginx will transparently route traffic to surviving nodes.`,
                          onConfirm: () => executeFaultAction(g.node_name, 'stop')
                        })}
                      >
                        Crash
                      </button>
                      <button
                        className="btn-success btn-sm"
                        disabled={actionLoading}
                        onClick={() => executeFaultAction(g.node_name, 'start')}
                      >
                        Start
                      </button>
                      <button
                        className="btn-secondary btn-sm"
                        disabled={actionLoading}
                        onClick={() => executeFaultAction(g.node_name, 'restart')}
                      >
                        Restart
                      </button>
                      <button
                        className="btn-danger btn-sm btn-icon"
                        title="Decommission & Remove Node"
                        disabled={actionLoading || allGateways.length <= 1}
                        onClick={() => setConfirmModal({
                          title: `Decommission ${g.node_name.toUpperCase()}`,
                          message: `Permanently delete and remove ${g.node_name} from the cluster. Nginx will hot-reload its upstream pool.`,
                          onConfirm: () => handleDecommissionGateway(g.node_name)
                        })}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 4: INFRASTRUCTURE MONITORING */}
        {/* ========================================================= */}
        {activeTab === 'Infrastructure' && (
          <div className="view-container">
            <div className="kpi-grid">
              <div className="kpi-card">
                <div className="kpi-icon"><Database size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">PostgreSQL Database</span>
                  <span className={`kpi-value ${infraData?.postgres?.status === 'ok' ? 'green' : 'red'}`}>
                    {infraData?.postgres?.status?.toUpperCase() ?? 'OFFLINE'}
                  </span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><Activity size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Redis Pub/Sub</span>
                  <span className={`kpi-value ${infraData?.redis?.status === 'ok' ? 'green' : 'red'}`}>
                    {infraData?.redis?.status?.toUpperCase() ?? 'OFFLINE'}
                  </span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><Layers size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Outbox Worker</span>
                  <span className={`kpi-value ${infraData?.worker?.status === 'ok' ? 'green' : 'red'}`}>
                    {infraData?.worker?.status?.toUpperCase() ?? 'OFFLINE'}
                  </span>
                </div>
              </div>
              <div className="kpi-card">
                <div className="kpi-icon"><CheckCircle size={22} /></div>
                <div className="kpi-details">
                  <span className="kpi-label">Published Outbox Events</span>
                  <span className="kpi-value green">{infraData?.postgres?.published_outbox ?? 0}</span>
                </div>
              </div>
            </div>

            <div className="two-col-grid">
              <div className="section-card">
                <div className="section-header">
                  <h3>Transactional Outbox Pattern</h3>
                  <span className="section-desc">Guarantees reliable message persistence and zero loss during broker outages</span>
                </div>
                <div className="infra-detail-box">
                  <div className="bench-stat-row">
                    <span>Total Persisted Messages:</span>
                    <strong>{infraData?.postgres?.total_messages ?? 0}</strong>
                  </div>
                  <div className="bench-stat-row">
                    <span>Pending Outbox Queue:</span>
                    <strong className={(infraData?.postgres?.pending_outbox || 0) > 0 ? 'amber' : 'green'}>
                      {infraData?.postgres?.pending_outbox ?? 0}
                    </strong>
                  </div>
                  <div className="bench-stat-row">
                    <span>Successfully Published Events:</span>
                    <strong className="green">{infraData?.postgres?.published_outbox ?? 0}</strong>
                  </div>
                  <div className="bench-stat-row">
                    <span>Worker Heartbeat:</span>
                    <strong>
                      {infraData?.worker?.last_heartbeat_seconds_ago != null
                        ? `${infraData.worker.last_heartbeat_seconds_ago}s ago`
                        : 'Active'}
                    </strong>
                  </div>
                </div>
              </div>

              <div className="section-card">
                <div className="section-header">
                  <h3>Docker Service Status</h3>
                  <span className="section-desc">Container health reported by Fault Controller</span>
                </div>
                <div className="services-status-list">
                  {servicesData.map(svc => (
                    <div key={svc.name} className="service-status-row">
                      <div className="service-name-cell">
                        <span className={`status-dot ${svc.status === 'running' ? 'green' : 'amber'}`}></span>
                        <strong>socketscale-{svc.name}</strong>
                      </div>
                      <span className={`status-pill ${svc.status === 'running' ? 'green' : 'amber'}`}>
                        {svc.status}
                      </span>
                    </div>
                  ))}
                  {servicesData.length === 0 && <p className="muted">Loading service container states...</p>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 5: FAULT TOLERANCE LAB (DYNAMICALLY INCLUDES ALL NODES) */}
        {/* ========================================================= */}
        {activeTab === 'FaultLab' && (
          <div className="view-container">
            <div className="alert-box warning">
              <AlertTriangle size={20} />
              <div>
                <strong>Fault Injection Warning:</strong> These controls manipulate actual Docker containers on your machine. You can crash any individual gateway node, crash all gateways together, or stop Redis to test outbox queueing.
              </div>
            </div>

            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3>Component Fault Injection Matrix</h3>
                  <span className="section-desc">Simulate independent component crashes and verify zero message loss</span>
                </div>
              </div>

              <div className="fault-matrix-grid">
                {/* Dynamically list all current gateway nodes */}
                {allGateways.map(g => (
                  <div key={g.node_name} className="fault-card">
                    <div className="fault-card-header">
                      <div>
                        <h4>{g.node_name.toUpperCase()}</h4>
                        <p className="muted">Elastic FastAPI gateway node</p>
                      </div>
                      <span className={`status-pill ${g.status === 'ok' ? 'green' : 'amber'}`}>
                        {g.status}
                      </span>
                    </div>

                    <div className="fault-card-actions">
                      <button
                        className="btn-danger btn-sm"
                        disabled={actionLoading}
                        onClick={() => setConfirmModal({
                          title: `Crash ${g.node_name.toUpperCase()}`,
                          message: `Are you sure you want to crash ${g.node_name}? This tests system resiliency and automated failover.`,
                          onConfirm: () => executeFaultAction(g.node_name, 'stop')
                        })}
                      >
                        CRASH (Stop)
                      </button>
                      <button
                        className="btn-success btn-sm"
                        disabled={actionLoading}
                        onClick={() => executeFaultAction(g.node_name, 'start')}
                      >
                        START
                      </button>
                      <button
                        className="btn-secondary btn-sm"
                        disabled={actionLoading}
                        onClick={() => executeFaultAction(g.node_name, 'restart')}
                      >
                        RESTART
                      </button>
                    </div>
                  </div>
                ))}

                {/* Crash All Gateways */}
                <div className="fault-card">
                  <div className="fault-card-header">
                    <div>
                      <h4>All Gateways Cluster</h4>
                      <p className="muted">Simulate simultaneous crash of all gateway nodes</p>
                    </div>
                  </div>
                  <div className="fault-card-actions">
                    <button
                      className="btn-danger btn-sm"
                      disabled={actionLoading}
                      onClick={() => setConfirmModal({
                        title: 'Crash All Gateways',
                        message: 'Are you sure you want to crash all gateway nodes in the cluster simultaneously?',
                        onConfirm: () => executeFaultAction('all-gateways', 'stop')
                      })}
                    >
                      CRASH ALL
                    </button>
                    <button
                      className="btn-success btn-sm"
                      disabled={actionLoading}
                      onClick={() => executeFaultAction('all-gateways', 'start')}
                    >
                      START ALL
                    </button>
                  </div>
                </div>

                {/* Core infrastructure */}
                {[
                  { id: 'redis', label: 'Redis Pub/Sub Broker', desc: 'Message broker and cross-gateway fan-out' },
                  { id: 'postgres', label: 'PostgreSQL Database', desc: 'Relational storage & transactional outbox' },
                  { id: 'worker', label: 'Outbox Background Worker', desc: 'Background queue processor to Redis' },
                  { id: 'nginx', label: 'Nginx Load Balancer', desc: 'Front-facing ingress router' }
                ].map(item => {
                  const currentSvc = servicesData.find(s => s.name === item.id);
                  const isRunning = currentSvc ? currentSvc.status === 'running' : true;

                  return (
                    <div key={item.id} className="fault-card">
                      <div className="fault-card-header">
                        <div>
                          <h4>{item.label}</h4>
                          <p className="muted">{item.desc}</p>
                        </div>
                        {currentSvc && (
                          <span className={`status-pill ${isRunning ? 'green' : 'amber'}`}>
                            {currentSvc.status}
                          </span>
                        )}
                      </div>

                      <div className="fault-card-actions">
                        <button
                          className="btn-danger btn-sm"
                          disabled={actionLoading}
                          onClick={() => setConfirmModal({
                            title: `Crash ${item.label}`,
                            message: `Are you sure you want to stop ${item.label}? This will test system resiliency.`,
                            onConfirm: () => executeFaultAction(item.id, 'stop')
                          })}
                        >
                          CRASH (Stop)
                        </button>
                        <button
                          className="btn-success btn-sm"
                          disabled={actionLoading}
                          onClick={() => executeFaultAction(item.id, 'start')}
                        >
                          START
                        </button>
                        <button
                          className="btn-secondary btn-sm"
                          disabled={actionLoading}
                          onClick={() => executeFaultAction(item.id, 'restart')}
                        >
                          RESTART
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Whole Stack Emergency Recovery */}
            <div className="section-card danger-zone">
              <div className="section-header">
                <div>
                  <h3 className="danger-text">Whole Cluster Emergency Shutdown & Restoration</h3>
                  <span className="section-desc">
                    Controlled shutdown of all containers. The Fault Controller agent stays alive to execute the recovery sequence.
                  </span>
                </div>
              </div>

              <div className="stack-actions-row">
                <button
                  className="btn-danger"
                  disabled={actionLoading}
                  onClick={() => setConfirmModal({
                    title: 'Stop Entire Cluster',
                    message: 'Are you sure you want to stop all application containers? The web UI will disconnect until you run Recovery Start.',
                    onConfirm: () => executeStackAction('stop')
                  })}
                >
                  <Power size={16} /> Cluster Emergency STOP
                </button>

                <button
                  className="btn-success"
                  disabled={actionLoading}
                  onClick={() => executeStackAction('start')}
                >
                  <RefreshCw size={16} /> Cluster Recovery START
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 6: DYNAMIC BENCHMARKS & LOAD TESTING */}
        {/* ========================================================= */}
        {activeTab === 'Benchmarks' && (
          <div className="view-container">
            <div className="section-card highlight-card">
              <div className="section-header">
                <div>
                  <h3 className="accent-title"><Zap size={20} /> Interactive Live Cluster Benchmark Runner</h3>
                  <span className="section-desc">
                    Adjust concurrent users and requests dynamically. The system spawns real WebSocket clients, distributes them across all available gateway nodes, and computes high-precision performance metrics.
                  </span>
                </div>
              </div>

              <form onSubmit={handleRunLiveBenchmark} className="dynamic-bench-form">
                <div className="bench-inputs-grid">
                  <div className="form-group">
                    <label>Concurrent Users / Clients:</label>
                    <div className="input-with-presets">
                      <input
                        type="number"
                        min="1"
                        max="100"
                        value={benchClients}
                        onChange={e => setBenchClients(Math.max(1, parseInt(e.target.value) || 1))}
                        disabled={benchRunning}
                      />
                      <div className="preset-chips">
                        {[10, 25, 50, 75, 100].map(val => (
                          <button
                            type="button"
                            key={val}
                            className={`chip ${benchClients === val ? 'active' : ''}`}
                            onClick={() => setBenchClients(val)}
                            disabled={benchRunning}
                          >
                            {val}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Requests / Messages Per User:</label>
                    <div className="input-with-presets">
                      <input
                        type="number"
                        min="1"
                        max="50"
                        value={benchMessages}
                        onChange={e => setBenchMessages(Math.max(1, parseInt(e.target.value) || 1))}
                        disabled={benchRunning}
                      />
                      <div className="preset-chips">
                        {[10, 20, 30, 50].map(val => (
                          <button
                            type="button"
                            key={val}
                            className={`chip ${benchMessages === val ? 'active' : ''}`}
                            onClick={() => setBenchMessages(val)}
                            disabled={benchRunning}
                          >
                            {val}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Target Room:</label>
                    <input
                      type="text"
                      value={benchRoom}
                      onChange={e => setBenchRoom(e.target.value)}
                      disabled={benchRunning}
                    />
                  </div>
                </div>

                <div className="bench-actions-row">
                  <div className="expected-badge">
                    <span>Total Expected Messages:</span>
                    <strong>{benchClients * benchMessages} msgs</strong>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary btn-lg"
                    disabled={benchRunning}
                  >
                    {benchRunning ? (
                      <>
                        <RefreshCw size={18} className="spin-icon" />
                        <span>Running Stress Test Across Nodes...</span>
                      </>
                    ) : (
                      <>
                        <Play size={18} />
                        <span>Run Live Benchmark</span>
                      </>
                    )}
                  </button>
                </div>
              </form>

              {latestLiveRun && (
                <div className="live-result-scorecard">
                  <h4>Live Measured Results (Run ID #{latestLiveRun.id}):</h4>
                  <div className="scorecard-grid">
                    <div className="scorecard-item">
                      <span className="sc-label">Throughput</span>
                      <span className="sc-val green">{latestLiveRun.results.throughput_msg_per_sec} msg/s</span>
                    </div>
                    <div className="scorecard-item">
                      <span className="sc-label">Mean Latency</span>
                      <span className="sc-val">{latestLiveRun.results.mean_latency_ms} ms</span>
                    </div>
                    <div className="scorecard-item">
                      <span className="sc-label">Median (P50)</span>
                      <span className="sc-val">{latestLiveRun.results.median_latency_ms} ms</span>
                    </div>
                    <div className="scorecard-item">
                      <span className="sc-label">P95 Tail Latency</span>
                      <span className="sc-val amber">{latestLiveRun.results.p95_latency_ms} ms</span>
                    </div>
                    <div className="scorecard-item">
                      <span className="sc-label">Duration</span>
                      <span className="sc-val">{latestLiveRun.results.duration_seconds}s</span>
                    </div>
                    <div className="scorecard-item">
                      <span className="sc-label">Gateway Distribution</span>
                      <span className="sc-val code-text">
                        {JSON.stringify(latestLiveRun.results.gateway_distribution || {})}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {benchmarksData.length > 0 ? (
              <div className="charts-grid-container">
                <div className="chart-card">
                  <h4>1. Message Throughput Comparison (msgs/sec)</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={benchmarksData.map(b => ({
                        name: `${b.clients}c x ${b.messages_per_client}m`,
                        throughput: b.results.throughput_msg_per_sec || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="throughput" fill="#4f46e5" name="Throughput (msg/s)" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="chart-card">
                  <h4>2. Average Latency Comparison (ms)</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={benchmarksData.map(b => ({
                        name: `${b.clients}c x ${b.messages_per_client}m`,
                        avg_latency: b.results.mean_latency_ms || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="avg_latency" fill="#06b6d4" name="Mean Latency (ms)" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="chart-card">
                  <h4>3. P95 Tail Latency Comparison (ms)</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={benchmarksData.map(b => ({
                        name: `${b.clients}c x ${b.messages_per_client}m`,
                        p95_latency: b.results.p95_latency_ms || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="p95_latency" fill="#f59e0b" name="P95 Latency (ms)" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="chart-card">
                  <h4>4. Successful vs Failed Messages</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={benchmarksData.map(b => ({
                        name: `${b.clients}c`,
                        success: b.results.acknowledged || 0,
                        failed: b.results.failed_messages || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="success" fill="#10b981" name="Acknowledged" stackId="a" />
                        <Bar dataKey="failed" fill="#ef4444" name="Failed" stackId="a" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="chart-card">
                  <h4>5. Concurrent Clients vs Throughput Curve</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={[...benchmarksData].reverse().map(b => ({
                        clients: b.clients,
                        throughput: b.results.throughput_msg_per_sec || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="clients" label={{ value: 'Concurrent Clients', position: 'insideBottom', offset: -5 }} />
                        <YAxis />
                        <Tooltip />
                        <Line type="monotone" dataKey="throughput" stroke="#6366f1" strokeWidth={3} dot={{ r: 5 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="chart-card">
                  <h4>6. Concurrent Clients vs Latency Curve (ms)</h4>
                  <div className="chart-wrapper">
                    <ResponsiveContainer width="100%" height={260}>
                      <LineChart data={[...benchmarksData].reverse().map(b => ({
                        clients: b.clients,
                        mean: b.results.mean_latency_ms || 0,
                        p95: b.results.p95_latency_ms || 0
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="clients" label={{ value: 'Concurrent Clients', position: 'insideBottom', offset: -5 }} />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="mean" stroke="#0ea5e9" strokeWidth={2} name="Mean Latency" />
                        <Line type="monotone" dataKey="p95" stroke="#f59e0b" strokeWidth={2} name="P95 Latency" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Historical Benchmark Runs Table */}
            <div className="section-card">
              <div className="section-header">
                <h3>Recorded Benchmark History</h3>
                <span className="section-desc">Downloadable CSV / JSON exports of actual recorded test metrics</span>
              </div>

              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Run Name</th>
                      <th>Clients</th>
                      <th>Msgs / Client</th>
                      <th>Total Msgs</th>
                      <th>Throughput</th>
                      <th>Mean Latency</th>
                      <th>P95 Latency</th>
                      <th>Errors</th>
                      <th>Recorded At</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {benchmarksData.map(b => (
                      <tr key={b.id}>
                        <td><strong>{b.name}</strong></td>
                        <td>{b.clients}</td>
                        <td>{b.messages_per_client}</td>
                        <td>{b.total_messages}</td>
                        <td><strong>{b.results.throughput_msg_per_sec || 0}</strong> msg/s</td>
                        <td>{b.results.mean_latency_ms || 0} ms</td>
                        <td>{b.results.p95_latency_ms || 0} ms</td>
                        <td>
                          <span className={`status-pill ${b.results.errors_count ? 'amber' : 'green'}`}>
                            {b.results.errors_count || 0}
                          </span>
                        </td>
                        <td>{new Date(b.created_at).toLocaleString()}</td>
                        <td>
                          <div className="btn-group-sm">
                            <a
                              href={`/api/admin/benchmarks/${b.id}/export?format=csv`}
                              target="_blank"
                              rel="noreferrer"
                              className="btn-secondary btn-xs"
                              title="Export CSV"
                            >
                              <Download size={12} /> CSV
                            </a>
                            <a
                              href={`/api/admin/benchmarks/${b.id}/export?format=json`}
                              target="_blank"
                              rel="noreferrer"
                              className="btn-secondary btn-xs"
                              title="Export JSON"
                            >
                              <Download size={12} /> JSON
                            </a>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {benchmarksData.length === 0 && (
                      <tr>
                        <td colSpan="10" className="text-center muted">No benchmark runs recorded in PostgreSQL yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 7: SYSTEM EVENT LOGS */}
        {/* ========================================================= */}
        {activeTab === 'Logs' && (
          <div className="view-container">
            <div className="section-card">
              <div className="section-header">
                <div>
                  <h3>System Operational Event Logs</h3>
                  <span className="section-desc">Auditable record of cluster lifecycle events, fault injections, and worker activity</span>
                </div>
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => apiFetch('/api/admin/logs?limit=100').then(setLogsData)}
                >
                  <RefreshCw size={14} /> Refresh Logs
                </button>
              </div>

              <div className="filter-bar">
                <div className="filter-group">
                  <label>Event Type:</label>
                  <select value={logFilterType} onChange={e => setLogFilterType(e.target.value)}>
                    <option value="">All Types</option>
                    <option value="SERVICE_LIFECYCLE">SERVICE_LIFECYCLE</option>
                    <option value="FAULT_INJECTION">FAULT_INJECTION</option>
                    <option value="CLUSTER_SCALE">CLUSTER_SCALE</option>
                    <option value="OUTBOX_WORKER">OUTBOX_WORKER</option>
                    <option value="BENCHMARK">BENCHMARK</option>
                    <option value="AUTH">AUTH</option>
                    <option value="ROOM">ROOM</option>
                  </select>
                </div>
                <div className="filter-group">
                  <label>Component:</label>
                  <select value={logFilterComp} onChange={e => setLogFilterComp(e.target.value)}>
                    <option value="">All Components</option>
                    <option value="cluster">cluster</option>
                    <option value="fault-agent">fault-agent</option>
                    <option value="worker">worker</option>
                    <option value="database">database</option>
                  </select>
                </div>
              </div>

              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Severity</th>
                      <th>Event Type</th>
                      <th>Component</th>
                      <th>Message</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logsData
                      .filter(l => (!logFilterType || l.event_type === logFilterType) && (!logFilterComp || l.component === logFilterComp))
                      .map(log => (
                        <tr key={log.id}>
                          <td className="timestamp-cell">
                            {new Date(log.created_at).toLocaleString()}
                          </td>
                          <td>
                            <span className={`log-badge ${log.severity.toLowerCase()}`}>
                              {log.severity}
                            </span>
                          </td>
                          <td><code>{log.event_type}</code></td>
                          <td><strong>{log.component}</strong></td>
                          <td>{log.message}</td>
                          <td className="details-cell">
                            {log.details ? <code>{log.details.slice(0, 50)}...</code> : '—'}
                          </td>
                        </tr>
                      ))}
                    {logsData.length === 0 && (
                      <tr>
                        <td colSpan="6" className="text-center muted">No operational logs recorded.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <AlertTriangle className="danger-icon" size={24} />
              <h3>{confirmModal.title}</h3>
            </div>
            <p className="modal-body">{confirmModal.message}</p>
            <div className="modal-actions">
              <button
                className="btn-secondary"
                disabled={actionLoading}
                onClick={() => setConfirmModal(null)}
              >
                Cancel
              </button>
              <button
                className="btn-danger"
                disabled={actionLoading}
                onClick={confirmModal.onConfirm}
              >
                {actionLoading ? 'Executing...' : 'Confirm & Proceed'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Room Modal */}
      {showRoomModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Create New Room</h3>
            </div>
            <form onSubmit={handleCreateRoom}>
              <div className="form-group">
                <label>Room Name</label>
                <input
                  type="text"
                  required
                  value={newRoomName}
                  onChange={e => setNewRoomName(e.target.value)}
                  placeholder="e.g. distributed-systems"
                />
                <small className="muted">Use letters, numbers, hyphens or underscores (1-40 chars)</small>
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={newRoomPrivate}
                    onChange={e => setNewRoomPrivate(e.target.checked)}
                  />
                  <span>Private Room (restricted membership)</span>
                </label>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowRoomModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Room
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const root = createRoot(document.getElementById('root'));
root.render(<App />);
