import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
export const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

export const getSessions = (params) => api.get('/sessions', { params }).then((res) => res.data);
export const createSession = (data) => api.post('/sessions', data).then((res) => res.data);
export const updateSession = (id, data) => api.put(`/sessions/${id}`, data).then((res) => res.data);
export const deleteSession = (id) => api.delete(`/sessions/${id}`).then((res) => res.data);
export const importSessions = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/sessions/import', formData).then((res) => res.data);
};
export const getGroups = () => api.get('/sessions/groups').then((res) => res.data);
export const createGroup = (data) => api.post('/sessions/groups', data).then((res) => res.data);
export const moveSessions = (data) => api.post('/sessions/move', data).then((res) => res.data);
export const runHealthCheck = () => api.post('/sessions/health-check').then((res) => res.data);
export const getSessionLogs = (params) => api.get('/sessions/logs', { params }).then((res) => res.data);
export const getMessages = (params) => api.get('/messages', { params }).then((res) => res.data);
