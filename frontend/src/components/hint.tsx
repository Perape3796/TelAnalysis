import { Tooltip } from "@base-ui/react/tooltip"
import { Info } from "lucide-react"

import { cn } from "@/lib/utils"

/** Small info icon that reveals an explanatory tooltip on hover/focus. */
export function Hint({ text, className }: { text: string; className?: string }) {
  return (
    <Tooltip.Provider delay={120}>
      <Tooltip.Root>
        <Tooltip.Trigger
          className={cn("inline-flex translate-y-px text-muted-foreground/60 transition-colors hover:text-foreground", className)}
          aria-label="info"
        >
          <Info className="size-3.5" />
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Positioner sideOffset={6}>
            <Tooltip.Popup className="z-50 max-w-xs rounded-md bg-popover px-2.5 py-1.5 text-xs leading-relaxed text-popover-foreground shadow-md ring-1 ring-foreground/10">
              {text}
            </Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
