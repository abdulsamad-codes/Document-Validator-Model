import { useState } from 'react';
import { type VerificationReport } from '../data/mockSchemas';
import { StatusBadge } from './StatusBadge';
import { Search, Filter, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

interface CaseQueueProps {
  cases: VerificationReport[];
  onSelectCase: (caseId: string) => void;
}

export function CaseQueue({ cases, onSelectCase }: CaseQueueProps) {
  const [filter, setFilter] = useState('ALL');

  const filteredCases = cases.filter(c => filter === 'ALL' || c.overall_status === filter);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-serif font-bold text-ink">Submission Queue</h2>
          <p className="text-ink-light mt-1">Pending sub-biller onboarding packages awaiting review.</p>
        </div>
        
        <div className="flex gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <input 
              type="text" 
              placeholder="Search case ID or org..." 
              className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ink"
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <select 
              className="pl-10 pr-8 py-2 border border-gray-300 rounded-lg appearance-none bg-white focus:outline-none focus:ring-2 focus:ring-ink"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="MANUAL_REVIEW">Needs Review</option>
              <option value="PASS">Passed</option>
              <option value="FAIL">Failed</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto pr-2">
        <div className="space-y-4">
          {filteredCases.map((c, i) => (
            <motion.div 
              key={c.case_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              onClick={() => onSelectCase(c.case_id)}
              className="group bg-white border border-gray-200 rounded-xl p-5 shadow-document cursor-pointer hover:border-ink hover:shadow-md transition-all flex items-center justify-between"
            >
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-mono text-sm text-ink-light">{c.case_id}</span>
                  <StatusBadge status={c.overall_status} />
                </div>
                <h3 className="text-lg font-bold text-ink">{c.organization_name}</h3>
                <p className="text-sm text-ink-light mt-2 flex items-center gap-4">
                  <span>Submitted: {new Date(c.submitted_at).toLocaleString()}</span>
                  <span>•</span>
                  <span>{c.total_rules_checked} rules checked</span>
                </p>
              </div>
              
              <div className="w-12 h-12 rounded-full bg-gray-50 flex items-center justify-center group-hover:bg-ink group-hover:text-white transition-colors">
                <ArrowRight size={20} />
              </div>
            </motion.div>
          ))}
          
          {filteredCases.length === 0 && (
            <div className="text-center py-20 text-ink-light">
              <p>No cases match the current filters.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
