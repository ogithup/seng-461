/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string;
  readonly VITE_API_BASE_URL?: string;
  /** Only for `npm run test:smoke`: base URL of a running backend to test against. */
  readonly VITE_SMOKE_API_URL?: string;
  readonly VITE_SMOKE_EXPECT_UNSUPPORTED?: string;
  readonly VITE_SMOKE_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
