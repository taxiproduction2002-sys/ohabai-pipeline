'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const [name, setName] = useState('');
  const router = useRouter();

  function handleSubmit(e) {
    e.preventDefault();
    localStorage.setItem('ohabai_logged_in', 'true');
    localStorage.setItem('ohabai_user_name', name || 'User');
    router.push('/inbox');
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Ohabai Pipeline</h1>
        <p className="login-sub">Inbox MVP — fake login</p>
        <input
          type="text"
          placeholder="Your name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit">Enter inbox</button>
      </form>
    </div>
  );
}
