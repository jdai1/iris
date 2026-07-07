import { ReactNode, useEffect, useState } from 'react';
import type { User as FirebaseUser } from 'firebase/auth';
import { getRedirectResult, onAuthStateChanged, signInWithPopup, signInWithRedirect, signOut } from 'firebase/auth';
import { getMe, setAuthTokenProvider } from '../api';
import { auth, firebaseEnabled, googleProvider } from '../firebase';
import type { User as IrisUser } from '../types';
import { AuthScreen } from './AuthScreen';

type AuthGateProps = {
  children: (currentUser: IrisUser | null, onSignOut: () => void) => ReactNode;
};

const localUser: IrisUser = {
  id: 0,
  firebase_uid: null,
  email: 'local-dev@iris',
  display_name: 'Local dev',
  photo_url: null,
  is_admin: true,
};

export function AuthGate({ children }: AuthGateProps) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [currentUser, setCurrentUser] = useState<IrisUser | null>(null);
  const [authReady, setAuthReady] = useState(!firebaseEnabled);
  const [authError, setAuthError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);

  useEffect(() => {
    if (!auth) {
      setAuthTokenProvider(null);
      return;
    }
    getRedirectResult(auth).catch((err) => {
      setAuthError(readAuthError(err, 'Sign-in failed'));
      setSigningIn(false);
    });
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setFirebaseUser(user);
      setCurrentUser(null);
      if (user) setAuthError(null);
      setAuthReady(true);
      setSigningIn(false);
      setAuthTokenProvider(user ? () => user.getIdToken() : null);
    });
    return () => {
      unsubscribe();
      setAuthTokenProvider(null);
    };
  }, []);

  useEffect(() => {
    if (!firebaseEnabled || !firebaseUser) return;
    let cancelled = false;
    getMe()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch((err) => {
        if (!cancelled) setAuthError(err instanceof Error ? err.message : 'Could not load user');
      });
    return () => {
      cancelled = true;
    };
  }, [firebaseUser]);

  async function signIn() {
    if (!auth) return;
    setAuthError(null);
    setSigningIn(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      if (shouldUseRedirectSignIn(err)) {
        await signInWithRedirect(auth, googleProvider);
        return;
      }
      setAuthError(readAuthError(err, 'Sign-in failed'));
      setSigningIn(false);
    }
  }

  async function handleSignOut() {
    if (!auth) return;
    setAuthError(null);
    await signOut(auth);
  }

  if (!firebaseEnabled) return <>{children(localUser, () => {})}</>;
  if (!authReady) return <div className="auth-shell auth-shell-center">Loading...</div>;
  if (!firebaseUser) return <AuthScreen error={authError} signingIn={signingIn} onSignIn={signIn} />;
  if (!currentUser && !authError) return <div className="auth-shell auth-shell-center">Loading...</div>;
  if (authError) return <AuthScreen error={authError} signingIn={signingIn} onSignIn={signIn} />;
  return <>{children(currentUser, handleSignOut)}</>;
}

function shouldUseRedirectSignIn(err: unknown): boolean {
  const code = typeof err === 'object' && err && 'code' in err ? String(err.code) : '';
  return code === 'auth/popup-blocked' || code === 'auth/cancelled-popup-request';
}

function readAuthError(err: unknown, fallback: string): string {
  const code = typeof err === 'object' && err && 'code' in err ? String(err.code) : '';
  if (code === 'auth/unauthorized-domain') {
    return 'This domain is not authorized in Firebase Authentication. Add the current localhost/domain to Authorized domains.';
  }
  if (err instanceof Error) return err.message;
  return fallback;
}
