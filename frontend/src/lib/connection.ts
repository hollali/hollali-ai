export interface BackendConnection {
  baseUrl: string;
}

export async function getBackendConnection(): Promise<BackendConnection> {
  const developmentApi = import.meta.env.VITE_HOLLALI_API_URL || "http://127.0.0.1:8765";
  return { baseUrl: import.meta.env.DEV ? developmentApi : window.location.origin };
}
