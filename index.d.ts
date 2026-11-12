export interface RunOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
  /** Defaults to "inherit". Set to "pipe" to capture stdout/stderr. */
  stdio?: 'inherit' | 'pipe' | 'ignore';
}

export type StudyType = 'unknown' | 'quantitative' | 'qualitative' | 'computational' |
  'theoretical' | 'systematic-review' | 'narrative-review' | 'mixed';
export type Discipline = 'clinical' | 'animal' | 'physics' | 'chemistry' | 'computing' | 'social-science';
export interface UnifiedReviewOptions extends RunOptions {
  out?: string;
  studyType?: StudyType;
  disciplines?: Discipline[];
  styleLanguage?: 'en' | 'tr' | 'none';
  statisticsSpec?: string;
  scientificSpec?: string;
  logicSpec?: string;
  toolkitSpec?: string;
  prepareInputs?: boolean;
  online?: boolean;
  sendToModel?: boolean;
  model?: string;
  baseUrl?: string;
  apiKeyEnv?: string;
  timeout?: number;
  chunkChars?: number;
  ocrMode?: 'off' | 'missing' | 'all';
  ocrLanguages?: string;
  visualPages?: boolean;
}
/** JSON stdout describes actual capabilities, not scientific validation. */
export function capabilities(options?: RunOptions): Promise<CommandResult>;
/** Exit 0 means requested execution completed; exit 1 preserves a partial report. */
export function reviewManuscript(input: string, options?: UnifiedReviewOptions): Promise<CommandResult>;
export interface LogicVerificationOptions extends OutputOptions {
  manuscript?: string;
}
/** Conditional Boolean/linear formal verification; writes a separate report. */
export function verifyLogic(input: string, options?: LogicVerificationOptions): Promise<CommandResult>;
/** Local exact/numerical checks and explicitly non-verdict sentence/passage candidates. */
export function verifyToolkit(input: string, options?: LogicVerificationOptions): Promise<CommandResult>;
/** Prepare source-located candidates without executing inferred checks. */
export function prepareInspection(input: string, options?: OutputOptions): Promise<CommandResult>;

export interface CommandResult {
  code: number;
  signal: string | null;
  stdout: string;
  stderr: string;
}

export interface AuditOptions extends RunOptions {
  out?: string;
  semanticReview?: string;
}

export interface ReviewTemplateOptions extends RunOptions {
  out?: string;
  mode?: 'single' | 'parallel';
}

export interface ModelReviewOptions extends RunOptions {
  model: string;
  baseUrl?: string;
  apiKeyEnv?: string;
  timeout?: number;
  out?: string;
}

export interface WritingAuditOptions extends RunOptions {
  out?: string;
  genre?: 'general' | 'original-research';
  abstractMinWords?: number;
  abstractMaxWords?: number;
  styleLanguage?: 'en' | 'tr' | 'none';
  design?: 'clinical-trial' | 'observational' | 'systematic-review' | 'computational';
  discipline?: 'clinical' | 'animal' | 'physics' | 'chemistry' | 'computing' | 'social-science';
  grammarEngine?: 'rules' | 'local-languagetool';
  grammarPort?: number;
  grammarTimeout?: number;
}

export interface OutputOptions extends RunOptions {
  out?: string;
}

export function run(args: string[], options?: RunOptions): Promise<CommandResult>;
export function audit(input: string, options?: AuditOptions): Promise<CommandResult>;
export function createReviewTemplate(input: string, options?: ReviewTemplateOptions): Promise<CommandResult>;
export function reviewModel(input: string, options: ModelReviewOptions): Promise<CommandResult>;

/** Model-assisted analysis of every extracted-text chunk, not a factual certification. */
export interface PaperReviewOptions extends ModelReviewOptions {
  chunkChars?: number;
  ocrMode?: 'off' | 'missing' | 'all';
  ocrLanguages?: string;
  /** Sends *every* PDF page image to a vision-capable model. */
  visualPages?: boolean;
}
export function paperReview(input: string, options: PaperReviewOptions): Promise<CommandResult>;
export function verifyStats(input: string, options?: OutputOptions): Promise<CommandResult>;
export function writingAudit(input: string, options?: WritingAuditOptions): Promise<CommandResult>;

export interface OnlineCheckOptions extends OutputOptions {
  online?: boolean;
  limit?: number;
}
export function verifyDoi(input: string, options?: OnlineCheckOptions): Promise<CommandResult>;
export function benchmarkPmc(manifest: string, options: OnlineCheckOptions): Promise<CommandResult>;

export function evaluateLabels(benchmark: string, labels: string, options?: OutputOptions): Promise<CommandResult>;

export interface DomainReviewOptions extends RunOptions {
  out?: string;
  discipline: 'clinical' | 'animal' | 'physics' | 'chemistry' | 'computing' | 'social-science';
}
export function domainReview(input: string, options: DomainReviewOptions): Promise<CommandResult>;
export function domainTemplate(input: string, options: DomainReviewOptions): Promise<CommandResult>;
export function domainValidate(input: string, assessments: string, options: DomainReviewOptions): Promise<CommandResult>;


/** Evaluate human-annotated scientific revision intents against the offline rules.
 * Outputs conditional sentence-revision agreement, NOT all-manuscript grammar accuracy.
 */
export interface LanguageBenchmarkOptions extends RunOptions {
  expectedSha256: string;
  out?: string;
  maxRows?: number;
}
export function languageBenchmark(input: string, options: LanguageBenchmarkOptions): Promise<CommandResult>;

/** Aggregate >=2 completed blinded reviews from independent domain experts.
 * Software only checks file structure; it cannot verify reviewer credentials.
 */
export function domainAggregate(reports: string[], options?: OutputOptions): Promise<CommandResult>;
