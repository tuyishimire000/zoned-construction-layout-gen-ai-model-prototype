import React, { useState, useEffect, useRef } from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import './index.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [isLogin, setIsLogin] = useState(true);
  const [docView, setDocView] = useState(null); // 'terms', 'privacy', 'forgot-password', 'reset-password', 'verify-pending', 'verify-processing'
  const [resetToken, setResetToken] = useState(null);
  const [verifyToken, setVerifyToken] = useState(null);
  const [authSuccess, setAuthSuccess] = useState("");
  
  const [authFullName, setAuthFullName] = useState("");
  
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const rToken = params.get('reset_token');
    const vToken = params.get('verify_token');
    
    if (rToken) {
      setResetToken(rToken);
      setDocView('reset-password');
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (vToken) {
      setVerifyToken(vToken);
      setDocView('verify-processing');
      window.history.replaceState({}, document.title, window.location.pathname);
      
      // Process verification immediately
      fetch('/api/auth/verify-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: vToken })
      })
      .then(res => res.json().then(data => ({ok: res.ok, data})))
      .then(({ok, data}) => {
        if (!ok) throw new Error(data.detail || "Error verifying email");
        setAuthSuccess(data.message);
      })
      .catch(err => {
        setAuthError(err.message);
      });
    }
  }, []);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authTerms, setAuthTerms] = useState(false);
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
    setAuthError("");    try {
      const endpoint = isLogin ? '/api/auth/login' : '/api/auth/register';
      const payload = isLogin 
        ? { email: authEmail, password: authPassword }
        : { email: authEmail, password: authPassword, full_name: authFullName };
      
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      
      if (isLogin) {
        localStorage.setItem('token', data.access_token);
        setToken(data.access_token);
        setAuthPassword("");
      } else {
        // Registration successful, show verify-pending
        setAuthSuccess(data.message);
        setDocView('verify-pending');
        setAuthPassword("");
        setAuthFullName("");
      }
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const loginWithGoogle = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setAuthError("");
      try {
        const res = await fetch('/api/auth/google', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential: tokenResponse.access_token })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Google authentication failed");
        
        localStorage.setItem('token', data.access_token);
        setToken(data.access_token);
      } catch (err) {
        setAuthError(err.message);
      }
    },
    onError: () => setAuthError("Google authentication failed"),
  });

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    try {
      const res = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: authEmail })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error sending reset link");
      setAuthSuccess(data.message);
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: resetToken, new_password: authPassword })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error resetting password");
      setAuthSuccess(data.message);
      setTimeout(() => {
        setDocView(null);
        setIsLogin(true);
        setAuthPassword("");
        setAuthSuccess("");
      }, 3000);
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

  const passwordScore = authPassword ? (() => {
    let score = 0;
    if(authPassword.length >= 8) score++;
    if(/[0-9]/.test(authPassword)) score++;
    if(/[^A-Za-z0-9]/.test(authPassword)) score++;
    if(/[A-Z]/.test(authPassword) && /[a-z]/.test(authPassword)) score++;
    return score;
  })() : 0;
  const pwColors = ['#E2766B','#E8A23D','#E8A23D','#6FE3D6'];

  if (docView === 'terms') return <Terms onBack={() => setDocView(null)} />;
  if (docView === 'privacy') return <Privacy onBack={() => setDocView(null)} />;

  if (docView === 'forgot-password') {
    return (
      <div className="auth-layout">
        <div className="card" style={{ maxWidth: '400px', width: '100%', margin: '0 auto', textAlign: 'center' }}>
          <div className="corner-bl"></div><div className="corner-br"></div>
          <h2 style={{ marginTop: 0, color: 'var(--text-hi)' }}>Reset Password</h2>
          <p className="subhead" style={{ marginBottom: '24px' }}>Enter your email to receive a reset link</p>
          
          {authError && <div className="error-box">{authError}</div>}
          {authSuccess && <div className="success-box" style={{ background: 'var(--cyan-dim)', color: 'var(--cyan)', padding: '12px', borderRadius: '4px', marginBottom: '16px', fontSize: '14px' }}>{authSuccess}</div>}

          <form onSubmit={handleForgotPassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="field" style={{ textAlign: 'left' }}>
              <label>Email Address</label>
              <input 
                type="email" 
                placeholder="architect@future.com"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                required
              />
            </div>
            <button className="btn-primary" type="submit">
              Send Reset Link
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8H14M9 3L14 8L9 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </form>
          
          <p className="switch-line" style={{ marginTop: '24px' }}>
            Remembered it? <span style={{ cursor: 'pointer', color: 'var(--cyan)' }} onClick={() => { setDocView(null); setIsLogin(true); setAuthError(""); setAuthSuccess(""); }}>Back to Sign in</span>
          </p>
        </div>
      </div>
    );
  }

  if (docView === 'reset-password') {
    return (
      <div className="auth-layout">
        <div className="card" style={{ maxWidth: '400px', width: '100%', margin: '0 auto', textAlign: 'center' }}>
          <div className="corner-bl"></div><div className="corner-br"></div>
          <h2 style={{ marginTop: 0, color: 'var(--text-hi)' }}>Set New Password</h2>
          <p className="subhead" style={{ marginBottom: '24px' }}>Please enter your new password</p>
          
          {authError && <div className="error-box">{authError}</div>}
          {authSuccess && <div className="success-box" style={{ background: 'var(--cyan-dim)', color: 'var(--cyan)', padding: '12px', borderRadius: '4px', marginBottom: '16px', fontSize: '14px' }}>{authSuccess}</div>}

          <form onSubmit={handleResetPassword} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="field" style={{ textAlign: 'left' }}>
              <label>New Password</label>
              <input 
                type="password" 
                placeholder="••••••••"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                required
              />
            </div>
            <button className="btn-primary" type="submit">
              Reset Password
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8H14M9 3L14 8L9 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (docView === 'verify-pending') {
    return (
      <div className="auth-layout">
        <div className="card" style={{ maxWidth: '400px', width: '100%', margin: '0 auto', textAlign: 'center' }}>
          <div className="corner-bl"></div><div className="corner-br"></div>
          <h2 style={{ marginTop: 0, color: 'var(--text-hi)' }}>Check your email</h2>
          <p className="subhead" style={{ marginBottom: '24px' }}>
            We've sent a verification link to <strong>{authEmail}</strong>. 
            Please check your inbox (and spam folder) to activate your account.
          </p>
          
          <button className="btn-primary" onClick={() => { setDocView(null); setIsLogin(true); setAuthError(""); setAuthSuccess(""); }} style={{ width: '100%' }}>
            Return to Sign in
          </button>
        </div>
      </div>
    );
  }

  if (docView === 'verify-processing') {
    return (
      <div className="auth-layout">
        <div className="card" style={{ maxWidth: '400px', width: '100%', margin: '0 auto', textAlign: 'center' }}>
          <div className="corner-bl"></div><div className="corner-br"></div>
          <h2 style={{ marginTop: 0, color: 'var(--text-hi)' }}>Email Verification</h2>
          
          {!authSuccess && !authError && (
            <p className="subhead" style={{ marginBottom: '24px' }}>Verifying your email address...</p>
          )}
          
          {authError && (
            <>
              <div className="error-box">{authError}</div>
              <p className="switch-line" style={{ marginTop: '24px' }}>
                <span style={{ cursor: 'pointer', color: 'var(--cyan)' }} onClick={() => { setDocView(null); setIsLogin(true); setAuthError(""); setAuthSuccess(""); }}>Back to Sign in</span>
              </p>
            </>
          )}
          
          {authSuccess && (
            <>
              <div className="success-box" style={{ background: 'var(--cyan-dim)', color: 'var(--cyan)', padding: '12px', borderRadius: '4px', marginBottom: '16px', fontSize: '14px' }}>{authSuccess}</div>
              <button className="btn-primary" onClick={() => { setDocView(null); setIsLogin(true); setAuthError(""); setAuthSuccess(""); }} style={{ width: '100%' }}>
                Continue to Sign in
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-layout">
        <div className="card">
          <div className="corner-bl"></div><div className="corner-br"></div>


          <div className="auth-brandmark">
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
              <rect x="1" y="1" width="24" height="24" rx="2" stroke="#6FE3D6" strokeWidth="1.4"/>
              <path d="M5 19V11L13 5L21 11V19" stroke="#E8A23D" strokeWidth="1.4" strokeLinejoin="round"/>
              <path d="M9.5 19V13.5H16.5V19" stroke="#6FE3D6" strokeWidth="1.4"/>
            </svg>
            <span className="name">AI Architect</span>
          </div>
          <p className="subhead">
            {isLogin ? 'Welcome back — sign in to continue your build.' : 'Create an account to start your first build.'}
          </p>

          <form onSubmit={handleAuth}>
            {!isLogin && (
              <div className="field">
                <label>Full name</label>
                <input 
                  type="text" 
                  placeholder="Alice Mwangi" 
                  value={authFullName}
                  onChange={(e) => setAuthFullName(e.target.value)}
                  required
                />
              </div>
            )}
            
            <div className="field">
              <label>Email</label>
              <input 
                type="email" 
                placeholder="name@studio.com" 
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Password</label>
              <input 
                type="password" 
                placeholder={isLogin ? "••••••••" : "At least 8 characters"}
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                required
              />
              {!isLogin && (
                <div className="pw-strength">
                  <div className="pw-bars">
                    {[1,2,3,4].map(i => (
                      <div key={i} className="pw-bar" style={{ background: i <= passwordScore ? pwColors[passwordScore-1] : 'var(--line)' }}></div>
                    ))}
                  </div>
                  <span style={{ color: passwordScore > 0 ? pwColors[passwordScore-1] : 'var(--text-faint)' }}>
                    {passwordScore === 0 && "Enter password"}
                    {passwordScore === 1 && "Weak"}
                    {passwordScore === 2 && "Fair"}
                    {passwordScore === 3 && "Good"}
                    {passwordScore === 4 && "Strong"}
                  </span>
                </div>
              )}
            </div>
            
            {isLogin ? (
              <div className="row-between">
                <label><input type="checkbox" /> Remember me</label>
                <span className="switch-line"><span style={{fontSize:'12.5px', cursor: 'pointer'}} onClick={() => { setDocView('forgot-password'); setAuthError(""); setAuthSuccess(""); }}>Forgot password?</span></span>
              </div>
            ) : (
              <div className="terms-row">
                <input 
                  type="checkbox" 
                  id="terms-email" 
                  checked={authTerms}
                  onChange={(e) => setAuthTerms(e.target.checked)}
                  required
                />
                <label htmlFor="terms-email">I agree to the <a href="#" onClick={(e) => { e.preventDefault(); setDocView('terms'); }}>Terms of service</a> and <a href="#" onClick={(e) => { e.preventDefault(); setDocView('privacy'); }}>Privacy policy</a>.</label>
              </div>
            )}

            {authError && <div className="auth-error">{authError}</div>}
            
            <button type="submit" className="btn-primary">
              {isLogin ? 'Sign in' : 'Sign up'}
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8H14M9 3L14 8L9 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </form>

          <div id="google-block">
            <div className="divider"><span>or continue with</span></div>
            <button className="btn-google" onClick={() => loginWithGoogle()} type="button">
              <svg width="17" height="17" viewBox="0 0 18 18">
                <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.9c1.7-1.57 2.7-3.88 2.7-6.62z"/>
                <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.36 0-4.36-1.6-5.08-3.74H.9v2.33A8.997 8.997 0 0 0 9 18z"/>
                <path fill="#FBBC05" d="M3.92 10.68A5.4 5.4 0 0 1 3.64 9c0-.58.1-1.15.28-1.68V4.99H.9A8.997 8.997 0 0 0 0 9c0 1.45.35 2.83.9 4.01l3.02-2.33z"/>
                <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A8.59 8.59 0 0 0 9 0 8.997 8.997 0 0 0 .9 4.99l3.02 2.33C4.64 5.18 6.64 3.58 9 3.58z"/>
              </svg>
              Sign {isLogin ? 'in' : 'up'} with Google
            </button>
          </div>

          <p className="switch-line">
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
          <span>{user.full_name || user.email}<span className="role">Signed in</span></span>
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
