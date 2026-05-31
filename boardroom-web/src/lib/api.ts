import type { SandboxImportResponse } from "@/types/sandbox";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function importSandboxScenario(
  file: File,
): Promise<SandboxImportResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/sandbox/import`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = `Import failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      /* use default message */
    }
    throw new Error(detail);
  }

  return response.json() as Promise<SandboxImportResponse>;
}
