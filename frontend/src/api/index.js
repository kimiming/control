import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
export const WS_BASE_URL =
  import.meta.env.VITE_WS_BASE_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export const login = (data) => api.post('/auth/login', data).then((res) => res.data);
export const getMe = () => api.get('/auth/me').then((res) => res.data);
export const getUsers = () => api.get('/auth/users').then((res) => res.data);
export const createUser = (data) => api.post('/auth/users', data).then((res) => res.data);
export const updateUser = (id, data) => api.put(`/auth/users/${id}`, data).then((res) => res.data);
export const changePassword = (data) => api.post('/auth/change-password', data).then((res) => res.data);

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
export const moveSessionsToAgent = (data) => api.post('/sessions/move-agent', data).then((res) => res.data);
export const moveSessionsToProxy = (data) => api.post('/sessions/move-proxy', data).then((res) => res.data);
export const disconnectSessions = (sessionIds) => api.post('/sessions/disconnect', { session_ids: sessionIds }).then((res) => res.data);
export const connectSessions = (sessionIds) => api.post('/sessions/connect', { session_ids: sessionIds }, { timeout: 0 }).then((res) => res.data);
export const runHealthCheck = () => api.post('/sessions/health-check').then((res) => res.data);
export const checkSessionBidirectional = (id) => api.post(`/sessions/${id}/bidirectional-check`, null, { timeout: 60000 }).then((res) => res.data);
export const checkAllSessionsBidirectional = (sessionIds) => api.post('/sessions/bidirectional-check', { session_ids: sessionIds }, { timeout: 0 }).then((res) => res.data);
export const scanSessionContacts = (id) => api.post(`/sessions/${id}/contacts/scan`, null, { timeout: 0 }).then((res) => res.data);
export const clearSessionContacts = (id) => api.post(`/sessions/${id}/contacts/clear`, null, { timeout: 0 }).then((res) => res.data);
export const importSessionContacts = (id, file, importLimit) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('import_limit', importLimit);
  return api.post(`/sessions/${id}/contacts/import`, formData, { timeout: 0 }).then((res) => res.data);
};
export const scanBatchSessionContacts = (sessionIds) => api.post('/sessions/contacts/scan', { session_ids: sessionIds }, { timeout: 0 }).then((res) => res.data);
export const clearBatchSessionContacts = (sessionIds) => api.post('/sessions/contacts/clear', { session_ids: sessionIds }, { timeout: 0 }).then((res) => res.data);
export const importBatchSessionContacts = (sessionIds, file, perSessionLimit) => {
  const formData = new FormData();
  formData.append('session_ids', JSON.stringify(sessionIds));
  formData.append('file', file);
  formData.append('per_session_limit', perSessionLimit);
  return api.post('/sessions/contacts/import', formData, { timeout: 0 }).then((res) => res.data);
};
export const getSessionLogs = (params) => api.get('/sessions/logs', { params }).then((res) => res.data);
export const getSessionTaskLogs = (id, params) => api.get(`/sessions/${id}/task-logs`, { params }).then((res) => res.data);
export const getMessages = (params) => api.get('/messages', { params }).then((res) => res.data);
export const getTasks = () => api.get('/tasks').then((res) => res.data);
export const getTask = (id) => api.get(`/tasks/${id}`).then((res) => res.data);
export const createTask = (data) => api.post('/tasks', data).then((res) => res.data);
export const updateTask = (id, data) => api.put(`/tasks/${id}`, data).then((res) => res.data);
export const deleteTask = (id) => api.delete(`/tasks/${id}`).then((res) => res.data);
export const executeTask = (id) => api.post(`/tasks/${id}/execute`).then((res) => res.data);
export const pauseTask = (id) => api.post(`/tasks/${id}/pause`).then((res) => res.data);
export const resumeTask = (id) => api.post(`/tasks/${id}/resume`).then((res) => res.data);
export const cancelTask = (id) => api.post(`/tasks/${id}/cancel`).then((res) => res.data);
export const retryTaskUnsent = (id) => api.post(`/tasks/${id}/retry-unsent`).then((res) => res.data);
export const requeueTaskSession = (taskId, sessionId) => api.post(`/tasks/${taskId}/sessions/${sessionId}/requeue`).then((res) => res.data);
export const getTaskActiveSessions = (id) => api.get(`/tasks/${id}/active-sessions`).then((res) => res.data);
export const getTaskSessionJobs = (id) => api.get(`/tasks/${id}/session-jobs`).then((res) => res.data);
export const getTaskLogs = (id, params) => api.get(`/tasks/${id}/logs`, { params }).then((res) => res.data);
export const exportTaskRemainingTargets = (id) => api.get(`/tasks/${id}/remaining-targets`, { responseType: 'blob' }).then((res) => ({
  blob: res.data,
  count: Number(res.headers['x-remaining-count'] || 0),
}));
export const getMaterials = (params) => api.get('/materials', { params }).then((res) => res.data);
export const createMaterial = (data) => api.post('/materials', data).then((res) => res.data);
export const updateMaterial = (id, data) => api.put(`/materials/${id}`, data).then((res) => res.data);
export const deleteMaterial = (id) => api.delete(`/materials/${id}`).then((res) => res.data);
export const batchDeleteMaterials = (ids) => api.post('/materials/batch-delete', { ids }).then((res) => res.data);
export const getMaterialGroups = () => api.get('/materials/groups').then((res) => res.data);
export const createMaterialGroup = (data) => api.post('/materials/groups', data).then((res) => res.data);
export const updateMaterialGroup = (id, data) => api.put(`/materials/groups/${id}`, data).then((res) => res.data);
export const deleteMaterialGroup = (id) => api.delete(`/materials/groups/${id}`).then((res) => res.data);
export const batchMoveMaterials = (ids, groupId) => api.post('/materials/batch-move', { ids, group_id: groupId }).then((res) => res.data);
export const importTextMaterials = (data) => api.post('/materials/import-text', data).then((res) => res.data);
export const importImageMaterials = (data) => api.post('/materials/import-images', data, { timeout: 0 }).then((res) => res.data);
export const getCustomers = (params) => api.get('/customers', { params }).then((res) => res.data);
export const getConversations = (params) => api.get('/customers/conversations', { params }).then((res) => res.data);
export const getCustomerMessages = (id, params) => api.get(`/customers/${id}/messages`, { params }).then((res) => res.data);
export const replyCustomer = (id, data) => api.post(`/customers/${id}/reply`, typeof data === 'string' ? { text: data } : data).then((res) => res.data);
export const updateCustomerFavorite = (id, isFavorite) => api.put(`/customers/${id}/favorite`, { is_favorite: isFavorite }).then((res) => res.data);
export const getCustomerProfiles = () => api.get('/customer-profiles').then((res) => res.data);
export const getCustomerProfile = (id) => api.get(`/customer-profiles/${id}`).then((res) => res.data);
export const createCustomerProfile = (data) => api.post('/customer-profiles', data).then((res) => res.data);
export const updateCustomerProfile = (id, data) => api.put(`/customer-profiles/${id}`, data).then((res) => res.data);
export const deleteCustomerProfile = (id) => api.delete(`/customer-profiles/${id}`).then((res) => res.data);
export const getSupportAgents = () => api.get('/support-agents').then((res) => res.data);
export const createSupportAgent = (data) => api.post('/support-agents', data).then((res) => res.data);
export const updateSupportAgent = (id, data) => api.put(`/support-agents/${id}`, data).then((res) => res.data);
export const deleteSupportAgent = (id) => api.delete(`/support-agents/${id}`).then((res) => res.data);
export const getProxies = () => api.get('/proxies').then((res) => res.data);
export const createProxy = (data) => api.post('/proxies', data).then((res) => res.data);
export const updateProxy = (id, data) => api.put(`/proxies/${id}`, data).then((res) => res.data);
export const deleteProxy = (id) => api.delete(`/proxies/${id}`).then((res) => res.data);
export const activateProxy = (id) => api.post(`/proxies/${id}/activate`).then((res) => res.data);
export const testProxy = (id) => api.post(`/proxies/${id}/test`).then((res) => res.data);
