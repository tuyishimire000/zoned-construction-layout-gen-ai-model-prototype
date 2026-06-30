import React, { useState, useEffect, useRef } from 'react';
import './index.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [isLogin, setIsLogin] = useState(true);
  
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  
  const [sessionId, setSessionId] = useState(null);
  const [sessions, setSessions] = useState([]);
  
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I am your AI Architect. What kind of building would you like to design today?' }
  ]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  
  // Loading state
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  const loadingMessages = [
    "Thinking about your request...",
    "Updating architectural parameters...",
    "Re-evaluating zoning compliance...",
    "Running physics layout engine...",
    "Rendering new blueprints..."
  ];

  // Auth Effects
  useEffect(() => {
    if (token) {
      fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(res => {
        if (!res.ok) throw new Error("Invalid token");
        return res.json();
      })
      .then(data => {
        setUser(data);
        fetchSessions();
      })
      .catch(() => {
        logout();
      });
    }
  }, [token]);

  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/sessions', {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (e) {
      console.error("Failed to fetch sessions");
    }
  };

  const handleAuth = async (e) => {
    e.preventDefault();
    setAuthError("");
    const endpoint = isLogin ? '/api/auth/login' : '/api/auth/register';
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername, password: authPassword })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      
      localStorage.setItem('token', data.access_token);
      setToken(data.access_token);
      setAuthPassword("");
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    setSessionId(null);
    setResult(null);
    setMessages([{ role: 'assistant', content: 'Hello! I am your AI Architect. What kind of building would you like to design today?' }]);
  };

  const loadSession = async (id) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/session/${id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        setMessages(data.messages);
        setResult(data.analysis);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const startNewSession = () => {
    setSessionId(null);
    setResult(null);
    setMessages([{ role: 'assistant', content: 'Hello! I am your AI Architect. What kind of building would you like to design today?' }]);
  };
  
  // Auto-scroll chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Cycle loading messages
  useEffect(() => {
    if (!loading) {
      setLoadingMsgIdx(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingMsgIdx((prev) => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
    }, 1500);
    return () => clearInterval(interval);
  }, [loading]);

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!inputMessage.trim() || loading) return;

    const userMessage = inputMessage.trim();
    setInputMessage("");
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ 
          session_id: sessionId,
          message: userMessage 
        }),
      });
      
      if (!response.ok) {
        let errorMsg = 'Failed to process request';
        try {
          const errorData = await response.json();
          errorMsg = errorData.detail || errorMsg;
        } catch (e) {}
        throw new Error(errorMsg);
      }
      
      const data = await response.json();
      
      if (!sessionId && data.session_id) {
         fetchSessions();
      }
      setSessionId(data.session_id);
      setMessages(data.messages);
      
      if (data.analysis) {
        setResult(data.analysis);
      }
    } catch (err) {
      console.error(err);
      setError(err.message);
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}. Please try again.` }]);
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <h1>AI Architect</h1>
            <p>{isLogin ? 'Welcome back' : 'Create your account'}</p>
          </div>
          <form onSubmit={handleAuth} className="auth-form">
            <input 
              type="text" 
              placeholder="Username" 
              value={authUsername}
              onChange={(e) => setAuthUsername(e.target.value)}
              required
            />
            <input 
              type="password" 
              placeholder="Password" 
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              required
            />
            {authError && <div className="auth-error">{authError}</div>}
            <button type="submit" className="btn auth-btn">
              {isLogin ? 'Sign In' : 'Sign Up'}
            </button>
          </form>
          <p className="auth-switch">
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <span onClick={() => setIsLogin(!isLogin)}>
              {isLogin ? 'Sign up' : 'Sign in'}
            </span>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="container app-layout">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>{user.username}</h2>
          <button className="btn sidebar-btn" onClick={startNewSession}>+ New Design</button>
        </div>
        <div className="sidebar-history">
          <h3>Recent Projects</h3>
          {sessions.map(s => (
            <div 
              key={s.id} 
              className={`history-item ${sessionId === s.id ? 'active' : ''}`}
              onClick={() => loadSession(s.id)}
            >
              <div className="history-icon">🏗️</div>
              <div className="history-text">
                Project {s.id.substring(0,6)}
                <small>{new Date(s.updated_at).toLocaleDateString()}</small>
              </div>
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <button className="btn logout-btn" onClick={logout}>Sign Out</button>
        </div>
      </aside>

      <main className="main-content">
        <header>
          <h1>AI Architect Studio</h1>
          <p>Chat with your AI to dynamically design and refine your building.</p>
        </header>

        <div className="layout">
          {/* Left Panel: Chat Interface */}
          <div className="panel chat-panel" style={{ display: 'flex', flexDirection: 'column' }}>
            <h2>Conversation</h2>
            
            <div className="message-list">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  {msg.content}
                </div>
              ))}
              
              {loading && (
                <div className="message assistant" style={{ fontStyle: 'italic', color: '#94a3b8' }}>
                  {loadingMessages[loadingMsgIdx]}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form onSubmit={handleSendMessage} className="input-area">
              <input 
                type="text" 
                value={inputMessage} 
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="e.g. Add another bedroom and a master suite..."
                disabled={loading}
              />
              <button type="submit" className="btn" disabled={loading || !inputMessage.trim()}>
                Send
              </button>
            </form>
          </div>

          {/* Right Panel: Results */}
          <div className="panel result-panel" style={{ display: 'flex', flexDirection: 'column' }}>
            
            {!result && !loading && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                <p>Your floor plan will appear here as we chat.</p>
              </div>
            )}

            {result && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem'}}>
                    <h3 style={{margin: 0}}>Schematic Floor Plan</h3>
                    <div style={{display: 'flex', gap: '8px'}}>
                        {result.dxf_base64 && (
                            <a href={result.dxf_base64} download="floorplan.dxf" className="btn" style={{backgroundColor: '#10b981', display: 'flex', alignItems: 'center', gap: '6px', padding: '0.5rem 1rem', fontSize: '0.9rem', textDecoration: 'none', color: 'white'}}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                Download CAD
                            </a>
                        )}
                    </div>
                </div>
                
                <div className="image-container" style={{ margin: 0, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'white' }}>
                  <img 
                    src={result.floor_plan_base64} 
                    alt="Floor plan" 
                    style={{ maxHeight: '100%', objectFit: 'contain' }}
                    key={result.floor_plan_base64.substring(0, 50)}
                  />
                </div>
                
                {result.compliance && (
                  <div style={{marginTop: '1.5rem'}}>
                    <h4 style={{marginBottom: '0.5rem'}}>Zoning Compliance</h4>
                    <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
                      <span className={`status-badge ${result.compliance.compliant ? 'pass' : 'fail'}`}>
                        {result.compliance.compliant ? '✓ Passed' : '✕ Issues Found'}
                      </span>
                      {result.compliance.metrics?.plot_coverage && (
                        <span className="status-badge" style={{background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)'}}>
                          Coverage: {result.compliance.metrics.plot_coverage.toFixed(1)}%
                        </span>
                      )}
                    </div>
                    {!result.compliance.compliant && result.compliance.recommendations && result.compliance.recommendations.length > 0 && (
                      <div className="issues-list" style={{ 
                        marginTop: '1rem', 
                        background: 'rgba(239, 68, 68, 0.1)', 
                        border: '1px solid rgba(239, 68, 68, 0.2)', 
                        borderRadius: '8px', 
                        padding: '1rem' 
                      }}>
                        <h5 style={{ margin: '0 0 0.5rem 0', color: '#f87171', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ fontSize: '1.2em' }}>⚠️</span> Required Fixes
                        </h5>
                        <ul style={{ margin: 0, paddingLeft: '1.5rem', color: '#fca5a5', fontSize: '0.9rem', lineHeight: '1.5' }}>
                          {result.compliance.recommendations.map((rec, i) => (
                            <li key={i} style={{ marginBottom: '0.25rem' }}>{rec}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
