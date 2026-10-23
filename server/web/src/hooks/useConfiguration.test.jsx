import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { ConfigurationContext, useConfiguration } from './useConfiguration'

vi.mock('../api', () => ({ getConfiguration: vi.fn().mockResolvedValue({ revision: 'shared' }) }))

function Consumer({ name }) {
  const { data } = useConfiguration()
  return <span>{name}: {data?.revision}</span>
}

function SharedQueries() {
  const query = useConfiguration()
  return <ConfigurationContext.Provider value={query}>
    <Consumer name="first" />
    <Consumer name="second" />
  </ConfigurationContext.Provider>
}

describe('shared configuration query', () => {
  it('shares one request and result across consumers', async () => {
    render(<SharedQueries />)
    expect(await screen.findByText('second: shared')).toBeInTheDocument()
    expect(screen.getByText('first: shared')).toBeInTheDocument()
    expect(api.getConfiguration).toHaveBeenCalledOnce()
  })
})
