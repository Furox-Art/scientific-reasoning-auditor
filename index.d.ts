export interface RunOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
  /** Defaults to "inherit". Set to "pipe" to capture stdout/stderr. */
  stdio?: 'inherit' | 'pipe' | 'ignore';
}

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
