import { createContext, useContext } from 'react'
import { getConfiguration } from '../api'
import { useDashboardQuery } from './useDashboardQuery'
import { POLL_INTERVAL_MS } from './constants'

export const ConfigurationContext = createContext(null)

export function useConfiguration() {
  const shared = useContext(ConfigurationContext)
  const local = useDashboardQuery(getConfiguration, {
    enabled: !shared,
    pollInterval: POLL_INTERVAL_MS,
  })
  return shared || local
}
