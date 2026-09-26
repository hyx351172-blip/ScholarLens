import {
  BookOpen,
  ChevronDown,
  FileText,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Settings,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { toast } from 'sonner';

import { config } from '../src/config';
import { type CitationSource } from '../src/citations';
import { AnswerSources } from './AnswerSources';
import { CitationMarkdown } from './CitationMarkdown';
import { EvidenceDrawer } from './EvidenceDrawer';
import { buttonStyles } from './ui/button';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: CitationSource[];
  isStreaming?: boolean;
}

interface KnowledgeBase {
  collection_id: string;
  display_name: string;
  created_at: string;
}

interface LLMConfig {
  api_url: string;
  api_key: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
}

interface ModelOption {
  name: string;
  display: string;
  provider: string;
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  knowledgeBaseId: string;
  knowledgeBaseName: string;
  createdAt: string;
  updatedAt: string;
}

interface SelectedEvidence {
  sourceId: string;
  source: CitationSource;
}

const suggestedQuestions = [
  '总结这些论文的核心贡献，并逐条给出证据',
  '比较不同论文的方法、数据集与实验结论',
  '这些论文还存在哪些研究局限？',
];

export function Chat() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [llmConfig, setLLMConfig] = useState<LLMConfig>({
    api_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api_key: '',
    model_name: 'qwen-plus',
    temperature: 0.7,
    max_tokens: 2000,
  });
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      const [knowledgeBaseRequest, modelConfigRequest] = await Promise.allSettled([
        fetch(`${config.milvusApiUrl}/knowledge_base/list`).then((response) => {
          if (!response.ok) throw new Error(`知识库服务 ${response.status}`);
          return response.json();
        }),
        fetch(`${config.chatApiUrl}/config/default`).then((response) => {
          if (!response.ok) throw new Error(`对话服务 ${response.status}`);
          return response.json();
        }),
      ]);

      if (knowledgeBaseRequest.status === 'fulfilled') {
        const result = knowledgeBaseRequest.value;
        if (result.status === 'success' && result.knowledge_bases.length > 0) {
          setKnowledgeBases(result.knowledge_bases);
          setSelectedKB(result.knowledge_bases[0]);
        }
      } else {
        console.error('知识库加载失败:', knowledgeBaseRequest.reason);
      }

      if (modelConfigRequest.status === 'fulfilled') {
        const result = modelConfigRequest.value;
        if (result.status === 'success') {
          setLLMConfig(result.config.llm);
          setAvailableModels(result.config.available_models);
        }
      } else {
        console.error('模型配置加载失败:', modelConfigRequest.reason);
      }

      if (knowledgeBaseRequest.status === 'rejected' && modelConfigRequest.status === 'rejected') {
        toast.error('后端服务尚未启动');
      } else if (modelConfigRequest.status === 'rejected') {
        toast.warning('知识库已加载，对话服务尚未启动');
      }

      const savedSessions = localStorage.getItem('chat_sessions');
      if (savedSessions) {
        try {
          const sessions: ChatSession[] = JSON.parse(savedSessions);
          setChatSessions(
            sessions.sort(
              (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
            ),
          );
        } catch (error) {
          console.error('历史对话数据损坏:', error);
          localStorage.removeItem('chat_sessions');
        }
      }
    };

    void fetchData();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!selectedKB || messages.length === 0) return;

    const now = new Date().toISOString();
    const firstMessage = messages[0]?.content ?? '新对话';
    const sessionTitle = firstMessage.slice(0, 30) + (firstMessage.length > 30 ? '...' : '');
    let updatedSessions: ChatSession[];

    if (currentSessionId) {
      updatedSessions = chatSessions.map((session) =>
        session.id === currentSessionId ? { ...session, messages, updatedAt: now } : session,
      );
    } else {
      const newSession: ChatSession = {
        id: `session-${Date.now()}`,
        title: sessionTitle,
        messages,
        knowledgeBaseId: selectedKB.collection_id,
        knowledgeBaseName: selectedKB.display_name,
        createdAt: now,
        updatedAt: now,
      };
      setCurrentSessionId(newSession.id);
      updatedSessions = [newSession, ...chatSessions];
    }

    updatedSessions = updatedSessions.slice(0, 50);
    setChatSessions(updatedSessions);
    localStorage.setItem('chat_sessions', JSON.stringify(updatedSessions));
    // Saving is driven by message changes; session state is intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading || !selectedKB) {
      if (!selectedKB) toast.error('请先选择知识库');
      return;
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message.trim(),
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    };
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      isStreaming: true,
    };

    setMessages((previous) => [...previous, userMessage, assistantMessage]);
    setMessage('');
    setIsLoading(true);
    setSelectedEvidence(null);

    try {
      abortControllerRef.current = new AbortController();
      const response = await fetch(`${config.chatApiUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage.content,
          collection_name: selectedKB.collection_id,
          llm_config: llmConfig,
          top_k: 10,
          score_threshold: 0.1,
          use_reranker: false,
          stream: true,
          return_source: true,
          history: messages.slice(-10).map((item) => ({
            role: item.role,
            content: item.content,
          })),
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let streamBuffer = '';
      let accumulatedContent = '';
      let sources: CitationSource[] | undefined;

      const processLine = (line: string) => {
        if (!line.trim()) return;
        const data = JSON.parse(line);
        if (data.type === 'content') {
          accumulatedContent += data.data;
          setMessages((previous) => previous.map((item) =>
            item.id === assistantMessage.id ? { ...item, content: accumulatedContent } : item,
          ));
        } else if (data.type === 'sources') {
          sources = data.data;
        } else if (data.type === 'error') {
          throw new Error(data.data?.error ?? '对话服务返回错误');
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        streamBuffer += decoder.decode(value, { stream: !done });
        const lines = streamBuffer.split('\n');
        streamBuffer = lines.pop() ?? '';
        lines.forEach(processLine);
        if (done) break;
      }
      if (streamBuffer.trim()) processLine(streamBuffer);

      setMessages((previous) => previous.map((item) =>
        item.id === assistantMessage.id ? { ...item, isStreaming: false, sources } : item,
      ));
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        toast.info('对话已取消');
      } else {
        console.error('对话失败:', error);
        toast.error(error instanceof Error ? error.message : '对话失败，请稍后重试');
      }
      setMessages((previous) => previous.filter((item) => item.id !== assistantMessage.id));
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setCurrentSessionId(null);
    setSelectedEvidence(null);
    toast.success('已创建新对话');
  };

  const loadSession = (session: ChatSession) => {
    setMessages(session.messages);
    setCurrentSessionId(session.id);
    setSelectedEvidence(null);
    const knowledgeBase = knowledgeBases.find(
      (item) => item.collection_id === session.knowledgeBaseId,
    );
    if (knowledgeBase) setSelectedKB(knowledgeBase);
  };

  const deleteSession = (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    const updatedSessions = chatSessions.filter((session) => session.id !== sessionId);
    setChatSessions(updatedSessions);
    localStorage.setItem('chat_sessions', JSON.stringify(updatedSessions));
    if (currentSessionId === sessionId) handleNewChat();
  };

  const selectSource = (sourceId: string, source?: CitationSource) => {
    if (!source) {
      toast.warning(`来源 ${sourceId} 未随回答返回，已阻止错误跳转`);
      return;
    }
    setSelectedEvidence({ sourceId, source });
  };

  return (
    <div className="relative flex h-[calc(100vh-64px)] overflow-hidden bg-[#f8f8fb]">
      <aside className="hidden w-[252px] flex-col border-r border-slate-200 bg-white xl:flex">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">Workspace</p>
            <h3 className="mt-1 font-semibold text-slate-900">研究对话</h3>
          </div>
          <button
            type="button"
            onClick={handleNewChat}
            className={buttonStyles({ variant: 'secondary', size: 'sm', iconOnly: true })}
            aria-label="新建对话"
          >
            <Plus size={17} />
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {chatSessions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-sm text-slate-400">
              暂无历史对话
            </div>
          ) : chatSessions.map((session) => (
            <motion.div
              key={session.id}
              className={`group flex w-full items-start rounded-xl border transition ${
                currentSessionId === session.id
                  ? 'border-violet-200 bg-violet-50'
                  : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
              }`}
              whileTap={{ scale: 0.99 }}
            >
              <button
                type="button"
                onClick={() => loadSession(session)}
                className="min-w-0 flex-1 p-3 text-left"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate text-sm font-medium text-slate-800">
                    <MessageSquare size={14} className="shrink-0 text-violet-600" />
                    {session.title}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">{session.knowledgeBaseName}</p>
                  <p className="mt-2 text-[11px] text-slate-400">
                    {new Date(session.updatedAt).toLocaleString('zh-CN', {
                      month: 'numeric',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              </button>
              <button
                type="button"
                onClick={(event) => deleteSession(session.id, event)}
                className={buttonStyles({ variant: 'danger', size: 'sm', iconOnly: true, className: 'mr-2 mt-2 opacity-0 group-hover:opacity-100' })}
                aria-label={`删除对话 ${session.title}`}
              >
                <Trash2 size={14} />
              </button>
            </motion.div>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-16 items-center justify-between gap-4 border-b border-slate-200 bg-white px-5 py-3 md:px-7">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-violet-600" />
              <h2 className="font-semibold text-slate-950">论文证据问答</h2>
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">回答中的引用可点击核对原文</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="relative hidden sm:block">
              <span className="sr-only">选择知识库</span>
              <select
                value={selectedKB?.collection_id || ''}
                onChange={(event) => {
                  const knowledgeBase = knowledgeBases.find(
                    (item) => item.collection_id === event.target.value,
                  );
                  setSelectedKB(knowledgeBase ?? null);
                }}
                className="max-w-[220px] appearance-none rounded-xl border border-slate-200 bg-white py-2 pl-3 pr-9 text-sm text-slate-700 outline-none transition hover:border-violet-300 focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
              >
                {knowledgeBases.length === 0 && <option value="">暂无知识库</option>}
                {knowledgeBases.map((knowledgeBase) => (
                  <option key={knowledgeBase.collection_id} value={knowledgeBase.collection_id}>
                    {knowledgeBase.display_name}
                  </option>
                ))}
              </select>
              <ChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
            </label>
            <button
              type="button"
              onClick={() => setShowSettings((visible) => !visible)}
              className={buttonStyles({ variant: showSettings ? 'secondary' : 'quiet', iconOnly: true })}
              aria-label="模型设置"
            >
              <Settings size={17} />
            </button>
          </div>
        </div>

        <AnimatePresence initial={false}>
          {showSettings && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-b border-slate-200 bg-white"
            >
              <div className="grid gap-4 px-5 py-4 md:grid-cols-3 md:px-7">
                <label className="text-xs font-medium text-slate-500">
                  模型
                  <select
                    value={llmConfig.model_name}
                    onChange={(event) => setLLMConfig({ ...llmConfig, model_name: event.target.value })}
                    className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-violet-400"
                  >
                    {availableModels.map((model) => (
                      <option key={model.name} value={model.name}>{model.display} · {model.provider}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-medium text-slate-500">
                  Temperature · {llmConfig.temperature}
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={llmConfig.temperature}
                    onChange={(event) => setLLMConfig({ ...llmConfig, temperature: Number(event.target.value) })}
                    className="mt-3 w-full accent-violet-600"
                  />
                </label>
                <label className="text-xs font-medium text-slate-500">
                  最大 Token 数
                  <input
                    type="number"
                    min="100"
                    max="4000"
                    step="100"
                    value={llmConfig.max_tokens}
                    onChange={(event) => setLLMConfig({ ...llmConfig, max_tokens: Number(event.target.value) })}
                    className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-violet-400"
                  />
                </label>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
          {messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
              <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-[0_16px_40px_rgba(99,102,241,0.24)]">
                <BookOpen size={30} />
              </div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-600">ScholarLens</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">从论文原文获得可验证的答案</h1>
              <p className="mt-3 max-w-xl leading-7 text-slate-500">
                {selectedKB
                  ? `当前知识库：${selectedKB.display_name}。每条事实性回答都会尽量附上可追溯来源。`
                  : '选择一个知识库后开始提问。'}
              </p>
              <div className="mt-7 grid w-full gap-3 md:grid-cols-3">
                {suggestedQuestions.map((question) => (
                  <button
                    type="button"
                    key={question}
                    onClick={() => setMessage(question)}
                    className="rounded-2xl border border-slate-200 bg-white p-4 text-left text-sm leading-6 text-slate-600 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-md"
                  >
                    <FileText size={17} className="mb-3 text-violet-600" />
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-4xl space-y-7">
              {messages.map((item) => (
                <motion.article
                  key={item.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={item.role === 'user' ? 'flex justify-end' : ''}
                >
                  {item.role === 'user' ? (
                    <div className="max-w-[82%] rounded-2xl rounded-br-md bg-violet-600 px-5 py-3.5 text-sm leading-7 text-white shadow-sm">
                      <p className="whitespace-pre-wrap">{item.content}</p>
                      <p className="mt-1 text-right text-[11px] text-violet-200">{item.timestamp}</p>
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-slate-200 bg-white px-5 py-5 shadow-[0_8px_30px_rgba(15,23,42,0.04)] md:px-6">
                      <div className="mb-4 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50 text-violet-700"><Sparkles size={16} /></span>
                          <div>
                            <p className="text-sm font-semibold text-slate-900">ScholarLens</p>
                            <p className="text-[11px] text-slate-400">基于检索证据生成</p>
                          </div>
                        </div>
                        <span className="text-[11px] text-slate-400">{item.timestamp}</span>
                      </div>
                      <CitationMarkdown
                        content={item.content}
                        sources={item.sources}
                        onSelectSource={selectSource}
                      />
                      {item.isStreaming && (
                        <div role="status" aria-live="polite" className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                          <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                          {item.content ? '正在整理来源，请稍候…' : '正在检索证据并生成、检查回答，请稍候…'}
                        </div>
                      )}
                      <AnswerSources content={item.content} sources={item.sources} onSelectSource={selectSource} />
                    </div>
                  )}
                </motion.article>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-4 md:px-8">
          <div className="mx-auto max-w-4xl">
            <div className="flex items-end gap-3 rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_8px_30px_rgba(15,23,42,0.06)] transition focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-50">
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value.slice(0, 2000))}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSendMessage();
                  }
                }}
                placeholder={selectedKB ? '询问论文中的方法、实验、结论或差异…' : '请先选择知识库'}
                disabled={!selectedKB || isLoading}
                rows={1}
                className="min-h-[48px] max-h-40 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void handleSendMessage()}
                disabled={!message.trim() || isLoading || !selectedKB}
                className={buttonStyles({ variant: 'primary', size: 'lg', iconOnly: true, className: 'shrink-0' })}
                aria-label="发送问题"
              >
                {isLoading ? <Loader2 size={19} className="animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-slate-400">
              <span>Enter 发送 · Shift + Enter 换行</span>
              <span>{message.length}/2000</span>
            </div>
          </div>
        </div>
      </section>

      <AnimatePresence>
        {selectedEvidence && (
          <EvidenceDrawer
            sourceId={selectedEvidence.sourceId}
            source={selectedEvidence.source}
            onClose={() => setSelectedEvidence(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
