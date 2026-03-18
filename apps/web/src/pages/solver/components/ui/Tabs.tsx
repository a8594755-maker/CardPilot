import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '../../lib/utils';

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ children, className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List className={cn('gto-tab-list', className)} {...props}>
      {children}
    </TabsPrimitive.List>
  );
}

export function TabsTrigger({ children, className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger className={cn('gto-tab-trigger', className)} {...props}>
      {children}
    </TabsPrimitive.Trigger>
  );
}
