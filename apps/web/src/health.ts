export function healthUrlFor(configuredBaseUrl: string | undefined): string {
  const baseUrl = configuredBaseUrl?.trim().replace(/\/+$/, "");

  return `${baseUrl || "/api"}/health`;
}

const healthUrl = healthUrlFor(import.meta.env.VITE_API_BASE_URL);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export async function fetchHealth(signal?: AbortSignal) {
  const response = await fetch(healthUrl, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Health request failed with HTTP ${response.status}`);
  }

  const payload: unknown = await response.json();
  if (
    !isRecord(payload) ||
    payload.status !== "ok" ||
    typeof payload.version !== "string" ||
    typeof payload.environment !== "string"
  ) {
    throw new Error("Health response does not match the published contract");
  }

  return { status: payload.status, version: payload.version, environment: payload.environment };
}
