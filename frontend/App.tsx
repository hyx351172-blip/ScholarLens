import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Dashboard } from './components/Dashboard';
import { KnowledgeBase } from './components/KnowledgeBase';
import { KnowledgeBaseDetail } from './components/KnowledgeBaseDetail';
import { DocumentViewer } from './components/DocumentViewer';
import { Chat } from './components/Chat';
import { RetrievalTest } from './components/RetrievalTest';
import { Settings } from './components/Settings';
import { Toaster } from './components/ui/sonner';

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);

  const getHeaderTitle = () => {
    switch (activeView) {
      case 'dashboard':
        return '概览';
      case 'knowledge':
        return selectedKnowledgeBase ? '文献详情' : '文献库';
      case 'chat':
        return '科研问答';
      case 'retrieval':
        return '检索测试';
      case 'settings':
        return '设置';
      default:
        return '仪表盘';
    }
  };

  const handleNavigate = (view: string) => {
    setActiveView(view);
    setMobileNavOpen(false);
    setSelectedKnowledgeBase(null);
    setSelectedDocument(null);
  };

  const handleViewKnowledgeBaseDetail = (collectionId: string) => {
    setSelectedKnowledgeBase(collectionId);
  };

  const handleBackToKnowledgeBase = () => {
    setSelectedKnowledgeBase(null);
    setSelectedDocument(null);
  };

  const handleViewDocument = (fileId: string) => {
    setSelectedDocument(fileId);
  };

  const handleBackToDetail = () => {
    // 只清除文档选择，保留知识库选择，返回到知识库详情页
    setSelectedDocument(null);
    // selectedKnowledgeBase 保持不变，这样就返回到知识库详情页
  };

  const renderContent = () => {
    if (activeView === 'knowledge') {
      if (selectedDocument) {
        return <DocumentViewer fileId={selectedDocument} onBack={handleBackToDetail} />;
      }
      if (selectedKnowledgeBase) {
        return (
          <KnowledgeBaseDetail
            collectionId={selectedKnowledgeBase}
            onBack={handleBackToKnowledgeBase}
            onViewDocument={handleViewDocument}
          />
        );
      }
      return <KnowledgeBase onViewDetail={handleViewKnowledgeBaseDetail} />;
    }

    switch (activeView) {
      case 'dashboard':
        return <Dashboard onNavigate={handleNavigate} />;
      case 'chat':
        return <Chat />;
      case 'retrieval':
        return <RetrievalTest />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard onNavigate={handleNavigate} />;
    }
  };

  return (
    <div className="min-h-screen bg-[#f8f8fb]">
      <Sidebar
        activeView={activeView}
        onNavigate={handleNavigate}
        mobileOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />

      <div className="app-shell-content min-h-screen">
        <Header title={getHeaderTitle()} onOpenNavigation={() => setMobileNavOpen(true)} />

        <main style={{
          paddingTop: (activeView === 'chat' || (activeView === 'knowledge' && selectedDocument)) ? '64px' : '80px',
          minHeight: 'calc(100vh - 64px)'
        }}>
          <div className={(activeView === 'chat' || (activeView === 'knowledge' && selectedDocument)) ? '' : 'mx-auto max-w-[1440px] p-6'}>
            <AnimatePresence mode="wait">
              <motion.div
                key={activeView + (selectedKnowledgeBase || '') + (selectedDocument || '')}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {renderContent()}
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      <Toaster />
    </div>
  );
}
