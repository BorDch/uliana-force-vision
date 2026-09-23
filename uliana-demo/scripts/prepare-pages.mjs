import { cp, rename, rm, stat } from "node:fs/promises";
import { join } from "node:path";

const output = join(process.cwd(), "dist", "client");
const exists = async (path) => stat(path).then(() => true, () => false);

// Vinext's static fallback is the complete client application. GitHub Pages
// also needs it as the project root document.
await cp(join(output, "404.html"), join(output, "index.html"));

// Asset-prefix builds mirror _next below the repository name. Pages already
// mounts this artifact at that path, so flatten only the generated asset tree.
const repositoryName = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/^\/+|\/+$/g, "");
if (repositoryName) {
  const nested = join(output, repositoryName, "_next");
  if (await exists(nested)) {
    await rm(join(output, "_next"), { recursive: true, force: true });
    await rename(nested, join(output, "_next"));
    await rm(join(output, repositoryName), { recursive: true, force: true });
  }
}
