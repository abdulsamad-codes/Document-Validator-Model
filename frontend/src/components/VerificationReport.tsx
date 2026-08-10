import { type VerificationReport } from '../data/mockSchemas';
import { StatusBadge } from './StatusBadge';
import { ArrowLeft, ChevronDown, Network } from 'lucide-react';


interface VerificationReportViewProps {
  selectedCase: VerificationReport;
  onBack: () => void;
}

export function VerificationReportView({ selectedCase, onBack }: VerificationReportViewProps) {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex flex-col gap-4 mb-6 shrink-0">
        <button 
          onClick={onBack}
          className="flex items-center gap-2 text-ink-light hover:text-ink font-medium w-fit transition-colors"
        >
          <ArrowLeft size={18} /> Back to Queue
        </button>
        
        <div className="flex justify-between items-end">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="font-mono text-sm text-ink-light">{selectedCase.case_id}</span>
              <StatusBadge status={selectedCase.overall_status} className="scale-110 origin-left" />
            </div>
            <h2 className="text-3xl font-serif font-bold text-ink">{selectedCase.organization_name}</h2>
          </div>
          
          <div className="flex gap-3">
            <button className="px-4 py-2 border-2 border-ink text-ink font-bold rounded-lg hover:bg-gray-50 transition-colors">
              Reject Package
            </button>
            <button className="px-4 py-2 bg-ink text-white font-bold rounded-lg shadow-md hover:bg-ink-light transition-colors">
              Approve Onboarding
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 pb-10 space-y-8">
        
        {/* Cross-Document Checks */}
        {selectedCase.cross_document_checks.length > 0 && (
          <section>
            <h3 className="text-lg font-bold text-ink flex items-center gap-2 mb-4 border-b border-gray-200 pb-2">
              <Network size={20} className="text-ink-light" />
              Cross-Document Consistency
            </h3>
            
            <div className="grid gap-4">
              {selectedCase.cross_document_checks.map((check, idx) => (
                <div key={idx} className={`p-4 border-l-4 rounded-r-lg bg-white shadow-sm ${check.is_consistent ? 'border-status-pass' : 'border-status-review'}`}>
                  <div className="flex justify-between items-start mb-3">
                    <h4 className="font-bold text-ink capitalize">{check.field_name.replace('_', ' ')} Match</h4>
                    <StatusBadge status={check.status} />
                  </div>
                  
                  <p className="text-sm text-ink mb-4">{check.message}</p>
                  
                  <div className="flex gap-2 relative">
                    {/* The visual "link" between values */}
                    {!check.is_consistent && (
                      <div className="absolute top-1/2 left-0 right-0 h-px bg-dashed border-t-2 border-dashed border-status-review opacity-30 z-0"></div>
                    )}
                    
                    {Object.entries(check.values_found).map(([doc, val]) => (
                      <div key={doc} className="flex-1 bg-paper p-3 rounded border border-gray-200 z-10">
                        <p className="text-xs text-ink-light uppercase tracking-wider mb-1 font-semibold">{doc.replace(/_/g, ' ')}</p>
                        <p className={`font-mono text-sm ${!check.is_consistent ? 'text-status-fail font-bold' : 'text-ink'}`}>
                          {val || 'Not Found'}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Per-Document Results */}
        <section>
          <h3 className="text-lg font-bold text-ink mb-4 border-b border-gray-200 pb-2">Document Reports</h3>
          
          <div className="grid gap-4">
            {selectedCase.document_results.map((doc, idx) => (
              <details key={idx} className="group bg-white border border-gray-200 rounded-lg shadow-sm [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-4">
                    <StatusBadge status={doc.overall_status} />
                    <div>
                      <h4 className="font-bold text-ink capitalize">{doc.document_type.replace(/_/g, ' ')}</h4>
                      <p className="text-xs text-ink-light font-mono">{doc.file_name}</p>
                    </div>
                  </div>
                  <ChevronDown size={20} className="text-ink-light transition-transform group-open:rotate-180" />
                </summary>
                
                <div className="p-4 border-t border-gray-100 bg-gray-50/50">
                  <div className="space-y-3">
                    {doc.rule_results.map((rule, ridx) => (
                      <div key={ridx} className="flex gap-4 p-3 bg-white rounded border border-gray-100 shadow-sm">
                        <div className="mt-1"><StatusBadge status={rule.status} /></div>
                        <div className="flex-1">
                          <p className="font-bold text-sm text-ink">{rule.rule_name}</p>
                          <p className="text-sm text-ink-light mt-1">{rule.message}</p>
                          
                          {(rule.field_value || rule.expected_value) && (
                            <div className="mt-3 grid grid-cols-2 gap-4 bg-paper p-2 rounded text-sm font-mono border border-gray-200">
                              <div>
                                <span className="text-xs text-ink-light block mb-1">Found Value:</span>
                                <span className="text-status-fail">{rule.field_value || 'null'}</span>
                              </div>
                              <div>
                                <span className="text-xs text-ink-light block mb-1">Expected:</span>
                                <span className="text-status-pass">{rule.expected_value || 'null'}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            ))}
            
            {selectedCase.document_results.length === 0 && (
              <p className="text-ink-light italic">No document results available for this case.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
