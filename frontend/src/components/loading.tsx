import { Skeleton } from "@/components/ui/skeleton"

/** Placeholder shown while a tab's primary query is in flight. */
export function TabLoading() {
  return (
    <div className="space-y-6 pt-2">
      <Skeleton className="h-7 w-48" />
      <Skeleton className="h-72 w-full" />
      <Skeleton className="h-7 w-40" />
      <Skeleton className="h-72 w-full" />
    </div>
  )
}
