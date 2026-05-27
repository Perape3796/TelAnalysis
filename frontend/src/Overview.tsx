import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { api, type LatencyStats, type SessionsStats, type Sel } from "@/lib/api"
import { fmtInt, humanizeDuration } from "@/lib/i18n"
import { Card } from "@/components/ui/card"
import { Bars, Calendar, HourWeekday, MediaPie } from "@/components/charts"
import { TabLoading } from "@/components/loading"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="gap-1 border-border bg-card px-4 py-3">
      <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </Card>
  )
}

function Timeline({ data }: { data: [string, number][] }) {
  const rows = data.map(([date, messages]) => ({ date, messages }))
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="tl" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: "#9ca3af", fontSize: 11 }} minTickGap={48} stroke="rgba(255,255,255,0.08)" />
        <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} width={36} stroke="rgba(255,255,255,0.08)" />
        <Tooltip contentStyle={{ background: "#14161d", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, color: "#e5e7eb" }} />
        <Area type="monotone" dataKey="messages" stroke="var(--chart-1)" strokeWidth={1.5} fill="url(#tl)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function LatencyBlock({ l }: { l: LatencyStats }) {
  const { t } = useTranslation()
  if (!l.overall_seconds?.length) return null
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label={t("halfFaster")} value={humanizeDuration(l.median_seconds)} />
        <Stat label={t("p90Faster")} value={humanizeDuration(l.p90_seconds)} />
        <Stat label={t("repliesCounted")} value={fmtInt(l.overall_seconds.length)} />
      </div>
      {l.qa_seconds?.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-semibold">{t("qSection")}</div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Stat label={t("halfFaster")} value={humanizeDuration(l.qa_median_seconds)} />
            <Stat label={t("p90Faster")} value={humanizeDuration(l.qa_p90_seconds)} />
            <Stat label={t("qWithAnswer")} value={fmtInt(l.qa_seconds.length)} />
          </div>
        </div>
      )}
    </div>
  )
}

function SessionsBlock({ s }: { s: SessionsStats }) {
  const { t } = useTranslation()
  if (!s.sessions?.length) return null
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Stat label={t("conversations")} value={fmtInt(s.sessions.length)} />
      <Stat label={t("perConvAvg")} value={s.avg_messages.toFixed(1)} />
      {s.longest && <Stat label={t("longestConv")} value={`${fmtInt(s.longest.msg_count)}`} sub={s.longest.start.slice(0, 10)} />}
    </div>
  )
}

export function Overview({ path, sel }: { path: string; sel: Sel }) {
  const { t } = useTranslation()
  const k = [path, sel.chat, sel.from, sel.to]
  const on = !!sel.chat

  const pd = useQuery({ queryKey: ["pd", ...k], queryFn: () => api.perDay(path, sel), enabled: on })
  const hw = useQuery({ queryKey: ["hw", ...k], queryFn: () => api.hourWeekday(path, sel), enabled: on })
  const media = useQuery({ queryKey: ["media", ...k], queryFn: () => api.media(path, sel), enabled: on })
  const emojis = useQuery({ queryKey: ["emojis", ...k], queryFn: () => api.emojis(path, sel), enabled: on })
  const lat = useQuery({ queryKey: ["lat", ...k], queryFn: () => api.latency(path, sel), enabled: on })
  const sess = useQuery({ queryKey: ["sess", ...k], queryFn: () => api.sessions(path, sel), enabled: on })
  const mono = useQuery({ queryKey: ["mono", ...k], queryFn: () => api.monologues(path, sel), enabled: on })

  if (pd.isLoading) return <TabLoading />

  return (
    <div className="space-y-8 pt-2">
      <Section title={t("howOften")}>
        {pd.data && <Card className="border-border bg-card p-3"><Timeline data={pd.data.per_day} /></Card>}
        {pd.data && pd.data.per_day.length > 0 && (
          <Card className="border-border bg-card p-3"><Calendar perDay={pd.data.per_day} /></Card>
        )}
      </Section>

      {hw.data && hw.data.grid.some((r) => r.some((v) => v > 0)) && (
        <Section title={t("whenHours")}>
          <Card className="border-border bg-card p-3"><HourWeekday grid={hw.data.grid} /></Card>
          {sess.data && <SessionsBlock s={sess.data} />}
        </Section>
      )}

      <Section title={t("whatAbout")}>
        {emojis.data && emojis.data.chat_top.length > 0 && (
          <Card className="border-border bg-card p-3">
            <Bars data={emojis.data.chat_top.slice(0, 20)} color="#9270CA" />
          </Card>
        )}
        {media.data && Object.keys(media.data.by_kind).length > 0 && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <Card className="border-border bg-card p-3 lg:col-span-2"><MediaPie byKind={media.data.by_kind} /></Card>
            {media.data.voice_count > 0 && (
              <div className="grid grid-cols-1 gap-3">
                <Stat label={t("voiceMessages")} value={fmtInt(media.data.voice_count)} />
                <Stat label={t("voiceTotal")} value={humanizeDuration(media.data.voice_total_seconds)} />
                <Stat label={t("voiceAvg")} value={humanizeDuration(Math.floor(media.data.voice_total_seconds / media.data.voice_count))} />
              </div>
            )}
          </div>
        )}
        {media.data && media.data.top_domains.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-semibold">{t("topDomains")}</div>
            <Card className="border-border bg-card p-3"><Bars data={media.data.top_domains.slice(0, 15)} /></Card>
          </div>
        )}
      </Section>

      {lat.data && lat.data.overall_seconds.length > 0 && (
        <Section title={t("whoToWhom")}>
          <LatencyBlock l={lat.data} />
        </Section>
      )}

      {mono.data && mono.data.longest.length > 0 && (
        <Section title={t("longestMonologues")}>
          <Card className="overflow-hidden border-border bg-card">
            <table className="w-full text-sm">
              <tbody>
                {mono.data.longest.slice(0, 8).map((r, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-2 font-medium">{r.name}</td>
                    <td className="px-4 py-2 tabular-nums text-muted-foreground">{fmtInt(r.msg_count)}</td>
                    <td className="px-4 py-2 text-muted-foreground">{r.start.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </Section>
      )}
    </div>
  )
}
