import type { BackendEvent, Conversation, Message, ModelInfo, PluginInfo, Settings, VoiceSnapshot } from "../types";
import type { BackendConnection } from "./connection";

export class HollaliApi {
  constructor(private readonly connection: BackendConnection) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.connection.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch {
        // Use the generic status message for non-JSON responses.
      }
      throw new Error(message);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  health() {
    return this.request<{ backend: string; ollama: boolean; model: string; voice: VoiceSnapshot }>("/api/health");
  }

  session() {
    return this.request<{ authenticated: boolean }>("/api/session");
  }

  conversations(search = "") {
    return this.request<Conversation[]>(`/api/conversations?search=${encodeURIComponent(search)}`);
  }

  messages(id: string) {
    return this.request<Message[]>(`/api/conversations/${encodeURIComponent(id)}/messages`);
  }

  createConversation(title = "New conversation") {
    return this.request<{ id: string; title: string }>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  }

  renameConversation(id: string, title: string) {
    return this.request<Conversation>(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  }

  deleteConversation(id: string) {
    return this.request<void>(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  settings() {
    return this.request<Settings>("/api/settings");
  }

  updateSettings(changes: Partial<Settings>) {
    return this.request<Settings>("/api/settings", { method: "PATCH", body: JSON.stringify(changes) });
  }

  models() {
    return this.request<{ current: string; models: ModelInfo[] }>("/api/models");
  }

  plugins() {
    return this.request<PluginInfo[]>("/api/plugins");
  }

  voice(action: "start" | "stop" | "interrupt" | "stop-speaking") {
    return this.request<VoiceSnapshot>("/api/voice", { method: "POST", body: JSON.stringify({ action }) });
  }

  async cancelChat(requestId: string) {
    return this.request<{ cancelled: boolean }>(`/api/chat/${encodeURIComponent(requestId)}/cancel`, { method: "POST" });
  }

  async streamChat(
    text: string,
    conversationId: string | null,
    requestId: string,
    onStarted: (conversationId: string) => void,
    onChunk: (chunk: string) => void,
    signal: AbortSignal,
  ) {
    const response = await fetch(`${this.connection.baseUrl}/api/chat/stream`, {
      method: "POST",
      signal,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text, conversation_id: conversationId, request_id: requestId }),
    });
    if (!response.ok || !response.body) {
      const message = await response.json().catch(() => ({}));
      throw new Error(message.detail || `Chat request failed (${response.status})`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let finalText = "";
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split("\n");
      pending = lines.pop() || "";
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line) as { type: string; text?: string; message?: string; conversation_id?: string };
        if (event.type === "start" && event.conversation_id) onStarted(event.conversation_id);
        if (event.type === "chunk" && event.text) {
          finalText += event.text;
          onChunk(event.text);
        } else if (event.type === "done") {
          finalText = event.text || finalText;
        } else if (event.type === "error") {
          throw new Error(event.message || "Hollali could not complete that request.");
        }
      }
      if (done) break;
    }
    return finalText.trim();
  }

  events(onEvent: (event: BackendEvent) => void, onStatus: (connected: boolean) => void) {
    let stopped = false;
    let socket: WebSocket | undefined;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      if (stopped) return;
      const url = new URL("/api/events", this.connection.baseUrl);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(url);
      socket.onopen = () => onStatus(true);
      socket.onmessage = (message) => {
        try {
          onEvent(JSON.parse(message.data) as BackendEvent);
        } catch {
          // Ignore malformed event payloads and keep the connection alive.
        }
      };
      socket.onclose = () => {
        onStatus(false);
        if (!stopped) reconnect = setTimeout(connect, 1800);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      stopped = true;
      if (reconnect) clearTimeout(reconnect);
      socket?.close();
    };
  }
}
