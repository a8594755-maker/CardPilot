import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  children,
  className,
  title,
  ...props
}: DialogPrimitive.DialogContentProps & { title: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className={cn('dialog-content', className)} {...props}>
        {/* GTO+ style title bar */}
        <div className="dialog-title-bar">
          <DialogPrimitive.Title asChild>
            <h2>{title}</h2>
          </DialogPrimitive.Title>
          <DialogPrimitive.Close>
            <X size={16} />
          </DialogPrimitive.Close>
        </div>
        {/* Content area */}
        <div className="px-4 py-3">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
