// shadcn/ui's usual `cn` is clsx + tailwind-merge; this app has no dynamic/
// conflicting Tailwind class composition anywhere yet, so a plain join
// covers it without adding two dependencies for what one line does.
export function cn(...inputs: Array<string | false | null | undefined>) {
  return inputs.filter(Boolean).join(' ')
}
