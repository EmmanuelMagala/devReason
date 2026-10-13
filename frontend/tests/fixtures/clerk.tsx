/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react';
const getToken = async () => 'fixture-session';
export function useAuth() { return {userId: 'fixture-user', isLoaded: true, isSignedIn: true, getToken}; }
export function ClerkProvider({children}: {children: ReactNode; publishableKey: string; afterSignOutUrl?: string}) { return <>{children}</>; }
export function UserButton() { return <button aria-label="Account menu" className="rounded-full bg-secondary px-3 py-2">T</button>; }
export function SignIn() { return <div>Sign in fixture</div>; }
export function SignUp() { return <div>Sign up fixture</div>; }
