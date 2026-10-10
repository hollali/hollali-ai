export type Role = "user" | "assistant";

export interface Message {
  role: Role;
  content: string;
  created_at?: string;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface Settings {
  theme: "dark" | "light";
  stt_engine: "google" | "vosk";
  tts_engine: "piper" | "espeak" | "pyttsx3";
  conversation_timeout: number;
  llm_model: string;
  wake_word: string;
  wake_engine: string;
  wake_listening: boolean;
}

export interface VoiceSnapshot {
  state: "idle" | "listening" | "processing" | "responding" | "speaking" | "interrupted" | "error";
  wake_word: string;
  wake_listener_active: boolean;
  wake_engine?: string;
  stt_engine?: string;
  transcript?: string;
  response?: string;
  error?: string;
}

export interface ModelInfo {
  name: string;
  size: number;
  modified_at: string;
}

export interface PluginInfo {
  name: string;
  available: boolean;
  management_supported: boolean;
}

export type BackendEvent =
  | { type: "voice_state"; state: VoiceSnapshot["state"]; wake_word: string; error?: string }
  | { type: "transcription"; text: string; final: boolean }
  | { type: "audio_level"; level: number }
  | { type: "wake_word_detected"; word: string }
  | { type: "voice_response"; conversation_id: string; text: string; created_at?: string }
  | { type: "voice_response_chunk"; conversation_id: string; text: string };
