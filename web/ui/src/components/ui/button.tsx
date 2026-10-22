import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50',
  {
    variants: {
      variant: {
        default: 'bg-accent font-bold text-black hover:brightness-95',
        outline: 'border border-border bg-surface text-foreground hover:border-accent',
        ghost: 'text-foreground hover:bg-surface',
      },
      size: { default: 'h-9 px-4', sm: 'h-8 px-3 text-xs', icon: 'h-9 w-9' },
    },
    defaultVariants: { variant: 'outline', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
}

export { buttonVariants }
