export type StepStatus = 'pending' | 'running' | 'complete' | 'error';

export interface StepState {
  status: StepStatus;
  name?: string;
}

export interface JobStatus {
  status: 'pending' | 'running' | 'complete' | 'error';
  progress: number;
  steps: Record<string, StepState>;
  error?: string;
}

export interface Component {
  name: string;
  type: string;
  technology?: string;
  description?: string;
}

export interface DataStore {
  name: string;
  type: string;
  technology: string;
}

export interface SecurityMechanism {
  mechanism: string;
  description?: string;
}

export interface ExtractedContext {
  document_title?: string;
  document_type?: string;
  system_name?: string;
  cloud_provider?: string;
  deployment_model?: string;
  components?: Component[];
  data_stores?: DataStore[];
  security_mechanisms?: SecurityMechanism[];
  traffic_expectations?: Record<string, string>;
  reliability_requirements?: Record<string, string>;
  architectural_patterns?: string[];
  notable_gaps?: string[];
}

export interface Guideline {
  source_id: string;
  collection: string;
  section_reference: string;
  guideline_summary: string;
  score: number;
}

export interface Bottleneck {
  id: string;
  area: string;
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  supporting_evidence?: string;
  affected_components?: string[];
  risk_probability?: string;
  risk_impact?: string;
}

export interface BottleneckSummary {
  total_issues: number;
  high_severity: number;
  medium_severity: number;
  low_severity: number;
  most_critical_area?: string;
}

export interface BottlenecksData {
  bottlenecks: Bottleneck[];
  summary: BottleneckSummary;
}

export interface RecommendedChange {
  component: string;
  change_type: string;
  description: string;
  implementation_notes?: string;
}

export interface Proposal {
  id: string;
  addresses_bottleneck: string;
  title: string;
  rationale: string;
  recommended_changes?: RecommendedChange[];
  alternative_patterns?: string[];
  tradeoffs?: { pros: string[]; cons: string[] };
  impact_analysis?: Record<string, string>;
  effort: 'low' | 'medium' | 'high';
  priority: 'immediate' | 'short_term' | 'long_term';
}

export interface ProposalsData {
  proposals: Proposal[];
  quick_wins?: string[];
  roadmap?: {
    phase_1_immediate?: string[];
    phase_2_short_term?: string[];
    phase_3_long_term?: string[];
  };
}

export interface Artifacts {
  mermaid_diagram?: string;
  openapi_spec?: string;
  review_summary?: string;
}

export interface Citation {
  finding_id: string;
  finding_title: string;
  claim: string;
  source_id: string;
  section_reference?: string;
  guideline_summary?: string;
  verification_status: 'verified' | 'not_in_evidence' | 'partially_verified';
  confidence?: 'high' | 'medium' | 'low';
}

export interface VerificationNotes {
  reviewer_notes?: string;
  overall_confidence?: string;
  verified_count?: number;
  total_claims?: number;
}

export interface AnalysisResults {
  context: ExtractedContext;
  retrieved_guidelines: Guideline[];
  bottlenecks: BottlenecksData;
  proposed_changes: ProposalsData;
  artifacts: Artifacts;
  citations: Citation[];
  verification_notes: VerificationNotes;
}
