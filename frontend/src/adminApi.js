let csrf = '';
export async function session() {
  const response = await fetch('/api/admin/session', { cache: 'no-store' });
  if (!response.ok) throw new Error('Не удалось проверить сессию');
  const data = await response.json();
  csrf = data.csrf_token;
  return data.authenticated;
}
export async function adminRequest(path, data) {
  const response = await fetch(`/api/admin/${path}`, data === undefined ? { cache: 'no-store' } : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(data),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || 'Не удалось выполнить запрос');
  }
  const result = await response.json();
  if (typeof result.csrf_token === 'string') csrf = result.csrf_token;
  return result;
}
