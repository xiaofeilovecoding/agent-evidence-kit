import type { DataAdapter } from "./api";
import { createApiAdapter } from "./api";
import { createShowcaseAdapter } from "./showcase";

const SHOWCASE = import.meta.env.VITE_APP_MODE === "showcase";

export const isShowcase = SHOWCASE;

export const adapter: DataAdapter = SHOWCASE
  ? createShowcaseAdapter()
  : createApiAdapter();
