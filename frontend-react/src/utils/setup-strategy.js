export function getSetupIdentity(setupName, isHdLockedSymbol) {
  const side = setupName.match(/^(CE|PE)\b/i)?.[1]?.toUpperCase()
  const recordedStrategy = setupName.match(/^(?:CE|PE)\s+(.+?)\s+setup$/i)?.[1]
  const inferHd = !recordedStrategy && isHdLockedSymbol
  return {
    side,
    strategy: recordedStrategy || (inferHd ? 'HD' : 'EMA21'),
    setupName: inferHd && side ? `${side} HD setup` : setupName,
  }
}