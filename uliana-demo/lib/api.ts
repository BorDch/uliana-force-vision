export function csrfToken() {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find((row) => row.startsWith("uliana_csrf="))?.split("=").slice(1).join("=") ?? "";
}

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRF-Token", csrfToken());
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}
