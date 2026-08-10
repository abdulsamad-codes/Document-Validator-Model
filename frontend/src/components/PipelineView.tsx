import { useEffect, useState } from 'react';
import { type VerificationReport } from '../data/mockSchemas';
import { motion } from 'framer-motion';
import { CheckCircle2, FileWarning, Search, Cpu, Type, Fingerprint, Network, ShieldCheck, FileCheck2 } from 'lucide-react';

interface PipelineViewProps {
  selectedCase: VerificationReport;
}

const STAGES = [
  { id: 'upload', label: 'Document Intake', icon: FileCheck2 },
  { id: 'pdf', label: 'PDF Rasterization', icon: Search },
  { id: 'enhance', label: 'Image Enhancement', icon: Cpu },
  { id: 'ocr', label: 'OCR Extraction', icon: Type },
  { id: 'fields', label: 'Field Parsing', icon: FileWarning },
  { id: 'detect', label: 'Signatures & Stamps', icon: Fingerprint },
  { id: 'cross', label: 'Cross-Doc Matching', icon: Network },
  { id: 'rules', label: 'Rule Engine', icon: ShieldCheck },
];

export function PipelineView({ selectedCase }: PipelineViewProps) {
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    // Simulate pipeline progress
    const interval = setInterval(() => {
      setActiveStage((prev) => {
        if (prev < STAGES.length) return prev + 1;
        clearInterval(interval);
        return prev;
      });
    }, 700);
    
    return () => clearInterval(interval);
  }, []);

  const hasIssues = selectedCase.overall_status === 'FAIL' || selectedCase.overall_status === 'MANUAL_REVIEW';

  return (
    <div className="flex flex-col h-full items-center justify-center max-w-4xl mx-auto w-full">
      <div className="text-center mb-16">
        <h2 className="text-3xl font-serif font-bold text-ink">Verifying {selectedCase.organization_name}</h2>
        <p className="text-ink-light mt-2 font-mono text-sm">{selectedCase.case_id}</p>
      </div>

      <div className="relative w-full">
        {/* Animated connecting line */}
        <div className="absolute top-8 left-10 right-10 h-1 bg-gray-200 rounded-full z-0 overflow-hidden">
          <motion.div 
            className={`h-full ${hasIssues && activeStage >= STAGES.length - 1 ? 'bg-status-review' : 'bg-status-pass'}`}
            initial={{ width: '0%' }}
            animate={{ width: `${(Math.min(activeStage, STAGES.length - 1) / (STAGES.length - 1)) * 100}%` }}
            transition={{ ease: "linear", duration: 0.7 }}
          />
        </div>

        <div className="relative z-10 flex justify-between w-full">
          {STAGES.map((stage, i) => {
            const isComplete = i < activeStage;
            const isCurrent = i === activeStage;
            const Icon = stage.icon;
            
            // If it's the last stage and the case has issues, diverge color
            const isFinalDiverge = i === STAGES.length - 1 && isComplete && hasIssues;

            return (
              <div key={stage.id} className="flex flex-col items-center w-24">
                <motion.div 
                  initial={{ scale: 0.8, backgroundColor: '#fff', borderColor: '#e5e7eb' }}
                  animate={{ 
                    scale: isCurrent ? 1.2 : 1,
                    backgroundColor: isFinalDiverge ? '#4A55A2' : isComplete ? '#276F4B' : '#fff',
                    borderColor: isFinalDiverge ? '#4A55A2' : isComplete ? '#276F4B' : isCurrent ? '#2A2C2B' : '#e5e7eb',
                    color: isComplete || isFinalDiverge ? '#fff' : isCurrent ? '#2A2C2B' : '#9ca3af'
                  }}
                  transition={{ ease: "easeInOut", duration: 0.3 }}
                  className="w-16 h-16 rounded-full border-2 flex items-center justify-center bg-white mb-4 shadow-sm"
                >
                  {isComplete && !isFinalDiverge ? <CheckCircle2 size={24} /> : <Icon size={24} />}
                </motion.div>
                <p className={`text-xs font-semibold text-center leading-tight transition-colors ${
                  isCurrent ? 'text-ink' : 'text-ink-light'
                }`}>
                  {stage.label}
                </p>
                
                {isCurrent && (
                  <motion.div 
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="absolute -bottom-8 whitespace-nowrap text-xs font-mono text-ink-light"
                  >
                    Processing...
                  </motion.div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
