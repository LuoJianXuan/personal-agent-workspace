import { createContext } from "react";

export const ConversationSidebar = createContext<{ recent: HTMLElement | null; action: HTMLElement | null }>({ recent: null, action: null });

const paths = {
  plug: "m8 8 8 8M7 11l-3 3a4 4 0 0 0 6 6l3-3M11 7l3-3a4 4 0 0 1 6 6l-3 3M9 15l6-6",
  grid: "M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z",
  search: "M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0Zm-1 5 6 6",
  map: "m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6",
  check: "m5 12 4 4L19 6",
  help: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.8 9a2.3 2.3 0 1 1 3.5 2c-1 .6-1.3 1-1.3 2M12 16v.1",
  settings: "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2",
  chat: "M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z",
  library: "M3 7h7l2-3h9v16H3V7Zm0 0V4h7l2 3",
  chart: "M4 3v17h17M9 16v-5m5 5V6m5 10V9",
  skill: "m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z",
  user: "M20 21v-2a7 7 0 0 0-14 0v2M17 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  plus: "M12 5v14M5 12h14",
  panel: "M3 4h18v16H3V4Zm12 0v16",
  arrow: "M12 20V4m-6 6 6-6 6 6",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12M6 18 18 6",
  edit: "m16 3 5 5-12 12H4v-5L16 3Zm-2 2 5 5",
} as const;

export function Icon({ name, size = 18 }: { name: keyof typeof paths; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
