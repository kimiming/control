import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getMe, login as loginApi } from '../api/index.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'));
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('auth_user');
    return raw ? JSON.parse(raw) : null;
  });
  const [loading, setLoading] = useState(Boolean(token));

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((data) => {
        setUser(data);
        localStorage.setItem('auth_user', JSON.stringify(data));
      })
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [token]);

  const login = async (values) => {
    const data = await loginApi(values);
    localStorage.setItem('auth_token', data.token);
    localStorage.setItem('auth_user', JSON.stringify(data.user));
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    setToken(null);
    setUser(null);
  };

  const value = useMemo(() => ({ token, user, loading, login, logout, setUser }), [token, user, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
