/**
 * A stand-in for a configured Supabase project.
 *
 * Without this, `useAuthBootstrap` sees no client, reports "unauthenticated",
 * and the gate sends every render to the welcome screen. Mocking at the client
 * boundary keeps the real bootstrap, gate and auth-service logic under test --
 * only the network is replaced.
 *
 * Used as:
 *   jest.mock('../src/services/auth/supabaseClient', () =>
 *     require('./supabaseMock').createSupabaseMock()
 *   );
 */

export const TEST_SESSION = {
  access_token: 'test-access-token',
  refresh_token: 'test-refresh-token',
  expires_in: 3600,
  token_type: 'bearer',
  user: {
    id: 'test-user',
    email: 'person@example.test',
    phone: null,
    app_metadata: { provider: 'email' },
    user_metadata: {},
    aud: 'authenticated',
    created_at: '2026-01-01T00:00:00Z',
  },
};

/** `session: null` produces a configured-but-signed-out project. */
export function createSupabaseMock(session: unknown = TEST_SESSION) {
  const listeners: ((event: string, session: unknown) => void)[] = [];

  const supabase = {
    auth: {
      getSession: jest.fn(async () => ({ data: { session }, error: null })),
      refreshSession: jest.fn(async () => ({ data: { session }, error: null })),
      onAuthStateChange: jest.fn((handler: (event: string, session: unknown) => void) => {
        listeners.push(handler);
        return {
          data: {
            subscription: {
              unsubscribe: jest.fn(() => {
                const index = listeners.indexOf(handler);
                if (index >= 0) listeners.splice(index, 1);
              }),
            },
          },
        };
      }),
      signOut: jest.fn(async () => ({ error: null })),
      signInWithPassword: jest.fn(async () => ({ data: { session }, error: null })),
      signUp: jest.fn(async () => ({ data: { session }, error: null })),
      signInWithOtp: jest.fn(async () => ({ data: {}, error: null })),
      verifyOtp: jest.fn(async () => ({ data: { session }, error: null })),
      resetPasswordForEmail: jest.fn(async () => ({ data: {}, error: null })),
      startAutoRefresh: jest.fn(),
      stopAutoRefresh: jest.fn(),
    },
  };

  return {
    supabase,
    isAuthConfigured: () => true,
    startAuthAutoRefresh: () => () => {},
    /** Lets a test push a sign-in or sign-out event through the real handler. */
    emitAuthChange: (event: string, next: unknown) => {
      listeners.forEach((handler) => handler(event, next));
    },
  };
}
