'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const loggedIn =
      typeof window !== 'undefined' &&
      localStorage.getItem('ohabai_logged_in');
    router.replace(loggedIn ? '/inbox' : '/login');
  }, [router]);
  return null;
}
