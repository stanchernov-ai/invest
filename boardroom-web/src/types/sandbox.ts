export type SandboxPosition = {
  symbol: string;
  shares: number;
  cost_basis: number;
  weight_pct?: number;
  theoretical_value?: number;
};

export type SandboxImportResponse = {
  message: string;
  disclaimer: string;
  theoretical_baseline: number;
  positions: SandboxPosition[];
  persisted?: boolean;
  user_slug?: string;
  portfolio_id?: string;
  portfolio_name?: string;
};
