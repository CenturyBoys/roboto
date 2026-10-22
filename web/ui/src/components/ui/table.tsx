import * as React from 'react'
import { cn } from '@/lib/utils'

export function Th({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn('px-2.5 py-2 text-left font-semibold', className)} {...props} />
}

interface TdProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  mono?: boolean
}

export function Td({ mono, className, ...props }: TdProps) {
  return <td className={cn('px-2.5 py-2 align-top', mono && 'font-mono text-xs', className)} {...props} />
}

// Scroll horizontal p/ tabelas densas no celular (mobile-first: não corta, rola).
export function TableWrap({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>
}
