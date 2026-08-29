import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js writes AGENTS.md/CLAUDE.md into the repo by default; not wanted
  // in a submission tree.
  agentRules: false,

  // The floating dev badge sits over the map's bottom-left corner and shows up
  // in every demo screenshot. Dev-only, so switching it off costs nothing.
  devIndicators: false,

  // Pinned explicitly. A stray package-lock.json in the user's Documents folder
  // made Next.js infer the wrong workspace root, which changes where it resolves
  // modules from.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
