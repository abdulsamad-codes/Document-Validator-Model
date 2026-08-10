import { useState } from 'react';
import { CaseQueue } from './components/CaseQueue';
import { PipelineView } from './components/PipelineView';
import { VerificationReportView } from './components/VerificationReport';
import { mockCases, type VerificationReport } from './data/mockSchemas';
import { FileText, LayoutDashboard, Settings, User } from 'lucide-react';

type ViewState = 'queue' | 'pipeline' | 'report';

function App() {
  const [currentView, setCurrentView] = useState<ViewState>('queue');
  const [selectedCase, setSelectedCase] = useState<VerificationReport | null>(null);

  const handleSelectCase = (caseId: string) => {
    const c = mockCases.find((x) => x.case_id === caseId);
    if (c) {
      setSelectedCase(c);
      setCurrentView('pipeline');
      
      // Simulate pipeline processing, then move to report
      setTimeout(() => {
        setCurrentView('report');
      }, 6000); // 6 seconds for the animation to play out
    }
  };

  const handleBackToQueue = () => {
    setCurrentView('queue');
    setSelectedCase(null);
  };

  return (
    <div className="flex h-screen bg-paper text-ink overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shadow-sm">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-xl font-serif font-bold tracking-tight text-ink">KPITB Validator</h1>
          <p className="text-xs text-ink-light mt-1 uppercase tracking-widest font-semibold">Diagnostic UI</p>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          <button 
            onClick={handleBackToQueue}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg font-medium transition-colors ${currentView === 'queue' ? 'bg-ink text-white' : 'text-ink-light hover:bg-gray-100 hover:text-ink'}`}
          >
            <LayoutDashboard size={18} />
            Case Queue
          </button>
          
          <button className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg font-medium text-ink-light hover:bg-gray-100 hover:text-ink transition-colors">
            <FileText size={18} />
            Archive
          </button>
          
          <button className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg font-medium text-ink-light hover:bg-gray-100 hover:text-ink transition-colors">
            <Settings size={18} />
            Rule Settings
          </button>
        </nav>
        
        <div className="p-4 border-t border-gray-200">
          <div className="flex items-center gap-3 px-4 py-2">
            <div className="w-8 h-8 rounded-full bg-status-review flex items-center justify-center text-white">
              <User size={16} />
            </div>
            <div className="text-sm">
              <p className="font-semibold text-ink">A. Reviewer</p>
              <p className="text-ink-light text-xs">Level 2 Analyst</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto p-8 h-full">
          {currentView === 'queue' && <CaseQueue cases={mockCases} onSelectCase={handleSelectCase} />}
          {currentView === 'pipeline' && selectedCase && <PipelineView selectedCase={selectedCase} />}
          {currentView === 'report' && selectedCase && (
            <VerificationReportView selectedCase={selectedCase} onBack={handleBackToQueue} />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
