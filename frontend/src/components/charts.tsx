import ReactECharts from "echarts-for-react"

import { mediaKindLabel, weekdayShort } from "@/lib/i18n"

const AXIS = "rgba(255,255,255,0.10)"
const GRID = "rgba(255,255,255,0.06)"
const TICK = "#9ca3af"
const HEAT = ["#1F2937", "#3B5BDB", "#FF6B6B", "#FFE66D"]
const TOOLTIP = {
  backgroundColor: "#14161d",
  borderColor: "rgba(255,255,255,0.1)",
  textStyle: { color: "#e5e7eb" },
}
const base = {
  backgroundColor: "transparent",
  textStyle: { color: TICK, fontFamily: "inherit" },
  tooltip: { ...TOOLTIP },
}

function Chart({ option, height = 280 }: { option: object; height?: number }) {
  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "svg" }}
      notMerge
    />
  )
}

export function HourWeekday({ grid }: { grid: number[][] }) {
  const wd = weekdayShort()
  const data: [number, number, number][] = []
  let max = 1
  grid.forEach((row, w) =>
    row.forEach((v, h) => {
      data.push([h, w, v])
      if (v > max) max = v
    }),
  )
  return (
    <Chart
      height={260}
      option={{
        ...base,
        tooltip: { ...TOOLTIP, position: "top" },
        grid: { left: 36, right: 8, top: 8, bottom: 24 },
        xAxis: {
          type: "category",
          data: [...Array(24).keys()],
          axisLine: { lineStyle: { color: AXIS } },
          axisLabel: { color: TICK, interval: 1 },
          splitArea: { show: false },
        },
        yAxis: {
          type: "category",
          data: wd,
          inverse: true,
          axisLine: { lineStyle: { color: AXIS } },
          axisLabel: { color: TICK },
        },
        visualMap: { min: 0, max, show: false, inRange: { color: HEAT } },
        series: [{ type: "heatmap", data, itemStyle: { borderColor: "#0e1117", borderWidth: 1 } }],
      }}
    />
  )
}

export function Calendar({ perDay }: { perDay: [string, number][] }) {
  const years = [...new Set(perDay.map((d) => d[0].slice(0, 4)))].sort()
  let max = 1
  for (const [, v] of perDay) if (v > max) max = v
  const calendar = years.map((y, i) => ({
    range: y,
    top: 30 + i * 140,
    left: 40,
    right: 16,
    cellSize: ["auto", 13],
    splitLine: { show: false },
    itemStyle: { color: "transparent", borderColor: GRID, borderWidth: 1 },
    dayLabel: { color: TICK, firstDay: 1 },
    monthLabel: { color: TICK },
    yearLabel: { show: true, color: "#e5e7eb", margin: 28 },
  }))
  const series = years.map((y, i) => ({
    type: "heatmap" as const,
    coordinateSystem: "calendar",
    calendarIndex: i,
    data: perDay.filter((d) => d[0].startsWith(y)),
  }))
  return (
    <Chart
      height={years.length * 140 + 30}
      option={{
        ...base,
        tooltip: { ...TOOLTIP },
        visualMap: { min: 0, max, show: false, inRange: { color: HEAT } },
        calendar,
        series,
      }}
    />
  )
}

export function MediaPie({ byKind }: { byKind: Record<string, number> }) {
  const data = Object.entries(byKind)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ name: mediaKindLabel(k), value: v }))
  const COLORS = ["#5B8FF9", "#5AD8A6", "#F6BD16", "#9270CA", "#5AD8F7", "#E86452", "#FF6B6B"]
  return (
    <Chart
      height={300}
      option={{
        ...base,
        tooltip: { ...TOOLTIP, trigger: "item", formatter: "{b}: {c} ({d}%)" },
        legend: { type: "scroll", orient: "vertical", right: 0, top: "center", textStyle: { color: TICK } },
        color: COLORS,
        series: [
          {
            type: "pie",
            radius: ["38%", "68%"],
            center: ["38%", "50%"],
            label: { color: "#e5e7eb" },
            data,
          },
        ],
      }}
    />
  )
}

export function Bars({
  data,
  height = 280,
  color = "#5B8FF9",
}: {
  data: [string, number][]
  height?: number
  color?: string
}) {
  return (
    <Chart
      height={height}
      option={{
        ...base,
        grid: { left: 8, right: 8, top: 16, bottom: 24, containLabel: true },
        xAxis: {
          type: "category",
          data: data.map((d) => d[0]),
          axisLine: { lineStyle: { color: AXIS } },
          axisLabel: { color: TICK, interval: 0, rotate: data.length > 12 ? 40 : 0 },
        },
        yAxis: {
          type: "value",
          axisLine: { show: false },
          splitLine: { lineStyle: { color: GRID } },
          axisLabel: { color: TICK },
        },
        series: [{ type: "bar", data: data.map((d) => d[1]), itemStyle: { color, borderRadius: [3, 3, 0, 0] } }],
      }}
    />
  )
}
