import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import App from './App';

// Mock Amplify Auth to prevent network calls
vi.mock('aws-amplify/auth', () => ({
    fetchAuthSession: vi.fn().mockResolvedValue({ tokens: { idToken: 'mock-token' } }),
    getCurrentUser: vi.fn().mockResolvedValue({ username: 'test-user', userId: '123' }),
    signInWithRedirect: vi.fn(),
    signOut: vi.fn(),
}));

// Mock Amplify UI — bypass Authenticator challenge and render children immediately
vi.mock('@aws-amplify/ui-react', () => ({
    Authenticator: ({ children }) =>
        children({ signOut: vi.fn(), user: { username: 'test-user' } }),
}));

// Mock useAuth to avoid token fetch
vi.mock('./hooks/useAuth', () => ({
    useAuth: () => ({ token: 'mock-token', loading: false }),
}));

// Mock API calls
global.fetch = vi.fn(() =>
    Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ restaurants: [] }),
    })
);

describe('App Component', () => {
    it('renders without crashing', () => {
        const { container } = render(<App />);
        expect(container.firstChild).not.toBeNull();
    });
});
