import { Plus, ChevronDown, Send, Bot, User, Sparkles, Loader2, Settings, Trash2, MessageSquare } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import { config } from '../src/config';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: SourceDocument[];
  isStreaming?: boolean;
}

interface SourceDocument {
  chunk_text: string;
  filename: string;
  score: number;
  retrieval_score?: number;
  rerank_score?: number;
  metadata: Record<string, any>;
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

export function Chat() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [expandedCitation, setExpandedCitation] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [llmConfig, setLLMConfig] = useState<LLMConfig>({
    api_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api_key: '',
    model_name: 'qwen-plus',
    temperature: 0.7,
    max_tokens: 2000
  });
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 加载知识库列表和默认配置
  useEffect(() => {
    const fetchData = async () => {
      try {
        // 加载知识库列表
        const kbResponse = await fetch(`${config.milvusApiUrl}/knowledge_base/list`);
        const kbResult = await kbResponse.json();

        if (kbResult.status === 'success' && kbResult.knowledge_bases.length > 0) {
          setKnowledgeBases(kbResult.knowledge_bases);
          setSelectedKB(kbResult.knowledge_bases[0]);
        }

        // 加载默认LLM配置
        const configResponse = await fetch(`${config.chatApiUrl}/config/default`);
        const configResult = await configResponse.json();

        if (configResult.status === 'success') {
          setLLMConfig(configResult.config.llm);
          setAvailableModels(configResult.config.available_models);
        }

        // 从localStorage加载对话历史
        const savedSessions = localStorage.getItem('chat_sessions');
        if (savedSessions) {
          const sessions: ChatSession[] = JSON.parse(savedSessions);
          setChatSessions(sessions.sort((a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
          ));
        }
      } catch (error) {
        console.error('加载数据失败:', error);
        toast.error('加载配置失败');
      }
    };

    fetchData();
  }, []);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 保存当前会话到localStorage
  const saveCurrentSession = () => {
    if (!selectedKB || messages.length === 0) return;

    const now = new Date().toISOString();
    const sessionTitle = messages[0]?.content.slice(0, 30) + (messages[0]?.content.length > 30 ? '...' : '');

    let updatedSessions: ChatSession[];

    if (currentSessionId) {
      // 更新现有会话
      updatedSessions = chatSessions.map(session =>
        session.id === currentSessionId
          ? { ...session, messages, updatedAt: now }
          : session
      );
    } else {
      // 创建新会话
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

    // 只保留最近50个会话
    updatedSessions = updatedSessions.slice(0, 50);

    setChatSessions(updatedSessions);
    localStorage.setItem('chat_sessions', JSON.stringify(updatedSessions));
  };

  // 当消息变化时保存会话
  useEffect(() => {
    if (messages.length > 0) {
      saveCurrentSession();
    }
  }, [messages]);

  // 发送消息
  const handleSendMessage = async () => {
    if (!message.trim() || isLoading || !selectedKB) {
      if (!selectedKB) {
        toast.error('请先选择知识库');
      }
      return;
    }

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message.trim(),
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMessage]);
    setMessage('');
    setIsLoading(true);

    // 创建助手消息
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMessage]);

    try {
      abortControllerRef.current = new AbortController();

      const response = await fetch(`${config.chatApiUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: userMessage.content,
          collection_name: selectedKB.collection_id,
          llm_config: llmConfig,
          top_k: 10,
          score_threshold: 0.3,
          use_reranker: false,
          stream: true,
          return_source: true,
          history: messages.slice(-10).map(msg => ({
            role: msg.role,
            content: msg.content,
          })),
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('无法读取响应流');
      }

      let accumulatedContent = '';
      let sources: SourceDocument[] | undefined;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n').filter(line => line.trim());

        for (const line of lines) {
          try {
            const data = JSON.parse(line);

            if (data.type === 'content') {
              accumulatedContent += data.data;
              setMessages(prev =>
                prev.map(msg =>
                  msg.id === assistantMessage.id
                    ? { ...msg, content: accumulatedContent }
                    : msg
                )
              );
            } else if (data.type === 'sources') {
              sources = data.data;
            } else if (data.type === 'metadata') {
              console.log('对话元数据:', data.data);
            } else if (data.type === 'error') {
              console.error('对话错误:', data.data);
              toast.error(`对话失败: ${data.data.error}`);
            }
          } catch (e) {
            console.warn('解析流数据失败:', line, e);
          }
        }
      }

      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessage.id
            ? { ...msg, isStreaming: false, sources }
            : msg
        )
      );
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('请求已取消');
        toast.info('对话已取消');
      } else {
        console.error('对话失败:', error);
        toast.error('对话失败，请稍后重试');
      }

      setMessages(prev => prev.filter(msg => msg.id !== assistantMessage.id));
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setCurrentSessionId(null);
    toast.success('已创建新对话');
  };

  const loadSession = (session: ChatSession) => {
    setMessages(session.messages);
    setCurrentSessionId(session.id);

    // 切换到对应的知识库
    const kb = knowledgeBases.find(k => k.collection_id === session.knowledgeBaseId);
    if (kb) {
      setSelectedKB(kb);
    }

    toast.success(`已加载对话: ${session.title}`);
  };

  const deleteSession = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updatedSessions = chatSessions.filter(s => s.id !== sessionId);
    setChatSessions(updatedSessions);
    localStorage.setItem('chat_sessions', JSON.stringify(updatedSessions));

    if (currentSessionId === sessionId) {
      setMessages([]);
      setCurrentSessionId(null);
    }

    toast.success('已删除对话');
  };

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Left Sidebar */}
      <div className="w-[280px] glass-strong border-r border-[rgba(0,212,255,0.15)] flex flex-col">
        <div className="p-4 border-b border-[rgba(0,212,255,0.15)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-[#00d4ff]" />
            <h3 className="text-[#e8eaed]">对话历史</h3>
          </div>
          <motion.button
            onClick={handleNewChat}
            className="w-8 h-8 rounded-lg glass hover:bg-[rgba(0,212,255,0.1)] flex items-center justify-center transition-all"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            <Plus size={18} className="text-[#00d4ff]" />
          </motion.button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {chatSessions.length === 0 ? (
            <div className="text-[#94a3b8] text-sm text-center py-4">暂无历史对话</div>
          ) : (
            chatSessions.map(session => (
              <motion.div
                key={session.id}
                onClick={() => loadSession(session)}
                className={`p-3 rounded-lg cursor-pointer transition-all group ${
                  currentSessionId === session.id
                    ? 'bg-[rgba(0,212,255,0.15)] border border-[rgba(0,212,255,0.3)]'
                    : 'glass hover:bg-[rgba(0,212,255,0.1)]'
                }`}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <MessageSquare size={14} className="text-[#00d4ff] flex-shrink-0" />
                      <p className="text-[#e8eaed] text-sm font-medium truncate">
                        {session.title}
                      </p>
                    </div>
                    <p className="text-[#94a3b8] text-xs truncate">
                      {session.knowledgeBaseName} • {session.messages.length}条消息
                    </p>
                    <p className="text-[#64748b] text-xs mt-1">
                      {new Date(session.updatedAt).toLocaleString('zh-CN', {
                        month: 'numeric',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </p>
                  </div>
                  <motion.button
                    onClick={(e) => deleteSession(session.id, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 rounded transition-all"
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                  >
                    <Trash2 size={14} className="text-red-400" />
                  </motion.button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-[rgba(10,14,39,0.3)]">
        {/* Top Bar */}
        <div className="h-16 glass border-b border-[rgba(0,212,255,0.15)] px-6 flex items-center justify-between">
          <div className="relative">
            <select
              value={selectedKB?.collection_id || ''}
              onChange={(e) => {
                const kb = knowledgeBases.find(k => k.collection_id === e.target.value);
                setSelectedKB(kb || null);
              }}
              className="px-4 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl text-[#e8eaed] appearance-none pr-10 cursor-pointer hover:bg-[rgba(0,212,255,0.1)] transition-all focus:outline-none focus:ring-2 focus:ring-[#00d4ff]"
            >
              {knowledgeBases.length === 0 && <option value="">暂无知识库</option>}
              {knowledgeBases.map(kb => (
                <option key={kb.collection_id} value={kb.collection_id}>
                  知识库: {kb.display_name}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="text-[#00d4ff] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
          <div className="flex items-center gap-4">
            <div className="text-[#94a3b8] text-sm">
              {messages.length > 0 && `${messages.length} 条消息`}
            </div>
            <motion.button
              onClick={() => setShowSettings(!showSettings)}
              className="w-9 h-9 rounded-lg glass hover:bg-[rgba(0,212,255,0.1)] flex items-center justify-center transition-all"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Settings size={18} className={`${showSettings ? 'text-[#00d4ff]' : 'text-[#94a3b8]'} transition-colors`} />
            </motion.button>
          </div>
        </div>

        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-24 h-24 rounded-full bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center mb-6 animate-pulse-glow">
                <Bot size={48} className="text-[#0a0e27]" />
              </div>
              <h2 className="text-2xl text-gradient mb-3">开始新对话</h2>
              <p className="text-[#94a3b8] max-w-md">
                {selectedKB ? `已选择知识库「${selectedKB.display_name}」，现在可以向我提问了` : '请先选择一个知识库，然后开始对话'}
              </p>
            </div>
          ) : (
            <AnimatePresence>
              {messages.map((msg, index) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.05 }}
                >
                  {msg.role === 'assistant' ? (
                    <div className="flex gap-3 items-start">
                      <motion.div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center flex-shrink-0 shadow-lg">
                        <Bot size={22} className="text-[#0a0e27]" />
                      </motion.div>
                      <div className="flex-1 max-w-[70%]">
                        <motion.div className="glass-strong rounded-2xl p-5 shadow-lg border border-[rgba(0,212,255,0.2)]">
                          <div className="prose prose-invert max-w-none text-[#e8eaed]">
                            <ReactMarkdown
                              components={{
                                h1: ({node, ...props}) => <h1 className="text-xl text-gradient mb-3" {...props} />,
                                h2: ({node, ...props}) => <h2 className="text-lg text-[#00d4ff] mb-2" {...props} />,
                                h3: ({node, ...props}) => <h3 className="text-base text-[#00d4ff] mb-2" {...props} />,
                                p: ({node, ...props}) => <p className="text-[#e8eaed] mb-2 leading-relaxed" {...props} />,
                                ul: ({node, ...props}) => <ul className="list-disc list-inside space-y-1 text-[#e8eaed] mb-2" {...props} />,
                                ol: ({node, ...props}) => <ol className="list-decimal list-inside space-y-1 text-[#e8eaed] mb-2" {...props} />,
                                li: ({node, ...props}) => <li className="text-[#e8eaed]" {...props} />,
                                strong: ({node, ...props}) => <strong className="text-[#00d4ff] font-semibold" {...props} />,
                                em: ({node, ...props}) => <em className="text-[#00ff88] italic" {...props} />,
                                code: ({node, ...props}) => (
                                  <code className="bg-[rgba(0,212,255,0.1)] text-[#00ff88] px-1.5 py-0.5 rounded text-sm" {...props} />
                                ),
                                pre: ({node, ...props}) => (
                                  <pre className="bg-[rgba(0,212,255,0.1)] p-3 rounded-xl overflow-x-auto my-2" {...props} />
                                ),
                                blockquote: ({node, ...props}) => (
                                  <blockquote className="border-l-4 border-[#00d4ff] pl-4 py-2 my-2 text-[#94a3b8] italic" {...props} />
                                ),
                                table: ({node, ...props}) => (
                                  <table className="w-full border border-[rgba(0,212,255,0.2)] rounded-lg my-2" {...props} />
                                ),
                                th: ({node, ...props}) => (
                                  <th className="border border-[rgba(0,212,255,0.2)] px-3 py-2 bg-[rgba(0,212,255,0.1)] text-[#00d4ff]" {...props} />
                                ),
                                td: ({node, ...props}) => (
                                  <td className="border border-[rgba(0,212,255,0.2)] px-3 py-2 text-[#e8eaed]" {...props} />
                                ),
                                hr: ({node, ...props}) => (
                                  <hr className="my-4 border-t border-[rgba(0,212,255,0.3)]" {...props} />
                                ),
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                            {msg.isStreaming && <span className="inline-block w-2 h-5 bg-[#00d4ff] ml-1 animate-pulse" />}
                          </div>
                        </motion.div>
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="mt-3">
                            <motion.button
                              onClick={() => setExpandedCitation(expandedCitation === msg.id ? null : msg.id)}
                              className="text-[#00d4ff] text-sm flex items-center gap-1 px-3 py-1.5 glass rounded-lg border border-[rgba(0,212,255,0.2)]"
                            >
                              📚 引用来源 [{msg.sources.length}个]
                              <ChevronDown size={14} className={`transition-transform ${expandedCitation === msg.id ? 'rotate-180' : ''}`} />
                            </motion.button>
                            {expandedCitation === msg.id && (
                              <div className="mt-3 space-y-2">
                                {msg.sources.map((source, idx) => (
                                  <div key={idx} className="glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl p-4 text-sm">
                                    <div className="flex items-center gap-2 mb-2">
                                      <span className="text-[#e8eaed]">📄 {source.filename}</span>
                                    </div>
                                    <div className="flex gap-2 mb-3">
                                      <span className="px-2 py-1 bg-[rgba(0,212,255,0.1)] text-[#00d4ff] rounded-lg text-xs">
                                        相似度: {source.score.toFixed(3)}
                                      </span>
                                    </div>
                                    <div className="text-[#94a3b8] text-xs line-clamp-3">{source.chunk_text}</div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        <div className="text-[#94a3b8] text-xs mt-2">{msg.timestamp}</div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-3 items-start justify-end">
                      <div className="max-w-[70%]">
                        <div className="bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] rounded-2xl p-5 shadow-lg">
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        </div>
                        <div className="text-[#94a3b8] text-xs mt-2 text-right">{msg.timestamp}</div>
                      </div>
                      <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#8b5cf6] to-[#6366f1] flex items-center justify-center flex-shrink-0 shadow-lg">
                        <User size={22} className="text-white" />
                      </div>
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Settings Panel */}
        <AnimatePresence>
          {showSettings && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="glass-strong border-t border-[rgba(0,212,255,0.15)] overflow-hidden"
            >
              <div className="p-4 space-y-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-[#e8eaed] font-medium flex items-center gap-2">
                    <Settings size={16} className="text-[#00d4ff]" />
                    模型配置
                  </h3>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-[#94a3b8] text-sm mb-2 block">模型选择</label>
                    <select
                      value={llmConfig.model_name}
                      onChange={(e) => setLLMConfig({...llmConfig, model_name: e.target.value})}
                      className="w-full px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg text-[#e8eaed] focus:outline-none focus:ring-2 focus:ring-[#00d4ff]"
                    >
                      {availableModels.map(model => (
                        <option key={model.name} value={model.name}>
                          {model.display} ({model.provider})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-[#94a3b8] text-sm mb-2 block">Temperature: {llmConfig.temperature}</label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={llmConfig.temperature}
                      onChange={(e) => setLLMConfig({...llmConfig, temperature: parseFloat(e.target.value)})}
                      className="w-full"
                    />
                    <div className="flex justify-between text-xs text-[#94a3b8] mt-1">
                      <span>精确</span>
                      <span>创造</span>
                    </div>
                  </div>

                  <div>
                    <label className="text-[#94a3b8] text-sm mb-2 block">最大Token数</label>
                    <input
                      type="number"
                      min="100"
                      max="4000"
                      step="100"
                      value={llmConfig.max_tokens}
                      onChange={(e) => setLLMConfig({...llmConfig, max_tokens: parseInt(e.target.value)})}
                      className="w-full px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg text-[#e8eaed] focus:outline-none focus:ring-2 focus:ring-[#00d4ff]"
                    />
                  </div>

                  <div>
                    <label className="text-[#94a3b8] text-sm mb-2 block">API Key</label>
                    <input
                      type="password"
                      value={llmConfig.api_key}
                      onChange={(e) => setLLMConfig({...llmConfig, api_key: e.target.value})}
                      placeholder="sk-xxxxxxxxxxxx"
                      className="w-full px-3 py-2 glass-strong border border-[rgba(0,212,255,0.2)] rounded-lg text-[#e8eaed] focus:outline-none focus:ring-2 focus:ring-[#00d4ff]"
                    />
                  </div>
                </div>

                <div className="pt-2 text-xs text-[#94a3b8]">
                  💡 提示：调整参数后立即生效，无需重启
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Input Area */}
        <div className="glass-strong border-t border-[rgba(0,212,255,0.15)] p-4">
          <div className="flex gap-3 items-end">
            <div className="flex-1 relative">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={selectedKB ? '💬 输入你的问题...' : '⚠️ 请先选择知识库'}
                disabled={!selectedKB || isLoading}
                className="w-full min-h-[56px] max-h-[200px] px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] resize-none text-[#e8eaed] placeholder-[#94a3b8] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                rows={1}
              />
              <div className="absolute bottom-3 right-3 text-xs text-[#94a3b8]">
                {message.length}/2000
              </div>
            </div>
            <motion.button
              onClick={handleSendMessage}
              disabled={!message.trim() || isLoading || !selectedKB}
              className="w-14 h-14 rounded-xl bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] flex items-center justify-center transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
              whileHover={!isLoading && message.trim() && selectedKB ? { scale: 1.05 } : {}}
              whileTap={!isLoading && message.trim() && selectedKB ? { scale: 0.95 } : {}}
            >
              {isLoading ? <Loader2 size={22} className="animate-spin" /> : <Send size={22} />}
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}
