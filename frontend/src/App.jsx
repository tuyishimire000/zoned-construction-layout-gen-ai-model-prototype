import React, { useState, useEffect, useRef } from 'react';
import './index.css';

function App() {
  const [sessionId, setSessionId] = useState(null);
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
      setSessionId(data.session_id);
      
      // Update messages from server
      setMessages(data.messages);
      
      // Update floorplan view
      if (data.analysis) {
        setResult(data.analysis);
      }
    } catch (err) {
      console.error(err);
      setError(err.message);
      // Remove the optimistic user message on failure, or add an error message
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}. Please try again.` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <header>
        <h1>AI Architect Studio</h1>
        <p>Chat with your AI to dynamically design and refine your building.</p>
      </header>

      <div className="layout">
        {/* Left Panel: Chat Interface */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '600px' }}>
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
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          
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
                  key={result.floor_plan_base64.substring(0, 50)} // force re-render animation if needed
                />
              </div>
              
              {result.compliance && (
                <div style={{marginTop: '1.5rem'}}>
                  <h4 style={{marginBottom: '0.5rem'}}>Zoning Compliance</h4>
                  <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
                    <span className={`status-badge ${result.compliance.status === 'PASS' ? 'pass' : 'fail'}`}>
                      {result.compliance.status === 'PASS' ? '✓ Passed' : '✕ Issues Found'}
                    </span>
                    {result.compliance.metrics?.plot_coverage && (
                      <span className="status-badge" style={{background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)'}}>
                        Coverage: {result.compliance.metrics.plot_coverage.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
