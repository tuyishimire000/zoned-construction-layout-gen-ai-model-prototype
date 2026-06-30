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
    { role: 'assistant', content: 'Hello — I\'m your AI architect. What kind of building would you like to design today?' }
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
    setMessages([{ role: 'assistant', content: 'Hello — I\'m your AI architect. What kind of building would you like to design today?' }]);
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
    setMessages([{ role: 'assistant', content: 'Hello — I\'m your AI architect. What kind of building would you like to design today?' }]);
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
          <div className="corner-bl"></div><div className="corner-br"></div>
          <div className="auth-header">
            <h1>Studio AI Architect</h1>
            <p>{isLogin ? 'Sign in to access your projects' : 'Register to start designing'}</p>
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
            <button type="submit" className="btn">
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

  const hasIssues = result?.compliance && !result.compliance.compliant && result.compliance.recommendations?.length > 0;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brandmark">
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <rect x="1" y="1" width="24" height="24" rx="2" stroke="#6FE3D6" strokeWidth="1.4"/>
            <path d="M5 19V11L13 5L21 11V19" stroke="#E8A23D" strokeWidth="1.4" strokeLinejoin="round"/>
            <path d="M9.5 19V13.5H16.5V19" stroke="#6FE3D6" strokeWidth="1.4"/>
          </svg>
          <div className="name">Studio<b>AI Architect</b></div>
        </div>

        <div className="user-chip">
          <div className="dot"></div>
          <span>{user.username}<span className="role">Signed in</span></span>
        </div>

        <button className="btn-new" onClick={startNewSession}>
          <svg viewBox="0 0 16 16" fill="none"><path d="M8 2.5V13.5M2.5 8H13.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
          New design
        </button>

        <div className="section-label">Recent projects</div>
        {sessions.map(s => (
          <div 
            key={s.id} 
            className={`project-row ${sessionId === s.id ? 'active' : ''}`}
            onClick={() => loadSession(s.id)}
          >
            <div className="project-icon">
              <svg viewBox="0 0 16 16" fill="none"><path d="M2 14V6L8 2L14 6V14" stroke="currentColor" strokeWidth="1.4"/><path d="M5 14V9H11V14" stroke="currentColor" strokeWidth="1.4"/></svg>
            </div>
            <div className="project-meta">
              <div className="name">Project {s.id.substring(0,6)}</div>
              <div className="date">{new Date(s.updated_at).toLocaleDateString('en-US', {month:'2-digit', day:'2-digit', year:'numeric'}).replace(/\//g, '.')}</div>
            </div>
          </div>
        ))}

        <div className="sidebar-foot">
          <button className="btn-signout" onClick={logout}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M6 14H3.5A1.5 1.5 0 0 1 2 12.5v-9A1.5 1.5 0 0 1 3.5 2H6M11 11.5L14.5 8L11 4.5M6 8H14.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        <div className="hero">
          <div>
            <h1>AI Architect Studio</h1>
            <p>Chat with your AI to dynamically design and refine your building, drawn to scale as you go.</p>
          </div>
          <div className="hero-tag">REV. 001 / DRAFT</div>
        </div>

        <div className="workspace">
          <div className="frame">
            <div className="corner-bl"></div><div className="corner-br"></div>
            <div className="frame-head">
              <h2>Conversation</h2>
              <span className="idx">01 / BRIEF</span>
            </div>

            <div className="thread">
              {messages.map((msg, idx) => (
                <div key={idx} className={`msg ${msg.role === 'assistant' ? 'ai' : 'user'}`}>
                  <div className="who">{msg.role === 'assistant' ? 'AI architect' : 'You'}</div>
                  <div className="bubble">{msg.content}</div>
                </div>
              ))}
              
              {loading && (
                <div className="msg ai">
                  <div className="who">AI architect</div>
                  <div className="bubble" style={{ color: 'var(--text-faint)', fontStyle: 'italic' }}>
                    {loadingMessages[loadingMsgIdx]}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="composer" onSubmit={handleSendMessage}>
              <input 
                type="text" 
                placeholder="Add another bedroom and a master suite…" 
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !inputMessage.trim()}>
                Send
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8H14M9 3L14 8L9 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            </form>
          </div>

          <div className="frame" style={{display: 'flex', flexDirection: 'column'}}>
            <div className="corner-bl"></div><div className="corner-br"></div>
            <div className="frame-head">
              <h2>Floor plan</h2>
              <span className="idx">02 / 1:100</span>
            </div>

            <div className="canvas-wrap">
              {!result && !loading && (
                <div className="empty-state">
                  <div className="icon">
                    <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><path d="M2 14V6L8 2L14 6V14" stroke="#9c9483" strokeWidth="1.3"/><path d="M5 14V9H11V14" stroke="#9c9483" strokeWidth="1.3"/></svg>
                  </div>
                  <p>Your floor plan will appear here as we chat.</p>
                  <span className="sub">AWAITING FIRST BRIEF</span>
                </div>
              )}
              
              {result && (
                <img src={result.floor_plan_base64} alt="Floor plan" key={result.floor_plan_base64.substring(0, 50)} />
              )}
              
              <span className="scale-tag">SCALE 1:100 · N ↑</span>
            </div>

            {hasIssues && (
              <div className="issues-banner">
                <h4>⚠️ Pending Revisions</h4>
                <ul>
                  {result.compliance.recommendations.map((rec, i) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="legend">
              <div className="legend-group">
                <div className="legend-item"><span className="legend-swatch" style={{background:'#6FE3D6'}}></span>Generated wall</div>
                <div className="legend-item"><span className="legend-swatch" style={{background: hasIssues ? '#E8A23D' : 'transparent'}}></span>{hasIssues ? 'Pending revision' : ''}</div>
              </div>
              
              {result?.dxf_base64 && (
                <a href={result.dxf_base64} download="floorplan.dxf" className="btn-download">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Export DXF
                </a>
              )}
            </div>
          </div>

        </div>
      </main>

    </div>
  );
}

export default App;
