import React from 'react';

export default function Privacy({ onBack }) {
  return (
    <div className="auth-layout" style={{ alignItems: 'flex-start', padding: '40px 20px', overflowY: 'auto' }}>
      <div className="card" style={{ maxWidth: '800px', width: '100%', margin: '0 auto', textAlign: 'left' }}>
        <div className="corner-bl"></div><div className="corner-br"></div>
        <button className="btn-secondary" onClick={onBack} style={{ marginBottom: '20px' }}>
          ← Back
        </button>
        <h1 style={{ marginTop: 0, color: 'var(--text-hi)' }}>Privacy Policy</h1>
        <p className="subhead">Last updated: June 2026</p>
        
        <div style={{ color: 'var(--text-lo)', lineHeight: 1.6, display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p>At AI Architect, we take your privacy seriously. This Privacy Policy explains how we collect, use, and protect your personal information.</p>
          
          <h3 style={{ color: 'var(--text-hi)', marginTop: '10px' }}>1. Information We Collect</h3>
          <p>We collect information you provide directly to us when you create an account, such as your name and email address. We also store the conversational prompts and design preferences you input into the AI Architect chat to generate your floor plans.</p>
          
          <h3 style={{ color: 'var(--text-hi)', marginTop: '10px' }}>2. How We Use Your Information</h3>
          <p>We use the information we collect to provide, maintain, and improve our services. Your chat history and generated floor plans are securely stored so you can access your past projects.</p>
          
          <h3 style={{ color: 'var(--text-hi)', marginTop: '10px' }}>3. Data Sharing</h3>
          <p>We do not sell your personal information to third parties. We may share information with trusted third-party service providers (such as hosting or database providers) who assist us in operating our platform.</p>
          
          <h3 style={{ color: 'var(--text-hi)', marginTop: '10px' }}>4. Data Security</h3>
          <p>We implement reasonable security measures to protect your personal information from unauthorized access, alteration, or disclosure.</p>
          
          <h3 style={{ color: 'var(--text-hi)', marginTop: '10px' }}>5. Your Rights</h3>
          <p>You have the right to access, correct, or delete your personal data. You can delete your account and associated data by contacting our support team.</p>
        </div>
      </div>
    </div>
  );
}
