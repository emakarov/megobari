import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface CopyMdProps {
  /** Function that returns the markdown string to copy */
  toMarkdown: () => string;
  /** Button size */
  size?: "sm" | "icon";
  /** Optional label */
  label?: string;
}

/**
 * Copy-to-clipboard button that copies content as Markdown.
 * Shows a checkmark for 2s after copying.
 */
export function CopyMd({ toMarkdown, size = "icon", label }: CopyMdProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(toMarkdown());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = toMarkdown();
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [toMarkdown]);

  if (label) {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={handleCopy}
        className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
        {copied ? "Copied!" : label}
      </Button>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size={size}
            onClick={handleCopy}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">
          <p className="text-xs">{copied ? "Copied!" : "Copy as Markdown"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// --- Markdown formatters for common data types ---

export function messagesToMd(
  messages: { role: string; content: string; session_name?: string; created_at: string }[]
): string {
  return messages
    .map((m) => {
      const role = m.role === "user" ? "**User**" : "**Assistant**";
      const session = m.session_name ? ` [${m.session_name}]` : "";
      const time = new Date(m.created_at).toLocaleString();
      return `### ${role}${session} — ${time}\n\n${m.content}`;
    })
    .join("\n\n---\n\n");
}

export function singleMessageToMd(m: {
  role: string;
  content: string;
  session_name?: string;
  created_at: string;
}): string {
  const role = m.role === "user" ? "**User**" : "**Assistant**";
  const session = m.session_name ? ` [${m.session_name}]` : "";
  const time = new Date(m.created_at).toLocaleString();
  return `### ${role}${session} — ${time}\n\n${m.content}`;
}

export function tableToMd(
  headers: string[],
  rows: string[][]
): string {
  const header = `| ${headers.join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((r) => `| ${r.join(" | ")} |`).join("\n");
  return `${header}\n${sep}\n${body}`;
}

export function summaryToMd(s: {
  session_name: string;
  short_summary?: string;
  summary: string;
  topics?: string[];
  message_count: number;
  created_at: string;
}): string {
  const lines = [`## ${s.session_name} — ${new Date(s.created_at).toLocaleString()}`];
  if (s.short_summary) lines.push(`\n**${s.short_summary}**`);
  lines.push(`\n${s.summary}`);
  if (s.topics?.length) lines.push(`\nTopics: ${s.topics.join(", ")}`);
  lines.push(`\n_${s.message_count} messages_`);
  return lines.join("\n");
}

export function personaToMd(p: {
  name: string;
  description: string;
  system_prompt: string;
  is_default: boolean;
}): string {
  const lines = [`## ${p.name}${p.is_default ? " (default)" : ""}`];
  if (p.description) lines.push(`\n${p.description}`);
  if (p.system_prompt) lines.push(`\n### System Prompt\n\n\`\`\`\n${p.system_prompt}\n\`\`\``);
  return lines.join("\n");
}

export function memoriesToMd(
  category: string,
  memories: { key: string; content: string }[]
): string {
  const lines = [`## ${category}`];
  for (const m of memories) {
    lines.push(`\n- **${m.key}**: ${m.content}`);
  }
  return lines.join("\n");
}
