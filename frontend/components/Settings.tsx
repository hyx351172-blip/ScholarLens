import { Eye, EyeOff, Check, X, Cpu, FileText, Target, Settings2 } from 'lucide-react';
import { useState } from 'react';
import { motion } from 'motion/react';
import { Slider } from './ui/slider';
import { Switch } from './ui/switch';

export function Settings() {
  const [activeTab, setActiveTab] = useState('model');
  const [showApiKey, setShowApiKey] = useState(false);
  const [temperature, setTemperature] = useState([0.7]);
  const [maxTokens, setMaxTokens] = useState([2000]);
  const [topK, setTopK] = useState([5]);
  const [similarityThreshold, setSimilarityThreshold] = useState([0.7]);
  const [enableRerank, setEnableRerank] = useState(true);
  const [extractionMode, setExtractionMode] = useState('fast');
  const [searchMode, setSearchMode] = useState('hybrid');
  const [chunkSize, setChunkSize] = useState(512);
  const [overlap, setOverlap] = useState(50);
  const [connectionStatus, setConnectionStatus] = useState<'success' | 'error' | null>(null);

  const tabs = [
    { id: 'model', label: '模型配置', icon: Cpu },
    { id: 'extraction', label: '提取配置', icon: FileText },
    { id: 'retrieval', label: '检索配置', icon: Target },
    { id: 'general', label: '通用设置', icon: Settings2 },
  ];

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <motion.div
        className="glass gradient-border rounded-2xl overflow-hidden"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="border-b border-[rgba(0,212,255,0.15)]">
          <div className="flex">
            {tabs.map((tab, index) => {
              const Icon = tab.icon;
              return (
                <motion.button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className={`flex-1 px-6 py-4 transition-all relative flex items-center justify-center gap-2 group ${
                    activeTab === tab.id
                      ? 'text-[#00d4ff]'
                      : 'text-[#94a3b8] hover:text-[#e8eaed]'
                  }`}
                >
                  {activeTab === tab.id && (
                    <motion.div
                      layoutId="activeSettingsTab"
                      className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[#00d4ff] to-[#0066ff]"
                      transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                    />
                  )}
                  <Icon size={18} className={activeTab === tab.id ? 'text-[#00d4ff]' : 'group-hover:text-[#00d4ff] transition-colors'} />
                  <span>{tab.label}</span>
                </motion.button>
              );
            })}
          </div>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          {/* Model Configuration Tab */}
          {activeTab === 'model' && (
            <motion.div
              className="space-y-8"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              {/* Embedding Model */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 pb-3 border-b border-[rgba(0,212,255,0.15)]">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00d4ff] to-[#0066ff] flex items-center justify-center">
                    <span className="text-[#0a0e27]">🔤</span>
                  </div>
                  <h3 className="text-[#e8eaed]">Embedding模型</h3>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">提供商</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>Jina AI</option>
                      <option>OpenAI</option>
                      <option>Cohere</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">模型</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>jina-embeddings-v4</option>
                      <option>jina-embeddings-v3</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[#94a3b8]">维度</label>
                  <input
                    type="text"
                    value="2048"
                    disabled
                    className="w-full px-4 py-3 glass rounded-xl bg-[rgba(15,18,53,0.8)] text-[#94a3b8] border border-[rgba(0,212,255,0.1)]"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-[#94a3b8]">API Key</label>
                  <div className="flex gap-3">
                    <div className="flex-1 relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        defaultValue=""
                        className="w-full px-4 py-3 pr-12 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                      />
                      <button
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[#94a3b8] hover:text-[#00d4ff] transition-colors"
                      >
                        {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                    <motion.button
                      onClick={() => setConnectionStatus('success')}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      className="px-6 py-3 border border-[#00d4ff] text-[#00d4ff] rounded-xl hover:bg-[rgba(0,212,255,0.1)] transition-all"
                    >
                      测试连接
                    </motion.button>
                  </div>
                  {connectionStatus === 'success' && (
                    <motion.div
                      className="flex items-center gap-2 text-[#00ff88] text-sm px-3 py-2 glass-strong rounded-lg border border-[rgba(0,255,136,0.2)]"
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                    >
                      <Check size={16} />
                      连接成功
                    </motion.div>
                  )}
                  {connectionStatus === 'error' && (
                    <motion.div
                      className="flex items-center gap-2 text-[#ff3b5c] text-sm px-3 py-2 glass-strong rounded-lg border border-[rgba(255,59,92,0.2)]"
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                    >
                      <X size={16} />
                      连接失败
                    </motion.div>
                  )}
                </div>
              </div>

              {/* LLM Model */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 pb-3 border-b border-[rgba(0,212,255,0.15)]">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#8b5cf6] to-[#6366f1] flex items-center justify-center">
                    <span className="text-white">🤖</span>
                  </div>
                  <h3 className="text-[#e8eaed]">LLM模型</h3>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">提供商</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>OpenAI</option>
                      <option>Claude</option>
                      <option>Qwen</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">模型</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>gpt-4-turbo</option>
                      <option>gpt-3.5-turbo</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-[#94a3b8]">Temperature</label>
                      <span className="text-[#00d4ff] px-3 py-1 rounded-lg bg-[rgba(0,212,255,0.1)] border border-[rgba(0,212,255,0.2)]">{temperature[0]}</span>
                    </div>
                    <Slider
                      value={temperature}
                      onValueChange={setTemperature}
                      min={0}
                      max={1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-[#94a3b8]">Max Tokens</label>
                      <span className="text-[#00d4ff] px-3 py-1 rounded-lg bg-[rgba(0,212,255,0.1)] border border-[rgba(0,212,255,0.2)]">{maxTokens[0]}</span>
                    </div>
                    <Slider
                      value={maxTokens}
                      onValueChange={setMaxTokens}
                      min={500}
                      max={4000}
                      step={100}
                      className="w-full"
                    />
                  </div>
                </div>
              </div>

              {/* Rerank Model */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 pb-3 border-b border-[rgba(0,212,255,0.15)]">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#00ff88] to-[#00d4a0] flex items-center justify-center">
                    <span className="text-[#0a0e27]">⚡</span>
                  </div>
                  <h3 className="text-[#e8eaed]">Rerank模型</h3>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">提供商</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>Cohere</option>
                      <option>Jina</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">模型</label>
                    <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                      <option>rerank-v3</option>
                      <option>rerank-v2</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-4 glass rounded-xl border border-[rgba(0,212,255,0.2)]">
                  <Switch checked={enableRerank} onCheckedChange={setEnableRerank} />
                  <label className="text-[#e8eaed]">启用重排序</label>
                </div>
              </div>
            </motion.div>
          )}

          {/* Extraction Configuration Tab */}
          {activeTab === 'extraction' && (
            <motion.div
              className="space-y-8"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              {/* Default Mode */}
              <div className="space-y-4">
                <h3 className="text-[#e8eaed]">默认提取模式</h3>

                <div className="grid grid-cols-2 gap-4">
                  <motion.button
                    onClick={() => setExtractionMode('fast')}
                    whileHover={{ scale: 1.02, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    className={`p-6 rounded-2xl border-2 transition-all text-left relative overflow-hidden group ${
                      extractionMode === 'fast'
                        ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)] shadow-[0_0_20px_rgba(0,212,255,0.3)]'
                        : 'border-[rgba(0,212,255,0.2)] glass hover:border-[rgba(0,212,255,0.4)]'
                    }`}
                  >
                    {extractionMode === 'fast' && (
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
                    )}
                    <div className="flex items-center gap-3 mb-3 relative z-10">
                      <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${extractionMode === 'fast' ? 'border-[#00d4ff]' : 'border-[#94a3b8]'}`}>
                        {extractionMode === 'fast' && <div className="w-3 h-3 rounded-full bg-[#00d4ff]" />}
                      </div>
                      <span className={`text-lg ${extractionMode === 'fast' ? 'text-[#00d4ff]' : 'text-[#e8eaed]'}`}>
                        快速模式(PyMuPDF4LLM)
                      </span>
                    </div>
                    <p className="text-sm text-[#94a3b8] relative z-10">
                      使用PyMuPDF进行快速文档提取，适合简单文档
                    </p>
                  </motion.button>

                  <motion.button
                    onClick={() => setExtractionMode('vlm')}
                    whileHover={{ scale: 1.02, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    className={`p-6 rounded-2xl border-2 transition-all text-left relative overflow-hidden group ${
                      extractionMode === 'vlm'
                        ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)] shadow-[0_0_20px_rgba(0,212,255,0.3)]'
                        : 'border-[rgba(0,212,255,0.2)] glass hover:border-[rgba(0,212,255,0.4)]'
                    }`}
                  >
                    {extractionMode === 'vlm' && (
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
                    )}
                    <div className="flex items-center gap-3 mb-3 relative z-10">
                      <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${extractionMode === 'vlm' ? 'border-[#00d4ff]' : 'border-[#94a3b8]'}`}>
                        {extractionMode === 'vlm' && <div className="w-3 h-3 rounded-full bg-[#00d4ff]" />}
                      </div>
                      <span className={`text-lg ${extractionMode === 'vlm' ? 'text-[#00d4ff]' : 'text-[#e8eaed]'}`}>
                        精确模式(VLM)
                      </span>
                    </div>
                    <p className="text-sm text-[#94a3b8] relative z-10">
                      使用视觉语言模型进行精确提取，支持复杂布局
                    </p>
                  </motion.button>
                </div>
              </div>

              {/* Chunking Parameters */}
              <div className="space-y-4">
                <h3 className="text-[#e8eaed]">切分参数</h3>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">Chunk Size</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        value={chunkSize}
                        onChange={(e) => setChunkSize(parseInt(e.target.value))}
                        className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                      />
                      <span className="px-4 py-3 glass rounded-xl border border-[rgba(0,212,255,0.2)] text-[#94a3b8]">
                        tokens
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">Overlap</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        value={overlap}
                        onChange={(e) => setOverlap(parseInt(e.target.value))}
                        className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                      />
                      <span className="px-4 py-3 glass rounded-xl border border-[rgba(0,212,255,0.2)] text-[#94a3b8]">
                        tokens
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">Max Page Span</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        defaultValue={2}
                        className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                      />
                      <span className="px-4 py-3 glass rounded-xl border border-[rgba(0,212,255,0.2)] text-[#94a3b8]">
                        页
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-[#94a3b8]">Bridge Length</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        defaultValue={100}
                        className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                      />
                      <span className="px-4 py-3 glass rounded-xl border border-[rgba(0,212,255,0.2)] text-[#94a3b8]">
                        tokens
                      </span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[#94a3b8]">切分方法</label>
                  <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                    <option>递归字符分割</option>
                    <option>固定大小分割</option>
                    <option>语义分割</option>
                  </select>
                </div>
              </div>
            </motion.div>
          )}

          {/* Retrieval Configuration Tab */}
          {activeTab === 'retrieval' && (
            <motion.div
              className="space-y-8"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              {/* Default Parameters */}
              <div className="space-y-4">
                <h3 className="text-[#e8eaed]">默认检索参数</h3>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-[#94a3b8]">Top K</label>
                      <span className="text-[#00d4ff] px-3 py-1 rounded-lg bg-[rgba(0,212,255,0.1)] border border-[rgba(0,212,255,0.2)]">{topK[0]}</span>
                    </div>
                    <Slider
                      value={topK}
                      onValueChange={setTopK}
                      min={1}
                      max={20}
                      step={1}
                      className="w-full"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-[#94a3b8]">相似度阈值</label>
                      <span className="text-[#00d4ff] px-3 py-1 rounded-lg bg-[rgba(0,212,255,0.1)] border border-[rgba(0,212,255,0.2)]">{similarityThreshold[0]}</span>
                    </div>
                    <Slider
                      value={similarityThreshold}
                      onValueChange={setSimilarityThreshold}
                      min={0}
                      max={1}
                      step={0.05}
                      className="w-full"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3 p-4 glass rounded-xl border border-[rgba(0,212,255,0.2)]">
                  <Switch checked={enableRerank} onCheckedChange={setEnableRerank} />
                  <label className="text-[#e8eaed]">启用重排序</label>
                </div>

                {enableRerank && (
                  <motion.div
                    className="space-y-2 ml-4 pl-4 border-l-2 border-[rgba(0,212,255,0.2)]"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                  >
                    <label className="text-[#94a3b8]">Rerank Top K</label>
                    <input
                      type="number"
                      defaultValue={3}
                      className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                    />
                  </motion.div>
                )}
              </div>

              {/* Search Mode */}
              <div className="space-y-4">
                <h3 className="text-[#e8eaed]">搜索模式</h3>

                <div className="grid grid-cols-3 gap-4">
                  {[
                    { id: 'vector', label: '向量搜索', icon: '🔵', desc: '基于语义相似度' },
                    { id: 'hybrid', label: '混合搜索', icon: '⚫', desc: '结合向量和关键词' },
                    { id: 'keyword', label: '关键词搜索', icon: '⚪', desc: '基于关键词匹配' },
                  ].map((mode) => (
                    <motion.button
                      key={mode.id}
                      onClick={() => setSearchMode(mode.id)}
                      whileHover={{ scale: 1.05, y: -2 }}
                      whileTap={{ scale: 0.95 }}
                      className={`p-6 rounded-2xl border-2 transition-all text-center relative overflow-hidden group ${
                        searchMode === mode.id
                          ? 'border-[#00d4ff] bg-[rgba(0,212,255,0.1)] shadow-[0_0_20px_rgba(0,212,255,0.3)]'
                          : 'border-[rgba(0,212,255,0.2)] glass hover:border-[rgba(0,212,255,0.4)]'
                      }`}
                    >
                      {searchMode === mode.id && (
                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.1)] to-transparent shimmer" />
                      )}
                      <div className="relative z-10">
                        <div className="text-3xl mb-3">{mode.icon}</div>
                        <div className={`mb-2 ${searchMode === mode.id ? 'text-[#00d4ff]' : 'text-[#e8eaed]'}`}>
                          {mode.label}
                        </div>
                        <div className="text-xs text-[#94a3b8]">{mode.desc}</div>
                      </div>
                    </motion.button>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {/* General Settings Tab */}
          {activeTab === 'general' && (
            <motion.div
              className="space-y-6"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
            >
              <div className="space-y-2">
                <label className="text-[#94a3b8]">语言</label>
                <select className="w-full px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                  <option>🇨🇳 简体中文</option>
                  <option>🇺🇸 English</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-[#94a3b8]">最大文件大小</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    defaultValue={100}
                    className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                  />
                  <select className="px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed] bg-[rgba(15,18,53,0.6)]">
                    <option>MB</option>
                    <option>GB</option>
                  </select>
                </div>
              </div>

              <div className="space-y-3">
                <label className="text-[#94a3b8]">允许的文件类型</label>
                <div className="flex flex-wrap gap-2">
                  {['PDF', 'Markdown', 'Word', 'Image', 'Audio'].map((type) => (
                    <motion.button
                      key={type}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      className="px-4 py-2 bg-[rgba(0,212,255,0.1)] text-[#00d4ff] rounded-xl hover:bg-[rgba(0,212,255,0.2)] transition-all border border-[rgba(0,212,255,0.2)]"
                    >
                      {type}
                    </motion.button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[#94a3b8]">上传文件夹路径</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    defaultValue="/uploads/documents"
                    className="flex-1 px-4 py-3 glass-strong border border-[rgba(0,212,255,0.2)] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#00d4ff] text-[#e8eaed]"
                  />
                  <motion.button
                    className="px-6 py-3 glass border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all text-[#e8eaed]"
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    浏览
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </motion.div>

      {/* Bottom Action Bar */}
      <motion.div
        className="flex items-center justify-between"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <motion.button
          className="text-[#00d4ff] hover:underline"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          恢复默认设置
        </motion.button>

        <div className="flex gap-3">
          <motion.button
            className="px-6 py-3 glass border border-[rgba(0,212,255,0.2)] rounded-xl hover:bg-[rgba(0,212,255,0.05)] transition-all text-[#e8eaed]"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            重置
          </motion.button>
          <motion.button
            className="px-6 py-3 bg-gradient-to-r from-[#00d4ff] to-[#0066ff] text-[#0a0e27] rounded-xl hover:shadow-[0_0_30px_rgba(0,212,255,0.6)] transition-all relative overflow-hidden group"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-0 group-hover:opacity-20 shimmer" />
            <span className="relative z-10">保存设置</span>
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
}
