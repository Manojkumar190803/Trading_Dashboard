export interface IdentifiedAlert {
  id: string
}

export declare function collectUnseenAlerts<T extends IdentifiedAlert>(
  alerts: readonly T[],
  seenIds: Set<string>,
): T[]
