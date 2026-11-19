import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "./api";
import type { Event as RunEvent, EventPage, ToolResult as ToolResultPayload } from "./contracts/models";
import { ActivityImage, activityImageFromTag } from "./tool-result";

type ActivityPreview = { title: string; src: string };
type ActivityPreviews = Map<string, ActivityPreview | undefined>;

function titleKey(text: string) {
  // Co-brand titles may be written as x or × by the model. Match both to the
  // same provider title; images still come only from that run's validated tool result.
  return text.normalize("NFKC").toLowerCase().replace(/[×✕]/g, "x").replace(/[^\p{L}\p{N}+]/gu, "");
}

function activityPreviews(events: RunEvent[], runId: string) {
  const previews: ActivityPreviews = new Map();
  const calendarCalls = new Set<string>();
  for (const event of events) {
    if (event.run_id !== runId) continue;
    if (event.type !== "tool.requested" && event.type !== "tool.completed") continue;
    const { text, execution_id, status } = event.payload as ToolResultPayload;
    if (event.type === "tool.requested") {
      if (text === "麦当劳中国 · 查询活动日历") calendarCalls.add(execution_id);
      continue;
    }
    if (status !== "SUCCEEDED" || !calendarCalls.has(execution_id)) continue;
    let title = "";
    let readImage = false;
    for (const line of text.split(/\r?\n/)) {
      const heading = /^\s*(?:[-*+]\s+)?\*\*活动标题\*\*\s*[:：]\s*(.+?)\s*$/.exec(line);
      if (heading) {
        title = heading[1];
        readImage = false;
        continue;
      }
      if (/^\s*\*\*活动图片介绍\*\*\s*[:：]\s*$/.test(line)) {
        readImage = true;
        continue;
      }
      if (!readImage || !line.trim()) continue;
      readImage = false;
      const src = activityImageFromTag(line);
      const key = titleKey(title);
      if (!key || !src) continue;
      if (!previews.has(key)) previews.set(key, { title, src });
      else if (previews.get(key)?.src !== src) previews.set(key, undefined);
    }
  }
  return previews;
}

async function readToolEvents(runId: string) {
  const events: RunEvent[] = [];
  let cursor = 0;
  for (;;) {
    const page = await api<EventPage>(`/runs/${runId}/events?after_seq=${cursor}`);
    events.push(...page.items.filter(event => event.type === "tool.requested" || event.type === "tool.completed"));
    if (!page.has_more || page.next_seq <= cursor) return events;
    cursor = page.next_seq;
  }
}

// Formed by the Markdown renderer. Tool and model HTML are never evaluated.
type HtmlNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HtmlNode[];
  value?: string;
};

function inlineText(node: HtmlNode): string {
  if (node.type === "text") return node.value ?? "";
  if (node.tagName === "ul" || node.tagName === "ol") return "";
  return node.children?.map(inlineText).join("") ?? "";
}

function matchesShortTitle(fullTitle: string, shortTitle: string) {
  if (fullTitle.includes(shortTitle)) return true;
  if (shortTitle.length * 3 < fullTitle.length * 2) return false;
  let index = 0;
  for (const character of fullTitle) {
    if (character === shortTitle[index]) index++;
    if (index === shortTitle.length) return true;
  }
  return false;
}

function findActivity(node: HtmlNode, previews: ActivityPreviews) {
  const text = titleKey(inlineText(node));
  const entries = Array.from(previews);
  const exact = entries.filter(([key]) => text.includes(key));
  if (exact.length) return exact.length === 1 ? exact[0] : undefined;
  if (node.tagName !== "li" && node.tagName !== "td") return undefined;
  const emphasis = node.children?.find(child => child.tagName === "strong");
  const title = emphasis ? titleKey(inlineText(emphasis)) : "";
  if (title.length < 6) return undefined;
  const shortened = entries.filter(([key]) => matchesShortTitle(key, title));
  return shortened.length === 1 ? shortened[0] : undefined;
}

function formatReply(tree: HtmlNode, previews: ActivityPreviews | undefined) {
  const used = new Set<string>();
  function visit(parent: HtmlNode) {
    if (!parent.children) return;
    parent.children = parent.children.flatMap(node => {
      if (node.type === "raw" && /^<br\s*\/?>$/i.test(node.value?.trim() ?? "")) {
        return [{ type: "element", tagName: "br", properties: {}, children: [] }];
      }
      if (previews?.size && node.tagName && /^(li|p|td|h[1-6])$/.test(node.tagName)) {
        const match = findActivity(node, previews);
        if (match?.[1] && !used.has(match[0])) {
          const [key, preview] = match;
          used.add(key);
          visit(node);
          const image: HtmlNode = {
            type: "element",
            tagName: "img",
            properties: { src: preview.src, alt: preview.title, activityPreview: true },
            children: [],
          };
          if (node.tagName !== "li" && node.tagName !== "td") return [node, image];
          node.children?.push(image);
          return [node];
        }
      }
      visit(node);
      return [node];
    });
  }
  visit(tree);
}

export function ReplyMarkdown({ text, previews }: { text: string; previews?: ActivityPreviews }) {
  return (
    <Markdown
      skipHtml
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[() => (tree: HtmlNode) => formatReply(tree, previews)]}
      components={{
        img: ({ node, src, alt }) => node?.properties.activityPreview === true && src ? <ActivityImage src={src} alt={alt} /> : null,
        table: ({ node: _node, ...props }) => <div className="message-table-scroll"><table {...props} /></div>,
      }}
    >{text}</Markdown>
  );
}

export function AssistantReply({ text, runId, events }: { text: string; runId: string; events?: RunEvent[] }) {
  const history = useQuery({
    queryKey: ["reply-tool-events", runId],
    queryFn: () => readToolEvents(runId),
    enabled: events === undefined,
    staleTime: Infinity,
  });
  const previews = activityPreviews(events ?? history.data ?? [], runId);
  return <ReplyMarkdown text={text} previews={previews} />;
}
