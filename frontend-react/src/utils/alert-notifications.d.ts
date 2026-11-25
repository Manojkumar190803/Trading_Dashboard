export interface IdentifiedAlert {
  id: string
}

export declare function collectUnseenAlerts<T extends IdentifiedAlert>(
  alerts: readonly T[],
  seenIds: Set<string>,
): T[]

export declare function getOrderEvent(alert: {
  alert_type: string
  message: string
  strategy?: string
}): 'placed' | 'modified' | 'executed' | null
