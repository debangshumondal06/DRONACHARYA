async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return body;
}