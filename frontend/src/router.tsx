import { ErrorFallback } from "@/pages/error-fallback";
import type { RouteRecord } from "vite-react-ssg";

const errorElement = <ErrorFallback />;

// The automatic flow is the app; the Composer editor is one optional step away from a job.
const routes: RouteRecord[] = [
  {
    path: "/",
    lazy: async () => ({ Component: (await import("@/auto/pages/start-page")).default }),
    entry: "src/auto/pages/start-page.tsx",
    errorElement,
  },
  {
    path: "/jobs/:jobId",
    lazy: async () => ({ Component: (await import("@/auto/pages/job-page")).default }),
    entry: "src/auto/pages/job-page.tsx",
    errorElement,
  },
  {
    path: "/editor",
    lazy: async () => ({ Component: (await import("@/pages/home")).default }),
    entry: "src/pages/home.tsx",
    errorElement,
  },
  {
    path: "/recover",
    lazy: async () => ({ Component: (await import("@/pages/recover")).default }),
    entry: "src/pages/recover.tsx",
    errorElement,
  },
  {
    path: "*",
    element: errorElement,
  },
];

export { routes };
