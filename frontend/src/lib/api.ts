// Thin client over the FastAPI backend (proxied at /api in dev, same-origin in prod).

const BASE = "/api"

async function get<T>(
  endpoint: string,
  params: Record<string, string | number | undefined>,
): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== "") qs.set(k, String(v))
  }
  const res = await fetch(`${BASE}/${endpoint}?${qs.toString()}`)
  if (!res.ok) throw new Error(`${endpoint} → ${res.status}`)
  return res.json() as Promise<T>
}

export interface Chat {
  id: string
  name: string
  type: string
  count: number
}
export interface Kpis {
  total_messages: number
  unique_users: number
  first_date: string | null
  last_date: string | null
  days_active: number
  media_messages: number
}
export interface Hero {
  title: string
  prose_html: string
  meta: string
  chat_type: string
  chat_id: string
}
export interface Highlight {
  icon: string
  label: string
  value: string
  sub: string
}
export interface MediaStats {
  by_kind: Record<string, number>
  voice_count: number
  voice_total_seconds: number
  top_domains: [string, number][]
  total_links: number
}
export interface EmojiStats {
  chat_top: [string, number][]
  total_emojis: number
  messages_with_emoji: number
}
export interface LatencyStats {
  overall_seconds: number[]
  median_seconds: number
  p90_seconds: number
  qa_seconds: number[]
  qa_median_seconds: number
  qa_p90_seconds: number
  dropped_over_cap: number
  cap_hours: number
}
export interface SessionsStats {
  sessions: { start: string; end: string; msg_count: number }[]
  avg_messages: number
  median_messages: number
  longest: { start: string; end: string; msg_count: number } | null
  duration_buckets: Record<string, number>
}
export interface MonologueRun {
  user_id: string
  name: string
  msg_count: number
  start: string
  end: string
  duration_seconds: number
}

// chat / period selector passed to every analysis call
type Sel = { chat?: string; from?: string; to?: string; lang?: string }
const p = (path: string, s: Sel = {}) => ({ path, chat: s.chat, from: s.from, to: s.to, lang: s.lang })

export const api = {
  chats: (path: string) => get<{ source: string; chats: Chat[] }>("chats", { path }),
  bounds: (path: string, chat?: string) =>
    get<{ bounds: [string, string] | null }>("bounds", { path, chat }),
  kpis: (path: string, s?: Sel) => get<Kpis>("kpis", p(path, s)),
  hero: (path: string, s?: Sel) => get<Hero>("hero", p(path, s)),
  highlights: (path: string, s?: Sel) => get<{ highlights: Highlight[] }>("highlights", p(path, s)),
  perDay: (path: string, s?: Sel) => get<{ per_day: [string, number][] }>("per-day", p(path, s)),
  hourWeekday: (path: string, s?: Sel) => get<{ grid: number[][] }>("hour-weekday", p(path, s)),
  media: (path: string, s?: Sel) => get<MediaStats>("media", p(path, s)),
  emojis: (path: string, s?: Sel) => get<EmojiStats>("emojis", p(path, s)),
  latency: (path: string, s?: Sel) => get<LatencyStats>("latency", p(path, s)),
  sessions: (path: string, s?: Sel, gap = 30) =>
    get<SessionsStats>("sessions", { ...p(path, s), gap_minutes: gap }),
  monologues: (path: string, s?: Sel) => get<{ longest: MonologueRun[] }>("monologues", p(path, s)),
}

export type { Sel }
