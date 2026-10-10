import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  Activity, ArrowLeft, ArrowUp, AudioLines, Check, ChevronDown, ChevronsLeft, ChevronsRight,
  CircleAlert, Command, Copy, Download, Headphones, LayoutPanelLeft, LoaderCircle, Mic, MicOff, Moon,
  MoreHorizontal, Plus, Search, Settings2, SlidersHorizontal, Sparkles, Sun, Trash2, VolumeX, WifiOff, X,
} from "lucide-react";
import { getBackendConnection } from "./lib/connection";
import { HollaliApi } from "./lib/api";
import type { BackendEvent, Conversation, Message, ModelInfo, PluginInfo, Settings, VoiceSnapshot } from "./types";

const MarkdownBody = lazy(() => import("./components/MarkdownBody"));

type Page = "chat" | "voice" | "plugins" | "settings";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

function friendlyDate(value: string) {
  if (!value) return "Just now";
  const parsed = new Date(value.replace(" ", "T") + (value.endsWith("Z") ? "" : "Z"));
  return Number.isNaN(parsed.getTime()) ? "Recent" : parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function groupHistory(items: Conversation[]) {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  return items.reduce<Record<string, Conversation[]>>((groups, item) => {
    const day = item.updated_at.slice(0, 10);
    const group = day === today ? "Today" : day === yesterday ? "Yesterday" : "Earlier";
    (groups[group] ||= []).push(item);
    return groups;
  }, {});
}

function App() {
  const [api, setApi] = useState<HollaliApi>();
  const [page, setPage] = useState<Page>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [settings, setSettings] = useState<Settings>();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [voice, setVoice] = useState<VoiceSnapshot>({ state: "idle", wake_word: "Hollali", wake_listener_active: false });
  const [level, setLevel] = useState(0);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [ollamaOnline, setOllamaOnline] = useState(false);
  const [eventsOnline, setEventsOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retryText, setRetryText] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | undefined>(undefined);
  const requestRef = useRef<string | undefined>(undefined);
  const chatGenerationRef = useRef(0);
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent>();
  const [online, setOnline] = useState(() => navigator.onLine);

  const reloadHistory = useCallback(async (client: HollaliApi, query = "") => {
    setConversations(await client.conversations(query));
  }, []);

  useEffect(() => {
    let cancelled = false;
    let disposeEvents: (() => void) | undefined;
    const connect = async () => {
      try {
        const connection = await getBackendConnection();
        const client = new HollaliApi(connection);
        await client.session();
        const [health, prefs, history] = await Promise.all([client.health(), client.settings(), client.conversations()]);
        if (cancelled) return;
        setApi(client);
        setBackendOnline(true);
        setOllamaOnline(health.ollama);
        setVoice(health.voice);
        setSettings(prefs);
        setConversations(history);
        document.documentElement.dataset.theme = prefs.theme;
        disposeEvents = client.events((event: BackendEvent) => {
          if (event.type === "voice_state") setVoice((current) => ({ ...current, ...event }));
          if (event.type === "audio_level") setLevel(event.level);
          if (event.type === "transcription") setVoice((current) => ({ ...current, transcript: event.text }));
          if (event.type === "voice_response_chunk") setVoice((current) => ({ ...current, response: `${current.response || ""}${event.text}` }));
          if (event.type === "wake_word_detected") {
            setPage("voice");
            setNotice(`Wake word “${event.word}” detected`);
          }
          if (event.type === "voice_response") {
            setActiveId(event.conversation_id);
            setPage("chat");
            void client.messages(event.conversation_id).then(setMessages).catch(() => undefined);
            void reloadHistory(client);
          }
        }, setEventsOnline);
        void client.models().then((result) => setModels(result.models)).catch(() => setModels([]));
      } catch (cause) {
        if (!cancelled) {
          setBackendOnline(false);
          setConnectionError(cause instanceof Error ? cause.message : "Could not connect to Hollali.");
        }
      }
    };
    void connect();
    return () => { cancelled = true; disposeEvents?.(); };
  }, [reloadHistory]);

  useEffect(() => {
    if (!api) return;
    const timer = window.setTimeout(() => {
      void reloadHistory(api, search).catch((cause) => setError(cause.message));
    }, 160);
    return () => window.clearTimeout(timer);
  }, [api, search, reloadHistory]);

  useEffect(() => {
    if (!api) return;
    const refreshStatus = async () => {
      try {
        await api.session();
        const health = await api.health();
        setBackendOnline(true);
        setOllamaOnline(health.ollama);
        setVoice((current) => ({ ...current, ...health.voice }));
      } catch {
        setBackendOnline(false);
      }
      try {
        setModels((await api.models()).models);
      } catch {
        setModels([]);
      }
    };
    const timer = window.setInterval(() => void refreshStatus(), 12_000);
    return () => window.clearInterval(timer);
  }, [api]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault(); setSidebarOpen((open) => !open);
      }
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault(); setPage("settings");
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "m") {
        event.preventDefault();
        void setVoiceActive(voice.state === "idle" || voice.state === "error");
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [voice.state]);

  useEffect(() => {
    const handleInstall = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const handleInstalled = () => setInstallPrompt(undefined);
    window.addEventListener("beforeinstallprompt", handleInstall);
    window.addEventListener("appinstalled", handleInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", handleInstall);
      window.removeEventListener("appinstalled", handleInstalled);
    };
  }, []);

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") === "new") setActiveId(null);
    if (params.get("page") === "voice") setPage("voice");
    const conversationId = params.get("conversation");
    if (conversationId) setActiveId(conversationId);
    if (params.size > 0) window.history.replaceState({}, "", window.location.pathname);
  }, []);

  const historyGroups = useMemo(() => groupHistory(conversations), [conversations]);
  const selectedConversation = conversations.find((item) => item.id === activeId);

  async function selectConversation(item: Conversation) {
    if (!api) return;
    await abandonChat();
    setActiveId(item.id); setPage("chat"); setError("");
    try { setMessages(await api.messages(item.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load this conversation."); }
  }

  async function abandonChat() {
    const requestId = requestRef.current;
    if (api && requestId) {
      const result = await api.cancelChat(requestId).catch(() => ({ cancelled: false }));
      if (!result.cancelled) {
        await new Promise((resolve) => window.setTimeout(resolve, 80));
        await api.cancelChat(requestId).catch(() => undefined);
      }
    }
    chatGenerationRef.current += 1;
    requestRef.current = undefined;
    abortRef.current?.abort();
    abortRef.current = undefined;
    setBusy(false);
  }

  async function newChat() {
    await abandonChat();
    setActiveId(null); setMessages([]); setDraft(""); setPage("chat"); setError(""); inputRef.current?.focus();
  }

  async function sendMessage(text = draft) {
    const prompt = text.trim();
    if (!api || !prompt || busy) return;
    setDraft(""); setError(""); setRetryText(prompt); setBusy(true);
    const generation = ++chatGenerationRef.current;
    const placeholderIndex = messages.length + 1;
    setMessages((current) => [...current, { role: "user", content: prompt }, { role: "assistant", content: "" }]);
    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller; requestRef.current = requestId;
    try {
      const response = await api.streamChat(prompt, activeId, requestId, (conversationId) => {
        if (generation === chatGenerationRef.current) setActiveId(conversationId);
      }, (chunk) => {
        if (generation !== chatGenerationRef.current) return;
        setMessages((current) => current.map((message, index) => index === placeholderIndex
          ? { ...message, content: message.content + chunk } : message));
      }, controller.signal);
      if (generation !== chatGenerationRef.current) return;
      setMessages((current) => current.map((message, index) => index === placeholderIndex && !message.content
        ? { ...message, content: response } : message).filter((message, index) => index !== placeholderIndex || message.content));
      await reloadHistory(api);
    } catch (cause) {
      if (generation === chatGenerationRef.current && !controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Message failed. Try again.");
        setMessages((current) => current.filter((_, index) => index !== placeholderIndex));
      }
    } finally {
      if (requestRef.current === requestId) {
        requestRef.current = undefined; abortRef.current = undefined; setBusy(false); inputRef.current?.focus();
      }
    }
  }

  async function stopGeneration() {
    if (!api || !requestRef.current) return;
    await api.cancelChat(requestRef.current).catch(() => undefined);
  }

  async function updatePreference(changes: Partial<Settings>) {
    if (!api) return;
    try {
      const next = await api.updateSettings(changes);
      setSettings(next); document.documentElement.dataset.theme = next.theme; setNotice("Preferences saved");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save this preference."); }
  }

  async function setVoiceActive(active: boolean) {
    if (!api) return;
    try { setVoice(await api.voice(active ? "start" : "stop")); setPage("voice"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Microphone could not be started."); }
  }

  async function installApp() {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === "accepted") setInstallPrompt(undefined);
  }

  async function loadPlugins() {
    if (!api) return;
    try { setPlugins(await api.plugins()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load plugins."); }
  }

  async function deleteConversation(item: Conversation) {
    if (!api || !window.confirm(`Delete “${item.title}”?`)) return;
    try { await api.deleteConversation(item.id); if (activeId === item.id) newChat(); await reloadHistory(api); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not delete conversation."); }
  }

  async function renameConversation(item: Conversation) {
    if (!api) return;
    const title = window.prompt("Conversation name", item.title)?.trim();
    if (!title || title === item.title) return;
    try { await api.renameConversation(item.id, title); await reloadHistory(api); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not rename conversation."); }
  }

  const isDark = settings?.theme !== "light";

  if (!api && backendOnline === false) return (
    <main className="connect-screen"><div className="connect-card">
      <div className="brand-mark large"><Sparkles size={22} /></div><span className="eyebrow">LOCAL DESKTOP ASSISTANT</span>
      <h1>Hollali can’t reach its local service.</h1><p>{connectionError}</p>
      <p className="subtle">Start the local Hollali web service with <code>hollali-web</code>.</p>
      <button className="primary-button" onClick={() => window.location.reload()}>Try again</button>
    </div></main>
  );

  return <div className={`app-shell ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
    <aside className="sidebar" aria-label="Main navigation">
      <div className="sidebar-top">
        <button className="brand-lockup" onClick={newChat} aria-label="Hollali home"><span className="brand-mark"><Sparkles size={17} strokeWidth={2.2} /></span>{sidebarOpen && <span className="brand-name">hollali<span className="brand-dot">.</span></span>}</button>
        <button className="icon-button sidebar-collapse" aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"} onClick={() => setSidebarOpen((open) => !open)}>{sidebarOpen ? <ChevronsLeft size={17} /> : <ChevronsRight size={17} />}</button>
      </div>
      <button className="new-chat-button" onClick={newChat} title="New conversation"><Plus size={17} /><span>{sidebarOpen && "New conversation"}</span><kbd>{sidebarOpen && "⌘ K"}</kbd></button>
      {sidebarOpen && <label className="history-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" /></label>}
      <div className="nav-links">
        <button className={`nav-item ${page === "chat" ? "active" : ""}`} onClick={() => setPage("chat")} title="Chat"><LayoutPanelLeft size={17} /><span>{sidebarOpen && "Chat"}</span></button>
        <button className={`nav-item ${page === "voice" ? "active" : ""}`} onClick={() => setPage("voice")} title="Voice"><AudioLines size={17} /><span>{sidebarOpen && "Voice"}</span>{sidebarOpen && voice.state !== "idle" && <span className="live-dot" />}</button>
        <button className={`nav-item ${page === "plugins" ? "active" : ""}`} onClick={() => { setPage("plugins"); void loadPlugins(); }} title="Integrations"><Command size={17} /><span>{sidebarOpen && "Integrations"}</span></button>
      </div>
      {sidebarOpen && <div className="history-section"><div className="section-label">Recent</div><div className="history-list">
        {Object.entries(historyGroups).map(([label, items]) => <section key={label} className="history-group"><span className="history-date">{label}</span>
          {items.map((item) => <div key={item.id} className={`history-row ${item.id === activeId ? "selected" : ""}`}>
            <button className="history-title" title={item.title} onClick={() => void selectConversation(item)}>{item.title}</button>
            <details className="history-menu"><summary aria-label={`Actions for ${item.title}`}><MoreHorizontal size={15} /></summary><div className="menu-popover"><button onClick={() => void renameConversation(item)}>Rename</button><button className="danger-text" onClick={() => void deleteConversation(item)}><Trash2 size={14} /> Delete</button></div></details>
          </div>)}
        </section>)}
        {!conversations.length && <p className="empty-history">Your conversations will appear here.</p>}
      </div></div>}
      <div className="sidebar-bottom">
        <div className="connection-card" title={backendOnline ? "Python service available" : "Connecting to Python service"}><span className={`status-point ${backendOnline ? "online" : ""}`} />{sidebarOpen && <div className="connection-copy"><strong>{backendOnline ? "Local service" : "Connecting…"}</strong><span>{ollamaOnline ? "Ollama ready" : "Model unavailable"}</span></div>}{sidebarOpen && <span className={`model-mini ${ollamaOnline ? "ok" : ""}`} />}</div>
        {installPrompt && <button className="install-button" onClick={() => void installApp()} title="Install Hollali"><Download size={15} />{sidebarOpen && <span>Install app</span>}</button>}
        <button className={`nav-item settings-link ${page === "settings" ? "active" : ""}`} onClick={() => setPage("settings")} title="Settings"><Settings2 size={17} /><span>{sidebarOpen && "Settings"}</span></button>
        <button className="profile-row" onClick={() => setPage("settings")}><span className="profile-avatar">H</span>{sidebarOpen && <><span className="profile-name">Hollali</span><MoreHorizontal size={16} className="profile-more" /></>}</button>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="topbar-context">
        <button className="icon-button mobile-sidebar-toggle" aria-label="Toggle sidebar" onClick={() => setSidebarOpen((open) => !open)}><LayoutPanelLeft size={17} /></button>
        <span className="breadcrumbs"><span>{page === "chat" ? "Workspace" : page === "voice" ? "Voice" : page === "plugins" ? "Integrations" : "Settings"}</span>{page === "chat" && selectedConversation && <><span className="crumb-separator">/</span><strong>{selectedConversation.title}</strong></>}</span>
      </div><div className="topbar-actions">
        {page === "chat" && <label className="model-select"><span className={`status-point small ${ollamaOnline ? "online" : ""}`} /><select aria-label="Local model" value={settings?.llm_model || ""} onChange={(event) => void updatePreference({ llm_model: event.target.value })} disabled={!models.length}><option value="">{settings?.llm_model || "No model"}</option>{models.map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select><ChevronDown size={13} /></label>}
        {!online && <span className="offline-pill"><WifiOff size={13} />Offline</span>}
        <button className="icon-button theme-toggle" onClick={() => void updatePreference({ theme: isDark ? "light" : "dark" })} aria-label={`Switch to ${isDark ? "light" : "dark"} theme`}>{isDark ? <Sun size={16} /> : <Moon size={16} />}</button>
        {page === "chat" && <button className="top-new-button" onClick={newChat}><Plus size={15} /><span>New chat</span></button>}
      </div></header>
      <div className="page-content">
        {page === "chat" && <section className="chat-page" aria-label="Conversation">
          <div className={`conversation-scroll ${messages.length ? "has-messages" : ""}`}>
            {messages.length === 0 ? <div className="welcome-block">
              <div className="welcome-orb"><Sparkles size={20} /></div><span className="eyebrow">YOUR PRIVATE AI ASSISTANT</span><h1>Good to see you.</h1><p>Ask a question, explore an idea, or get something done.</p>
              <div className="suggestion-grid">
                <button onClick={() => void sendMessage("What can you help me with?")}><span className="suggestion-icon violet"><Sparkles size={16} /></span><span><strong>Explore Hollali</strong><small>See what your assistant can do</small></span><ArrowUp size={14} /></button>
                <button onClick={() => setPage("voice")}><span className="suggestion-icon green"><AudioLines size={16} /></span><span><strong>Talk it through</strong><small>Start a hands-free voice chat</small></span><ArrowUp size={14} /></button>
                <button onClick={() => void sendMessage("What time is it?")}><span className="suggestion-icon amber"><Activity size={16} /></span><span><strong>Quick question</strong><small>Time, date, or a calculation</small></span><ArrowUp size={14} /></button>
              </div>
            </div> : <div className="message-list">
              {messages.map((message, index) => <article key={`${index}-${message.role}`} className={`message-row ${message.role}`}>
                <div className={`message-avatar ${message.role === "assistant" ? "assistant-avatar" : "user-avatar"}`}>{message.role === "assistant" ? <Sparkles size={15} /> : "Y"}</div>
                <div className="message-body"><div className="message-meta"><strong>{message.role === "assistant" ? "Hollali" : "You"}</strong><time>{friendlyDate(message.created_at || "")}</time>{busy && index === messages.length - 1 && <span className="streaming-indicator"><span /> Writing</span>}</div>
                  {message.role === "assistant" ? <div className="markdown-content"><Suspense fallback={<p>{message.content}</p>}><MarkdownBody content={message.content} /></Suspense>{busy && index === messages.length - 1 && !message.content && <span className="typing-dots"><i /><i /><i /></span>}</div> : <p className="user-message-text">{message.content}</p>}
                  {message.role === "assistant" && message.content && <button className="copy-button" aria-label="Copy response" onClick={() => { void navigator.clipboard.writeText(message.content); setNotice("Copied to clipboard"); }}><Copy size={14} /><span>Copy</span></button>}
                </div>
              </article>)}
              {error && <div className="inline-error"><CircleAlert size={16} /><span>{error}</span><button onClick={() => void sendMessage(retryText)}>Retry</button></div>}
              <div ref={bottomRef} />
            </div>}
          </div>
          <div className="composer-wrap"><div className={`composer ${busy ? "is-busy" : ""}`}>
            <textarea ref={inputRef} rows={1} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="Message Hollali…" aria-label="Message Hollali" disabled={!api} />
            <div className="composer-actions"><div className="composer-hint"><span className="hint-dot" />{ollamaOnline ? settings?.llm_model || "Local model" : "Ollama is offline"}<span className="hint-divider">·</span>Local processing</div>
              <div className="composer-buttons"><button className="icon-button voice-shortcut" aria-label="Open voice mode" onClick={() => setPage("voice")}><Mic size={17} /></button>{busy ? <button className="send-button stop-button" onClick={() => void stopGeneration()} aria-label="Stop generating"><X size={16} /></button> : <button className="send-button" onClick={() => void sendMessage()} disabled={!draft.trim()} aria-label="Send message"><ArrowUp size={17} /></button>}</div>
            </div>
          </div><p className="composer-footnote">Hollali runs on your computer. Responses can still be inaccurate.</p></div>
        </section>}
        {page === "voice" && <VoicePage voice={voice} level={level} connected={eventsOnline} onStart={() => void setVoiceActive(true)} onStop={() => void setVoiceActive(false)} onInterrupt={() => void api?.voice("interrupt").then(setVoice).catch((cause) => setError(cause.message))} onStopSpeaking={() => void api?.voice("stop-speaking").then(setVoice).catch((cause) => setError(cause.message))} onChat={() => setPage("chat")} />}
        {page === "settings" && <SettingsPage settings={settings} models={models} ollamaOnline={ollamaOnline} onUpdate={updatePreference} />}
        {page === "plugins" && <PluginsPage plugins={plugins} onRefresh={() => void loadPlugins()} />}
      </div>
    </main>
    {notice && <div className="toast"><Check size={15} />{notice}<button aria-label="Dismiss notification" onClick={() => setNotice("")}><X size={14} /></button></div>}
    {error && page !== "chat" && <div className="toast error-toast"><CircleAlert size={15} />{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}
    <div className="sr-only" aria-live="polite">{eventsOnline ? "Voice event service connected" : "Voice event service reconnecting"}</div>
  </div>;
}

function VoicePage({ voice, level, connected, onStart, onStop, onInterrupt, onStopSpeaking, onChat }: {
  voice: VoiceSnapshot; level: number; connected: boolean; onStart: () => void; onStop: () => void; onInterrupt: () => void; onStopSpeaking: () => void; onChat: () => void;
}) {
  const active = ["listening", "processing", "responding", "speaking", "interrupted"].includes(voice.state);
  const labels: Record<VoiceSnapshot["state"], string> = { idle: "Ready when you are", listening: "Listening", processing: "Thinking through it", responding: "Putting together a response", speaking: "Speaking", interrupted: "Request interrupted", error: "Microphone needs attention" };
  const descriptions: Record<VoiceSnapshot["state"], string> = {
    idle: `Say “${voice.wake_word}” or start a voice session.`, listening: "Go ahead. Hollali is listening for your request.",
    processing: "Your request is being handled by the local assistant.", responding: "Hollali is forming a reply.",
    speaking: "Hollali is reading its reply aloud.", interrupted: "Returning to listening.", error: voice.error || "Check the configured microphone and speech recognition engine.",
  };
  return <section className="voice-page">
    <div className="voice-header"><button className="back-link" onClick={onChat}><ArrowLeft size={15} />Back to chat</button><span className={`event-status ${connected ? "connected" : ""}`}><span />{connected ? "Live connection" : "Reconnecting"}</span></div>
    <div className="voice-center"><div className={`voice-visual ${active ? "active" : ""} state-${voice.state}`} aria-label={`Voice status: ${labels[voice.state]}`}>
      <div className="voice-ring ring-one" /><div className="voice-ring ring-two" /><div className="voice-ring ring-three" /><div className="voice-disc"><AudioLines size={29} strokeWidth={1.6} /></div>
      <div className="voice-levels" aria-hidden="true">{Array.from({ length: 24 }, (_, index) => <i key={index} style={{ height: `${Math.max(2, 2 + level * (2 + 10 * (1 - Math.abs(index - 11.5) / 15)))}px` } as CSSProperties} />)}</div>
    </div>
      <span className="eyebrow voice-eyebrow">VOICE SESSION</span><h1>{labels[voice.state]}</h1><p className="voice-description">{descriptions[voice.state]}</p>
      {voice.transcript && <div className="transcript-card"><span>LIVE TRANSCRIPTION</span><p>{voice.transcript}</p></div>}
      {voice.response && ["responding", "speaking"].includes(voice.state) && <div className="transcript-card response-card"><span>HOLLALI</span><p>{voice.response}</p></div>}
      {voice.state === "error" && <div className="voice-error"><CircleAlert size={16} />{voice.error || "Audio service unavailable"}</div>}
      <div className="voice-controls">{!active ? <button className="primary-button voice-primary" onClick={onStart}><Mic size={17} />Start listening</button> : <button className="primary-button voice-primary listening-button" onClick={onStop}><MicOff size={17} />End session</button>}{["processing", "responding"].includes(voice.state) && <button className="secondary-button" onClick={onInterrupt}><X size={15} />Interrupt response</button>}{voice.state === "speaking" && <button className="secondary-button" onClick={onStopSpeaking}><VolumeX size={16} />Stop speaking</button>}</div>
      <div className="wake-note"><span className={`wake-indicator ${voice.wake_listener_active ? "ready" : ""}`} />Wake word <strong>“{voice.wake_word}”</strong> {voice.wake_listener_active ? "is active in the background" : "is starting with the local service"}</div>
      <div className="voice-privacy"><span className="privacy-lock">⌁</span>Audio is handled by your configured {voice.stt_engine || "speech"} engine.</div>
    </div>
  </section>;
}

function SettingsPage({ settings, models, ollamaOnline, onUpdate }: {
  settings?: Settings; models: ModelInfo[]; ollamaOnline: boolean; onUpdate: (changes: Partial<Settings>) => Promise<void>;
}) {
  if (!settings) return <div className="loading-page"><LoaderCircle className="spin" size={20} />Loading preferences</div>;
  return <section className="settings-page"><div className="screen-heading"><span className="eyebrow">PREFERENCES</span><h1>Settings</h1><p>Fine-tune Hollali for the way you work.</p></div>
    <div className="settings-layout"><nav className="settings-index" aria-label="Settings sections"><a href="#appearance">Appearance</a><a href="#model">Language model</a><a href="#voice-settings">Voice</a><a href="#privacy">Privacy</a></nav>
      <div className="settings-sections">
        <section id="appearance" className="settings-section"><div className="settings-section-heading"><span className="settings-icon"><Sun size={17} /></span><div><h2>Appearance</h2><p>Choose a comfortable look for your workspace.</p></div></div>
          <div className="setting-row"><div><strong>Theme</strong><span>Applies across Hollali and is saved locally.</span></div><select value={settings.theme} onChange={(event) => void onUpdate({ theme: event.target.value as Settings["theme"] })}><option value="dark">Dark</option><option value="light">Light</option></select></div>
        </section>
        <section id="model" className="settings-section"><div className="settings-section-heading"><span className="settings-icon"><Sparkles size={17} /></span><div><h2>Language model</h2><p>Inference uses the Ollama service configured on this computer.</p></div></div>
          <div className="setting-row"><div><strong>Ollama connection</strong><span>{ollamaOnline ? "Connected to your local model service." : "Ollama is not responding at the configured address."}</span></div><span className={`health-pill ${ollamaOnline ? "healthy" : "offline"}`}><i />{ollamaOnline ? "Connected" : "Offline"}</span></div>
          <div className="setting-row"><div><strong>Model</strong><span>{models.length ? `${models.length} model${models.length === 1 ? "" : "s"} installed locally.` : "No models found. Start Ollama and pull a model to continue."}</span></div><select value={settings.llm_model} onChange={(event) => void onUpdate({ llm_model: event.target.value })} disabled={!models.length}><option value={settings.llm_model}>{settings.llm_model}</option>{models.filter((model) => model.name !== settings.llm_model).map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select></div>
        </section>
        <section id="voice-settings" className="settings-section"><div className="settings-section-heading"><span className="settings-icon"><Headphones size={17} /></span><div><h2>Voice</h2><p>Use the speech services already configured for Hollali.</p></div></div>
          <div className="setting-row"><div><strong>Speech recognition</strong><span>{settings.stt_engine === "vosk" ? "Vosk runs offline on this device." : "Google Speech Recognition sends audio for transcription."}</span></div><select value={settings.stt_engine} onChange={(event) => void onUpdate({ stt_engine: event.target.value as Settings["stt_engine"] })}><option value="google">Google (online)</option><option value="vosk">Vosk (offline)</option></select></div>
          <div className="setting-row"><div><strong>Text to speech</strong><span>Uses the selected engine installed on this computer.</span></div><select value={settings.tts_engine} onChange={(event) => void onUpdate({ tts_engine: event.target.value as Settings["tts_engine"] })}><option value="piper">Piper</option><option value="espeak">espeak-ng</option><option value="pyttsx3">pyttsx3</option></select></div>
          <div className="setting-row"><div><strong>Listening timeout</strong><span>Return to idle after a pause in conversation.</span></div><select value={settings.conversation_timeout} onChange={(event) => void onUpdate({ conversation_timeout: Number(event.target.value) })}>{[5, 8, 12, 20, 30].map((seconds) => <option value={seconds} key={seconds}>{seconds} seconds</option>)}</select></div>
          <div className="setting-row"><div><strong>Wake word</strong><span>The activation phrase follows your current backend configuration.</span></div><span className="readonly-value">{settings.wake_word}</span></div>
          <div className="setting-row"><div><strong>Background listening</strong><span>Keep listening for the wake word while Hollali runs in the background.</span></div><label className="switch"><input type="checkbox" checked={settings.wake_listening} onChange={(event) => void onUpdate({ wake_listening: event.target.checked })} /><i aria-hidden="true" /></label></div>
        </section>
        <section id="privacy" className="settings-section privacy-section"><div className="settings-section-heading"><span className="settings-icon"><VolumeX size={17} /></span><div><h2>Privacy & local processing</h2><p>Hollali’s API is bound to localhost and requires an app-scoped token.</p></div></div>
          <div className="privacy-summary"><span className="privacy-check"><Check size={14} /></span><p><strong>Conversation history stays in the local database.</strong> Text goes to your configured Ollama endpoint (local by default). Integrations such as weather, calendar, Gmail, or Google speech recognition may contact their configured providers.</p></div>
          <div className="setting-row compact-row"><div><strong>Conversation storage</strong><span>Saved in the existing SQLite database under ~/.hollali.</span></div><span className="readonly-value">Local</span></div>
        </section>
        <p className="settings-note"><SlidersHorizontal size={14} />Additional integration credentials remain managed in your local .env configuration.</p>
      </div>
    </div>
  </section>;
}

function PluginsPage({ plugins, onRefresh }: { plugins: PluginInfo[]; onRefresh: () => void }) {
  return <section className="settings-page integrations-page"><div className="screen-heading"><span className="eyebrow">EXTEND YOUR WORKFLOW</span><h1>Integrations</h1><p>Capabilities discovered by Hollali’s existing Python plugin loader.</p><button className="secondary-button refresh-button" onClick={onRefresh}><Activity size={15} />Refresh</button></div>
    <div className="plugin-list">{plugins.map((plugin) => <article className="plugin-card" key={plugin.name}><span className="plugin-icon"><Command size={18} /></span><div className="plugin-copy"><strong>{plugin.name}</strong><span>Loaded by the local plugin system and available to command routing.</span></div><span className="plugin-status"><i />Available</span></article>)}
      {!plugins.length && <div className="empty-plugins"><span className="settings-icon"><Command size={19} /></span><h2>No plugins discovered</h2><p>Add a supported Python plugin to the project’s <code>plugins/</code> directory and restart Hollali.</p></div>}
    </div><div className="capability-note"><CircleAlert size={16} /><p>Plugin enable/disable and per-plugin configuration aren’t supported by the current backend interface. Plugins already load through their existing Python contract.</p></div>
  </section>;
}

export default App;
